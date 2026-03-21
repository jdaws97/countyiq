# Decision Log

## Decision Log

| Decision | Choice | Rationale |
|---|---|---|
| Compute | EC2 t3.micro | Free tier 12 months; sufficient for sequential scraper workloads |
| OS | Amazon Linux 2023 | Familiar, well-supported, lightweight |
| Orchestrator | Dagster (self-hosted) | Dependency management, asset lineage, retry logic, scheduling UI |
| Database | RDS PostgreSQL 16 + PostGIS | Free tier 12 months (db.t3.micro); same VPC as EC2; 20 GB storage; automated backups |
| Object storage | S3 | Raw scrape archival, PDF storage, future imagery |
| Instance access | Session Manager | No SSH port, no IP whitelisting, free, audit logging via CloudTrail |
| Dagster UI access | Port forwarding via Session Manager | No ALB, no domain, no TLS certs needed |
| IaC | Terraform | Jarod's preference; modules for separation of concerns |
| VPC | Default VPC | No NAT gateway cost; instance needs outbound internet |
| Observability | Minimal CloudWatch + Dagster UI | Dagster handles pipeline monitoring; CloudWatch for infra health only |
| Log retention | 7 days | Keeps costs negligible; Dagster UI retains run history independently |
| Budget controls | Email alerts at thresholds | Automated kill switch deferred to future enhancement |
| Schema migrations | Alembic | Versioned, reversible migrations; LLM-friendly structured framework; local Docker Postgres for testing |
| Pipeline structure | Dagster assets, organized by source type | arcgis/, scrapers/, bulk/, pdf/, enrichment/ — maps to how data is fetched |
| Language | Python (all pipelines) | Dagster is Python; scraping libs (Playwright, BS4, pdfplumber) are Python; bottleneck is network I/O not CPU |
| Repository | Single monorepo (infra + pipelines) | Solo dev simplicity; Terraform and Dagster code in one repo |
| Entity resolution | Deterministic matching in PostgreSQL (pg_trgm) | Start simple; schema designed for future Zingg upgrade; reusable across counties |
| Frontend framework | React + MapLibre GL JS + Deck.gl | Free, open source, modern vector tile rendering, GPU-accelerated data layers |
| Frontend hosting | S3 + CloudFront (static site) | No server to manage; HTTPS + CDN; pennies/month |
| API layer | Lambda + API Gateway (FastAPI via Mangum) | Decoupled from Dagster EC2; auto-scaling; permanent free tier; no memory contention with scrapers |
| Frontend access | Publicly accessible | No auth for MVP; CloudFront URL initially, custom domain later |
| CI/CD | GitHub Actions + OIDC federation | Zero stored credentials; short-lived tokens; path-filtered workflows per deploy target |
| Data refresh schedules | Staggered daily/weekly/monthly | Full deployment target: 6 daily (2hr gaps), 11 weekly (spread Sun–Fri), 3 monthly (1st of month), 2 on-demand. **MVP launch: 5 weekly schedules only** (source #13 assessment is bulk import, not scheduled) |
| Alerting | Slack (free tier) + Dagster sensors + CloudWatch→Lambda→Slack | #alerts-critical (phone ON), #alerts-warning, #pipeline-runs |
| Retry policy | 3 retries, exponential backoff (5→10→20 min) | Alert only after all retries exhausted |
| Operational dashboard | /ops/health page in React frontend | Green/yellow/red per source; infra metrics; powered by Dagster run history + CloudWatch |
| Product name | CountyIQ | Available, no conflicts in civic/data/GIS space |
| Data retention | Keep everything forever, no Glacier | Raw snapshots in S3 Standard (~$0.23/month/yr); change-tracked records in RDS (SCD Type 2); operational logs pruned at 90 days |
| Backfill strategy | Full snapshot on Day 1; deep scrape archives; accept "from launch" for current-only sources | ~4-6 hour Day 1 backfill; Dagster `full_history` config flag per asset |
| Testing | 3 layers: CI (lint + type check + schema tests), smoke test on deploy, Dagster asset checks in production | No live API tests in CI; no Docker Postgres in CI; no coverage requirements |
| WAF rate limiting | **Deferred to public launch.** Terraform ready but not applied at MVP. | ~$6.60/month, no free tier. Not needed while URL is private. Uncomment and apply when the platform goes public. See `docs/infrastructure/waf.md`. |
| Backup strategy | RDS automated backups (7-day) + S3 versioning + rebuildable EC2 | No multi-AZ (cost); no cross-region (unnecessary); EC2 recovery via terraform apply ~15 min |
| Imagery sources | NAIP only | One source, deferred to Phase 2 |
| Satellite imagery | Dropped (Landsat, Sentinel-2) | Too coarse for parcel-level intelligence |
| MVP schedule scope | 6 MVP sources, 5 weekly schedules at launch | 6 sources: #1 GIS Portal, #2 Flood Zones, #3 Assessment DB, #4 PA Open Data, #5 PennDOT Open Data, #13 PennDOT Projects. #3 Assessment is a one-time bulk import (not scheduled). 5 weekly schedules enabled. All daily schedules are Phase 2. |
| Privacy & access control | No auth for MVP; phased approach for sensitive data | All MVP data is already public; access controls added in Phase 2 when court records and sensitive aggregated data arrive |
| Lambda credential delivery | Terraform env vars (NOT Parameter Store at runtime) | Lambda in VPC can't reach Parameter Store without NAT/$32/mo; Terraform sets encrypted env vars at deploy time |
| API route prefix | All Lambda routes under `/api/*` | CloudFront only forwards `/api/*` to API Gateway; ops health at `/api/ops/health`; tiles served from S3 via `/tiles/*` (not Lambda) |
| API Gateway access control | Origin-verify header (CloudFront → Lambda) | CloudFront adds `x-origin-verify` secret header; FastAPI middleware rejects direct API Gateway calls. $0 cost. No WAF needed for API lockdown. |
| Meta schema ownership | App-owned DDL; Dagster sensors write; Lambda reads | Separate from Dagster's internal `dagster` database; authoritative DDL in docs/schema/meta.md |
| MVP entity resolution | Parcels + assessment only (2 sources) | Dynamically detects available staging tables; Phase 2 sources added incrementally as pipelines are built |
| Schema authority | Infra plan is single source of truth; data model doc is Phase 2/3 appendix | all MVP schema defined in docs/schema/; data model doc reclassified to docs/data-model-phase2-appendix.md |
| Connection pooling | Module-level connection reuse + reserved concurrency = 10 | Warm Lambda invocations reuse `_conn`; 10 cap keeps RDS within 50-connection limit alongside Dagster/sensors/admin |
| Rollback strategy | 5 documented procedures (Lambda, Dagster, migration, pipeline data, frontend) | Each scenario has specific steps; SCD2 enables data-level rollback by expiring bad records and re-running |
| CHECK constraints | Enforce valid values on meta schema columns | `status`, `schedule_type`, `check_name` constrained; non-negative on counts/durations; staging tables use DQ checks instead of hard constraints for upstream flexibility |
| RDS backup window | 06:00–06:30 UTC | After all weekly pipelines complete (overnight US Eastern); consistent across all doc references |
| Lambda package size | 250 MB uncompressed limit; current deps ~50 MB | Ample headroom; monitor if adding heavy deps like pandas/numpy |

### Acknowledged Tradeoffs

Items below have been raised in review and are **intentional choices**, not oversights. They are listed here to prevent re-flagging.

| Concern | Status | Reasoning |
|---|---|---|
| No staging/dev environment | Accepted | Solo developer; cost of duplicating RDS + EC2 not justified. Branch-based development with `terraform plan` review and Dagster dry-run mode is sufficient. Revisit if a second contributor joins. |
| Single-AZ RDS | Accepted | Multi-AZ doubles RDS cost (~$14→$28/mo post-free-tier). Acceptable RTO for a non-critical civic tool: restore from automated backup in ~15 min. Revisit at public launch or if uptime SLA is needed. |
| No NAT Gateway or VPC Endpoints | Accepted | Lambda doesn't need AWS service access at runtime — credentials delivered via Terraform env vars, metrics bridged through `meta` schema. NAT adds ~$32/mo, VPC endpoints ~$7/mo each. Zero benefit for this architecture. |
| No Parameter Store reads at runtime | Accepted | Direct consequence of no NAT/VPC endpoints. Terraform injects secrets as encrypted env vars (KMS default key). Tradeoff: redeploy required to rotate DB password. Acceptable for solo ops. |
| No ALB | Accepted | API Gateway + Lambda replaces ALB + ECS/Fargate at a fraction of the cost. Dagster UI accessed via Session Manager port forwarding — no public endpoint needed. |
| EC2 is a single point of failure | Accepted | If EC2 dies, pipelines stop but the frontend + API keep working (Lambda + S3). Recovery: `terraform apply` rebuilds EC2 in ~15 min, Dagster resumes on next schedule tick. No data loss (RDS is separate). |
| No container orchestration (ECS/EKS) | Accepted | Dagster on bare EC2 is simpler and free-tier eligible. Containerization adds complexity with no scaling benefit — pipelines run sequentially and are network-bound, not CPU-bound. |
| CloudWatch-only monitoring (no Datadog/Grafana) | Accepted | CloudWatch is free for basic metrics. Dagster UI provides pipeline-level observability. `meta.infra_metrics` bridges the gap to the frontend. Third-party monitoring adds cost with minimal incremental value at this scale. |
| No automated failover or self-healing | Accepted | EC2 health check + CloudWatch alarm → Slack alert → manual intervention. Auto-recovery (EC2 auto-recover or ASG min=1) can be added later without architectural changes. |
| No encryption at rest for S3 | Non-issue | S3 default encryption (SSE-S3) is enabled automatically since Jan 2023. No configuration needed. |
| `raw` schema removed | Intentional | Original data model doc had a `raw` schema. Removed during architecture consolidation — staging tables ingest directly from sources with SCD2 tracking, making a separate raw layer redundant. |
| Data model doc is "deprecated" | Intentional | Reclassified as Phase 2/3 appendix. The infra plan is the single source of truth for all MVP schema. The data model doc contains forward-looking designs (UUIDs, entity_relationships, Cognito) that don't apply yet. |
| No automated integration tests in CI | Accepted | CI runs lint + type check + schema validation. Live API and database tests run as Dagster asset checks in production. Adding a Docker Postgres to CI is deferred — the risk surface is low with a solo developer testing locally. |
| Daily schedules exist but are disabled | Intentional | Schedule definitions are in code for Phase 2 readiness. Only 5 weekly schedules are enabled at MVP. `dagster schedule start` targets them explicitly by name. |

---
