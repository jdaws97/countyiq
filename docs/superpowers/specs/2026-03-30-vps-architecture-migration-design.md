# VPS Architecture Migration — Design Spec

**Date:** 2026-03-30
**Scope:** Docs only (no code/infra changes)

## Context

CountyIQ was designed around AWS (EC2, RDS, Lambda, API Gateway, CloudFront, S3) with ~1,500 lines of Terraform and 44 architecture docs. After analysis, the AWS architecture is over-engineered for a solo-dev civic data tool serving one county:

- Lambda in a VPC can't reach the internet (breaks LLM search, forces workarounds for Parameter Store, CloudWatch)
- EC2 + Lambda split doubles operational surface for <100 concurrent users
- CloudFront routing adds ~289 lines of Terraform for what Cloudflare does for free
- t3.micro (1GB RAM) is barely adequate for Playwright browsers
- Free tier is temporary; the architecture was shaped by it

**Decision:** Migrate to a single Hetzner VPS with Docker Compose, Cloudflare for CDN/frontend, and Cloudflare R2 for object storage. This migration starts with docs — rewriting the architecture documentation to reflect the new target before touching any code or infrastructure.

## Target Architecture

```
Users → Cloudflare (CDN + DNS + DDoS protection)
         ├── /* (default) → Cloudflare Pages (React app, auto-deploy from GitHub)
         ├── /tiles/* → Cloudflare R2 (pre-generated vector tiles)
         └── /api/* → Hetzner VPS (proxied through Cloudflare)
                        ┌─────────────────────────────────┐
                        │  Hetzner VPS (CX23)             │
                        │  2 vCPU, 4GB RAM, 40GB disk     │
                        │                                 │
                        │  ┌─────────────────────────┐    │
                        │  │ Caddy (reverse proxy)    │    │
                        │  │ Auto-TLS via Let's Encrypt│   │
                        │  │ Routes /api/* → FastAPI   │   │
                        │  └─────────────────────────┘    │
                        │                                 │
                        │  ┌─────────────────────────┐    │
                        │  │ FastAPI (Uvicorn)        │    │
                        │  │ Docker container          │   │
                        │  │ Port 8000                 │   │
                        │  └─────────────────────────┘    │
                        │                                 │
                        │  ┌─────────────────────────┐    │
                        │  │ Dagster (webserver+daemon)│   │
                        │  │ Docker container          │   │
                        │  │ Port 3000 (internal only) │   │
                        │  └─────────────────────────┘    │
                        │                                 │
                        │  ┌─────────────────────────┐    │
                        │  │ PostgreSQL 16 + PostGIS  │    │
                        │  │ Docker container          │   │
                        │  │ Port 5432 (internal only) │   │
                        │  └─────────────────────────┘    │
                        │                                 │
                        │  ┌─────────────────────────┐    │
                        │  │ Watchtower               │    │
                        │  │ Polls GHCR, auto-restarts│   │
                        │  └─────────────────────────┘    │
                        │                                 │
                        │  Cron: pg_dump → R2 (daily)     │
                        └─────────────────────────────────┘

CI/CD: Push to main → GH Actions → build Docker images → push to GHCR
       Watchtower on VPS detects new images → pulls → restarts containers
       Cloudflare Pages auto-deploys frontend on push (no VPS involved)
```

### Key Differences from AWS Architecture

