# Phase 0-1: Local Environment Setup & Production Infrastructure

## Phase 0: Local Environment Setup

**Goal:** Your local machine has everything needed to develop and test CountyIQ.

**Time estimate:** 30 minutes

### Step 0.1: Install Required Tools

| Tool | Version | Purpose |
|---|---|---|
| **Git** | Latest | Version control |
| **Docker + Docker Compose** | v2 | Local Postgres, container builds |
| **Python** | 3.11 (via `uv`) | Dagster pipelines, API |
| **Node.js** | 20 LTS (via `nvm` or system package) | React frontend |
| **psql** (PostgreSQL client) | Latest | Database inspection |
| **rclone** | Latest | R2 backups |
| **SSH client** | Standard | VPS access (built-in on Linux/Mac) |

```bash
# Verify all tools are installed
git --version
docker --version
docker compose version
python3 --version
node --version
psql --version
rclone --version
ssh -V
```

### Step 0.2: Local Development Setup

```bash
# Clone the repository
git clone https://github.com/jarod/countyiq.git
cd countyiq

# Python environment (pipelines)
cd pipelines
uv venv .venv --python 3.11
source .venv/bin/activate
uv pip install -e ".[dev]"
cd ..

# Start local Postgres
cd pipelines && docker compose up -d postgres-test && cd ..

# API development
cd api && uvicorn main:app --reload --port 8000

# Frontend development (separate terminal)
cd frontend && npm ci && npm run dev

# Dagster UI (separate terminal)
cd pipelines && source .venv/bin/activate && dagster dev -m countyiq.definitions
```

### Step 0.3: Environment Variables for Local Dev

```bash
export DATABASE_HOST=localhost
export DATABASE_PORT=5433
export DATABASE_NAME=countyiq
export DATABASE_USER=dagster_admin
export DATABASE_PASSWORD=localtest
export DATABASE_URL="postgresql://dagster_admin:localtest@localhost:5433/countyiq"
```

> **Checkpoint:** `docker compose ps` shows postgres-test running. `psql $DATABASE_URL -c "SELECT 1"` returns 1. `curl http://localhost:8000/api/health` returns OK. Frontend loads at `http://localhost:5173`.

---

## Phase 1: Production Infrastructure Setup

**Goal:** A Hetzner VPS is running all CountyIQ services via Docker Compose, with Cloudflare for CDN/DNS and R2 for object storage.

**Time estimate:** 1-2 hours

**Prerequisites:** Phase 0 complete. The full stack works locally against Docker Postgres.

### Step 1.1: Provision Hetzner VPS

1. Create a Hetzner Cloud account at https://console.hetzner.cloud
2. Create a new project: "CountyIQ"
3. Add your SSH public key: Settings -> SSH Keys
4. Create a server:
   - **Type:** CX23 (x86, 2 vCPU, 4GB RAM, 40GB SSD)
   - **Image:** Ubuntu 24.04
   - **Location:** Falkenstein
   - **SSH key:** Select the key you added
   - **Name:** `countyiq`
5. Note the public IP address

### Step 1.2: Configure Firewall

1. Hetzner Console -> Firewalls -> Create
2. Add inbound rules:
   - TCP 22 (SSH)
   - TCP 80 (HTTP)
   - TCP 443 (HTTPS)
3. Deny all other inbound traffic. All outbound allowed.
4. Attach the firewall to the `countyiq` server.

### Step 1.3: Initial VPS Setup

```bash
# SSH into VPS
ssh root@<VPS_IP>

# Update system
apt update && apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
systemctl enable docker

# Install rclone (for R2 backups)
curl https://rclone.org/install.sh | bash

# Create app directory
mkdir -p /opt/countyiq
cd /opt/countyiq

# Clone repository
git clone https://github.com/jarod/countyiq.git .
# Or set up a deploy key for a private repo
```

### Step 1.4: Configure Secrets

```bash
# Create .env file (NOT in git)
cat > /opt/countyiq/.env << 'EOF'
DATABASE_HOST=postgres
DATABASE_PORT=5432
DATABASE_NAME=countyiq
DATABASE_USER=dagster_admin
DATABASE_PASSWORD=<generate-strong-password>
DATABASE_URL=postgresql://dagster_admin:<password>@postgres:5432/countyiq

SLACK_WEBHOOK_CRITICAL=<webhook-url>
SLACK_WEBHOOK_WARNING=<webhook-url>
SLACK_WEBHOOK_PIPELINE=<webhook-url>

OPENROUTER_API_KEY=<api-key>

R2_ACCESS_KEY_ID=<r2-key>
R2_SECRET_ACCESS_KEY=<r2-secret>
R2_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
EOF

chmod 600 /opt/countyiq/.env
```

### Step 1.5: Configure Cloudflare

1. Create a Cloudflare account (or log in)
2. Add your domain (or configure later when domain is purchased)
3. Create R2 buckets:
   - `countyiq-raw` (raw pipeline data)
   - `countyiq-tiles` (vector tiles)
   - `countyiq-backups` (Postgres backups)
4. Generate an R2 API token with Object Read & Write permissions
5. Configure rclone on the VPS:

```bash
rclone config
# Name: r2
# Type: s3
# Provider: Cloudflare
# Access key: <R2_ACCESS_KEY_ID>
# Secret key: <R2_SECRET_ACCESS_KEY>
# Endpoint: https://<account-id>.r2.cloudflarestorage.com
```

### Step 1.6: Deploy Services

```bash
cd /opt/countyiq
docker compose up -d

# Verify all containers are running
docker compose ps

# Check logs
docker compose logs --tail=50
```

### Step 1.7: Initialize Database

```bash
# Run database init script (extensions, schemas)
docker exec -i countyiq-postgres psql -U dagster_admin -d countyiq < infra/modules/database/init.sql

# Run Alembic migrations
docker exec countyiq-dagster alembic upgrade head

# Create Dagster database
docker exec countyiq-postgres createdb -U dagster_admin dagster
```

> **Note:** `init.sql` handles extensions (postgis, pg_trgm, pg_stat_statements) and schemas (staging, meta). All tables are owned by Alembic. See `docs/implementation/phase-2-database.md` for the schema ownership split.

### Step 1.8: Configure Backups

```bash
# Add backup cron job
crontab -e
# Add: 0 4 * * * /opt/countyiq/docker/backup.sh >> /var/log/countyiq-backup.log 2>&1

# Test backup manually
/opt/countyiq/docker/backup.sh

# Verify backup exists in R2
rclone ls r2:countyiq-backups/postgres/
```

### Step 1.9: Verify Infrastructure

```bash
# Check API is responding
curl -s http://localhost:8000/api/health | jq .

# Check Postgres is accessible
docker exec countyiq-postgres psql -U dagster_admin -d countyiq -c "SELECT version();"

# Verify database initialized
docker exec countyiq-postgres psql -U dagster_admin -d countyiq -c "\dx"
# Should show: postgis, pg_trgm, pg_stat_statements

docker exec countyiq-postgres psql -U dagster_admin -d countyiq -c "\dn"
# Should show: staging, meta, public

# Check Dagster UI (via SSH tunnel from local machine)
# On your local machine:
ssh -L 3000:localhost:3000 root@<VPS_IP>
# Then open http://localhost:3000 in browser
```

> **Checkpoint:** All containers healthy (`docker compose ps` shows "Up" + "healthy"). Postgres has extensions and schemas. API returns health OK. Dagster UI accessible via SSH tunnel. Backup exists in R2.

---
