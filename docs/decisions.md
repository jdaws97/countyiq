# Decision Log

## Decision Log

| Decision | Choice | Rationale |
|---|---|---|
| Compute | Hetzner VPS CX23 (Docker Compose) | 2 vCPU x86, 4GB RAM, 40GB SSD. 4x RAM vs EC2 t3.micro, simpler ops, ~$5/mo vs $30+/mo post-free-tier |
| OS | Debian 12 (VPS host) | Stable, well-supported, native Docker packages |
| Orchestrator | Dagster (self-hosted, Docker container) | Dependency management, asset lineage, retry logic, scheduling UI |
| Database | PostgreSQL 16 + PostGIS (Docker container, self-managed) | Same DB engine, no vendor lock-in, localhost access from all containers, no VPC networking constraints |
| Object storage | Cloudflare R2 | S3-compatible (boto3 with endpoint override), no egress fees, 10GB free tier |
| Instance access | SSH key auth | Standard, simple, restricted by Hetzner Cloud Firewall (port 22 only) |
| Dagster UI access | SSH tunnel to localhost:3000 | No public endpoint needed; `ssh -L 3000:localhost:3000 countyiq` |
| IaC | Docker Compose + Caddyfile | Docker Compose IS the infrastructure definition. ~50 lines replaces ~1,500 lines of Terraform |
| Reverse proxy / TLS | Caddy (Docker container) | Auto-TLS via Let's Encrypt, reverse proxy `/api/*` to FastAPI, zero config renewal |
| CDN / DDoS / WAF | Cloudflare (free tier) | DNS, CDN, DDoS protection, WAF rules, SSL (Full Strict mode) — all free |
| Log retention | Docker logs + logrotate (7 days) | Same retention as before; Dagster UI retains run history independently |
| Budget controls | Hetzner fixed monthly pricing | No variable costs to monitor; R2 egress is free; Cloudflare is free tier |
| Schema migrations | Alembic | Versioned, reversible migrations; LLM-friendly structured framework; local Docker Postgres for testing |
| Pipeline structure | Dagster assets, organized by source type | arcgis/, scrapers/, bulk/, pdf/, enrichment/ — maps to how data is fetched |
| Language | Python (all pipelines) | Dagster is Python; scraping libs (Playwright, BS4, pdfplumber) are Python; bottleneck is network I/O not CPU |
| Repository | Single monorepo (docker + pipelines + api + frontend) | Solo dev simplicity; Docker Compose, Dagster, and API code in one repo |
| Entity resolution | Deterministic matching in PostgreSQL (pg_trgm) | Start simple; schema designed for future Zingg upgrade; reusable across counties |
| Frontend framework | React + MapLibre GL JS + Deck.gl | Free, open source, modern vector tile rendering, GPU-accelerated data layers |
| Frontend hosting | Cloudflare Pages | Auto-deploy from GitHub, free CDN, SPA routing handled natively, zero config |
| API layer | FastAPI + Uvicorn (Docker container) | No VPC networking trap — full internet access for LLM search (OpenRouter). No Lambda cold starts. No Mangum wrapper. |
| Frontend access | Publicly accessible | No auth for MVP; Cloudflare Pages URL initially, custom domain later |
| CI/CD | GitHub Actions + GHCR + Watchtower | Push to main builds Docker images, pushes to GHCR. Watchtower on VPS polls and auto-restarts. Pull-based deploys — no SSH keys in CI, no cloud credentials. Cloudflare Pages auto-deploys frontend separately. |
| Data refresh schedules | Staggered daily/weekly/monthly | Full deployment target: 6 daily (2hr gaps), 11 weekly (spread Sun-Fri), 3 monthly (1st of month), 2 on-demand. **MVP launch: 5 weekly schedules only** (source #13 assessment is bulk import, not scheduled) |
| Alerting | Slack (free tier) + Dagster sensors + cron healthcheck | #alerts-critical (phone ON), #alerts-warning, #pipeline-runs. Webhook URLs in `.env` file. |
| Retry policy | 3 retries, exponential backoff (5-10-20 min) | Alert only after all retries exhausted |
| Operational dashboard | /ops/health page in React frontend | Green/yellow/red per source; infra metrics; powered by Dagster run history + Docker healthchecks |
| Product name | CountyIQ | Available, no conflicts in civic/data/GIS space |
| Data retention | Keep everything forever | Raw snapshots in R2 (~$0.015/GB/mo after 10GB free); change-tracked records in Postgres (SCD Type 2); operational logs pruned at 90 days |
| Backfill strategy | Full snapshot on Day 1; deep scrape archives; accept "from launch" for current-only sources | ~4-6 hour Day 1 backfill; Dagster `full_history` config flag per asset |
| Testing | 3 layers: CI (lint + type check + schema tests), smoke test on deploy, Dagster asset checks in production | No live API tests in CI; no Docker Postgres in CI; no coverage requirements |
| WAF rate limiting | Cloudflare WAF (free tier) | Free tier includes rate limiting rules, bot management, managed rulesets. Active from day one — no cost reason to defer. |
| Backup strategy | pg_dump daily to R2 (30-day retention) + Docker volumes | Cron at 4am UTC, rclone to R2. Restore tested monthly. Docker Postgres volume survives container restarts. |
| Monitoring | Docker healthchecks + cron script + Slack | Cron every 5 min checks container health, disk, memory, Postgres reachability. Posts to Slack on failure. Dagster sensors unchanged. |
| Imagery sources | NAIP only | One source, deferred to Phase 2 |
| Satellite imagery | Dropped (Landsat, Sentinel-2) | Too coarse for parcel-level intelligence |
| MVP schedule scope | 6 MVP sources, 5 weekly schedules at launch | 6 sources: #1 GIS Portal, #2 Flood Zones, #3 Assessment DB, #4 PA Open Data, #5 PennDOT Open Data, #13 PennDOT Projects. #3 Assessment is a one-time bulk import (not scheduled). 5 weekly schedules enabled. |
| Privacy & access control | No auth for MVP; phased approach for sensitive data | All MVP data is already public; access controls added in Phase 2 when court records and sensitive aggregated data arrive |
| Secrets management | `.env` file + Docker Compose `env_file` | Simple, local, no network dependency. Secrets never leave the VPS. Redeploy not required to rotate — restart container after editing `.env`. |
| API route prefix | All routes under `/api/*` | Caddy reverse proxies `/api/*` to FastAPI container on port 8000. Tiles served from R2 via Cloudflare CDN at `/tiles/*`. |
| Connection pooling | Uvicorn workers + psycopg2 pool | All services on localhost via Docker network. No concurrency cap needed. Postgres max_connections ~100, actual usage ~15. |
| Meta schema ownership | App-owned DDL; Dagster sensors write; API reads | Separate from Dagster's internal `dagster` database; authoritative DDL in docs/schema/meta.md |
| Assessment scraper deferred | Code exists but not wired into jobs/schedules/VIEW | Portal "cannot be sold" disclaimer creates commercial-use ambiguity; GIS Parcels already provides owner, values, sale history, class, LUC, municipality, school district. Only loses value_history, permits (eFACTS #17 Phase 2), delinquent_taxes (Tax Claim #14 Phase 2). Scraper/parser/tests preserved for reactivation. |
| MVP entity resolution | Parcels only (assessment deferred) | Dynamically detects available staging tables; Phase 2 sources added incrementally as pipelines are built |
| Schema authority | Infra plan is single source of truth; data model doc is Phase 2/3 appendix | All MVP schema defined in docs/schema/; data model doc reclassified to docs/data-model-phase2-appendix.md |
| Rollback strategy | 3 documented procedures (API, pipeline data, frontend) | API: `docker compose pull api && docker compose up -d api` with previous image tag. Data: SCD2 enables rollback by expiring bad records and re-running. Frontend: Cloudflare Pages rollback (one click in dashboard). |
| CHECK constraints | Enforce valid values on meta schema columns | `status`, `schedule_type`, `check_name` constrained; non-negative on counts/durations; staging tables use DQ checks instead of hard constraints for upstream flexibility |
| Deployments | Pull-based via Watchtower | Watchtower polls GHCR every 5 minutes for new images. GH Actions CI checks run before image push. No SSH keys or cloud credentials in CI. |

### Acknowledged Tradeoffs

Items below have been raised in review and are **intentional choices**, not oversights. They are listed here to prevent re-flagging.

| Concern | Status | Reasoning |
|---|---|---|
| Self-managed PostgreSQL | Accepted | No automated PITR like RDS. Mitigated by daily pg_dump to R2, tested monthly. Restore is ~5-10 min. |
| Single VPS is SPOF | Accepted | Same as EC2 was. If VPS dies, frontend (Cloudflare Pages) stays up. Recovery: provision new VPS + `docker compose up` (~15 min). Data safe in R2 backups + Postgres volume. |
| No staging/dev environment | Accepted | Solo developer. Docker Compose makes local dev identical to prod. Branch-based dev sufficient. |
| No managed backups | Accepted | Cron + rclone handles it. Must monitor cron job health (Slack alert on failure). |
| No auto-scaling | Accepted | County-level tool, <100 concurrent users expected. VPS resize takes 2 minutes if needed. |
| SSH exposed on port 22 | Accepted | Key auth only (no password), Hetzner Cloud Firewall, fail2ban. Attack surface is minimal. |
| Self-signed TLS on direct IP | Accepted | Before domain is configured, Caddy uses self-signed cert. Cloudflare handles public TLS once domain is set. |
| No container orchestration (k8s) | Accepted | Docker Compose is sufficient. No scaling benefit at this scale. |
| Watchtower auto-restarts | Accepted | Small risk of deploying broken images automatically. Mitigated by GH Actions CI checks before image push + Docker healthchecks (Watchtower won't mark unhealthy containers as running). |
| `raw` schema removed | Intentional | Original data model doc had a `raw` schema. Removed during architecture consolidation — staging tables ingest directly from sources with SCD2 tracking, making a separate raw layer redundant. |
| Data model doc is "deprecated" | Intentional | Reclassified as Phase 2/3 appendix. The infra plan is the single source of truth for all MVP schema. The data model doc contains forward-looking designs (UUIDs, entity_relationships) that don't apply yet. |
| No automated integration tests in CI | Accepted | CI runs lint + type check + schema validation. Live API and database tests run as Dagster asset checks in production. Adding a Docker Postgres to CI is deferred — the risk surface is low with a solo developer testing locally. |
| Daily schedules exist but are disabled | Intentional | Schedule definitions are in code for Phase 2 readiness. Only 5 weekly schedules are enabled at MVP. `dagster schedule start` targets them explicitly by name. |

---