| Concern | AWS (old) | VPS (new) |
|---|---|---|
| **API compute** | Lambda + API Gateway + Mangum | FastAPI + Uvicorn in Docker container |
| **Pipeline compute** | EC2 t3.micro (1GB RAM) | Hetzner VPS (4GB RAM) — same box as API |
| **Database** | RDS db.t3.micro (managed) | PostgreSQL in Docker (self-managed) |
| **Frontend hosting** | S3 + CloudFront | Cloudflare Pages (auto-deploy from GitHub) |
| **CDN / TLS** | CloudFront + ACM | Cloudflare (free tier) + Caddy (Let's Encrypt) |
| **Object storage** | S3 (raw data, tiles) | Cloudflare R2 (S3-compatible, no egress fees) |
| **Reverse proxy** | API Gateway + CloudFront | Caddy |
| **Deployments** | GH Actions → aws cli (S3 sync, Lambda update, SSM) | GH Actions → GHCR → Watchtower (pull-based) |
| **IaC** | Terraform (1,500 lines, 8 modules) | docker-compose.yml + Caddyfile + setup script |
| **VPS access** | Session Manager (no SSH) | SSH with key auth (firewall: allow 22, 80, 443 only) |
| **Monitoring** | CloudWatch alarms + SNS + Lambda forwarder | Container healthchecks + cron script → Slack |
| **Backups** | RDS automated (7-day PITR) | pg_dump cron → R2 (daily, 30-day retention) |
| **Secrets** | Parameter Store + Terraform env vars | `.env` file on VPS (gitignored) + Docker Compose env |
| **WAF / rate limiting** | AWS WAF ($6.60/mo) | Cloudflare WAF (free tier) |
| **Cost (Year 1)** | $0 (free tier) | ~$5/mo |
| **Cost (Year 2+)** | ~$30-35/mo | ~$5/mo |
| **VPC networking** | Lambda in VPC, can't reach internet | All containers share host network, full internet access |

### What This Fixes

1. **LLM search works** — FastAPI container can call OpenRouter directly (no VPC trap)
2. **4x more RAM** — Dagster + Playwright get 4GB instead of 1GB, no OOM risk
3. **No connection pool budget** — All services are localhost, no cross-network connection limits
4. **Simpler deployments** — No Lambda packaging, no S3 sync, no CloudFront invalidation
5. **$25-30/mo cheaper** post-free-tier
6. **One operational surface** — SSH into one box, `docker compose logs`, done

### What This Doesn't Change

- PostgreSQL + PostGIS (same database, same schema)
- Dagster for orchestration (same assets, same schedules)
- FastAPI for the API (same routes, same code — just drop Mangum wrapper)
- React + MapLibre + Deck.gl frontend (same code, different hosting)
- S3-compatible storage for raw data (R2 is S3-compatible, boto3 works with endpoint override)
- SCD Type 2 in staging, `public.properties` VIEW, PIDN identifiers
- Alembic migrations, entity resolution, county_config pattern
- Slack alerting (webhook URLs in env vars instead of Parameter Store)

## Docs Migration Plan

### Tier 1 — Delete and Replace (infrastructure core)

These files are so deeply AWS-specific that editing in place would leave confusing artifacts. Write fresh.

#### 1.1 Delete `docs/infrastructure/` (9 files)

Delete:
- `docs/infrastructure/services.md`
- `docs/infrastructure/database.md`
- `docs/infrastructure/compute.md`
- `docs/infrastructure/networking.md`
- `docs/infrastructure/terraform.md`
- `docs/infrastructure/cicd.md`
- `docs/infrastructure/waf.md`
- `docs/infrastructure/bootstrap.md`
- `docs/infrastructure/backup-recovery.md`

Replace with single file: **`docs/infrastructure.md`**

Contents:
- **VPS spec** — Hetzner CX23 (x86), 2 vCPU, 4GB RAM, 40GB SSD, Falkenstein DC
- **Docker Compose services** — postgres, dagster, api, caddy, watchtower (service definitions, volumes, networks, healthchecks)
- **Caddy configuration** — reverse proxy rules, auto-TLS, API routing, Dagster UI (optional, SSH tunnel)
- **Cloudflare setup** — DNS (A record → VPS IP), proxied mode, SSL mode (Full Strict), R2 bucket config, Pages project
- **Firewall** — Hetzner Cloud Firewall: allow 22 (SSH), 80/443 (HTTP/S), deny all else
- **Secrets management** — `.env` file on VPS, Docker Compose `env_file` directive, GHCR token for Watchtower
- **Backups** — pg_dump cron (daily 4am UTC), rclone to R2, 30-day retention, restore procedure
- **CI/CD** — GH Actions workflow: build images → push GHCR. Watchtower polls every 5 minutes. Cloudflare Pages auto-deploy for frontend.
- **VPS access** — SSH key auth, no password, firewall-restricted
- **Monitoring** — Docker healthchecks, cron-based system check → Slack webhook, Dagster sensors unchanged
- **Upgrade path** — CX23 → CX33 (resize in Hetzner console, 2 minutes downtime)

#### 1.2 Rewrite `docs/architecture-overview.md`

Replace AWS architecture diagram with the VPS diagram from this spec. Keep the narrative about decoupled public frontend + private backend, but update the components.

#### 1.3 Rewrite `docs/cost.md`

New cost model:

| Service | Monthly Cost |
|---|---|
| Hetzner CX23 (2 vCPU x86, 4GB RAM, 40GB) | EUR3.49 (~$3.80) |
| Cloudflare (free tier: CDN, DNS, Pages, WAF) | $0 |
| Cloudflare R2 (10GB free, then $0.015/GB) | $0 (MVP) |
| Domain registration (annual, amortized) | ~$1/mo |
| **Total** | **~$5/mo** |

No Year 1 vs Year 2 distinction — no free tier expiration to worry about.

Cost traps to document: Hetzner snapshots ($0.012/GB/mo if enabled), R2 Class A operations ($4.50/million — only matters at scale), domain auto-renewal.

#### 1.4 Rewrite `docs/decisions.md`

Update the decision log table. Most decisions stay (Dagster, PostgreSQL, React, FastAPI, Alembic, etc.). Changes:

| Decision | Old | New |
|---|---|---|
| Compute | EC2 t3.micro | Hetzner VPS (Docker Compose) |
| Database | RDS db.t3.micro (managed) | PostgreSQL in Docker (self-managed) |
| API hosting | Lambda + API Gateway | FastAPI + Uvicorn in Docker |
| Frontend hosting | S3 + CloudFront | Cloudflare Pages |
| Object storage | S3 | Cloudflare R2 |
| CDN / TLS | CloudFront + ACM | Cloudflare + Caddy (Let's Encrypt) |
| IaC | Terraform | Docker Compose + Caddyfile |
| Instance access | Session Manager | SSH key auth |
| CI/CD | GH Actions + OIDC + aws cli | GH Actions + GHCR + Watchtower |
| Monitoring | CloudWatch + SNS + Lambda | Docker healthchecks + cron → Slack |
| WAF | AWS WAF ($6.60/mo) | Cloudflare WAF (free) |
| Backups | RDS automated PITR | pg_dump → R2 daily |
| Secrets | Parameter Store + Terraform env vars | .env file + Docker Compose env |

Tradeoffs section updates:
- Remove: Single-AZ RDS, no NAT Gateway, no VPC Endpoints, no ALB, no Parameter Store — all moot
- Add: Self-managed Postgres (no automated PITR, must test pg_dump restores), single VPS SPOF (same as before, but recovery is VPS rebuild + docker compose up), no managed backups (cron must be monitored)

#### 1.5 Rewrite `docs/api/lambda-api.md` → `docs/api/api.md`

- Remove: Lambda config, Mangum handler, CloudFront distribution, S3 buckets, cold start mitigation, Lambda concurrency
- Keep: API endpoints table, FastAPI app structure, connection pooling concept (simpler — single psycopg2 connection pool, no concurrency cap needed)
- Add: Uvicorn config, Docker container setup, Caddy routing, healthcheck endpoint

#### 1.6 Rewrite `docs/future-enhancements.md`

Remove AWS-specific enhancements. New list:
1. **VPS resize** — CX23 → CX33 (4 vCPU, 8GB) when memory > 80%. EUR6/mo.
2. **NAIP Imagery Pipeline** — unchanged (data source, not infra)
3. **Dagster Cloud Hybrid** — still relevant for multi-user UI access
4. **Cloudflare Workers** — edge compute for rate limiting, geo-blocking, or API caching if needed
5. **Automated cost alerting** — Hetzner budget alerts (API-based) + R2 usage monitoring
6. **Multi-VPS** — separate pipeline VPS from API VPS if load requires (unlikely at county scale)

#### 1.7 Rewrite `docs/implementation/phase-0-1-setup.md`

Phase 0 (local setup): mostly unchanged — Docker, Python, Node.js, Git, psql. Remove AWS CLI, Terraform.
Phase 1 (infrastructure): completely new:
- Create Hetzner account, provision VPS
- Configure Hetzner Cloud Firewall
- SSH key setup
- Install Docker + Docker Compose on VPS
- Create Cloudflare account, add domain, configure DNS
- Create R2 bucket, generate API token
- Write docker-compose.yml, Caddyfile
- Deploy and verify

#### 1.8 Rewrite `docs/implementation/phase-5-cicd-golive.md`

- Step 5.0: Docker Compose up on VPS (replaces Terraform apply)
- Step 5.1: GH Actions workflow — build + push Docker images to GHCR
- Step 5.2: Configure Watchtower on VPS, GHCR auth token
- Step 5.3: Cloudflare Pages project — connect GitHub repo, set build command
- Step 5.4: End-to-end validation (curl API, check frontend, verify tiles, test backup/restore)
- Step 5.5: Enable Dagster schedules

### Tier 2 — Heavy Edits (8 files)

These files have a mix of AWS-specific and agnostic content. Edit in place, replacing AWS sections.

#### 2.1 `docs/operations/runbook.md`
- `aws ssm start-session` → `ssh countyiq` (with SSH config alias)
- `aws ec2 stop-instances` → `ssh countyiq 'docker compose -f /opt/countyiq/docker-compose.yml down'`
- RDS PITR → `pg_dump` restore from R2
- CloudWatch metrics → `docker stats` / `df -h` / `free -m`
- Lambda rollback → `docker compose pull api && docker compose up -d api`
- S3/CloudFront frontend rollback → Cloudflare Pages rollback (one click in dashboard)

#### 2.2 `docs/operations/alerting.md`
- Remove CloudWatch → SNS → Lambda forwarder section
- Replace with: cron script (every 5 min) checks Docker container health + disk/memory + Postgres reachability → posts to Slack webhook on failure
- Keep: Slack channels, Dagster sensor alerting, retry policy (all unchanged)
- Webhook URLs: env vars in `.env` (not Parameter Store)

#### 2.3 `docs/operations/health-dashboard.md`
- Replace `boto3.client("cloudwatch")` infra metrics sensor with system metrics collection via `psutil` + `docker` Python SDK
- Metrics: CPU, memory, disk from host OS; container status from Docker; Postgres connection count from `pg_stat_activity`
- Keep: `meta.infra_metrics` table, `meta.pipeline_status` table, API handler, status logic, dashboard UI

#### 2.4 `docs/frontend/architecture.md`
- Stack: remove Lambda/Mangum, add Docker FastAPI + Uvicorn
- Infrastructure section: CloudFront → Cloudflare, S3 → Cloudflare Pages/R2
- SPA routing: CloudFront Function → Cloudflare Pages (handles SPA routing natively)
- Deployment: `aws s3 sync` → Cloudflare Pages auto-deploy
- Cold start: remove (no Lambda cold starts)
- Custom domain: Route 53 → Cloudflare DNS
- Keep: everything about React, MapLibre, Deck.gl, product views, API endpoints, computed fields, tile strategy

#### 2.5 `docs/pipelines/dagster-config.md`
- Components: "all on single EC2 instance" → "all in Docker containers on Hetzner VPS"
- Memory budget: 1GB → 4GB. Remove OOM warnings. New budget: OS ~200MB, Postgres ~500MB, Dagster ~500MB, available for jobs ~2.5GB. Multiple Playwright browsers OK.
- Dagster storage: RDS → Postgres container (same instance, `dagster` database)
- Keep: log levels, schedules, staggered timing (still good practice even with more RAM)

#### 2.6 `docs/pipelines/code-structure.md`
- Monorepo layout: remove `infra/` Terraform tree, add `docker/` directory (docker-compose.yml, Caddyfile, .env.example)
- S3 archival: `s3.archive()` → R2 (same boto3 calls with custom endpoint URL)
- Dependencies: `boto3` stays (R2 is S3-compatible), remove "Parameter Store access" comment
- `lib/slack.py`: "reads from SSM" → "reads from env vars"
- `resources/storage.py`: S3 client → R2 client (endpoint override only)
- `resources/database.py`: "RDS connection pool" → "Postgres connection" (localhost in Docker network)

#### 2.7 `docs/implementation/phase-4-api-frontend.md`
- Step 4.1: remove Lambda packaging notes, 250MB limit, Mangum. Add Docker build instructions.
- Step 4.2: replace `aws s3 sync` + CloudFront invalidation with Cloudflare Pages auto-deploy note
- Keep: all FastAPI endpoint development, SQL, curl testing, React component development, Slack setup

#### 2.8 `docs/implementation/file-inventory.md`
- Replace `infra/` Terraform module tree with:
  ```
  docker/
  ├── docker-compose.yml
  ├── docker-compose.dev.yml
  ├── Caddyfile
  ├── .env.example
  ├── backup.sh
  └── setup.sh
  ```

### Tier 3 — Light Patches (8 files)

Find-and-replace level changes. A few lines each.

| File | Change |
|---|---|
| `docs/pipelines/data-retention.md` | `s3://countyiq-raw/` → R2 bucket URL. S3 Standard pricing → R2 pricing. RDS storage cost → disk cost. |
| `docs/schema/meta.md` | Remove "Module: Database" RDS config section (keep all DDL). Remove SSM initialization commands. |
| `docs/schema/strategy.md` | `s3://countyiq-raw/` → R2 path. "Raw data goes to S3" → "Raw data goes to R2". |
| `docs/schema/migrations.md` | SSM port forwarding command → `ssh -L 5434:localhost:5432 countyiq`. "On EC2 (direct)" → "On VPS (direct)". |
| `docs/implementation/expansion-roadmap.md` | "Cognito/Clerk auth" → "Clerk auth". "t3.small" → "VPS resize". S3 paths → R2. Remove "CloudWatch shows memory > 80%". |
| `docs/privacy.md` | "Cognito or Clerk" → "Clerk". "CloudFront: No change" → "Cloudflare: No change". |
| `docs/open-items.md` | Remove: RDS master password/SSM, Terraform state backend, PostGIS on RDS. Add: Docker Postgres PostGIS extension, R2 bucket creation, Cloudflare Pages project setup. |
| `docs/pipelines/backfill.md` | "t3.micro to its 1 GB limit" → "VPS has 4GB, memory is not a constraint". |
| `docs/operations/testing.md` | Replace SSM smoke test (`aws ssm send-command`) with SSH or Docker healthcheck equivalent. One section change. |

### Tier 4 — Unchanged (11 files)

No changes needed:
- `docs/pipelines/entity-resolution.md` — pure SQL/Dagster
- `docs/data-source-feasibility.md` — data source analysis
- `docs/data-model-phase2-appendix.md` — Phase 2 schema design
- `docs/implementation/README.md` — meta doc
- `docs/implementation/phase-2-database.md` — Alembic setup (agnostic)
- `docs/implementation/phase-3-pipelines.md` — Dagster asset development (agnostic)
- `docs/products/county-scout.md` — product doc
- `docs/aopc-court-records-draft.md` — research doc
- `docs/rtk-recorder-of-deeds-draft.md` — research doc
- Existing specs and plans in `docs/superpowers/` — historical, leave as-is

### Also Update: `CLAUDE.md`

The CountyIQ skill file and `CLAUDE.md` both contain AWS-specific constraints that guide Claude Code's behavior. These need updating:

**Remove:**
- Lambda VPC networking constraints ("Lambda can only reach RDS on port 5432")
- CloudFront routing rules (`/api/*` → API Gateway, `/tiles/*` → S3, `/*` → S3 frontend)
- Lambda credential delivery pattern (Terraform env vars, not Parameter Store)
- Connection pool budget (Lambda 10, Dagster 3-5, sensors 2-3)
- "No `raw` schema in RDS. Raw data goes to S3" → "Raw data goes to R2"
- S3 bucket names
- All references to Terraform, EC2, RDS as managed service

**Add/Update:**
- Docker Compose is the infrastructure definition
- All services run on one VPS (Caddy, FastAPI, Dagster, Postgres)
- R2 for object storage (raw data, tiles, backups) — S3-compatible, use boto3 with endpoint override
- Cloudflare Pages for frontend hosting
- FastAPI runs under Uvicorn (no Mangum/Lambda wrapper)
- Caddy handles TLS and reverse proxy
- Secrets in `.env` file, loaded via Docker Compose `env_file`
- Watchtower handles deployments (pull-based from GHCR)

### Also Update: `.claude/skills/countyiq/` skill file

Same changes as CLAUDE.md — the skill file is the detailed version that gets loaded on every task.

## Verification

After all docs are modified:

1. **Grep for stale references:** Search all `docs/` files for: `EC2`, `RDS`, `Lambda`, `CloudFront`, `API Gateway`, `S3` (as AWS service, not generic), `SSM`, `Parameter Store`, `t3.micro`, `db.t3.micro`, `Terraform`, `terraform`, `NAT Gateway`, `VPC`, `OIDC`, `Mangum`. Each hit should be either intentional (historical reference) or a miss.

2. **Cross-reference check:** Every file in `docs/infrastructure/` skill routing table should point to valid files. The file-inventory should match the actual repo.

3. **CLAUDE.md consistency:** The rules in CLAUDE.md should match what the architecture docs describe. No contradictions.

4. **Read-through:** Read `docs/architecture-overview.md` → `docs/infrastructure.md` → `docs/cost.md` end-to-end and verify they tell a coherent story.
