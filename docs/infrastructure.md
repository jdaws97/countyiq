# Infrastructure

## Overview

CountyIQ runs on a single Hetzner VPS with all services managed by Docker Compose. Cloudflare handles CDN, DNS, DDoS protection, frontend hosting (Pages), and object storage (R2). There is no multi-service cloud orchestration -- one box, one `docker-compose.yml`, SSH to manage it.

## VPS Specification

| Spec | Value |
|---|---|
| Provider | Hetzner Cloud |
| Plan | CX23 (2 vCPU x86, 4GB RAM, 40GB SSD) |
| vCPU | 2 |
| RAM | 4 GB |
| Disk | 40 GB SSD (local) |
| Datacenter | Falkenstein, Germany |
| Cost | EUR3.49/mo |
| Traffic | 20 TB/mo included |

CX23 is an x86 instance. No ARM compatibility concerns.

## Docker Compose Services

| Service | Image | Port | Purpose |
|---|---|---|---|
| `postgres` | `postgis/postgis:16-3.4` | 5432 (internal) | PostgreSQL 16 + PostGIS. Application database + Dagster storage. |
| `dagster` | `ghcr.io/jarod/countyiq-dagster` | 3000 (internal) | Dagster webserver + daemon. Runs pipeline schedules, sensors, assets. |
| `api` | `ghcr.io/jarod/countyiq-api` | 8000 (internal) | FastAPI + Uvicorn. Serves `/api/*` routes. |
| `caddy` | `caddy:2-alpine` | 80, 443 (public) | Reverse proxy. Auto-TLS via Let's Encrypt. Routes traffic to API. |
| `watchtower` | `containrrr/watchtower` | -- | Polls GHCR every 5 minutes. Pulls new images, restarts containers. |

### Volumes

| Volume | Mount | Purpose |
|---|---|---|
| `postgres-data` | `/var/lib/postgresql/data` | Persistent database storage |
| `dagster-storage` | `/opt/dagster/storage` | Dagster run storage and event logs |
| `raw-data` | `/data/raw` | Local raw data cache (primary archive is R2) |

### Network

All services share a single Docker bridge network: `countyiq-net`. Services communicate by container name (e.g., `postgres:5432`, `api:8000`). Only Caddy exposes ports to the host (80, 443).

## Caddy Configuration

Caddy handles TLS termination and reverse proxying. The `Caddyfile`:

```
{$DOMAIN} {
    handle /api/* {
        reverse_proxy api:8000
    }

    handle {
        # Fallback: Cloudflare Pages serves the frontend directly.
        # This block can serve a maintenance page or redirect.
        respond "CountyIQ API" 200
    }
}
```

Caddy obtains and renews TLS certificates automatically via Let's Encrypt. No certificate management needed.

**Dagster UI access** (not public): SSH tunnel from your machine.

```bash
ssh -L 3000:localhost:3000 countyiq
# Then open http://localhost:3000 in your browser
```

## Cloudflare Setup

### DNS

- A record: `countyiq.com` (or chosen domain) pointing to VPS public IP
- Proxy status: **Proxied** (orange cloud) -- all traffic routes through Cloudflare
- SSL mode: **Full (Strict)** -- Cloudflare verifies the origin certificate (Caddy's Let's Encrypt cert)

### Cloudflare Pages

- Source: GitHub repo, `frontend/` directory
- Build command: `npm run build`
- Output directory: `dist`
- Auto-deploy on push to `main`
- Handles SPA routing natively (no rewrite rules needed)

### Cloudflare R2

| Bucket | Purpose |
|---|---|
| `countyiq-raw` | Raw data archives (scraped HTML, PDFs, JSON snapshots) |
| `countyiq-tiles` | Pre-generated vector tiles (PMTiles or directory structure) |
| `countyiq-backups` | Daily `pg_dump` backups |

R2 is S3-compatible. Use `boto3` with a custom endpoint:

```python
import boto3

s3 = boto3.client(
    "s3",
    endpoint_url=os.environ["R2_ENDPOINT_URL"],
    aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
)
```

### WAF

Cloudflare free tier includes basic rate limiting. No additional configuration needed at MVP scale.

## Firewall

Hetzner Cloud Firewall (configured in Hetzner console):

| Direction | Protocol | Port | Source | Action |
|---|---|---|---|---|
| Inbound | TCP | 22 | Any | Allow (SSH) |
| Inbound | TCP | 80 | Any | Allow (HTTP) |
| Inbound | TCP | 443 | Any | Allow (HTTPS) |
| Inbound | * | * | Any | Deny (default) |
| Outbound | * | * | Any | Allow |

Postgres (5432) and Dagster (3000) are **not** exposed to the internet. They are only accessible within the Docker network or via SSH tunnel.

## Secrets Management

Secrets live in `/opt/countyiq/.env` on the VPS. This file is **not** in the repo (gitignored).

Docker Compose loads it via `env_file: .env`.

