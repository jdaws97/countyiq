# Phase 5: CI/CD & Go-Live

**Goal:** Automated deployments via GitHub Actions + Watchtower, frontend on Cloudflare Pages, production validated end-to-end.

**Time estimate:** 1 day

**Prerequisites:** Phases 2-4 complete and verified locally. VPS deployed and services running (Phase 1).

### Step 5.0: Verify Production Infrastructure

```bash
# Confirm all services healthy
docker compose ps
# All containers should show "Up" + "(healthy)" status

# Confirm database initialized
docker exec countyiq-postgres psql -U dagster_admin -d countyiq \
  -c "SELECT table_name FROM information_schema.tables WHERE table_schema = 'staging' ORDER BY table_name;"

# Confirm Dagster loaded definitions
docker exec countyiq-dagster dagster definitions list
```

### Step 5.1: Set Up GitHub Container Registry (GHCR)

1. Generate a Personal Access Token (classic) with `write:packages` scope:
   - Settings -> Developer settings -> Personal access tokens -> Tokens (classic)
2. Store the token as a GitHub Actions secret:
   - Repository -> Settings -> Secrets -> Actions -> New repository secret
   - Name: `GHCR_TOKEN`
   - Value: `<your-pat>`

### Step 5.2: Create GitHub Actions Workflow

Create `.github/workflows/deploy.yml` with these jobs:

| Job | Depends on | What it does |
|---|---|---|
| **ci** | -- | Lint, type check, schema tests |
| **build-api** | ci | Build Docker image from `api/Dockerfile`, push to `ghcr.io/jarod/countyiq-api:latest` |
| **build-dagster** | ci | Build Docker image from `pipelines/Dockerfile`, push to `ghcr.io/jarod/countyiq-dagster:latest` |
| **frontend** | -- | Handled by Cloudflare Pages auto-deploy (no GH Actions step needed) |

Trigger: push to `main`.

> **Note:** Watchtower on the VPS polls GHCR every 5 minutes. Once images are pushed, containers auto-restart. No SSH or deployment commands needed in the workflow.

### Step 5.3: Configure Watchtower on VPS

```bash
# Authenticate Docker to GHCR on the VPS
echo '<GHCR_TOKEN>' | docker login ghcr.io -u jarod --password-stdin

# Watchtower is already defined in docker-compose.yml and uses the Docker config for auth.
# Verify it's polling:
docker compose logs watchtower --tail=20
```

### Step 5.4: Set Up Cloudflare Pages

1. Cloudflare Dashboard -> Pages -> Create a project
2. Connect GitHub repository: `jarod/countyiq`
3. Build settings:
   - **Framework preset:** None
   - **Build command:** `cd frontend && npm ci && npm run build`
   - **Build output directory:** `frontend/dist`
   - **Root directory:** `/` (or `frontend/`)
4. Environment variables: none needed (frontend calls `/api/*` on the same domain)
5. Deploy

### Step 5.5: Configure Custom Domain (when ready)

1. Register domain (e.g., `countyiq.com`)
2. Cloudflare Dashboard -> add domain -> update nameservers at registrar
3. DNS records:
   - `A countyiq.com` -> `<VPS_IP>` (proxied, orange cloud)
   - `CNAME www` -> `countyiq.com` (proxied)
4. Cloudflare Pages -> Custom domains -> add `countyiq.com`
5. SSL mode: Full (Strict)
6. Update Caddyfile: replace IP/placeholder with `countyiq.com`
7. Restart Caddy: `docker compose restart caddy`

### Step 5.6: End-to-End Validation

**Data layer:**
- [ ] Dagster definitions loaded (check Dagster UI via SSH tunnel)
- [ ] Alembic migrations applied (`docker exec countyiq-dagster alembic current`)
- [ ] Staging tables exist in Postgres

**API layer:**
- [ ] `curl https://countyiq.com/api/health` returns `{"status": "ok"}`
- [ ] `curl https://countyiq.com/api/stats` returns homepage stats
- [ ] `curl https://countyiq.com/api/search?q=test` returns results

**Frontend layer:**
- [ ] `https://countyiq.com` loads React app
- [ ] Map renders with parcels
- [ ] Search works end-to-end

**Tiles:**
- [ ] Vector tiles loading from R2 via Cloudflare (`/tiles/parcels/{z}/{x}/{y}.pbf`)

**Backups:**
- [ ] Run manual backup: `/opt/countyiq/docker/backup.sh`
- [ ] Verify backup in R2: `rclone ls r2:countyiq-backups/postgres/`
- [ ] Test restore to temporary container (see backup-restore drill in `docs/infrastructure.md`)

**Monitoring:**
- [ ] Stop a container (`docker compose stop api`), verify Slack alert fires within 5 minutes
- [ ] Restart container, verify recovery

### Step 5.7: Enable Scheduled Runs

```bash
# Uncomment weekly schedules in pipelines/jobs/schedules.py
# (or enable via Dagster UI -> Schedules -> toggle ON)

# Verify schedules are active
docker exec countyiq-dagster dagster schedule list
```

### Step 5.8: Go-Live Checklist

- [ ] All containers healthy (`docker compose ps`)
- [ ] Database initialized with schema + seed data
- [ ] API responding on custom domain
- [ ] Frontend deployed via Cloudflare Pages
- [ ] Vector tiles loading from R2
- [ ] Dagster schedules enabled
- [ ] Backup cron running (check `/var/log/countyiq-backup.log`)
- [ ] Monitoring cron running (Slack alerts tested)
- [ ] GHCR + Watchtower auto-deploy tested (push a trivial change, verify container restarts)
- [ ] SSH access verified from local machine

---