### `.env` contents

```bash
# Database
DATABASE_URL=postgresql://dagster_admin:<password>@postgres:5432/countyiq
DATABASE_HOST=postgres
DATABASE_PORT=5432
DATABASE_NAME=countyiq
DATABASE_USER=dagster_admin
DATABASE_PASSWORD=<password>

# Slack
SLACK_WEBHOOK_CRITICAL=https://hooks.slack.com/services/...
SLACK_WEBHOOK_WARNING=https://hooks.slack.com/services/...
SLACK_WEBHOOK_PIPELINE=https://hooks.slack.com/services/...

# LLM
OPENROUTER_API_KEY=sk-or-...

# Cloudflare R2
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
```

### GHCR Token

Watchtower needs a GitHub Container Registry token to pull private images. Stored separately:

```
/opt/countyiq/.ghcr-token
```

Watchtower reads it via environment variable or Docker config. Not in `.env` to keep concerns separated.

## Backups

### Daily pg_dump

Cron job on the VPS host (not inside a container). Runs daily at 04:00 UTC.

```bash
# /etc/cron.d/countyiq-backup
0 4 * * * root /opt/countyiq/backup.sh >> /var/log/countyiq-backup.log 2>&1
```

**`/opt/countyiq/backup.sh`:**

```bash
#!/bin/bash
set -euo pipefail

DUMP_FILE="/tmp/countyiq-$(date +%F).dump"

docker exec countyiq-postgres pg_dump -Fc countyiq > "$DUMP_FILE"
rclone copy "$DUMP_FILE" r2:countyiq-backups/postgres/
rm "$DUMP_FILE"

# Retention: delete backups older than 30 days
rclone delete r2:countyiq-backups/postgres/ --min-age 30d
```

### Restore

```bash
# Download the backup
rclone copy r2:countyiq-backups/postgres/countyiq-YYYY-MM-DD.dump /tmp/

# Restore (replace existing database)
docker exec -i countyiq-postgres pg_restore -d countyiq /tmp/countyiq-YYYY-MM-DD.dump
```

## CI/CD

Three deployment flows, all triggered by pushing to `main`:

### 1. Frontend (Cloudflare Pages)

Push to `main` --> Cloudflare Pages auto-builds and deploys. Zero config after initial setup. No VPS involvement.

### 2. API + Pipelines (Docker images)

Push to `main` --> GitHub Actions builds Docker images --> pushes to `ghcr.io/jarod/countyiq-api` and `ghcr.io/jarod/countyiq-dagster` --> Watchtower on VPS polls every 5 minutes, pulls new images, restarts containers.

No SSH, no manual deployment. Watchtower handles the rollout.

### 3. Database Migrations

SSH into VPS, run manually:

```bash
ssh countyiq
docker exec countyiq-dagster alembic upgrade head
```

Migrations are intentionally manual. Schema changes require review before applying.

## VPS Access

- **SSH key auth only.** Password authentication is disabled.
- **No public keys in the repo.** Keys are provisioned manually on VPS setup.

SSH config alias (`~/.ssh/config`):

```
Host countyiq
    HostName <VPS-IP>
    User root
    IdentityFile ~/.ssh/countyiq
```

Usage:

```bash
ssh countyiq                           # Shell access
ssh -L 3000:localhost:3000 countyiq    # Dagster UI tunnel
ssh -L 5432:localhost:5432 countyiq    # Postgres tunnel (for local psql)
```

## Monitoring

### Container Healthchecks

Each Docker service defines a healthcheck:

| Service | Healthcheck |
|---|---|
| `postgres` | `pg_isready -U dagster_admin` |
| `api` | `curl -f http://localhost:8000/api/health` |
| `dagster` | `curl -f http://localhost:3000/health` |

Docker restarts unhealthy containers automatically (with `restart: unless-stopped`).

### System Monitoring

Cron script runs every 5 minutes on the VPS host. Checks:

- `docker compose ps` -- all containers running
- Disk usage (`df -h`) -- alert if > 80%
- Memory usage (`free -m`) -- alert if > 80%
- Postgres connectivity (`docker exec countyiq-postgres pg_isready`)

On failure, posts to Slack webhook (`SLACK_WEBHOOK_CRITICAL`).

### Dagster Sensors

Dagster's built-in sensors are unchanged:

- Write pipeline status to `meta.pipeline_status`
- Write infrastructure metrics to `meta.infra_metrics`
- Alert on pipeline failures via Slack

## Upgrade Path

| Trigger | Action | New Cost | Downtime |
|---|---|---|---|
| Sustained memory > 80% | Resize CX23 --> CX33 (4 vCPU, 8GB RAM) | EUR6/mo | ~2 minutes |
| Disk > 80% | Attach Hetzner volume (EUR0.052/GB/mo) | +EUR2-5/mo | None |

Resize is done in the Hetzner console. Docker Compose, volumes, and data persist across resizes. No architecture changes needed.
