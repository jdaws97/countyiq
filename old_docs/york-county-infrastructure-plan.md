# CountyIQ — York County Intelligence Platform — Infrastructure Plan

> **Product Name:** CountyIQ
> **Status:** Planning (not yet provisioned)
> **Author:** Jarod Daws
> **Last updated:** March 20, 2026
> **Target monthly cost (Year 1):** ~$1–2/month (free tier)
> **Target monthly cost (Year 2+):** ~$25–29/month (or ~$17–21 with reserved instances)

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Decision Log](#decision-log)
3. [AWS Infrastructure](#aws-infrastructure)
4. [RDS PostgreSQL / PostGIS](#rds-postgresql--postgis)
5. [Dagster Configuration](#dagster-configuration)
6. [Terraform Project Structure](#terraform-project-structure)
7. [Module: Networking](#module-networking)
8. [Module: IAM](#module-iam)
9. [Module: Compute](#module-compute)
10. [Module: Monitoring](#module-monitoring)
11. [Module: Database](#module-database)
12. [Schema Migrations (Alembic)](#schema-migrations-alembic)
13. [Pipeline Code Structure (Dagster)](#pipeline-code-structure-dagster)
14. [Entity Resolution](#entity-resolution)
15. [Frontend Architecture](#frontend-architecture)
16. [CI/CD (GitHub Actions + OIDC)](#cicd-github-actions--oidc)
17. [Data Refresh Schedules](#data-refresh-schedules)
18. [Error Handling, Alerting & Retry Policy](#error-handling-alerting--retry-policy)
19. [Operational Visibility](#operational-visibility)
20. [Data Retention & Archival Policy](#data-retention--archival-policy)
21. [Backfill Strategy](#backfill-strategy)
22. [Testing Strategy](#testing-strategy)
23. [WAF Rate Limiting](#waf-rate-limiting)
24. [Backup & Disaster Recovery](#backup--disaster-recovery)
25. [Cost Breakdown](#cost-breakdown)
26. [Future Enhancements (Not Implemented)](#future-enhancements-not-implemented)
27. [Bootstrap / User Data Script](#bootstrap--user-data-script)
28. [Operational Runbook](#operational-runbook)

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           PUBLIC INTERNET                                │
│                                                                          │
│   Users ───▶ CloudFront ───▶ S3 (React + MapLibre + Deck.gl)            │
│                  │                                                       │
│                  └──▶ API Gateway ───▶ Lambda (FastAPI) ──┐              │
│                                                           │              │
└───────────────────────────────────────────────────────────┼──────────────┘
                                                            │
┌───────────────────────────────────────────────────────────┼──────────────┐
│                           AWS VPC                         │              │
│                                                           ▼              │
│   ┌──────────────┐                              ┌──────────────┐        │
│   │  EC2 t3.micro│                              │ RDS Postgres │        │
│   │  Amazon Linux│                              │ + PostGIS    │        │
│   │              │                              │              │        │
│   │  ┌─────────┐ │                              │ york_county  │        │
│   │  │ Dagster  │ │─────────────────────────────▶│ _intel (app) │        │
│   │  │ webserver│ │                              │              │        │
│   │  │ daemon   │ │                              │ dagster (meta)│       │
│   │  │ workers  │ │                              └──────────────┘        │
│   │  └─────────┘ │                                                      │
│   │       │      │     ┌──────────────┐                                 │
│   │       ▼      │────▶│ S3 Buckets   │                                 │
│   │  Scrapers:   │     │ - raw data   │                                 │
│   │  - requests  │     │ - static site│                                 │
│   │  - Playwright│     └──────────────┘                                 │
│   │  - pdfplumber│                                                      │
│   └──────────────┘                                                      │
│         │                                                               │
│         ▼                                                               │
│   ┌──────────────┐                                                      │
│   │ Data Sources  │                                                      │
│   │ (outbound)   │                                                      │
│   └──────────────┘                                                      │
└─────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│                          YOUR MACHINE                                    │
│                                                                          │
│   AWS CLI ──── Session Manager ────▶ EC2 (Dagster UI on localhost:3000)  │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

**Two access patterns:**

1. **Public (frontend):** Users hit CloudFront → static React app from S3 + API calls routed through API Gateway → Lambda → RDS. No EC2 involvement for public requests.
2. **Private (admin):** You access Dagster UI via Session Manager port forwarding. Dagster + scrapers run on EC2, writing to the same RDS database.

**Key design:** The public frontend (Lambda) and the private backend (EC2/Dagster) share the same RDS database but are completely decoupled. Scraper jobs running at 3am don't affect API response times. A traffic spike on the public site doesn't slow down pipeline execution.

---

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
| Data refresh schedules | Staggered daily/weekly/monthly | 6 daily (2hr gaps), 11 weekly (spread Sun–Fri), 3 monthly (1st of month), 2 on-demand |
| Alerting | Slack (free tier) + Dagster sensors + CloudWatch→Lambda→Slack | #alerts-critical (phone ON), #alerts-warning, #pipeline-runs |
| Retry policy | 3 retries, exponential backoff (5→10→20 min) | Alert only after all retries exhausted |
| Operational dashboard | /ops/health page in React frontend | Green/yellow/red per source; infra metrics; powered by Dagster run history + CloudWatch |
| Product name | CountyIQ | Available, no conflicts in civic/data/GIS space |
| Data retention | Keep everything forever, no Glacier | Raw snapshots in S3 Standard (~$0.23/month/yr); change-tracked records in RDS (SCD Type 2); operational logs pruned at 90 days |
| Backfill strategy | Full snapshot on Day 1; deep scrape archives; accept "from launch" for current-only sources | ~4-6 hour Day 1 backfill; Dagster `full_history` config flag per asset |
| Testing | 3 layers: CI (lint + type check + schema tests), smoke test on deploy, Dagster asset checks in production | No live API tests in CI; no Docker Postgres in CI; no coverage requirements |
| WAF rate limiting | AWS WAF on CloudFront (1 Web ACL + rate-based rule) | 2,000 req/5min per IP; blocks abuse/scraping; ~$6.60/month (no free tier — can defer until public launch) |
| Backup strategy | RDS automated backups (7-day) + S3 versioning + rebuildable EC2 | No multi-AZ (cost); no cross-region (unnecessary); EC2 recovery via terraform apply ~15 min |
| Imagery sources | NAIP only | One source, deferred to Phase 2 |
| Satellite imagery | Dropped (Landsat, Sentinel-2) | Too coarse for parcel-level intelligence |
| MVP schedule scope | 5 weekly sources active at launch; all daily schedules are Phase 2 | All 6 MVP sources (#1,#2,#3,#4,#5,#13) are weekly; daily schedules exist in code but disabled until Phase 2 pipelines are built |
| Privacy & access control | No auth for MVP; phased approach for sensitive data | All MVP data is already public; access controls added in Phase 2 when court records and sensitive aggregated data arrive |
| Lambda credential delivery | Terraform env vars (NOT Parameter Store at runtime) | Lambda in VPC can't reach Parameter Store without NAT/$32/mo; Terraform sets encrypted env vars at deploy time |
| API route prefix | All Lambda routes under `/api/*` | CloudFront only forwards `/api/*` to API Gateway; ops health at `/api/ops/health`; tiles served from S3 via `/tiles/*` (not Lambda) |
| Meta schema ownership | App-owned DDL; Dagster sensors write; Lambda reads | Separate from Dagster's internal `dagster` database; authoritative DDL in infra plan Meta Schema DDL section |
| MVP entity resolution | Parcels + assessment only (2 sources) | Dynamically detects available staging tables; Phase 2 sources added incrementally as pipelines are built |
| Schema authority | Infra plan is single source of truth; data model doc is Phase 2/3 appendix | Data model doc reclassified; all MVP schema defined in infra plan |
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

## AWS Infrastructure

### Account Details

- **Account:** Fresh account with $100 credit
- **Free tier:** 12 months from account creation
- **Region:** `us-east-1` (closest to York County, PA; cheapest region)

### Services Used

| Service | Purpose | Free Tier Allowance |
|---|---|---|
| EC2 (t3.micro) | Dagster + scrapers | 750 hrs/month for 12 months |
| RDS (db.t3.micro) | PostgreSQL 16 + PostGIS | 750 hrs/month for 12 months + 20 GB storage |
| EBS (gp3) | EC2 instance storage (20 GB) | 30 GB for 12 months |
| S3 | Raw data archival + static site hosting | 5 GB for 12 months |
| CloudFront | CDN + HTTPS for public frontend | 1 TB transfer/month for 12 months |
| API Gateway | REST API for frontend → Lambda | 1M calls/month for 12 months |
| Lambda | FastAPI backend for public API | 1M requests + 400K GB-sec/month (permanent free tier) |
| ACM | TLS certificate for HTTPS | Free (always) |
| Systems Manager | Instance access (Session Manager) | Free |
| CloudWatch Logs | Dagster + system logs | 5 GB ingest/month + 5 GB storage (free tier) |
| CloudWatch Alarms | Infrastructure health | 10 alarms free |
| SNS | Budget alert notifications | First 1,000 email notifications free |
| AWS Budgets | Cost monitoring | First 2 budgets free |
| IAM | Roles, policies, instance profiles | Free |

---

## RDS PostgreSQL / PostGIS

### Instance Configuration

| Setting | Value |
|---|---|
| Engine | PostgreSQL 16 |
| Instance class | `db.t3.micro` (2 vCPU burstable, 1 GB RAM) |
| Storage | 20 GB gp3 (free tier covers 20 GB) |
| Multi-AZ | No (single AZ — cost savings, acceptable for solo dev) |
| Database name | `york_county_intel` |
| Port | 5432 |
| Public access | **No** (private subnet only, accessible from EC2 within same VPC) |
| Extensions required | `postgis`, `postgis_topology`, `pg_trgm` (fuzzy text matching for entity resolution) |
| Encryption | At rest (default AWS-managed key) |

### Free Tier Details

- **750 hours/month of db.t3.micro** for 12 months (enough to run 24/7 for a full year)
- **20 GB of General Purpose (gp3) storage** included
- **20 GB of backup storage** included (automated backups)
- After free tier: ~$12–15/month for db.t3.micro with 20 GB gp3

### Storage Growth Plan

Estimated dataset sizes by phase:

| Phase | Sources Loaded | Estimated Size |
|---|---|---|
| MVP (5–6 sources) | Parcels, zoning, roads, assessment, PennDOT | 1–2 GB |
| Phase 2 (15+ sources) | + deeds, permits, business entities, licenses | 3–8 GB |
| Phase 3 (20+ sources) | + full enrichment, entity resolution, historical | 8–15 GB |

20 GB is comfortable through Phase 2. If you approach the limit, RDS storage can be increased in-place with no downtime (gp3 supports online expansion). Going to 50 GB adds roughly $4/month.

### Automated Backups

| Setting | Value |
|---|---|
| Backup retention | 7 days (free tier covers 20 GB backup storage) |
| Backup window | 06:00–06:30 UTC (2:00 AM ET — after all scraper jobs finish) |
| Maintenance window | Sun 07:00–07:30 UTC (3:00 AM ET Sunday) |
| Point-in-time recovery | Enabled (continuous backup to the second within retention window) |

### Connection from EC2

The EC2 instance connects to RDS over the **private VPC network** (not the public internet). Both resources sit in the same default VPC. The connection uses the RDS endpoint hostname on port 5432.

**Security:** The RDS security group allows inbound on port 5432 **only from the EC2 security group**. No other access is permitted. This means the database is completely inaccessible from the internet.

**Credential storage:** The RDS master password is stored in AWS Systems Manager Parameter Store (SecureString) at `/york-county/rds-password`. The EC2 instance retrieves it at boot time via the IAM instance profile. The full connection string is assembled from Parameter Store values — never hardcoded or committed to git.

**Parameter Store values:**

| Parameter Path | Type | Value |
|---|---|---|
| `/york-county/rds-host` | String | RDS endpoint (output from Terraform) |
| `/york-county/rds-password` | SecureString | Master password |
| `/york-county/rds-dbname` | String | `york_county_intel` |
| `/york-county/rds-username` | String | `dagster_admin` |

### Local Development Access

To connect to RDS from your local machine (e.g., for running queries in pgAdmin or DBeaver), use Session Manager port forwarding through the EC2 instance:

```bash
# Forward local port 5433 to RDS through the EC2 instance
aws ssm start-session \
  --target <instance-id> \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters '{"host":["<rds-endpoint>"],"portNumber":["5432"],"localPortNumber":["5433"]}'

# Then connect your SQL client to:
# Host: localhost
# Port: 5433
# Database: york_county_intel
# User: dagster_admin
```

### Why RDS over Neon

| Factor | RDS | Neon |
|---|---|---|
| Free tier storage | 20 GB for 12 months | 0.5 GB |
| Free tier compute | 750 hrs/month (always-on) | 100 hrs/month (metered) |
| Post free tier cost | ~$12–15/month | $19/month (Launch) |
| Networking | Private VPC (zero latency, no transfer costs) | Public internet (latency, TLS overhead) |
| Backups | Automated + point-in-time recovery (included) | Branching (different model) |
| Managed by | AWS (single account, single Terraform state) | Separate vendor, separate dashboard |
| PostGIS support | Full (install via CREATE EXTENSION) | Full |

---

## Dagster Configuration

### Components (all on single EC2 instance)

| Component | Purpose | Resource Profile |
|---|---|---|
| `dagster-webserver` | UI + GraphQL API | ~100–150 MB RAM |
| `dagster-daemon` | Scheduler + sensor evaluation | ~100–150 MB RAM |
| Run workers | Execute pipeline code in-process | ~50–400 MB per run (varies) |

### Memory Budget (1 GB total on t3.micro)

| Consumer | Estimated Usage |
|---|---|
| OS + system processes | ~150 MB |
| Dagster webserver | ~150 MB |
| Dagster daemon | ~150 MB |
| **Available for jobs** | **~550 MB** |
| Typical requests/BS4 scraper | ~50–100 MB |
| Typical Playwright scraper | ~200–400 MB |

**Key constraint:** Only run one Playwright job at a time. Stagger all schedules so Playwright-based scrapers never overlap.

### Dagster Storage

Dagster needs a storage backend for run history, event logs, and schedule state. Two options:

1. **SQLite (default)** — stored on the EBS volume. Simplest, no additional config. Fine for a solo developer.
2. **RDS PostgreSQL** — use a separate database (`dagster`) on the same RDS instance. Better durability, no extra cost since RDS has 20 GB to spare.

**Recommendation:** Use RDS PostgreSQL. Since you're already running a 24/7 RDS instance with plenty of storage headroom, there's no reason to use SQLite. Dagster's metadata is small (a few MB), and having it in Postgres means run history survives if the EC2 EBS volume is ever rebuilt. Create a second database named `dagster` on the same RDS instance — keeps it isolated from your application data.

### Log Levels

- **Production:** `WARNING` for Dagster internals, `INFO` for pipeline code
- **Debug sessions:** Temporarily set to `DEBUG` via environment variable, revert after

### Schedules (staggered to avoid memory contention)

```
02:00  ArcGIS REST sources (parcels, zoning, roads, structures, PennDOT)
02:30  SODA API sources (PA Open Data Portal datasets)
03:00  Playwright scrapers — sequential:
         03:00  eFACTS
         03:15  CRIMEWATCH
         03:30  PALS
         03:45  Assessment portal
04:00  HTML/PDF scrapers (BS4/pdfplumber):
         04:00  YCCD Conservation District
         04:10  County Bids
         04:20  Tax Claim Bureau
         04:30  Commissioners meetings
         04:40  YCPC subdivision reports
         04:50  York City RFPs
05:00  Bulk downloads:
         05:00  PLCB+ CSV
         05:10  UJS Portal
05:30  Entity resolution / enrichment pipelines
         (only runs if upstream sources succeeded)
```

**Note:** These are starting points. Actual frequencies vary by source (daily, weekly, monthly). Dagster cron expressions will reflect the real update cadence — not every source runs every night.

---

## Terraform Project Structure

```
york-county-infra/
├── main.tf                    # Provider config, backend, module calls
├── variables.tf               # Top-level input variables
├── terraform.tfvars           # Actual values (GITIGNORED)
├── outputs.tf                 # Instance ID, connection commands, S3 bucket name
├── backend.tf                 # S3 remote state configuration
│
├── modules/
│   ├── networking/
│   │   ├── main.tf            # Security groups (EC2 + RDS), subnet group
│   │   ├── variables.tf
│   │   └── outputs.tf         # Security group IDs, default VPC/subnet IDs, subnet group name
│   │
│   ├── iam/
│   │   ├── main.tf            # Instance profile, role, policies
│   │   ├── variables.tf
│   │   └── outputs.tf         # Instance profile ARN
│   │
│   ├── database/
│   │   ├── main.tf            # RDS instance, parameter group
│   │   ├── variables.tf       # Instance class, storage, credentials
│   │   ├── outputs.tf         # RDS endpoint, port, database name
│   │   └── init.sql           # Post-provisioning initialization script
│   │
│   ├── compute/
│   │   ├── main.tf            # EC2 instance, EBS
│   │   ├── variables.tf
│   │   ├── outputs.tf         # Instance ID, SSM connect command
│   │   └── user_data.sh       # Bootstrap script
│   │
│   ├── frontend/
│   │   ├── main.tf            # S3 static site, CloudFront, ACM cert
│   │   ├── variables.tf
│   │   └── outputs.tf         # CloudFront URL, S3 bucket name
│   │
│   ├── api/
│   │   ├── main.tf            # Lambda function, API Gateway, IAM role
│   │   ├── variables.tf
│   │   └── outputs.tf         # API Gateway URL, Lambda function name
│   │
│   └── monitoring/
│       ├── main.tf            # Budgets, alarms, SNS, log groups
│       ├── variables.tf
│       └── outputs.tf         # SNS topic ARN, budget name
│
└── .gitignore                 # terraform.tfvars, .terraform/, *.tfstate*
```

### State Backend (bootstrap manually before first `terraform apply`)

```
S3 bucket:    york-county-infra-tfstate
DynamoDB:     york-county-infra-tflock  (for state locking)
Region:       us-east-1
Encryption:   AES-256 (SSE-S3)
Versioning:   Enabled
```

**Bootstrap steps** (one-time, done via AWS CLI before Terraform):
1. Create the S3 bucket for state
2. Create the DynamoDB table for locking
3. Run `terraform init` with the backend config

---

## Module: Networking

### What it creates

| Resource | Configuration |
|---|---|
| Data source: default VPC | References `aws_vpc.default` |
| Data source: default subnets | For EC2, RDS, and Lambda placement |
| Security group: `dagster-ec2-sg` | **No inbound rules** (Session Manager needs none); all outbound allowed |
| Security group: `api-lambda-sg` | **No inbound rules** (invoked by API Gateway, not network); outbound to RDS |
| Security group: `dagster-rds-sg` | Inbound PostgreSQL (5432) **from `dagster-ec2-sg` and `api-lambda-sg`** |
| RDS subnet group: `dagster-rds-subnets` | Default VPC subnets (minimum 2 AZs required by RDS) |

### Security group relationship

```
┌──────────────────┐         ┌──────────────────┐
│  dagster-ec2-sg  │         │  dagster-rds-sg   │
│                  │         │                   │
│  Inbound: NONE   │────────▶│  Inbound: 5432    │
│  Outbound: ALL   │  (ref)  │  from ec2-sg      │
│                  │         │  AND lambda-sg    │
└──────────────────┘         │  Outbound: NONE   │
                             └──────────────────┘
┌──────────────────┐                  ▲
│  api-lambda-sg   │                  │
│                  │──────────────────┘
│  Inbound: NONE   │  (ref)
│  Outbound: 5432  │
│   to rds-sg only │
└──────────────────┘
```

Both the EC2 security group and the Lambda security group are allowed to reach RDS on port 5432. Lambda's outbound is scoped to only RDS — it doesn't need general internet access since it's only querying the database.

**⚠️ VPC networking constraint:** Lambda in a VPC can reach RDS (private), but CANNOT reach AWS service endpoints (Parameter Store, CloudWatch API, etc.) without either a NAT Gateway (~$32/month) or VPC Endpoints (~$7/month each). To avoid this cost:

1. **RDS credentials:** Passed to Lambda as encrypted environment variables (set by Terraform, encrypted with default KMS key). Lambda does NOT call Parameter Store at runtime.
2. **CloudWatch Logs:** Lambda's built-in log shipping works regardless of VPC placement (handled by the Lambda control plane, not the function's network path).
3. **CloudWatch metrics for /ops/health:** Lambda does NOT call the CloudWatch API. Instead, a Dagster sensor on EC2 polls CloudWatch every 5 minutes and writes infra metrics to a `meta.infra_metrics` table in RDS. The /ops/health endpoint queries only RDS.

This means Lambda has exactly one network dependency: RDS on port 5432. No NAT Gateway, no VPC Endpoints, no extra cost.

### Why no inbound rules on EC2

Session Manager connects through the SSM agent on the instance, which initiates an **outbound** connection to the SSM service endpoint. No inbound ports need to be open — not even SSH. This is the primary security advantage over traditional SSH access.

---

## Module: IAM

### Resources

| Resource | Purpose |
|---|---|
| IAM Role: `dagster-ec2-role` | Assumed by EC2 instance |
| Instance Profile: `dagster-instance-profile` | Attaches role to EC2 |
| Managed Policy: `AmazonSSMManagedInstanceCore` | Required for Session Manager |
| Managed Policy: `CloudWatchAgentServerPolicy` | Required for memory/disk metrics |
| Inline Policy: `dagster-s3-access` | Read/write to the raw data S3 bucket only |
| Inline Policy: `dagster-ssm-params` | Read-only access to Parameter Store (for RDS credentials) |

### S3 Policy (scoped to single bucket)

```json
{
  "Effect": "Allow",
  "Action": [
    "s3:GetObject",
    "s3:PutObject",
    "s3:ListBucket"
  ],
  "Resource": [
    "arn:aws:s3:::york-county-raw",
    "arn:aws:s3:::york-county-raw/*"
  ]
}
```

### Parameter Store Policy

```json
{
  "Effect": "Allow",
  "Action": [
    "ssm:GetParameter",
    "ssm:GetParameters"
  ],
  "Resource": "arn:aws:ssm:us-east-1:*:parameter/york-county/*"
}
```

---

## Module: Compute

### EC2 Instance

| Setting | Value |
|---|---|
| AMI | Amazon Linux 2023 (latest, `al2023-ami-kernel-default-x86_64`) |
| Instance type | `t3.micro` (2 vCPU burstable, 1 GB RAM) |
| Subnet | Default VPC, `us-east-1a` (or any default subnet) |
| Security group | `dagster-ec2-sg` (no inbound — see Module: Networking) |
| IAM instance profile | `dagster-instance-profile` |
| EBS root volume | 20 GB gp3 (encrypted, `gp3` baseline: 3000 IOPS, 125 MB/s) |
| Monitoring | Detailed monitoring disabled (free tier basic is sufficient) |
| User data | Bootstrap script (see below) |
| Tags | `Name=york-county-dagster`, `Project=york-county-intel`, `Environment=production` |

### Elastic IP

**Not using.** Session Manager doesn't need a static IP for access, and no data source requires IP whitelisting. The instance gets a dynamic public IP from the default VPC that works fine for outbound scraping. Add an Elastic IP later only if a data source requires a static IP (note: Elastic IPs now cost $3.65/month even on stopped instances as of Feb 2024).

### Key Pair

**Not needed.** Session Manager replaces SSH entirely. No key pair to generate, store, rotate, or lose.

---

## Module: Monitoring

### AWS Budgets

| Budget | Type | Threshold | Action |
|---|---|---|---|
| `york-county-monthly` | Cost | Actual spend | Email alert at $10, $25, $50, $75 |
| (same budget) | Cost | Forecasted spend | Email alert if forecast exceeds $50 |

**Alert recipient:** jarod.daws@gmail.com (via SNS)

### CloudWatch Log Groups

| Log Group | Retention | Purpose |
|---|---|---|
| `/york-county/dagster` | 7 days | Dagster webserver + daemon + run logs |
| `/york-county/system` | 7 days | System logs (syslog, cloud-init) |

### CloudWatch Alarms

| Alarm | Metric | Threshold | Period | Action |
|---|---|---|---|---|
| `high-cpu` | CPUUtilization | > 80% for 15 min | 5 min | SNS notification |
| `high-memory` | mem_used_percent (CW Agent) | > 85% for 10 min | 5 min | SNS notification |
| `high-disk` | disk_used_percent (CW Agent) | > 80% | 5 min | SNS notification |
| `instance-status` | StatusCheckFailed | ≥ 1 | 5 min | SNS notification |
| `dagster-health` | Custom (process check) | 0 (process not running) | 5 min | SNS notification |

**Note:** Memory and disk metrics require the CloudWatch Agent to be installed on the instance. EC2 basic monitoring only provides CPU, network, and disk I/O — not memory or disk usage percentage. The bootstrap script installs and configures the agent.

### SNS Topic

| Setting | Value |
|---|---|
| Topic name | `york-county-alerts` |
| Protocol | Email |
| Endpoint | jarod.daws@gmail.com |

---

## Module: Database

### What it creates

| Resource | Configuration |
|---|---|
| RDS instance: `york-county-db` | db.t3.micro, PostgreSQL 16, 20 GB gp3 |
| DB subnet group: `dagster-rds-subnets` | Default VPC subnets (min 2 AZs) |
| Parameter group: `york-county-pg16` | Custom parameter group for PostgreSQL 16 tuning |
| (Security group created in networking module) | `dagster-rds-sg` |

### Parameter Group Customizations

| Parameter | Value | Rationale |
|---|---|---|
| `shared_preload_libraries` | `pg_stat_statements` | Query performance monitoring |
| `log_min_duration_statement` | `1000` (ms) | Log slow queries > 1 second |
| `max_connections` | `50` | Sufficient for Dagster + scrapers; reduces memory overhead |
| `work_mem` | `4MB` | Conservative for 1 GB instance |
| `maintenance_work_mem` | `64MB` | For VACUUM, index builds |
| `effective_cache_size` | `512MB` | ~50% of instance memory |

### Database Initialization (post-Terraform, one-time)

After `terraform apply` creates the RDS instance, connect via Session Manager port forwarding and run:

```sql
-- Connect to york_county_intel database
-- Enable spatial extensions
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Create Dagster's SEPARATE database (isolates internal metadata from application data)
-- Dagster stores run history, event logs, and schedule state here.
-- This is NOT queried by the application or API — it's Dagster-internal only.
CREATE DATABASE dagster;

-- Create application schemas (all in york_county_intel database)
CREATE SCHEMA IF NOT EXISTS staging;   -- Cleaned, normalized, change-tracked data (SCD Type 2)
CREATE SCHEMA IF NOT EXISTS meta;      -- Application metadata: infra metrics, pipeline status summaries, data quality logs
```

### Meta Schema DDL

The `meta` schema stores application-level summaries that the Lambda API can query. These tables are written by Dagster sensors running on EC2 (which has internet access) and read by the Lambda API (which only has RDS access). This is the bridge that lets the `/api/ops/health` endpoint show pipeline and infrastructure status without Lambda needing to call CloudWatch or Dagster APIs.

```sql
-- meta.pipeline_status: Written by a Dagster sensor that summarizes run history.
-- One row per source asset, updated after each run completes.
CREATE TABLE meta.pipeline_status (
    source_name         TEXT PRIMARY KEY,       -- Dagster asset key, e.g. 'parcels_arcgis'
    schedule_type       TEXT NOT NULL
                        CHECK (schedule_type IN ('daily', 'weekly', 'monthly', 'on_demand')),
    status              TEXT NOT NULL
                        CHECK (status IN ('SUCCESS', 'FAILURE', 'IN_PROGRESS')),
    last_run_at         TIMESTAMPTZ,
    duration_seconds    INTEGER
                        CHECK (duration_seconds >= 0),
    record_count        INTEGER
                        CHECK (record_count >= 0),
    prev_record_count   INTEGER
                        CHECK (prev_record_count >= 0),
    error_message       TEXT,                   -- NULL on success; error text on failure
    next_scheduled_run  TIMESTAMPTZ,            -- Computed from cron expression
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- meta.infra_metrics: Written by the infra_metrics_sensor every 5 minutes.
-- Stores a JSON blob of EC2/RDS CloudWatch metrics so Lambda can read them from RDS
-- instead of calling the CloudWatch API (which it can't reach from a VPC).
CREATE TABLE meta.infra_metrics (
    id                  SERIAL PRIMARY KEY,
    checked_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metrics             JSONB NOT NULL          -- {"ec2_cpu_pct": 12.3, "rds_free_storage_gb": 15.8, "rds_connections": 3}
);

-- Prune old metrics (sensor deletes rows > 24 hours old on each write)
CREATE INDEX idx_infra_metrics_checked ON meta.infra_metrics (checked_at);

-- meta.data_quality_checks: Written by Dagster asset checks.
-- Records pass/fail results for data quality assertions (record count, schema, freshness).
CREATE TABLE meta.data_quality_checks (
    id                  SERIAL PRIMARY KEY,
    source_name         TEXT NOT NULL,
    check_name          TEXT NOT NULL
                        CHECK (check_name IN ('record_count_nonzero', 'schema_valid', 'freshness_ok', 'row_count_delta')),
    passed              BOOLEAN NOT NULL,
    details             TEXT,                   -- Failure explanation or stats
    checked_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_dq_checks_source ON meta.data_quality_checks (source_name, checked_at DESC);
```

> **CHECK constraint pattern for staging tables:** Staging tables that contain type or status columns (e.g., `staging.assessment_properties.property_class`, future `staging.permits.permit_type`) should also use CHECK constraints to enforce known value sets. Add them at table creation time when the valid values are known from the source data dictionary. For sources where the value set may change upstream, prefer a `meta.data_quality_checks` assertion instead of a hard CHECK — that way bad data gets flagged rather than silently rejected by the database.

**Dagster sensor that writes `meta.pipeline_status`:**

```python
# pipelines/sensors/pipeline_status.py
from dagster import sensor, DagsterInstance

@sensor(minimum_interval_seconds=60)
def pipeline_status_sensor(context):
    """Summarize Dagster run history into meta.pipeline_status for the API."""
    instance = DagsterInstance.get()
    conn = get_connection()  # york_county_intel database

    # Get latest run for each asset
    for asset_key in get_all_source_asset_keys():
        records = instance.get_latest_materialization_events([asset_key])
        event = records.get(asset_key)
        if not event:
            continue

        run = instance.get_run_by_id(event.run_id)
        conn.execute("""
            INSERT INTO meta.pipeline_status
                (source_name, schedule_type, status, last_run_at, duration_seconds,
                 record_count, prev_record_count, error_message, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (source_name) DO UPDATE SET
                status = EXCLUDED.status,
                last_run_at = EXCLUDED.last_run_at,
                duration_seconds = EXCLUDED.duration_seconds,
                record_count = EXCLUDED.record_count,
                prev_record_count = meta.pipeline_status.record_count,
                error_message = EXCLUDED.error_message,
                updated_at = NOW()
        """, [asset_key.path[-1], get_schedule_type(asset_key), ...])
```

### Schema Strategy

**Raw data goes to S3, not RDS.** Every pipeline run dumps its unmodified response to `s3://york-county-raw/<source>/<date>/`. This is the audit trail and replay source. No `raw` schema exists in RDS.

| Schema | Purpose | Example Tables |
|---|---|---|
| `staging` | Cleaned, normalized, change-tracked data (SCD Type 2). This is where all source data lives after parsing. | `staging.parcels`, `staging.assessment_properties`, `staging.flood_zones`, `staging.crimewatch_incidents` |
| `public` | Entity-resolved output and cross-source views | `public.owners`, `public.owner_source_links`, `public.properties` (view joining staging.parcels + staging.assessment_properties) |
| `meta` | Application metadata — NOT Dagster internals (those are in the separate `dagster` database) | `meta.infra_metrics`, `meta.pipeline_status`, `meta.data_quality_checks` |

**Note:** `public.properties` is a **PostgreSQL view**, not a table. It joins `staging.parcels` (geometry, ownership, sale history) with `staging.assessment_properties` (detailed assessment data, permits, delinquent taxes) on the canonical parcel identifier (PIDN). This avoids data duplication while providing a unified query target for the API.

```sql
-- public.properties is a VIEW, not a table
CREATE VIEW public.properties AS
SELECT
    p.pidn,
    p.geom,
    p.owner_full,
    p.propadr,
    p.aprtotal,
    p.saledt,
    p.price,
    p.municipality,
    p.school_dis,
    p.acres,
    p.class,
    a.permits,
    a.delinquent_taxes,
    a.value_history,
    p.valid_from,
    p.valid_to
FROM staging.parcels p
LEFT JOIN staging.assessment_properties a
    ON p.pidn = a.pidn
    AND a.valid_to IS NULL  -- Current assessment records only (SCD Type 2)
WHERE p.valid_to IS NULL;   -- Current parcel records only (SCD Type 2)
```

**Dagster metadata separation:** Dagster's internal database (`dagster` on the same RDS instance) stores run history, event logs, and schedule state. The `meta` schema in `york_county_intel` stores application-level summaries that the API can query — specifically, a Dagster sensor writes summarized pipeline status and infra metrics to `meta` tables. This keeps the API decoupled from Dagster's internal schema (which can change between Dagster versions).

### Identifier Strategy

**The canonical parcel identifier is PIDN** (Parcel ID Number), a 13-character string from the GIS data (e.g., `4300006006500`). This is the primary key for `staging.parcels` and the join key across all source tables.

The assessment database uses a different identifier — **PARID**, an 18-digit string (e.g., `46000060065000000`). PARID encodes the same district/block/map/parcel components as PIDN but in a different format with zero-padding.

**Crosswalk:** The PIDN and PARID contain the same underlying components:

```
PIDN format:    DD-BBB-MM-PPPPPP      (13 chars, from GIS DISTRICT+BLOCK+MAP+PARCEL fields)
PARID format:   DD000BBB0MM00PPPPPP   (18 digits, zero-padded, from Assessment portal)

Example:
  GIS:        PIDN = "4300006006500"
              DISTRICT=43, BLOCK=000, MAP=06, PARCEL=006500

  Assessment: PARID = "43000060065000000"
```

**Conversion function (used by the assessment pipeline on ingest):**

```sql
CREATE OR REPLACE FUNCTION staging.parid_to_pidn(parid TEXT) RETURNS TEXT AS $$
    -- Strip zero-padding to reconstruct PIDN from PARID
    SELECT CONCAT(
        SUBSTRING(parid FROM 1 FOR 2),     -- District (2 digits)
        SUBSTRING(parid FROM 4 FOR 3),     -- Block (3 digits, skip zero pad)
        SUBSTRING(parid FROM 8 FOR 2),     -- Map (2 digits, skip zero pad)
        SUBSTRING(parid FROM 11 FOR 6)     -- Parcel (6 digits)
    );
$$ LANGUAGE sql IMMUTABLE;
```

**All tables use PIDN as the join key.** The assessment pipeline converts PARID → PIDN on ingest. No table stores PARID as a primary key.

**Entity identifiers:**

| Entity | Primary Key | Type | Rationale |
|---|---|---|---|
| Parcels | `pidn` | TEXT(13) | Natural key from GIS; stable across refreshes |
| Owners (resolved entities) | `owner_id` | SERIAL | Synthetic key; entities are created by resolution, not by any source |
| Source links | `link_id` | SERIAL | Synthetic key for the join table |
| All staging tables | Source-specific natural key + `valid_from` | Varies | SCD Type 2 requires composite key |

**Why SERIAL (not UUID) for owners:** Owner entities are created and consumed entirely within this platform. They're never shared with external systems. SERIAL is simpler, uses less storage, and is faster for joins. If CountyIQ ever needs to federate owner data across county instances, UUIDs can be added as an additional column without changing the primary key.

---

## Schema Migrations (Alembic)

### What Alembic does

Alembic is a database migration tool for Python. Every time you need to change the database structure — add a table, add a column, rename something, change a data type — you create a migration file. Each file has two functions: `upgrade()` (apply the change) and `downgrade()` (reverse it). Alembic tracks which migrations have been applied and runs them in order.

### Why Alembic over raw SQL files

- **Reversible:** Every migration can be rolled back with `alembic downgrade -1`. If a migration breaks something, undo it instantly.
- **Automatic tracking:** Alembic maintains a `alembic_version` table in the database that records which migration was last applied. No manual bookkeeping.
- **LLM-friendly:** The structured `upgrade()`/`downgrade()` format gives LLMs a clear template to work within. You describe the change in English, the LLM generates the migration file.
- **Integrates with Dagster:** Migrations can be run as part of the Dagster pipeline startup or as a separate pre-deploy step.

### Project structure

```
york-county-pipelines/
├── alembic/
│   ├── alembic.ini              # Alembic configuration
│   ├── env.py                   # Migration environment (DB connection setup)
│   ├── script.py.mako           # Template for new migration files
│   └── versions/                # Migration files live here
│       ├── 001_initial_schema.py
│       ├── 002_add_parcels_table.py
│       ├── 003_add_assessment_table.py
│       └── ...
├── docker-compose.yml           # Local Postgres for testing
└── ...
```

### How a migration file looks

```python
"""Add permit_status column to permits table

Revision ID: a1b2c3d4e5f6
Revises: 9z8y7x6w5v4u
Create Date: 2026-04-15 14:30:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'a1b2c3d4e5f6'
down_revision = '9z8y7x6w5v4u'

def upgrade():
    op.add_column('permits',
        sa.Column('permit_status', sa.String(50), nullable=True),
        schema='public'
    )

def downgrade():
    op.drop_column('permits', 'permit_status', schema='public')
```

You don't need to write this yourself. You describe what you want ("add a permit_status column to the permits table") and the LLM generates the file. You review it — even without deep SQL knowledge you can see it's adding a column called `permit_status` to the `permits` table — and then run it.

### Common Alembic commands

| Command | What it does |
|---|---|
| `alembic upgrade head` | Apply all pending migrations (bring database up to date) |
| `alembic downgrade -1` | Undo the last migration |
| `alembic history` | Show all migrations and which have been applied |
| `alembic current` | Show which migration the database is currently at |
| `alembic revision -m "description"` | Create a new empty migration file |

### Testing migrations locally with Docker Postgres

Since RDS doesn't have a "branching" feature like Neon, you test migrations on a throwaway local Postgres database before applying them to production. This is the equivalent of Neon's branching — you get a fresh copy of the schema, test your migration, and throw it away if it breaks.

**`docker-compose.yml` (in your project root):**

```yaml
services:
  postgres-test:
    image: postgis/postgis:16-3.4
    environment:
      POSTGRES_DB: york_county_intel
      POSTGRES_USER: dagster_admin
      POSTGRES_PASSWORD: localtest
    ports:
      - "5433:5432"
    volumes:
      - pgdata-test:/var/lib/postgresql/data

volumes:
  pgdata-test:
```

This spins up a PostGIS-enabled Postgres 16 instance on your machine — identical to RDS in every way that matters for migrations.

### Migration testing workflow

Here's what the process looks like end-to-end when you need to make a schema change:

**Step 1: Start local Postgres**
```bash
docker compose up -d postgres-test
```

**Step 2: Bring local database up to current state**
```bash
# Point Alembic at the local database
export DATABASE_URL="postgresql://dagster_admin:localtest@localhost:5433/york_county_intel"
alembic upgrade head
```

**Step 3: Create and test the new migration**
```bash
# Generate a new migration file (or have an LLM write one)
alembic revision -m "add permit_status column"

# Edit the generated file (or paste in LLM-generated code)
# Then apply it to the local database
alembic upgrade head

# Verify it worked
psql -h localhost -p 5433 -U dagster_admin -d york_county_intel \
  -c "\d public.permits"

# Test the rollback too
alembic downgrade -1

# Re-apply if rollback worked cleanly
alembic upgrade head
```

**Step 4: Apply to production (RDS)**
```bash
# Point Alembic at production (via Session Manager port forward)
# In terminal 1:
aws ssm start-session \
  --target <instance-id> \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters '{"host":["<rds-endpoint>"],"portNumber":["5432"],"localPortNumber":["5434"]}'

# In terminal 2:
export DATABASE_URL="postgresql://dagster_admin:<password>@localhost:5434/york_county_intel"
alembic upgrade head
```

**Step 5: Clean up local test database**
```bash
docker compose down -v    # -v removes the volume (fresh start next time)
```

### Alembic environment configuration (`env.py`)

The `env.py` file reads the database connection from an environment variable, so the same Alembic configuration works against both local Docker Postgres and production RDS — you just change the `DATABASE_URL`:

| Environment | DATABASE_URL |
|---|---|
| Local testing | `postgresql://dagster_admin:localtest@localhost:5433/york_county_intel` |
| Production (via port forward) | `postgresql://dagster_admin:<password>@localhost:5434/york_county_intel` |
| On EC2 (direct) | `postgresql://dagster_admin:<password>@<rds-endpoint>:5432/york_county_intel` |

### Migration naming convention

Migrations are auto-numbered by Alembic using revision IDs (hex hashes). For readability, always include a descriptive message:

```
001_initial_schema.py              # Base tables, extensions, schemas
002_add_parcels_table.py           # Parcel polygons + attributes
003_add_assessment_table.py        # Assessment/tax data
004_add_owners_table.py            # Owner entities from deeds
005_add_spatial_indexes.py         # GiST indexes on geometry columns
...
```

### Integration with deployment

When you deploy new pipeline code to the EC2 instance, the deployment process should include:

```bash
# After pulling new code
cd /opt/york-county/pipelines
git pull origin main

# Run any pending migrations
alembic upgrade head

# Restart Dagster
sudo systemctl restart dagster-webserver
sudo systemctl restart dagster-daemon
```

This ensures the database schema is always in sync with the pipeline code. If a pipeline expects a new column, the migration that adds that column runs before the pipeline does.

---

## Pipeline Code Structure (Dagster)

### Dagster concepts in plain English

| Concept | What it is | Your example |
|---|---|---|
| **Asset** | A thing that exists (a database table, a file). You write a Python function that produces it, and Dagster tracks whether it's fresh or stale. | The `parcels` table, the `assessment` table |
| **Resource** | A shared connection that assets use. Configured once, shared everywhere. | Your RDS database connection, your S3 bucket |
| **Job** | A group of assets to build together. | "Build all ArcGIS source assets" |
| **Schedule** | A cron timer that triggers a job. | "Run the ArcGIS job every Monday at 2am" |
| **Sensor** | A trigger that watches for a condition, then kicks off a job. Optional — schedules work fine alone. | "When parcels_raw finishes, start the enrichment job" |
| **`definitions.py`** | The single entry point file that tells Dagster about all your assets, jobs, schedules, and resources. | See below |

### How assets relate to each other

```
ArcGIS REST API                 Playwright Scrapers           Bulk Downloads
─────────────                   ────────────────────          ──────────────
parcels_raw ─┐                  efacts_raw ───┐              plcb_raw ─────┐
zoning_raw ──┤                  crimewatch_raw┤              pa_open_raw ──┤
roads_raw ───┤  ┌──────────┐   pals_raw ─────┤              ujs_raw ──────┤
penndot_raw ─┤  │ staging  │   assessment_raw ┤                            │
             ├─▶│ (clean)  │                  │  ┌───────────────┐         │
             │  └────┬─────┘   ┌──────────┐   ├─▶│   staging     │         │
             │       │         │ staging  │   │  │   (clean)     │         │
             │       ▼         │ (clean)  │◀──┘  └───────┬───────┘         │
             │  ┌──────────┐   └────┬─────┘              │                 │
             │  │ public   │        │                     ▼                 │
             └─▶│ (final)  │        │         ┌───────────────────┐        │
                └────┬─────┘        └────────▶│   enrichment      │◀───────┘
                     │                        │   (entity res,    │
                     └───────────────────────▶│    joins, links)  │
                                              └───────────────────┘
```

Each box is one or more Dagster assets. Arrows show dependencies. Dagster sees this graph and knows the execution order automatically. If `parcels_raw` fails, nothing downstream of it runs.

### Monorepo layout

Since infrastructure (Terraform) and pipeline code (Dagster) live in the same repo:

```
countyiq/
│
├── infra/                              # Terraform (already designed)
│   ├── main.tf
│   ├── variables.tf
│   ├── terraform.tfvars                # GITIGNORED
│   ├── outputs.tf
│   ├── backend.tf
│   └── modules/
│       ├── networking/
│       ├── iam/
│       ├── database/
│       ├── compute/
│       └── monitoring/
│
├── pipelines/                          # Dagster project
│   ├── pyproject.toml                  # Python dependencies
│   ├── setup.py                        # Package installation
│   ├── docker-compose.yml              # Local Postgres for testing
│   │
│   ├── alembic/                        # Schema migrations
│   │   ├── alembic.ini
│   │   ├── env.py
│   │   └── versions/
│   │
│   ├── york_county/                    # Main Python package
│   │   ├── __init__.py
│   │   │
│   │   ├── definitions.py              # Dagster entry point
│   │   │
│   │   ├── resources/                  # Shared connections
│   │   │   ├── __init__.py
│   │   │   ├── database.py             # RDS connection (psycopg2)
│   │   │   └── storage.py              # S3 client for raw archival
│   │   │
│   │   ├── assets/                     # Data assets by source type
│   │   │   ├── __init__.py
│   │   │   │
│   │   │   ├── arcgis/                 # ArcGIS REST API sources
│   │   │   │   ├── __init__.py
│   │   │   │   ├── parcels.py
│   │   │   │   ├── zoning.py
│   │   │   │   ├── roads.py
│   │   │   │   ├── structures.py
│   │   │   │   └── penndot.py
│   │   │   │
│   │   │   ├── scrapers/               # Playwright + BeautifulSoup
│   │   │   │   ├── __init__.py
│   │   │   │   ├── efacts.py           # PA DEP eFACTS (Playwright)
│   │   │   │   ├── crimewatch.py       # CRIMEWATCH (Playwright)
│   │   │   │   ├── pals.py             # Professional licenses (Playwright)
│   │   │   │   ├── assessment.py       # Assessment portal (Playwright)
│   │   │   │   ├── county_bids.py      # County bids (BeautifulSoup)
│   │   │   │   ├── tax_claim.py        # Tax Claim Bureau (BeautifulSoup)
│   │   │   │   ├── commissioners.py    # Commissioners meetings (BS4)
│   │   │   │   └── york_city_rfp.py    # York City RFPs (BeautifulSoup)
│   │   │   │
│   │   │   ├── bulk/                   # Bulk download / API sources
│   │   │   │   ├── __init__.py
│   │   │   │   ├── plcb.py             # PLCB+ liquor licenses CSV
│   │   │   │   ├── pa_open_data.py     # SODA API datasets
│   │   │   │   └── ujs.py             # UJS Portal
│   │   │   │
│   │   │   ├── pdf/                    # PDF extraction sources
│   │   │   │   ├── __init__.py
│   │   │   │   ├── conservation.py     # YCCD plan review list
│   │   │   │   └── subdivision.py      # YCPC subdivision reports
│   │   │   │
│   │   │   └── enrichment/             # Derived / joined assets
│   │   │       ├── __init__.py
│   │   │       ├── owners.py           # Entity resolution across sources
│   │   │       └── parcel_enriched.py  # Parcel + assessment + zoning
│   │   │
│   │   ├── jobs/                       # Job definitions
│   │   │   ├── __init__.py
│   │   │   ├── arcgis_refresh.py       # All ArcGIS source assets
│   │   │   ├── scraper_refresh.py      # All scraper assets
│   │   │   ├── bulk_refresh.py         # All bulk download assets
│   │   │   └── enrichment.py           # Downstream enrichment assets
│   │   │
│   │   ├── schedules/                  # Schedule definitions
│   │   │   ├── __init__.py
│   │   │   └── daily.py                # Staggered cron schedules
│   │   │
│   │   └── lib/                        # Shared utilities
│   │       ├── __init__.py
│   │       ├── arcgis_client.py        # Reusable ArcGIS REST query + pagination
│   │       ├── playwright_utils.py     # Browser launch, anti-detection, screenshot
│   │       ├── s3_archive.py           # Archive raw responses to S3
│   │       └── scrape_utils.py         # Common HTML parsing helpers
│   │
│   └── tests/                          # Pipeline tests
│       ├── __init__.py
│       ├── test_arcgis_client.py
│       └── test_scrape_utils.py
│
├── frontend/                           # React + MapLibre + Deck.gl
│   ├── package.json
│   ├── vite.config.ts                  # Vite build tool
│   ├── tsconfig.json
│   ├── public/
│   │   └── favicon.ico
│   └── src/
│       ├── main.tsx                    # React entry point
│       ├── App.tsx                     # Root component
│       ├── components/
│       │   ├── Map.tsx                 # MapLibre + Deck.gl map
│       │   ├── ParcelPanel.tsx         # Side panel for parcel details
│       │   ├── SearchBar.tsx           # Owner/address/parcel search
│       │   ├── LayerControls.tsx       # Toggle map layers
│       │   └── EntityProfile.tsx       # Full entity view (owner details)
│       ├── api/
│       │   └── client.ts              # API client (fetch wrapper)
│       ├── layers/
│       │   ├── parcels.ts             # Deck.gl parcel polygon layer
│       │   ├── zoning.ts              # Zoning overlay layer
│       │   └── points.ts              # Points layer (businesses, permits)
│       ├── hooks/
│       │   ├── useMapView.ts          # Map state management
│       │   └── useSearch.ts           # Search state + API calls
│       └── types/
│           └── index.ts               # TypeScript interfaces
│
├── api/                                # FastAPI Lambda backend
│   ├── requirements.txt
│   ├── handler.py                      # Lambda entry point (Mangum adapter)
│   ├── main.py                         # FastAPI app definition
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── parcels.py                 # /api/parcels endpoints
│   │   ├── owners.py                  # /api/owners endpoints
│   │   ├── search.py                  # /api/search endpoints
│   │   └── tiles.py                   # /api/tiles vector tile endpoints
│   ├── lib/
│   │   ├── database.py                # RDS connection pool
│   │   ├── cloudwatch.py              # CloudWatch metrics helper
│   │   └── schemas.py                 # Pydantic response models
│   └── tests/
│       └── test_routes.py
│
├── .gitignore
├── .env.example                        # Template for environment variables
└── README.md
```

### What `definitions.py` does

This is the single file Dagster reads on startup. It registers all assets, jobs, schedules, and resources. Think of it as the "table of contents" for your entire data platform:

```python
from dagster import Definitions, EnvVar

from york_county.resources.database import database_resource
from york_county.resources.storage import s3_resource
from york_county.assets.arcgis import parcels, zoning, roads, structures, penndot
from york_county.assets.scrapers import (
    efacts, crimewatch, pals, assessment,
    county_bids, tax_claim, commissioners, york_city_rfp
)
from york_county.assets.bulk import plcb, pa_open_data, ujs
from york_county.assets.pdf import conservation, subdivision
from york_county.assets.enrichment import owners, parcel_enriched
from york_county.jobs import (
    arcgis_refresh, scraper_refresh, bulk_refresh, enrichment
)
from york_county.schedules.daily import all_schedules

defs = Definitions(
    assets=[
        # ArcGIS REST sources
        *parcels.assets,
        *zoning.assets,
        *roads.assets,
        *structures.assets,
        *penndot.assets,
        # Scrapers
        *efacts.assets,
        *crimewatch.assets,
        *pals.assets,
        *assessment.assets,
        *county_bids.assets,
        *tax_claim.assets,
        *commissioners.assets,
        *york_city_rfp.assets,
        # Bulk downloads
        *plcb.assets,
        *pa_open_data.assets,
        *ujs.assets,
        # PDF extraction
        *conservation.assets,
        *subdivision.assets,
        # Enrichment
        *owners.assets,
        *parcel_enriched.assets,
    ],
    jobs=[
        arcgis_refresh.job,
        scraper_refresh.job,
        bulk_refresh.job,
        enrichment.job,
    ],
    schedules=all_schedules,
    resources={
        "database": database_resource,
        "s3": s3_resource,
    },
)
```

When Dagster starts, it loads this file and knows about every asset, every dependency, every schedule. The Dagster UI then renders the full graph and lets you monitor everything.

### What a typical asset file looks like

**Simple example — ArcGIS parcels (HTTP/JSON, no browser needed):**

```python
# york_county/assets/arcgis/parcels.py

from dagster import asset, AssetExecutionContext

@asset(
    group_name="arcgis",
    description="Raw parcel polygons from YCPC ArcGIS REST API",
)
def parcels_raw(context: AssetExecutionContext, database, s3):
    """Fetch all York County parcels and load into raw.parcels"""

    # 1. Query ArcGIS REST API (uses shared lib for pagination)
    from york_county.lib.arcgis_client import query_all_features
    features = query_all_features(
        url="https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/...",
        where="1=1",  # all records
    )
    context.log.info(f"Fetched {len(features)} parcels")

    # 2. Archive raw response to S3
    s3.archive("arcgis/parcels", features)

    # 3. Load into raw.parcels table
    database.load_raw("raw.parcels", features)

    return len(features)  # metadata visible in Dagster UI


@asset(
    group_name="arcgis",
    deps=["parcels_raw"],
    description="Cleaned parcel data in public.parcels",
)
def parcels(context: AssetExecutionContext, database):
    """Clean raw parcels → public.parcels"""

    # Read from raw, clean, write to public
    count = database.execute("""
        INSERT INTO public.parcels (parcel_id, geometry, ...)
        SELECT parcel_id, ST_Transform(geom, 4326), ...
        FROM raw.parcels
        WHERE parcel_id IS NOT NULL
        ON CONFLICT (parcel_id) DO UPDATE SET ...
    """)
    context.log.info(f"Upserted {count} parcels to public.parcels")


# Export for definitions.py
assets = [parcels_raw, parcels]
```

**Key things to notice:**
- `parcels_raw` has no dependencies — it just fetches from the API
- `parcels` depends on `parcels_raw` via `deps=["parcels_raw"]`
- Both use `database` and `s3` — these are the shared resources injected by Dagster
- The `context.log` calls show up in the Dagster UI so you can see what happened
- The `assets` list at the bottom is what `definitions.py` imports

### What the shared `lib/` utilities do

| File | Purpose | Used by |
|---|---|---|
| `arcgis_client.py` | Handles ArcGIS REST API pagination (queries return max 1000–2000 records at a time, so it loops until all records are fetched), coordinate system transforms, and GeoJSON conversion | All `arcgis/` assets |
| `playwright_utils.py` | Launches Playwright Chromium with consistent settings (headless, timeout, viewport), handles anti-bot detection basics, captures screenshots for debugging | All `scrapers/` assets that need Playwright |
| `s3_archive.py` | Uploads raw API responses / HTML / PDFs to S3 with timestamped keys for audit trail and debugging | All assets (archive before processing) |
| `scrape_utils.py` | Common BeautifulSoup helpers — extract tables from HTML, clean whitespace, normalize dates | HTML scraper assets |

### How jobs and schedules connect

A **job** selects which assets to build. A **schedule** triggers that job on a cron timer:

```python
# york_county/jobs/arcgis_refresh.py

from dagster import define_asset_job, AssetSelection

job = define_asset_job(
    name="arcgis_refresh",
    selection=AssetSelection.groups("arcgis"),  # all assets in the "arcgis" group
    description="Refresh all ArcGIS REST API data sources",
)
```

```python
# york_county/schedules/daily.py

from dagster import ScheduleDefinition
from york_county.jobs.arcgis_refresh import job as arcgis_job
from york_county.jobs.scraper_refresh import job as scraper_job
from york_county.jobs.bulk_refresh import job as bulk_job
from york_county.jobs.enrichment import job as enrichment_job

all_schedules = [
    ScheduleDefinition(
        job=arcgis_job,
        cron_schedule="0 2 * * 1",      # Every Monday at 2:00 AM
        name="weekly_arcgis",
    ),
    ScheduleDefinition(
        job=scraper_job,
        cron_schedule="0 3 * * 1",      # Every Monday at 3:00 AM
        name="weekly_scrapers",
    ),
    ScheduleDefinition(
        job=bulk_job,
        cron_schedule="0 5 1 * *",      # First of each month at 5:00 AM
        name="monthly_bulk",
    ),
    ScheduleDefinition(
        job=enrichment_job,
        cron_schedule="0 6 * * 2",      # Every Tuesday at 6:00 AM (after Monday sources refresh)
        name="weekly_enrichment",
    ),
]
```

**Why enrichment runs on Tuesday:** The ArcGIS and scraper jobs run Monday overnight. By Tuesday morning, all raw + cleaned data is fresh. The enrichment job then runs against up-to-date tables. This is the kind of dependency ordering Dagster makes easy.

### Python dependencies (`pyproject.toml`)

```toml
[project]
name = "york-county-pipelines"
version = "0.1.0"
requires-python = ">=3.11"

dependencies = [
    # Dagster core
    "dagster",
    "dagster-webserver",
    "dagster-postgres",          # For Dagster storage on RDS

    # Database
    "psycopg2-binary",
    "sqlalchemy>=2.0",
    "alembic",
    "geoalchemy2",               # PostGIS integration with SQLAlchemy

    # Scraping
    "requests",
    "beautifulsoup4",
    "lxml",                      # Fast HTML parser for BS4
    "playwright",
    "pdfplumber",

    # Data processing
    "geojson",
    "shapely",                   # Geometry manipulation
    "pyproj",                    # Coordinate system transforms

    # AWS
    "boto3",                     # S3 + Parameter Store access

    # Utilities
    "python-dotenv",             # .env file loading for local dev
]

[project.optional-dependencies]
dev = [
    "pytest",
    "ruff",                      # Linter
]
```

### Local development workflow

To work on pipelines on your own machine:

```bash
# 1. Clone the repo
git clone <repo-url>
cd countyiq/pipelines

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -e ".[dev]"
playwright install chromium

# 4. Start local Postgres (for testing)
docker compose up -d postgres-test

# 5. Run migrations against local DB
export DATABASE_URL="postgresql://dagster_admin:localtest@localhost:5433/york_county_intel"
alembic upgrade head

# 6. Start Dagster UI (local dev mode)
dagster dev -m york_county.definitions

# 7. Open http://localhost:3000 — full Dagster UI with all your assets
#    You can trigger individual assets, view the dependency graph, etc.
```

This gives you the full Dagster experience locally — same UI, same asset graph, same everything — just pointed at a local database instead of RDS. When you're happy with changes, commit, push, deploy to EC2.

---

## Entity Resolution

### What it does

Entity resolution answers the question: "Are these two records from different sources talking about the same person, business, or property?" Your platform pulls owner names from assessment records, deed transfers, business filings, professional licenses, and liquor licenses — all with slightly different formatting, abbreviations, and errors. Entity resolution links them together into a single canonical entity.

### Approach: Deterministic matching in PostgreSQL

For the MVP, all matching logic runs as SQL inside the `enrichment/owners.py` Dagster asset. No external tools, no Spark, no ML models. Just PostgreSQL functions using the `pg_trgm` extension (already planned for installation) and well-designed normalization logic.

The approach has three stages:

**Stage 1: Normalize.** Before comparing anything, clean and standardize all names and addresses into a consistent format.

Name normalization:
- Uppercase everything
- Strip suffixes: JR, SR, II, III, IV
- Strip entity types: LLC, INC, CORP, LP, LTD, CO, TRUST, ESTATE
- Strip punctuation and extra whitespace
- Handle common abbreviations: WM → WILLIAM, ROBT → ROBERT, CHAS → CHARLES
- Result: "John A. Smith Jr." → "JOHN A SMITH"
- Result: "York Properties, LLC" → "YORK PROPERTIES"

Address normalization:
- Uppercase everything
- Standardize street types: STREET/ST → ST, AVENUE/AVE → AVE, ROAD/RD → RD, etc.
- Standardize directionals: NORTH/N → N, SOUTH/S → S, etc.
- Strip unit/apt/suite numbers (these vary wildly across sources)
- Pad zip codes to 5 digits
- Result: "123 North Main Street, Apt 2" → "123 N MAIN ST"

These normalizations live as PostgreSQL functions in the `public` schema so they can be reused everywhere:

```sql
CREATE OR REPLACE FUNCTION normalize_name(raw_name TEXT)
RETURNS TEXT AS $$
    SELECT UPPER(
        REGEXP_REPLACE(
            REGEXP_REPLACE(
                TRIM(raw_name),
                '\s+(JR|SR|II|III|IV|LLC|INC|CORP|LP|LTD|CO|TRUST|ESTATE)\.?$',
                '', 'gi'
            ),
            '[^A-Za-z0-9\s]', '', 'g'
        )
    );
$$ LANGUAGE SQL IMMUTABLE;

CREATE OR REPLACE FUNCTION normalize_address(raw_address TEXT)
RETURNS TEXT AS $$
    -- Similar pattern: uppercase, standardize types, strip units
    ...
$$ LANGUAGE SQL IMMUTABLE;
```

**Stage 2: Match.** Compare normalized records across sources using a tiered confidence system:

| Tier | Rule | Confidence | Example |
|---|---|---|---|
| Exact | Normalized name AND normalized address match exactly | 0.95 | "JOHN SMITH" + "123 N MAIN ST" appears in both assessment and deeds |
| Strong | Normalized name exact match + address similarity > 0.8 (pg_trgm) | 0.80 | "JOHN SMITH" at "123 N MAIN ST" vs "123 NORTH MAIN STREET" |
| Fuzzy name | Name similarity > 0.85 (pg_trgm) + exact address | 0.70 | "JOHN A SMITH" vs "JOHN SMITH" at same address |
| Business alias | Normalized business name similarity > 0.8 + same municipality | 0.65 | "YORK PROPERTIES" vs "YORK PROPS" in same township |
| Address only | Same parcel ID across sources (strongest geographic link) | 0.90 | Assessment and deed both reference parcel 43-000-01-0001 |

The parcel ID match (last row) is actually the most reliable link you have — if two records reference the same parcel, they're almost certainly related to the same property, even if the owner names differ slightly (could be a trust, an LLC, etc.).

```sql
-- MVP example: Match owners across GIS parcels and assessment records using PIDN
-- This is the core MVP matching query — parcels + assessment only.
SELECT
    p.owner_full AS gis_owner,
    a.owner_name AS assessment_owner,
    p.pidn,
    similarity(normalize_name(p.owner_full), normalize_name(a.owner_name)) AS name_score,
    CASE
        WHEN p.pidn = a.pidn THEN 0.95  -- Same parcel in both sources (strongest link)
        WHEN normalize_name(p.owner_full) = normalize_name(a.owner_name)
            AND p.pidn = a.pidn THEN 0.95
        WHEN normalize_name(p.owner_full) = normalize_name(a.owner_name)
            AND similarity(p.propadr, a.address) > 0.8 THEN 0.80
        WHEN similarity(normalize_name(p.owner_full), normalize_name(a.owner_name)) > 0.85
            AND p.pidn = a.pidn THEN 0.70
        ELSE NULL
    END AS confidence
FROM staging.parcels p
JOIN staging.assessment_properties a ON (
    p.pidn = a.pidn  -- PIDN is the primary join key
    OR (similarity(normalize_name(p.owner_full), normalize_name(a.owner_name)) > 0.7
        AND similarity(p.propadr, a.address) > 0.7)
)
WHERE p.valid_to IS NULL  -- Current records only (SCD Type 2)
AND confidence IS NOT NULL;

-- Phase 2 example: Add deeds to the matching pool (when deeds pipeline is built)
-- Same pattern — join staging.deeds on PIDN or name+address similarity
```

**Stage 3: Cluster.** Group matched records into entities. Each entity gets a canonical name (the most frequently occurring normalized form) and a canonical address (from the most authoritative source — assessment data, since it's county-maintained).

### Schema

```sql
-- Resolved entities
CREATE TABLE public.owners (
    owner_id        SERIAL PRIMARY KEY,
    canonical_name  TEXT NOT NULL,
    canonical_addr  TEXT,
    entity_type     TEXT,  -- 'person', 'business', 'trust', 'government'
    municipality    TEXT,
    parcel_count    INTEGER DEFAULT 0,
    first_seen      DATE,
    last_seen       DATE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Links back to every source record
CREATE TABLE public.owner_source_links (
    link_id         SERIAL PRIMARY KEY,
    owner_id        INTEGER REFERENCES public.owners(owner_id),
    source_type     TEXT NOT NULL,  -- 'assessment', 'deed', 'business_filing', 'license', 'liquor'
    source_id       TEXT NOT NULL,  -- Original ID from that source
    source_name     TEXT,           -- Original (un-normalized) name from source
    source_address  TEXT,           -- Original (un-normalized) address from source
    match_tier      TEXT,           -- 'exact', 'strong', 'fuzzy_name', 'business_alias', 'parcel_link'
    confidence      NUMERIC(3,2),   -- 0.00 to 1.00
    matched_at      TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(source_type, source_id)  -- One link per source record
);

-- Indexes for fast lookups
CREATE INDEX idx_owners_name ON public.owners USING gin (canonical_name gin_trgm_ops);
CREATE INDEX idx_owners_municipality ON public.owners (municipality);
CREATE INDEX idx_owner_links_owner ON public.owner_source_links (owner_id);
CREATE INDEX idx_owner_links_source ON public.owner_source_links (source_type, source_id);
```

### What this enables

Once the `owners` table is populated, the platform can answer questions like:

- **"Who owns the most parcels in Conewago Township?"** — Query `owners` joined to `owner_source_links` where source_type = 'assessment', grouped by owner_id, filtered by municipality.
- **"Show me everything we know about York Properties LLC"** — Find the owner_id, then pull all source links — every parcel they own, every deed transfer, business filing details, any licenses.
- **"Which businesses in this area have both a liquor license and recent code violations?"** — Join owners to PLCB source links and permit/violation source links through the same owner_id.

### Why this design scales to other counties

The `owners` table and `owner_source_links` table know nothing about York County specifically. The normalization functions are generic (they handle Pennsylvania address patterns, but that's a config change, not a code change). The matching tiers work on any name + address data. If you ever add Lancaster County, you'd create the same schema in a separate database (or a separate schema within the same database), run the same normalization and matching logic against Lancaster's data sources, and get a resolved entity set for Lancaster.

The scrapers change per county. The entity resolution doesn't.

### Dagster asset: `enrichment/owners.py`

Entity resolution has two scopes: an MVP contract (parcels + assessment only) and a Phase 2 enriched contract (all sources). The Dagster asset dynamically resolves whichever sources are available.

**MVP resolution (parcels + assessment):**
- Matches owner names from `staging.parcels` (GIS `owner_full` field) against `staging.assessment_properties` owner records
- Joins on PIDN (strongest link — same parcel across both sources)
- Falls back to name + address fuzzy matching (pg_trgm) for records without a PIDN match
- This already provides meaningful value: unified ownership across the two largest datasets

**Phase 2 enriched resolution (+ deeds, business filings, licenses):**
- Same matching logic, but with additional source tables feeding into the candidate pool
- Each new source type gets added to the `owner_source_links.source_type` enum as its pipeline is built
- Adding a source to resolution = adding it to the deps list and the matching query

```python
# MVP deps — only parcels + assessment exist at launch
MVP_DEPS = ["parcels", "assessment_properties"]

# Phase 2 deps — added one at a time as pipelines are built.
# Dagster won't fail if these don't exist yet; use check_fn or config flag.
PHASE2_DEPS = ["deeds", "business_filings", "pals_licenses", "plcb_licenses"]

@asset(
    group_name="enrichment",
    deps=MVP_DEPS,  # Start with MVP; add Phase 2 deps as sources come online
    description="Resolved owner entities across all available data sources",
)
def owners(context: AssetExecutionContext, database):
    """Run entity resolution across all loaded source tables"""

    # Detect which source tables actually have data
    available_sources = database.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'staging'
        AND table_name IN ('parcels', 'assessment_properties', 'deeds',
                           'business_filings', 'pals_licenses', 'plcb_licenses')
    """).fetchall()
    source_tables = [row[0] for row in available_sources]
    context.log.info(f"Running entity resolution against: {source_tables}")

    # 1. Normalize all source names/addresses (using SQL functions)
    # 2. Run tiered matching (exact → strong → fuzzy → parcel-link)
    # 3. Cluster matches into entities
    # 4. Write to public.owners + public.owner_source_links
    # 5. Log stats: total entities, match distribution by tier

    stats = database.execute_entity_resolution(source_tables)
    context.log.info(
        f"Resolved {stats['total_entities']} entities "
        f"from {stats['total_source_records']} source records "
        f"across {len(source_tables)} sources. "
        f"Match distribution: {stats['tier_counts']}"
    )
```

**MVP:** This asset depends only on `parcels` and `assessment_properties`. Dagster runs it after the weekly GIS + Assessment refresh completes (Sunday). It dynamically detects which staging tables have data, so it won't break when Phase 2 tables don't exist yet.

**Phase 2:** As each new source pipeline is built and its staging table is populated, entity resolution automatically picks it up on the next run. Update the `deps` list to include the new source so Dagster waits for it before running resolution.

### Known limitations and when to upgrade

| Limitation | Impact | When to upgrade |
|---|---|---|
| No ML confidence scoring | Rigid tiers; edge cases fall through | When false positive/negative rate is unacceptable |
| No incremental matching | Full rebuild on every run | When dataset grows large enough that full rebuild is slow (>30 min) |
| No human-in-the-loop review | Ambiguous matches auto-resolved by tier | When match accuracy is critical for official use |
| Name abbreviation handling is limited | Custom abbreviation list needs maintenance | When common abbreviations cause consistent misses |
| No cross-county entity linking | Each county is a separate entity universe | When multi-county product is in scope |

**Upgrade path:** If deterministic matching isn't sufficient, the next step is **Zingg** (open-source, Spark-based ML matching). The schema doesn't change — Zingg would replace the matching logic in Stage 2, outputting to the same `owners` and `owner_source_links` tables. The normalization functions and schema are already designed to be tool-agnostic.

---

## Frontend Architecture

### Stack

| Component | Technology | Purpose |
|---|---|---|
| UI framework | React 18+ (TypeScript) | Component-based UI, hooks for state management |
| Map rendering | MapLibre GL JS (via `react-map-gl`) | Free, open-source vector tile map rendering with WebGL |
| Data visualization | Deck.gl | GPU-accelerated rendering of 220K+ parcel polygons with interactive tooltips |
| Build tool | Vite | Fast builds, hot reload for development |
| API backend | FastAPI (Python) | Async REST API for data queries |
| Lambda adapter | Mangum | Makes FastAPI work inside AWS Lambda with zero code changes |
| Hosting | S3 + CloudFront | Static site hosting with CDN and HTTPS |
| API routing | API Gateway (REST) | Routes `/api/*` requests to Lambda |

### Why MapLibre + Deck.gl

MapLibre GL JS renders the base map (streets, labels, terrain) as vector tiles in the browser using WebGL. It handles zoom, pan, rotation, and 3D tilt natively. `react-map-gl` wraps it in React components so it integrates cleanly with the rest of the UI.

Deck.gl sits on top of the map as a data visualization layer. The key advantage: it renders large datasets using the GPU instead of the CPU. Your 220,000 parcel polygons, color-coded by zoning or assessed value, with hover tooltips and click interactions — Deck.gl handles that at 60fps where raw MapLibre would start struggling past ~50K features. It's built by the same team that maintains `react-map-gl` (Vis.gl, originally from Uber), so the integration is seamless.

Both are free and open source with no usage limits. Unlike Mapbox, there's no per-map-load pricing.

### What the UI looks like

```
┌─────────────────────────────────────────────────────────────────┐
│  [🔍 Search owners, addresses, parcels...]     [Layer ▾] [⚙]  │
├────────────────────────────────────┬────────────────────────────┤
│                                    │                            │
│                                    │   PARCEL DETAILS           │
│                                    │                            │
│          MAP VIEW                  │   Parcel: 43-000-01-0001   │
│                                    │   Owner: JOHN A SMITH      │
│     (MapLibre + Deck.gl)           │   Assessed: $185,000       │
│                                    │   Zoning: R-1 Residential  │
│     Parcels color-coded            │   Municipality: Conewago   │
│     by active layer                │   Acres: 1.24              │
│                                    │                            │
│     Click parcel → details         │   ── LINKED RECORDS ──     │
│     in side panel                  │                            │
│                                    │   📋 Deed: 2024-03-15     │
│                                    │      Sale: $215,000        │
│                                    │   🏢 Business: Smith LLC   │
│                                    │   📄 License: Contractor   │
│                                    │   🌿 DEP: No violations    │
│                                    │                            │
│                                    │   [View Full Entity ▸]     │
│                                    │                            │
├────────────────────────────────────┴────────────────────────────┤
│  York County Civic Intelligence Platform     Data as of 3/20   │
└─────────────────────────────────────────────────────────────────┘
```

### Core views (MVP)

**1. Map view (default):** Full-screen map of York County. Parcels render as polygons when zoomed in. Click a parcel to open the side panel with details. Toggle layers: parcels (colored by assessment value, zoning, or owner), roads, municipal boundaries, flood zones.

**2. Search:** Text search for owner names, addresses, or parcel IDs. Results appear as a list and are highlighted on the map. Searches hit the `/api/search` endpoint which queries the `owners` and `parcels` tables with `pg_trgm` fuzzy matching.

**3. Entity profile:** Clicking "View Full Entity" in the side panel opens a full-page view of a resolved owner — every parcel they own, every deed transfer, every business filing, every license. This is where the entity resolution pays off visually.

### What it does NOT include (MVP)

- **No user accounts or login** — fully public, read-only
- **No dashboards or charts** — add later once you know what questions keep coming up
- **No editing or data entry** — read-only intelligence platform
- **No real-time updates** — data refreshes weekly; frontend serves cached responses

### API endpoints (FastAPI on Lambda)

| Endpoint | Method | Purpose | Example |
|---|---|---|---|
| `/api/parcels/bbox` | GET | Parcels within a map bounding box | `?west=-76.8&south=39.8&east=-76.6&north=40.0` |
| `/api/parcels/{parcel_id}` | GET | Single parcel full details | `/api/parcels/43-000-01-0001` |
| `/api/owners/{owner_id}` | GET | Resolved entity with all source links | `/api/owners/12345` |
| `/api/search` | GET | Fuzzy search across owners, addresses, parcels | `?q=smith+main+st&municipality=Conewago` |
| `/api/tiles/{layer}/{z}/{x}/{y}.pbf` | GET | Vector tiles for map layers | Protobuf vector tiles for Deck.gl |
| `/api/stats/municipality/{name}` | GET | Summary stats for a township | Parcel count, avg assessment, top owners |

### Vector tiles strategy

For 220,000 parcels, you have two options for serving map data:

**Option A: Dynamic vector tiles from PostGIS.** Lambda queries RDS using `ST_AsMVT()` (PostGIS's built-in vector tile function) and returns Protobuf tiles on the fly. Simple, always up-to-date, but every tile request hits the database.

**Option B: Pre-generated tile cache in S3.** A Dagster job runs after data refresh, generates all vector tiles for standard zoom levels using `ST_AsMVT()`, and stores them in S3. CloudFront serves them directly — no Lambda or RDS involved for tile requests. Much faster for users, but tiles are only as fresh as the last generation run.

**Recommendation: Option B (pre-generated tiles in S3).** Your data refreshes weekly at most. Pre-generating tiles once after each refresh means 99% of map requests never touch Lambda or RDS. CloudFront serves tiles in under 50ms from edge cache. This also drastically reduces Lambda invocations and RDS query load.

The tile generation becomes another Dagster asset:

```python
@asset(
    group_name="tiles",
    deps=["parcels", "zoning", "roads"],
    description="Pre-generated vector tiles for map frontend",
)
def vector_tiles(context: AssetExecutionContext, database, s3):
    """Generate MVT tiles for zoom levels 8-16 and upload to S3"""
    for z in range(8, 17):
        for tile in get_tile_coords(z, YORK_COUNTY_BOUNDS):
            mvt = database.execute(f"""
                SELECT ST_AsMVT(tile, 'parcels', 4096, 'geom')
                FROM (
                    SELECT pidn, owner_full, aprtotal, municipality,
                           ST_AsMVTGeom(geom, ST_TileEnvelope({z}, {tile.x}, {tile.y})) AS geom
                    FROM public.properties
                    WHERE ST_Intersects(geom, ST_TileEnvelope({z}, {tile.x}, {tile.y}))
                ) AS tile
            """)
            s3.put(f"tiles/parcels/{z}/{tile.x}/{tile.y}.pbf", mvt)
    context.log.info(f"Generated tiles for zoom 8-16")
```

The `/api/search` and `/api/owners` endpoints still go through Lambda → RDS (these are dynamic queries), but the map tiles — which account for the vast majority of requests — are served statically from S3/CloudFront.

### Lambda configuration

| Setting | Value |
|---|---|
| Runtime | Python 3.11 |
| Handler | `handler.handler` (Mangum wrapping FastAPI) |
| Memory | 256 MB (sufficient for JSON queries against RDS) |
| Timeout | 30 seconds |
| VPC | Same default VPC as EC2/RDS |
| Security group | `api-lambda-sg` (outbound to RDS only) |
| Environment variables | `DATABASE_HOST`, `DATABASE_NAME`, `DATABASE_USER` — set by Terraform (values sourced from Terraform outputs/variables at deploy time, NOT read from Parameter Store at runtime) |
| Secrets | `DATABASE_PASSWORD` — set by Terraform as encrypted env var (KMS default key). Lambda does NOT call Parameter Store at runtime (see VPC networking constraint in Module: Networking). |

**Package size awareness:** Lambda has a 250 MB uncompressed deployment limit. The API's dependencies are lightweight — FastAPI (~2 MB), Mangum (~0.5 MB), psycopg2-binary (~3 MB), and a few stdlib-only utilities. Total is well under 50 MB. If the package approaches the limit after adding dependencies in the future, use a Lambda Layer for psycopg2-binary (which contains compiled C extensions and is the heaviest dep) or switch to the `psycopg[binary]` package which is smaller. Monitor with `du -sh package/` during CI before zipping.

### Lambda `handler.py`

```python
from mangum import Mangum
from mangum import Mangum
from main import app

handler = Mangum(app, lifespan="off")
```

That's the entire Lambda entry point. Mangum translates API Gateway events into ASGI requests that FastAPI understands. If you ever want to run the API on EC2 or a container instead of Lambda, you just run `uvicorn main:app` and remove this file. Zero code changes to the actual API.

### FastAPI app (`api/main.py`)

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import parcels, owners, search, ops

app = FastAPI(
    title="CountyIQ API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Lock down to CloudFront domain in production
    allow_methods=["GET"],
    allow_headers=["*"],
)

# All routes use /api/* prefix so CloudFront routes them to API Gateway.
# Tiles are NOT served by Lambda — they're pre-generated in S3 and served
# directly via CloudFront's /tiles/* → S3 origin (see CloudFront distribution).
app.include_router(parcels.router, prefix="/api/parcels", tags=["parcels"])
app.include_router(owners.router, prefix="/api/owners", tags=["owners"])
app.include_router(search.router, prefix="/api/search", tags=["search"])
app.include_router(ops.router, prefix="/api/ops", tags=["ops"])

@app.get("/api/health")
def health():
    return {"status": "ok"}
```

### CloudFront distribution

CloudFront sits in front of everything and routes requests:

| Path Pattern | Origin | Cache Behavior |
|---|---|---|
| `/api/*` | API Gateway | No cache (dynamic queries) |
| `/tiles/*` | S3 (tile bucket) | Cache 7 days (tiles regenerated weekly) |
| `/*` (default) | S3 (static site bucket) | Cache 1 hour (React app assets) |

This means a single CloudFront URL serves both the React app and the API. No CORS issues between frontend and backend since they share the same domain.

### S3 buckets

| Bucket | Purpose | Public Access |
|---|---|---|
| `york-county-frontend` | React build output (HTML/JS/CSS) | Via CloudFront only (OAC) |
| `york-county-tiles` | Pre-generated vector tiles (.pbf) | Via CloudFront only (OAC) |
| `york-county-raw` | Raw scrape archives (existing) | No public access |

**OAC (Origin Access Control):** S3 buckets are not publicly accessible. Only CloudFront can read from them, enforced by bucket policies referencing the CloudFront distribution.

### Frontend deployment workflow

```bash
# Local development
cd frontend
npm install
npm run dev          # Vite dev server on localhost:5173
                     # API calls proxied to local FastAPI or Lambda

# Production build + deploy
npm run build        # Outputs to frontend/dist/
aws s3 sync dist/ s3://york-county-frontend --delete
aws cloudfront create-invalidation --distribution-id <id> --paths "/*"
```

### API deployment workflow

```bash
# Package Lambda
cd api
pip install -r requirements.txt -t package/
cp -r *.py routes/ lib/ package/
cd package && zip -r ../lambda.zip . && cd ..

# Deploy
aws lambda update-function-code \
  --function-name york-county-api \
  --zip-file fileb://lambda.zip
```

**Note:** This manual packaging gets tedious. Once CI/CD is set up, both deployments will be automated by git push.

### Cold start mitigation

Lambda cold starts (1-3 seconds) happen when the function hasn't been invoked for ~5-15 minutes. Two options:

**Option 1 (free): CloudWatch keepalive.** A CloudWatch Events rule pings `/api/health` every 5 minutes. Keeps one Lambda instance warm. Cost: $0 (within free tier).

**Option 2 ($5-6/month): Provisioned Concurrency.** Keeps one Lambda instance permanently initialized. Eliminates cold starts entirely. Only worth it if you have real users noticing the delay.

**Recommendation:** Start with the CloudWatch keepalive. Add provisioned concurrency later if needed.

### Connection pooling (Lambda → RDS)

RDS db.t3.micro has a default `max_connections` of ~50. Each Lambda cold start opens a new database connection. Without controls, a burst of concurrent API requests could exhaust the connection pool and cause errors for both Lambda and the Dagster EC2 instance (which also needs connections).

**Strategy: connection reuse + concurrency cap.**

Lambda reuses connections across warm invocations within the same execution context. The key is to create the connection object outside the handler function so it persists:

```python
# api/lib/database.py
import os
import psycopg2

# Connection created once per Lambda execution context (reused across warm invocations)
_conn = None

def get_connection():
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg2.connect(
            host=os.environ["DATABASE_HOST"],
            dbname=os.environ["DATABASE_NAME"],
            user=os.environ["DATABASE_USER"],
            password=os.environ["DATABASE_PASSWORD"],
            connect_timeout=5,
        )
        _conn.autocommit = True  # Read-only API — no transactions needed
    return _conn
```

**Concurrency cap:** Set Lambda reserved concurrency to **10** in the Terraform `api` module. This guarantees at most 10 simultaneous Lambda instances, each holding 1 connection = 10 connections max. Leaves 40 connections for Dagster (which uses 2-3 during active pipeline runs) plus overhead.

```hcl
# infra/modules/api/main.tf
resource "aws_lambda_function" "api" {
  # ... existing config ...
  reserved_concurrent_executions = 10
}
```

| Consumer | Max Connections | Notes |
|---|---|---|
| Lambda API | 10 | Reserved concurrency cap |
| Dagster (webserver + daemon) | 3-5 | Varies during pipeline runs |
| Dagster sensors | 2-3 | Infra metrics + pipeline status |
| Alembic migrations | 1 | Only during deploys |
| Your local psql via SSM | 1-2 | Development/debugging |
| **Total** | **~20** | Well under 50 limit |

**When to upgrade:** If you see `FATAL: too many connections` in Lambda logs or Dagster, consider RDS Proxy (~$15/month) or upgrading to db.t3.small (max_connections ~85). For a solo-dev platform, the concurrency cap is sufficient.

### Custom domain (future)

Not needed for MVP. The CloudFront distribution URL (`d1234abcd.cloudfront.net`) works fine. When you want a custom domain:

1. Register a domain (Route 53: ~$12/year for `.com`)
2. Create a hosted zone in Route 53
3. Request an ACM certificate (free)
4. Add the domain as an alternate domain name on the CloudFront distribution
5. Create an A record (alias) pointing to CloudFront

All of this is Terraform-able and can be added to the `frontend` module later.

---

## CI/CD (GitHub Actions + OIDC)

### Why GitHub Actions

| Option | Verdict | Reason |
|---|---|---|
| **GitHub Actions** | ✅ Chosen | 2,000 free minutes/month; zero infra to manage; YAML workflows in repo |
| AWS CodePipeline + CodeBuild | ❌ | More complex Terraform; 100 build min/month free tier; no real advantage for solo dev |
| Self-hosted runner on EC2 | ❌ | Eats into t3.micro memory budget; adds operational complexity |

### Authentication: OIDC Federation (No Stored Secrets)

Instead of storing long-lived AWS access keys in GitHub, we use **OIDC federation**. GitHub Actions gets a short-lived token (valid ~15 minutes) that AWS trusts — but ONLY for this specific repo and branch.

**How it works:**

```
GitHub Actions                         AWS
─────────────                         ───
1. Workflow starts
2. Requests OIDC token from GitHub ──▶
3.                                     IAM OIDC provider validates token
4.                                     Checks: repo = jarod/countyiq
5.                                     Checks: branch = main
6.                                     Issues temporary STS credentials
7. ◀── Receives short-lived creds ────
8. Uses creds for deploy actions
9. Token expires after ~15 min
```

**What this means:** Zero AWS credentials stored in GitHub. Nothing to rotate. Nothing to leak. Even if someone gained access to your GitHub repo, the OIDC role can only do the three specific deploy actions listed below.

### Terraform Resources for OIDC

These go in a new `infra/modules/cicd/` module:

```hcl
# infra/modules/cicd/main.tf

# Step 1: Tell AWS to trust GitHub's OIDC provider
resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

# Step 2: Create a role that GitHub Actions can assume
resource "aws_iam_role" "github_actions" {
  name = "york-county-github-actions"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = aws_iam_openid_connect_provider.github.arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          }
          StringLike = {
            # ONLY this repo, ONLY the main branch
            "token.actions.githubusercontent.com:sub" = "repo:jarod/countyiq:ref:refs/heads/main"
          }
        }
      }
    ]
  })
}

# Step 3: Scoped permissions — only what deployments need
resource "aws_iam_role_policy" "deploy_permissions" {
  name = "deploy-permissions"
  role = aws_iam_role.github_actions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "FrontendDeploy"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::york-county-frontend",
          "arn:aws:s3:::york-county-frontend/*"
        ]
      },
      {
        Sid    = "FrontendCacheInvalidation"
        Effect = "Allow"
        Action = [
          "cloudfront:CreateInvalidation"
        ]
        Resource = "*"  # CloudFront doesn't support resource-level permissions for invalidations
      },
      {
        Sid    = "ApiDeploy"
        Effect = "Allow"
        Action = [
          "lambda:UpdateFunctionCode",
          "lambda:GetFunction"
        ]
        Resource = "arn:aws:lambda:us-east-1:*:function:york-county-api"
      },
      {
        Sid    = "DagsterDeploy"
        Effect = "Allow"
        Action = [
          "ssm:SendCommand",
          "ssm:GetCommandInvocation"
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "ssm:resourceTag/Name" = "york-county-dagster"
          }
        }
      }
    ]
  })
}
```

**Terraform module added to structure:**

```
infra/
├── modules/
│   ├── networking/
│   ├── iam/
│   ├── compute/
│   ├── database/
│   ├── frontend/
│   ├── api/
│   ├── monitoring/
│   └── cicd/          ◀ NEW
│       ├── main.tf
│       ├── variables.tf
│       └── outputs.tf     (exports role ARN for workflow files)
```

### Three Deployment Workflows

All workflows live in `.github/workflows/` at the repo root. Each uses **path filters** so pushing changes to `frontend/` only triggers the frontend deploy, etc.

#### Workflow 1: Frontend Deploy

**Trigger:** Push to `main` that changes files in `frontend/`
**Steps:** Install deps → Build React app → Sync to S3 → Invalidate CloudFront
**Time:** ~60 seconds

```yaml
# .github/workflows/deploy-frontend.yml
name: Deploy Frontend

on:
  push:
    branches: [main]
    paths: ['frontend/**']

permissions:
  id-token: write   # Required for OIDC
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json

      - name: Install and build
        working-directory: frontend
        run: |
          npm ci
          npm run build

      - name: Configure AWS credentials (OIDC)
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_DEPLOY_ROLE_ARN }}
          aws-region: us-east-1

      - name: Sync to S3
        run: aws s3 sync frontend/dist/ s3://york-county-frontend --delete

      - name: Invalidate CloudFront cache
        run: |
          aws cloudfront create-invalidation \
            --distribution-id ${{ secrets.CLOUDFRONT_DISTRIBUTION_ID }} \
            --paths "/*"
```

#### Workflow 2: API Deploy (Lambda)

**Trigger:** Push to `main` that changes files in `api/`
**Steps:** Install Python deps into package dir → Zip everything → Upload to Lambda
**Time:** ~90 seconds

```yaml
# .github/workflows/deploy-api.yml
name: Deploy API

on:
  push:
    branches: [main]
    paths: ['api/**']

permissions:
  id-token: write
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'  # Must match Lambda runtime

      - name: Package Lambda
        working-directory: api
        run: |
          pip install -r requirements.txt -t package/
          # Copy ALL application code — top-level .py files AND subdirectories
          cp -r *.py routes/ lib/ package/
          cd package && zip -r ../lambda.zip .

      - name: Configure AWS credentials (OIDC)
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_DEPLOY_ROLE_ARN }}
          aws-region: us-east-1

      - name: Deploy to Lambda
        run: |
          aws lambda update-function-code \
            --function-name york-county-api \
            --zip-file fileb://api/lambda.zip
```

#### Workflow 3: Dagster Deploy (EC2 via SSM)

**Trigger:** Push to `main` that changes files in `pipelines/`
**Steps:** Send SSM command to EC2 → EC2 pulls code, installs deps, restarts Dagster
**Time:** ~2-3 minutes

```yaml
# .github/workflows/deploy-dagster.yml
name: Deploy Dagster

on:
  push:
    branches: [main]
    paths: ['pipelines/**']

permissions:
  id-token: write
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Configure AWS credentials (OIDC)
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_DEPLOY_ROLE_ARN }}
          aws-region: us-east-1

      - name: Deploy via SSM
        run: |
          COMMAND_ID=$(aws ssm send-command \
            --instance-ids ${{ secrets.EC2_INSTANCE_ID }} \
            --document-name "AWS-RunShellScript" \
            --parameters 'commands=[
              "cd /opt/york-county/pipelines",
              "git pull origin main",
              "source /opt/york-county/venv/bin/activate",
              "pip install -e .",
              "sudo systemctl restart dagster-webserver dagster-daemon"
            ]' \
            --query "Command.CommandId" \
            --output text)

          # Wait for completion
          aws ssm wait command-executed \
            --command-id $COMMAND_ID \
            --instance-id ${{ secrets.EC2_INSTANCE_ID }}

          echo "✅ Dagster deploy complete"
```

### GitHub Repository Secrets

Even though OIDC eliminates AWS credentials, you still need a few non-sensitive reference values stored as GitHub Secrets:

| Secret Name | Value | Sensitive? |
|---|---|---|
| `AWS_DEPLOY_ROLE_ARN` | `arn:aws:iam::role/york-county-github-actions` | No (just a resource identifier) |
| `CLOUDFRONT_DISTRIBUTION_ID` | CloudFront distribution ID | No |
| `EC2_INSTANCE_ID` | `i-xxxxxxxxxxxxxxxxx` | No |

These are resource identifiers, not credentials. They tell the workflow where to deploy to, but they can't be used to authenticate or access anything on their own.

### Branch Strategy

| Branch | Purpose |
|---|---|
| `main` | Production. Pushes here trigger deploys. |
| `feature/*` | Development branches. No deploys triggered. |

**Workflow:** Create feature branch → make changes → push → open PR → merge to `main` → auto-deploy.

For a solo developer, this is sufficient. If you ever add collaborators, you can add required PR reviews and status checks later.

**Acknowledged tradeoff:** There is no staging environment. `main` is production and pushes deploy directly. This is the biggest unmitigated operational risk — a bad merge can break the live platform. Mitigation: CI runs lint + type checks + parser tests before deploy, and the Dagster smoke test catches pipeline breaks after deploy. If this becomes uncomfortable, add a `staging` branch with a parallel set of AWS resources (a second CloudFront distribution pointing at a staging S3 bucket, etc.), but that doubles cost.

### What About Terraform Changes?

Terraform runs **manually from your local machine** via SSM port forwarding. This is intentional:

- Infrastructure changes are rare and high-impact
- You want to review `terraform plan` output before applying
- Automating `terraform apply` risks accidental resource destruction
- Solo dev doesn't need the overhead of Atlantis or Terraform Cloud

```bash
# From your local machine:
cd infra/
terraform plan       # Review changes
terraform apply      # Apply when satisfied
```

### Deployment Flow Summary

```
                    ┌──────────────────┐
                    │   git push main  │
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
         frontend/**    pipelines/**     api/**
              │              │              │
              ▼              ▼              ▼
       ┌────────────┐ ┌───────────┐ ┌───────────┐
       │ npm build  │ │ SSM cmd   │ │ pip + zip  │
       │ S3 sync    │ │ git pull  │ │ Lambda     │
       │ CF inval.  │ │ pip inst. │ │ upload     │
       │            │ │ restart   │ │            │
       └─────┬──────┘ └─────┬─────┘ └─────┬─────┘
             │              │              │
             ▼              ▼              ▼
          S3/CDN          EC2           Lambda
        (frontend)     (Dagster)        (API)
```

### Cost

GitHub Actions: **$0/month** (free tier provides 2,000 minutes/month; these three workflows combined will use ~10-20 minutes/month at typical push frequency).

---

## Data Refresh Schedules

All schedules are staggered to avoid running multiple Playwright scrapers concurrently on the t3.micro (~550 MB available for jobs). ArcGIS REST API and bulk download sources are lighter on memory than Playwright scrapers.

### Daily Sources (6) — Phase 2 Target Schedules

> **Note:** All 6 daily sources are **Phase 2** additions. At MVP launch, no daily schedules are active — all 6 MVP sources (#1 GIS, #2 Assessment, #3 FEMA, #4 PA Open Data, #5 PennDOT, #13 PennDOT Projects) run on weekly schedules. The table below documents the **target configuration** for when each Phase 2 source is implemented. Enable each schedule in Dagster as its pipeline is built and tested.

Run at staggered times throughout the day. These sources have data that changes frequently enough to warrant daily pulls.

| Time (ET) | Source | # | Method | Phase | Notes |
|---|---|---|---|---|---|
| 06:00 | CRIMEWATCH (Police Blotters) | 19 | Playwright | Phase 2 | Most time-sensitive; new incidents post throughout the day |
| 08:00 | Assessment Database | 2 | Playwright | Phase 2 | Permits, sales, value changes post regularly |
| 10:00 | Sheriff Sales / Tax Claim | 9 | Scraper + PDF | Phase 2 ⚠️ URL changed | New listings on a rolling basis; county site reorganized — verify URLs before building |
| 12:00 | Tax Claim Bureau | 14 | HTML + PDF | Phase 2 | Related to sheriff sales; delinquent property updates |
| 14:00 | Inmate Records | 20 | TBD | Phase 2 ❌ DNS failed | Bookings/releases daily; `inmatelocator.yorkcountypa.gov` unreachable — verify from local browser before building |
| 16:00 | UJS Portal (Court Records) | 6 | Playwright | Phase 2 | New filings daily (pending AOPC access) |

**Dagster cron expressions:**

```python
# Daily sources — staggered 2-hour gaps
# NOTE: All Phase 2. These schedule definitions exist in code but are DISABLED
# at MVP launch (set enabled=False in Dagster). Enable per-source as pipelines are built.
daily_schedules = {
    "crimewatch_incidents":   "0 6 * * *",   # 6:00 AM ET  (Phase 2)
    "assessment_properties":  "0 8 * * *",   # 8:00 AM ET  (Phase 2 — daily; weekly in MVP)
    "sheriff_sales":          "0 10 * * *",  # 10:00 AM ET (Phase 2)
    "tax_claim_delinquent":   "0 12 * * *",  # 12:00 PM ET (Phase 2)
    "inmate_records":         "0 14 * * *",  # 2:00 PM ET  (Phase 2)
    "ujs_court_records":      "0 16 * * *",  # 4:00 PM ET  (Phase 2)
}
```

### Weekly Sources (11)

Spread across the week to avoid overloading any single day. Sunday is reserved for the heaviest pull (GIS portal — 49 layers, 176K+ parcels). Weekday sources run at 02:00 AM to avoid overlap with daily sources.

> **MVP sources** are marked below. At launch, only 5 weekly schedules are active (#1, #3, #4, #5, #13). The remaining 6 weekly sources are Phase 2 — their schedule definitions exist in code but are disabled until their pipelines are built. Assessment (#2) is also MVP but runs on the weekly GIS schedule initially; it moves to daily in Phase 2 when its standalone scraper is built.

| Day | Time (ET) | Source | # | Method | Phase |
|---|---|---|---|---|---|
| Sunday | 02:00 | York County GIS Portal (all 49 layers) | 1 | ArcGIS REST API | **MVP** |
| Sunday | 04:00 | FEMA Flood Hazard Layer | 3 | Direct download | **MVP** |
| Monday | 02:00 | PA Open Data Portal (data.pa.gov) | 4 | SODA API | **MVP** |
| Monday | 03:00 | PennDOT Open Data | 5 | ArcGIS REST API | **MVP** ⚠️ Not live-tested (same ArcGIS pattern as GIS Portal) |
| Tuesday | 02:00 | PennDOT Projects | 13 | ArcGIS MapServer | **MVP** |
| Tuesday | 03:00 | PA DOS Business Entities | 8 | file.dos.pa.gov + data.pa.gov | Phase 2 |
| Wednesday | 02:00 | PA DEP eFACTS | 17 | Playwright | Phase 2 |
| Wednesday | 03:00 | PALS Professional Licenses | 21 | Playwright | Phase 2 |
| Thursday | 02:00 | York City RFPs | 18 | BeautifulSoup | Phase 2 |
| Thursday | 03:00 | County Bids | 12 | BeautifulSoup | Phase 2 |
| Friday | 02:00 | Commissioners Meetings | 15 | HTML + PDF | Phase 2 |

**Dagster cron expressions:**

```python
# Weekly sources — spread across the week, 2 AM ET
weekly_schedules = {
    "gis_portal_all_layers":     "0 2 * * 0",  # Sunday 2 AM
    "fema_flood_hazard":         "0 4 * * 0",  # Sunday 4 AM
    "pa_open_data":              "0 2 * * 1",  # Monday 2 AM
    "penndot_open_data":         "0 3 * * 1",  # Monday 3 AM
    "penndot_projects":          "0 2 * * 2",  # Tuesday 2 AM
    "pa_dos_business":           "0 3 * * 2",  # Tuesday 3 AM
    "dep_efacts":                "0 2 * * 3",  # Wednesday 2 AM
    "pals_licenses":             "0 3 * * 3",  # Wednesday 3 AM
    "york_city_rfps":            "0 2 * * 4",  # Thursday 2 AM
    "county_bids":               "0 3 * * 4",  # Thursday 3 AM
    "commissioners_meetings":    "0 2 * * 5",  # Friday 2 AM
}
```

### Monthly Sources (3)

Run on the 1st of each month, staggered 2 hours apart.

| Time (ET) | Source | # | Method | Phase |
|---|---|---|---|---|
| 02:00 on 1st | PLCB Liquor Licenses | 22 | CSV bulk download | Phase 2 (early add) |
| 04:00 on 1st | Conservation District (YCCD) | 11 | PDF download | Phase 2 |
| 06:00 on 1st | YCPC Subdivision Activity | 16 | HTML + PDF | Phase 2 |

```python
monthly_schedules = {
    "plcb_liquor_licenses":     "0 2 1 * *",  # 1st of month, 2 AM
    "conservation_district":    "0 4 1 * *",  # 1st of month, 4 AM
    "ycpc_subdivisions":        "0 6 1 * *",  # 1st of month, 6 AM
}
```

### On-Demand / One-Time Bulk Loads (2)

| Source | # | Notes |
|---|---|---|
| Recorder of Deeds | 7 | RTK bulk request; refresh cadence TBD based on format received |
| Municipal Meeting Minutes | 10 | Phase 3; 72 municipality sites; initial bulk load, then weekly per-site checks |

These are triggered manually via the Dagster UI, not scheduled.

### Entity Resolution (Enrichment)

The entity resolution pipeline (`enrichment/entity_resolution.py`) is dependency-driven — Dagster runs it automatically after its upstream source assets succeed.

- **MVP:** Runs after the weekly GIS + Assessment + FEMA + PA Open Data sources complete on Sunday (typically fires Sunday morning)
- **Phase 2+:** Runs after all daily sources complete (typically fires around 5:00–6:00 PM ET)

```python
# Dependency-driven, no fixed cron expression.
# Dagster triggers it when upstream assets materialize.
```

### Schedule Summary

```
AT MVP LAUNCH (6 sources active):
┌────────────────────────────────────────────────────────────────────┐
│  WEEKLY (5 sources)      Sun–Tue 02:00–04:00 ET                   │
│  ENRICHMENT              After weekly sources complete (Sunday)    │
│  ON-DEMAND (1 source)    Recorder of Deeds — manual Dagster UI    │
└────────────────────────────────────────────────────────────────────┘

FULL DEPLOYMENT (all 22 sources, Phase 2+):
┌────────────────────────────────────────────────────────────────────┐
│  DAILY (6 sources)       06:00 → 16:00 ET, 2-hour gaps           │
│  WEEKLY (11 sources)     Sun–Fri 02:00–04:00 ET, 2 per day       │
│  MONTHLY (3 sources)     1st of month, 02:00–06:00 ET            │
│  ENRICHMENT              After daily sources complete (~17:00 ET) │
│  ON-DEMAND (2 sources)   Manual trigger via Dagster UI            │
└────────────────────────────────────────────────────────────────────┘

Peak memory window (Phase 2+): 06:00–16:00 ET (daily scrapers, one at a time)
Safe maintenance window: 18:00–01:00 ET (nothing scheduled)
```

---

## Error Handling, Alerting & Retry Policy

### Notification Hub: Slack (Free Tier)

All pipeline and infrastructure alerts flow into a **free Slack workspace**. Slack provides push notifications on your phone, searchable history (90 days on free tier), and channel-based organization.

**Workspace:** `CountyIQ` (countyiq.slack.com)

| Channel | Purpose | Phone Notifications |
|---|---|---|
| `#alerts-critical` | Run failures after all retries exhausted, infra alarms (CPU/memory/disk) | **ON** — these need attention |
| `#alerts-warning` | Single run failures (before retries), zero-record results, schema changes | OFF — check when convenient |
| `#pipeline-runs` | Every successful run posts a one-liner | Muted — scroll through when curious |

### Integration Architecture

```
┌─────────────────────────────────────┐
│          DAGSTER (EC2)              │
│                                     │
│  Run succeeds ──▶ Slack #pipeline-runs  ("✅ parcels: 176,060 records, 4m 12s")
│  Run fails    ──▶ Retry (up to 3x)
│  All retries  ──▶ Slack #alerts-critical ("❌ parcels failed 3x: ConnectionTimeout")
│  Zero records ──▶ Slack #alerts-warning  ("⚠️ assessment returned 0 records")
│  Schema change──▶ Slack #alerts-warning  ("⚠️ parcels API has new field: XYZ")
│                                     │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│        CLOUDWATCH (AWS)             │
│                                     │
│  CPU > 90% 5min  ──▶ SNS ──▶ Slack #alerts-critical
│  Memory > 85%    ──▶ SNS ──▶ Slack #alerts-critical
│  Disk > 80%      ──▶ SNS ──▶ Slack #alerts-critical
│  RDS connections ──▶ SNS ──▶ Slack #alerts-critical
│  RDS storage     ──▶ SNS ──▶ Slack #alerts-critical
│                                     │
└─────────────────────────────────────┘
```

**Dagster → Slack:** Direct webhook integration. Dagster failure/success sensors post to Slack via incoming webhook URL (stored in Parameter Store). No intermediate Lambda needed.

**CloudWatch → Slack:** CloudWatch Alarm → SNS Topic → Lambda (tiny forwarder) → Slack webhook. The Lambda is a ~20 line Python function that reformats the SNS message and posts to Slack. Runs within the permanent Lambda free tier.

### Dagster Slack Integration Code

```python
# pipelines/lib/slack.py
import requests
import json
import boto3

def get_slack_webhook_url():
    """Retrieve Slack webhook URL from Parameter Store."""
    ssm = boto3.client("ssm", region_name="us-east-1")
    response = ssm.get_parameter(
        Name="/york-county/slack-webhook-url",
        WithDecryption=True
    )
    return response["Parameter"]["Value"]

def send_slack_message(channel: str, text: str, emoji: str = "🔔"):
    """Post a message to a Slack channel via incoming webhook."""
    webhook_url = get_slack_webhook_url()
    payload = {
        "channel": channel,
        "icon_emoji": emoji,
        "username": "CountyIQ",
        "text": text
    }
    requests.post(webhook_url, json=payload, timeout=10)
```

### Dagster Sensors

```python
# pipelines/sensors/alerting.py
from dagster import (
    run_failure_sensor,
    run_status_sensor,
    DagsterRunStatus,
    RunStatusSensorContext,
    RunFailureSensorContext,
)
from lib.slack import send_slack_message


@run_status_sensor(run_status=DagsterRunStatus.SUCCESS)
def success_reporter(context: RunStatusSensorContext):
    """Post successful run summary to #pipeline-runs."""
    run = context.dagster_run
    duration = (run.end_time - run.start_time) if run.end_time else 0
    minutes = int(duration // 60)
    seconds = int(duration % 60)

    send_slack_message(
        channel="#pipeline-runs",
        text=f"✅ *{run.job_name}* completed in {minutes}m {seconds}s",
        emoji="✅"
    )


@run_failure_sensor
def failure_alerter(context: RunFailureSensorContext):
    """Post failures to #alerts-critical after all retries exhausted."""
    run = context.dagster_run
    error = context.failure_event.message[:200] if context.failure_event else "Unknown error"

    send_slack_message(
        channel="#alerts-critical",
        text=f"❌ *{run.job_name}* failed after all retries.\n```{error}```",
        emoji="🚨"
    )
```

### Retry Policy

Applied globally to all Dagster assets via a default policy. Individual assets can override if needed.

```python
# pipelines/lib/retry.py
from dagster import RetryPolicy, Backoff

default_retry_policy = RetryPolicy(
    max_retries=3,
    delay=300,                    # 5 minutes between retries
    backoff=Backoff.EXPONENTIAL,  # 5min → 10min → 20min
)
```

| Attempt | Wait Before | What Happens |
|---|---|---|
| 1st try | — | Normal run |
| 2nd try | 5 minutes | Retry after transient failure |
| 3rd try | 10 minutes | Retry with exponential backoff |
| 4th try | 20 minutes | Final retry |
| All failed | — | `#alerts-critical` notification fires |

**Why exponential backoff:** If a website is down or rate-limiting you, hammering it every 30 seconds makes things worse. Spreading retries over ~35 minutes gives the upstream source time to recover.

### Alert Types

| Alert Type | Channel | Trigger | Example Message |
|---|---|---|---|
| Run failure (all retries) | `#alerts-critical` | Dagster failure sensor | "❌ crimewatch_incidents failed 3x: TimeoutError" |
| Consecutive failures | `#alerts-critical` | Custom sensor (3+ days of failures for same source) | "🔴 assessment_properties has failed 3 days in a row" |
| Zero records returned | `#alerts-warning` | Asset check in Dagster | "⚠️ sheriff_sales returned 0 records (expected 50+)" |
| Schema change detected | `#alerts-warning` | Asset check comparing field names | "⚠️ parcels API returned unknown field: NEW_COLUMN" |
| Infra alarm | `#alerts-critical` | CloudWatch → SNS → Lambda → Slack | "🔴 EC2 CPU > 90% for 5 minutes" |
| Successful run | `#pipeline-runs` | Dagster success sensor | "✅ parcels_arcgis: 176,060 records, 4m 12s" |

### CloudWatch → Slack Forwarder Lambda

```python
# infra/lambda/cloudwatch_to_slack.py
import json
import os
import urllib.request

def handler(event, context):
    """Forward CloudWatch alarm SNS messages to Slack."""
    webhook_url = os.environ["SLACK_WEBHOOK_URL"]

    for record in event["Records"]:
        message = json.loads(record["Sns"]["Message"])
        alarm_name = message.get("AlarmName", "Unknown")
        state = message.get("NewStateValue", "Unknown")
        reason = message.get("NewStateReason", "")[:200]

        slack_msg = {
            "channel": "#alerts-critical",
            "username": "CloudWatch",
            "icon_emoji": "🔴" if state == "ALARM" else "✅",
            "text": f"{'🔴' if state == 'ALARM' else '✅'} *{alarm_name}*: {state}\n```{reason}```"
        }

        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(slack_msg).encode(),
            headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req)
```

This Lambda is subscribed to the existing SNS topic used by CloudWatch alarms. Add it to the `monitoring` Terraform module.

### Parameter Store Values (New)

One webhook per channel — Dagster sensors and the CloudWatch forwarder Lambda pick the right URL based on alert severity.

| Parameter | Channel | Used By |
|---|---|---|
| `/york-county/slack-webhook-critical` | `#alerts-critical` | CloudWatch forwarder Lambda, Dagster failure sensor (after all retries exhausted) |
| `/york-county/slack-webhook-warning` | `#alerts-warning` | Dagster failure sensor (single failure, before retries) |
| `/york-county/slack-webhook-pipeline` | `#pipeline-runs` | Dagster success sensor (all completions) |

---

## Operational Visibility

### The Three Layers

| Layer | Tool | Purpose | When to Use |
|---|---|---|---|
| **Phone buzzes** | Slack push notifications | Something needs attention NOW | Automatic — `#alerts-critical` |
| **Scrollable history** | Slack channels | What happened today/this week | Open Slack, scroll `#pipeline-runs` |
| **Dashboard** | `/ops/health` page in your frontend | "Is everything healthy?" at a glance | Morning check-in, or whenever curious |
| **Deep-dive** | Dagster UI (via SSM port forward) | Investigate specific run failures, view logs, re-trigger runs | When debugging a specific issue |
| **Infra deep-dive** | CloudWatch console | EC2/RDS metrics, log streams | Rarely — only for infra-level investigation |

### Health Dashboard (`/ops/health`)

A page built into your React frontend that queries the Lambda API for system health. This is your "single pane of glass" — open it on your phone or laptop and see green/yellow/red for everything.

**API Endpoint:** `GET /api/ops/health` (CloudFront routes `/api/*` to API Gateway → Lambda)

**Frontend route:** `/ops/health` (React client-side route — the React page fetches `/api/ops/health` and renders the dashboard)

**Response structure:**

```json
{
  "overall_status": "healthy",
  "checked_at": "2026-03-20T18:00:00Z",
  "sources": [
    {
      "name": "parcels_arcgis",
      "schedule": "weekly",
      "last_success": "2026-03-17T02:14:33Z",
      "last_record_count": 176060,
      "prev_record_count": 175982,
      "status": "healthy",
      "next_run": "2026-03-23T02:00:00Z"
    },
    {
      "name": "crimewatch_incidents",
      "schedule": "daily",
      "last_success": "2026-03-20T06:04:12Z",
      "last_record_count": 23,
      "prev_record_count": 18,
      "status": "healthy",
      "next_run": "2026-03-21T06:00:00Z"
    },
    {
      "name": "sheriff_sales",
      "schedule": "daily",
      "last_success": null,
      "last_record_count": 0,
      "prev_record_count": null,
      "status": "error",
      "error": "Failed 3x: ConnectionTimeout",
      "next_run": "2026-03-21T10:00:00Z"
    }
  ],
  "infrastructure": {
    "ec2_status": "running",
    "rds_status": "available",
    "rds_storage_used_gb": 4.2,
    "rds_storage_total_gb": 20,
    "ec2_disk_used_pct": 38
  }
}
```

**Status logic:**

| Status | Color | Rule |
|---|---|---|
| `healthy` | 🟢 Green | Last run succeeded within expected schedule window |
| `late` | 🟡 Yellow | Last run succeeded, but it's overdue for the next run (missed schedule) |
| `error` | 🔴 Red | Last run failed after all retries |
| `unknown` | ⚪ Gray | Never run (new source, or on-demand only) |

**UI mockup:**

```
┌──────────────────────────────────────────────────────────────────┐
│  YORK COUNTY PLATFORM — OPERATIONS HEALTH          March 20 6PM │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Overall: 🟢 HEALTHY (19/20 sources OK)                         │
│                                                                  │
│  ┌─── DAILY SOURCES ──────────────────────────────────────────┐  │
│  │ 🟢 CRIMEWATCH        23 records    today 6:04 AM          │  │
│  │ 🟢 Assessment         1,204 records today 8:02 AM         │  │
│  │ 🟢 Sheriff Sales      12 records    today 10:01 AM        │  │
│  │ 🟢 Tax Claim          8 records     today 12:03 PM        │  │
│  │ 🔴 Inmate Records     FAILED        ConnectionTimeout     │  │
│  │ 🟢 UJS Court          342 records   today 4:05 PM         │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌─── WEEKLY SOURCES ─────────────────────────────────────────┐  │
│  │ 🟢 GIS Portal (49 layers)   176,060 parcels   Sun 2:14 AM │  │
│  │ 🟢 FEMA Flood               1 file            Sun 4:01 AM │  │
│  │ 🟢 PA Open Data             3,421 records     Mon 2:03 AM │  │
│  │ 🟢 PennDOT Open Data        892 records       Mon 3:01 AM │  │
│  │    ... (all green)                                         │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌─── INFRASTRUCTURE ─────────────────────────────────────────┐  │
│  │ EC2: Running    CPU 12%   Memory 58%   Disk 38%           │  │
│  │ RDS: Available  Storage 4.2 / 20 GB    Connections 3      │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌─── ENTITY RESOLUTION ──────────────────────────────────────┐  │
│  │ Last run: today 5:42 PM   Owners: 142,318   Matches: 8,921│  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### How the Health Page Gets Its Data

The health data comes from one place: **RDS**. Lambda is in a VPC with no internet access, so it cannot call AWS APIs (CloudWatch, etc.) directly. All data the health page needs is in the database.

1. **Dagster run history** — Dagster stores all run metadata (status, timestamps, record counts) in its own database on the same RDS instance. The Lambda API queries a `meta.pipeline_status` view (see below).

2. **Infrastructure metrics** — A Dagster sensor on EC2 polls CloudWatch every 5 minutes and writes EC2/RDS metrics to `meta.infra_metrics`. Lambda reads this table instead of calling CloudWatch directly. This avoids the need for a NAT Gateway or VPC Endpoints.

**Dagster infra metrics sensor (runs on EC2, which HAS internet access):**

```python
# pipelines/sensors/infra_metrics.py
import boto3
from dagster import sensor, RunRequest
from lib.database import get_connection

@sensor(minimum_interval_seconds=300)  # Every 5 minutes
def infra_metrics_sensor(context):
    """Poll CloudWatch and write EC2/RDS metrics to RDS for the health page."""
    cw = boto3.client("cloudwatch", region_name="us-east-1")
    conn = get_connection()

    # Fetch key metrics
    metrics = {
        "ec2_cpu_pct": get_metric(cw, "AWS/EC2", "CPUUtilization", "york-county-dagster"),
        "rds_free_storage_gb": get_metric(cw, "AWS/RDS", "FreeStorageSpace", "york-county-db") / 1e9,
        "rds_connections": get_metric(cw, "AWS/RDS", "DatabaseConnections", "york-county-db"),
    }

    conn.execute("""
        INSERT INTO meta.infra_metrics (checked_at, metrics)
        VALUES (NOW(), %s)
    """, [json.dumps(metrics)])

    # Keep only last 24 hours of metrics
    conn.execute("DELETE FROM meta.infra_metrics WHERE checked_at < NOW() - INTERVAL '24 hours'")
```

**Lambda API handler:**

```python
# api/routes/ops.py
from fastapi import APIRouter
from lib.database import get_connection

router = APIRouter()

@router.get("/health")  # Mounted at /api/ops by main.py → full path: /api/ops/health
def health_check():
    conn = get_connection()

    # Query pipeline status (written by Dagster sensor, decoupled from Dagster internals)
    sources = conn.execute("""
        SELECT
            source_name,
            status,
            last_run_at,
            duration_seconds,
            record_count,
            prev_record_count,
            error_message
        FROM meta.pipeline_status
        ORDER BY source_name
    """).fetchall()

    # Get infra metrics from RDS (written by Dagster sensor, NOT from CloudWatch API)
    infra = conn.execute("""
        SELECT metrics FROM meta.infra_metrics
        ORDER BY checked_at DESC LIMIT 1
    """).scalar()

    return {
        "overall_status": "healthy" if all(s.status == "SUCCESS" for s in sources) else "degraded",
        "sources": [format_source(s) for s in sources],
        "infrastructure": json.loads(infra) if infra else {}
    }
```

### Access

The `/ops/health` page is part of the public frontend (no auth for MVP). If you want to restrict it later, you can add a simple API key check or move it behind CloudFront's signed URLs.

**Quick access pattern:**
- Bookmark `https://your-cloudfront-url.cloudfront.net/ops/health` on your phone (this is the React frontend route; the page calls `/api/ops/health` internally)
- Morning routine: open bookmark, glance at colors, done

---

## Data Retention & Archival Policy

### Design Principle

CountyIQ's value comes from connecting data across time, not just across sources. A zoning variance filed in 2024, a building permit in 2025, and an ownership transfer in 2026 might all relate to the same development — the platform needs to answer "what happened here over time," not just "what's happening now."

**Policy: Keep everything. No deletions. No archival tiers.**

### Layer 1: Raw Snapshots (S3 Standard) — Keep Forever

Every pipeline run dumps its raw response to S3 with a timestamped path:

```
s3://york-county-raw/
├── arcgis/parcels/2026-03-20/response.json
├── arcgis/parcels/2026-03-27/response.json
├── crimewatch/2026-03-20/page-1.html
├── crimewatch/2026-03-20/page-2.html
├── assessment/2026-03-20/batch-001.html
├── plcb/2026-04-01/licenses.csv
└── ...
```

**Why keep raw data:**
- If a scraper bug corrupts processed data, you can replay from raw
- If you improve parsing logic later, you can re-process historical snapshots
- Audit trail — proves what the source looked like at a given time
- If a source disappears or changes format, you still have the original data

**Storage cost estimate:**

| Timeframe | Estimated Raw Data | S3 Standard Cost |
|---|---|---|
| Year 1 | ~10 GB | $0.23/month |
| Year 3 | ~30 GB | $0.69/month |
| Year 5 | ~50 GB | $1.15/month |

At these volumes, tiered storage (Glacier, etc.) saves cents while adding retrieval complexity and cost risk. Not worth it. S3 Standard forever.

### Layer 2: Processed Records (RDS) — Change-Tracked, Keep All Versions

Tables that represent entities with mutable attributes use **Slowly Changing Dimensions (Type 2)** — every row has `valid_from` and `valid_to` timestamps. When data changes, the old row gets closed and a new row opens.

**Change-tracked tables (SCD Type 2):**

| Table | Why Track Changes | Example |
|---|---|---|
| `parcels` | Ownership transfers, assessment value changes, sale history | "Who owned this property in 2024?" |
| `businesses` | Status changes, officer changes, address changes | "This LLC was active when the permit was filed" |
| `permits` | Status updates (applied → approved → completed → expired) | "Permit issued 2024, never completed" |
| `zoning` | Variance applications, rezoning decisions | "Rezoned from residential to commercial in 2025" |
| `environmental` | Inspection results, violation status changes | "DEP violation opened 2024, resolved 2025" |
| `licenses` | Professional and liquor license status changes | "License revoked in 2025" |
| `owners` (entity resolution) | Resolved entity attributes change as new sources are linked | "Entity gained a new business association" |

**Schema pattern:**

```sql
-- Example: parcels table with change tracking
CREATE TABLE staging.parcels (
    id              SERIAL PRIMARY KEY,
    pidn            TEXT NOT NULL,          -- Parcel ID (natural key)
    owner_full      TEXT,
    aprtotal        NUMERIC,
    sale_date       DATE,
    price           NUMERIC,
    -- ... other fields ...

    -- Change tracking columns
    valid_from      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to        TIMESTAMPTZ,            -- NULL = current record
    source_run_id   TEXT,                   -- Dagster run ID that created this row
    raw_snapshot    TEXT,                   -- S3 key to the raw data

    -- Indexes for common queries
    CONSTRAINT current_record UNIQUE (pidn) WHERE (valid_to IS NULL)
);

-- Current snapshot (fast):
-- SELECT * FROM staging.parcels WHERE valid_to IS NULL;

-- Historical query (what did this parcel look like on a date):
-- SELECT * FROM staging.parcels
-- WHERE pidn = '46000060065000000'
--   AND valid_from <= '2024-06-15'
--   AND (valid_to IS NULL OR valid_to > '2024-06-15');
```

**Append-only tables (no change tracking needed):**

| Table | Why Append-Only | Notes |
|---|---|---|
| `court_records` | New filings are added; existing records don't change | Naturally grows over time |
| `crimewatch_incidents` | Incidents are posted once | Deduplication on insert |
| `sheriff_sales` | Each sale is a distinct event | Historical sales are valuable context |
| `meeting_minutes` | Published once per meeting | PDF reference stored in S3 |
| `bids_rfps` | Posted once, may close but don't change | Track status if needed |

### Layer 3: Operational Logs — Pruned

| Log Type | Retention | Rationale |
|---|---|---|
| Dagster run metadata (RDS `meta` schema) | 90 days | Slack history + S3 raw snapshots provide longer-term record |
| CloudWatch logs | 7 days | Already configured; infra logs are transient |
| Slack message history | 90 days (free tier limit) | Sufficient for operational troubleshooting |

### Storage Growth Projections (RDS)

| Timeframe | Estimated RDS Size | Notes |
|---|---|---|
| Initial load | ~2 GB | 176K parcels + geometry, initial scraper data |
| Year 1 | ~4-6 GB | Change tracking adds rows gradually; most records don't change every pull |
| Year 3 | ~8-12 GB | Court records and incidents are the main growth drivers |
| Year 5 | ~15-18 GB | Still within 20 GB allocation |

If RDS approaches 20 GB, the first lever is increasing storage (scales to 64 TB, costs $0.115/GB/month). The second lever is partitioning historical data by year. But at these growth rates, 20 GB should last 5+ years.

### What This Enables

With full history retained, CountyIQ can answer questions like:
- "Show me all ownership changes for this parcel in the last 3 years"
- "Which properties had permits filed but never completed?"
- "This business was registered in 2024 — what properties did its officers own at that time?"
- "How has the assessed value of properties in this neighborhood trended?"
- "When did this environmental violation first appear, and is it resolved?"

This is what makes CountyIQ an intelligence platform rather than just a data viewer.

---

## Backfill Strategy

On Day 1, every pipeline runs in "backfill mode" to populate the database with as much data as possible. After that, scheduled runs maintain freshness.

### Full Snapshot Sources (No Backfill Problem)

These sources return the complete dataset on every pull. The first run IS the backfill.

| Source | # | What You Get on First Run |
|---|---|---|
| York County GIS Portal (49 layers) | 1 | All 176K+ parcels with full attribute history (sale dates, previous owners, previous prices) |
| FEMA Flood Hazard Layer | 3 | Complete flood zone boundaries |
| PA Open Data Portal | 4 | Full datasets via SODA API |
| PennDOT Open Data | 5 | Full road/bridge/infrastructure datasets |
| PennDOT Projects | 13 | All project records with status history |
| PA DOS Business Entities | 8 | Full business registry via data.pa.gov |
| PLCB Liquor Licenses | 22 | Complete bulk CSV of all licenses |
| PALS Professional Licenses | 21 | Searchable — can pull everything |
| Assessment Database | 2 | Current records (value history available per-property via scraping) |
| PA DEP eFACTS | 17 | Searchable by county — can pull all York County records |

**Dagster approach:** Each asset has a `backfill` config option:

```python
from dagster import asset, Config

class SourceConfig(Config):
    full_history: bool = False   # True on first run (backfill), False on scheduled runs

@asset
def parcels_arcgis(config: SourceConfig):
    if config.full_history:
        # Paginate through ALL 176K records
        return fetch_all_records(offset=0, limit=None)
    else:
        # Fetch only records modified since last run
        last_run = get_last_materialization_time()
        return fetch_records_modified_since(last_run)
```

To trigger backfill from the Dagster UI: select the asset → Materialize → set `full_history: true`.

### Archive-Scrapeable Sources (One-Time Deep Scrape)

These sources have archive pages that go back months or years. The Day 1 backfill scrapes ALL available archive pages, not just the first page.

| Source | # | Archive Depth | Backfill Approach |
|---|---|---|---|
| Commissioners Meetings | 15 | Meeting archives going back years | Scrape all archive pages; download all available PDFs |
| YCPC Subdivision Activity | 16 | Activity logs with historical entries | Scrape full activity list |
| Conservation District (YCCD) | 11 | PDF reports archive | Download all available PDFs |
| County Bids | 12 | Archive of past bids | Scrape all pages including closed/expired bids |
| York City RFPs | 18 | Past RFP listings | Scrape full listing history |

### Current-Only Sources (History Starts at Launch)

These sources only show what's currently posted. There's no practical way to retrieve historical data. History builds forward from Day 1.

| Source | # | What You Miss | Acceptable? |
|---|---|---|---|
| CRIMEWATCH | 19 | Incidents older than what's currently displayed | Yes — police blotter value is in recent patterns, not 2-year-old incidents |
| Sheriff Sales | 9 | Past sales that have already been removed from the site | Yes — GIS parcel data includes sale history (dates + prices) as a partial substitute |
| Tax Claim Bureau | 14 | Previously resolved delinquencies | Yes — current delinquencies are what matter |
| Inmate Records | 20 | Past bookings/releases | Yes — current status is primary use case |

### Formal Request Sources (Their Timeline)

| Source | # | Action | Backfill Depends On |
|---|---|---|---|
| Recorder of Deeds | 7 | File RTK request | Whatever format/timespan they provide |
| UJS Court Records | 6 | File AOPC application | Scope of access granted |

### Day 1 Execution Order

The backfill should run in a specific order because of asset dependencies (entity resolution needs source data first):

```
Phase 1: Full snapshot sources (parallel where memory allows)
  ├── GIS Portal (all 49 layers)     ~30 min (176K parcels + geometry)
  ├── FEMA Flood Layer                ~2 min
  ├── PA Open Data                    ~5 min
  ├── PennDOT (Open Data + Projects)  ~10 min
  ├── PA DOS Business                 ~5 min
  ├── PLCB Licenses (CSV)             ~1 min
  └── PALS Licenses                   ~15 min

Phase 2: Scraper sources (sequential — memory constraints)
  ├── Assessment Database             ~2-4 hours (176K properties, throttled)
  ├── CRIMEWATCH                      ~10 min
  ├── DEP eFACTS                      ~20 min
  ├── Sheriff Sales + Tax Claim       ~10 min
  ├── County Bids + York City RFPs    ~5 min
  └── Commissioners + YCPC + YCCD     ~15 min

Phase 3: Enrichment (after all sources complete)
  └── Entity Resolution               ~20 min

Phase 4: Frontend data generation
  └── Vector tile generation           ~15 min

Total estimated Day 1 backfill: ~4-6 hours
```

Run this on a weekday morning so you can monitor via the Dagster UI and Slack. Trigger Phase 1 assets manually, let Dagster's dependency graph handle the rest.

---

## Testing Strategy

### Guiding Principle

Practical tests that catch real problems before merge. No mocks, no fake data fixtures, no elaborate test infrastructure. Three layers: CI catches code bugs, smoke tests catch deploy problems, Dagster asset checks catch data quality issues in production.

### Layer 1: Pre-Merge Checks (GitHub Actions CI)

A new workflow that runs on **pull requests** to `main` (not on push — the deploy workflows handle push). Tests must pass before the PR can be merged.

```yaml
# .github/workflows/ci.yml
name: CI

on:
  pull_request:
    branches: [main]

jobs:
  lint-and-type-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dev dependencies
        run: pip install ruff mypy

      - name: Lint (ruff)
        run: ruff check pipelines/ api/

      - name: Type check (mypy)
        run: mypy pipelines/ api/ --ignore-missing-imports

  pipeline-schema-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install -e pipelines/[dev]

      - name: Run schema validation tests
        run: pytest pipelines/tests/ -v

  frontend-build:
    runs-on: ubuntu-latest
    if: ${{ contains(github.event.pull_request.changed_files, 'frontend/') }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json

      - name: Install and build
        working-directory: frontend
        run: |
          npm ci
          npm run build
```

**What this catches:**
- Syntax errors, unused imports, formatting issues (ruff)
- Type mismatches, missing attributes (mypy)
- Schema/parsing regressions (pytest)
- Frontend build failures (npm)

**What this intentionally does NOT do:**
- Hit live APIs (flaky, slow, rate limits)
- Require a database (no Docker Postgres in CI)
- Run integration tests (that's what Dagster asset checks do in production)

### Schema Validation Tests

Each pipeline source defines its expected output schema. Tests verify that the parsing logic produces the right structure. These use sample response fixtures (a small saved JSON/HTML file checked into the repo).

```
pipelines/
├── tests/
│   ├── conftest.py
│   ├── fixtures/              # Small sample responses from each source
│   │   ├── parcels_sample.json
│   │   ├── crimewatch_sample.html
│   │   ├── plcb_sample.csv
│   │   └── ...
│   ├── test_arcgis_parser.py
│   ├── test_crimewatch_parser.py
│   ├── test_plcb_parser.py
│   └── ...
```

**Example test:**

```python
# pipelines/tests/test_arcgis_parser.py
import json
from pathlib import Path
from pipelines.lib.parsers.arcgis import parse_parcels_response

FIXTURES = Path(__file__).parent / "fixtures"

def test_parcels_parser_returns_expected_fields():
    """Verify the parser produces all required columns."""
    sample = json.loads((FIXTURES / "parcels_sample.json").read_text())
    records = parse_parcels_response(sample)

    assert len(records) > 0
    required_fields = ["pidn", "owner_full", "propadr", "aprtotal", "saledt", "price"]
    for field in required_fields:
        assert field in records[0], f"Missing required field: {field}"


def test_parcels_parser_handles_null_values():
    """Verify the parser doesn't crash on null/missing fields."""
    sample = json.loads((FIXTURES / "parcels_sample.json").read_text())
    # Null out some fields to simulate real-world data
    sample["features"][0]["attributes"]["PRICE"] = None
    records = parse_parcels_response(sample)
    assert records[0]["price"] is None
```

**Effort per source:** ~1-2 test functions, ~15 minutes to write. The fixtures are just a small copy-paste from a real API response (already captured during feasibility testing).

### Layer 2: Smoke Test on Deploy

After the Dagster deploy workflow restarts services, verify they came up cleanly. Added as a final step in the `deploy-dagster.yml` workflow:

```yaml
      - name: Smoke test
        run: |
          # Wait for Dagster to start
          sleep 30

          # Verify Dagster can load all definitions
          SMOKE_RESULT=$(aws ssm send-command \
            --instance-ids ${{ secrets.EC2_INSTANCE_ID }} \
            --document-name "AWS-RunShellScript" \
            --parameters 'commands=[
              "source /opt/york-county/venv/bin/activate",
              "cd /opt/york-county/pipelines",
              "python -c \"from definitions import defs; print(f\"{len(defs.get_all_asset_keys())} assets loaded\")\" "
            ]' \
            --query "Command.CommandId" \
            --output text)

          aws ssm wait command-executed \
            --command-id $SMOKE_RESULT \
            --instance-id ${{ secrets.EC2_INSTANCE_ID }}

          echo "✅ Dagster smoke test passed"
```

**What this catches:** Missing imports, broken config files, dependency issues that only surface when Dagster tries to load the full asset graph. These don't show up in unit tests because unit tests don't import the full Dagster definitions.

### Layer 3: Data Quality Checks (Dagster Asset Checks)

These run in production as part of the pipeline, not in CI. After each asset materializes, Dagster validates the output.

```python
# pipelines/lib/checks.py
from dagster import asset_check, AssetCheckResult, AssetCheckSeverity

@asset_check(asset="parcels_arcgis")
def parcels_record_count(context):
    """Verify parcel count is within expected range."""
    conn = get_connection()
    count = conn.execute(
        "SELECT COUNT(*) FROM staging.parcels WHERE valid_to IS NULL"
    ).scalar()

    passed = 150_000 < count < 200_000  # Expected ~176K
    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.WARN,
        metadata={"record_count": count},
        description=f"Got {count:,} records (expected 150K-200K)"
    )


@asset_check(asset="parcels_arcgis")
def parcels_no_null_pidn(context):
    """Verify no parcel records have null PIDN."""
    conn = get_connection()
    null_count = conn.execute(
        "SELECT COUNT(*) FROM staging.parcels WHERE valid_to IS NULL AND pidn IS NULL"
    ).scalar()

    return AssetCheckResult(
        passed=null_count == 0,
        severity=AssetCheckSeverity.ERROR,
        metadata={"null_pidn_count": null_count}
    )


@asset_check(asset="crimewatch_incidents")
def crimewatch_not_empty(context):
    """Verify scraper returned at least some incidents."""
    conn = get_connection()
    today_count = conn.execute(
        "SELECT COUNT(*) FROM staging.crimewatch WHERE DATE(created_at) = CURRENT_DATE"
    ).scalar()

    return AssetCheckResult(
        passed=today_count > 0,
        severity=AssetCheckSeverity.WARN,
        metadata={"today_count": today_count},
        description=f"Got {today_count} incidents today"
    )
```

**Failed checks trigger the Slack alerting pipeline** described in the Error Handling section:
- `WARN` severity → `#alerts-warning`
- `ERROR` severity → `#alerts-critical`

### What Each Layer Catches

| Problem | Layer 1 (CI) | Layer 2 (Smoke) | Layer 3 (Checks) |
|---|---|---|---|
| Syntax error in pipeline code | ✅ ruff | | |
| Type mismatch in function call | ✅ mypy | | |
| Parser returns wrong columns | ✅ pytest | | |
| Missing import after refactor | ✅ mypy | ✅ definition load | |
| Broken Dagster config | | ✅ definition load | |
| Website changed HTML structure | | | ✅ schema check |
| API returned 0 records | | | ✅ count check |
| Source went offline | | | ✅ run failure → retry → alert |
| Database constraint violation | | | ✅ run failure → alert |
| Frontend won't build | ✅ npm build | | |

### Dev Dependencies

```toml
# pipelines/pyproject.toml [project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "ruff>=0.4",
    "mypy>=1.10",
]
```

### What's Intentionally NOT Included

| Approach | Why Skipped |
|---|---|
| Integration tests with live APIs | Flaky, slow, may hit rate limits; asset checks cover this in production |
| Docker Postgres in CI | Adds build time and complexity; schema migration testing is done locally (see Alembic section) |
| End-to-end frontend tests (Cypress, Playwright) | Overkill for MVP; manual browser testing is fine initially |
| Code coverage requirements | Chasing coverage percentages leads to bad tests; focus on meaningful assertions |
| Snapshot testing | Brittle; breaks on any output change even if the change is correct |

---

## WAF Rate Limiting

### Why

The frontend and API are publicly accessible with no authentication. Without rate limiting, someone (or a bot) could:
- Hammer the API endpoint and run up Lambda invocation costs
- Scrape all the data from the API (ironic, given that CountyIQ is itself a scraper platform)
- DDoS the CloudFront distribution

AWS WAF attached to CloudFront provides basic protection with minimal cost.

### Configuration

A single Web ACL with two rules: a rate-based rule (throttles any IP that exceeds a request threshold) and a geographic restriction (optional — limit to US traffic since this is county-level data).

**Terraform (add to `infra/modules/frontend/` alongside the CloudFront distribution):**

```hcl
# infra/modules/frontend/waf.tf

resource "aws_wafv2_web_acl" "countyiq" {
  name        = "countyiq-rate-limit"
  description = "Rate limiting for CountyIQ CloudFront distribution"
  scope       = "CLOUDFRONT"
  provider    = aws.us_east_1  # WAF for CloudFront must be in us-east-1

  default_action {
    allow {}
  }

  # Rule 1: Rate limiting — block IPs that exceed 2,000 requests in 5 minutes
  rule {
    name     = "rate-limit"
    priority = 1

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit              = 2000      # Requests per 5-minute window per IP
        aggregate_key_type = "IP"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "countyiq-rate-limit"
      sampled_requests_enabled   = true
    }
  }

  # Rule 2: Block non-US traffic (optional — uncomment if desired)
  # rule {
  #   name     = "geo-restrict-us"
  #   priority = 2
  #
  #   action {
  #     block {}
  #   }
  #
  #   statement {
  #     not_statement {
  #       statement {
  #         geo_match_statement {
  #           country_codes = ["US"]
  #         }
  #       }
  #     }
  #   }
  #
  #   visibility_config {
  #     cloudwatch_metrics_enabled = true
  #     metric_name                = "countyiq-geo-block"
  #     sampled_requests_enabled   = true
  #   }
  # }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "countyiq-waf"
    sampled_requests_enabled   = true
  }
}

# Attach WAF to CloudFront distribution
resource "aws_wafv2_web_acl_association" "countyiq" {
  resource_arn = aws_cloudfront_distribution.frontend.arn
  web_acl_arn  = aws_wafv2_web_acl.countyiq.arn
}
```

### Rate Limit Tuning

The 2,000 requests per 5 minutes (400/minute) threshold is generous for normal usage — a user browsing the map generates maybe 20-50 requests per minute (tile loads, API calls, searches). The rate limit is there to catch abuse, not restrict normal users.

| Scenario | Requests/5min | Blocked? |
|---|---|---|
| Normal user browsing map | 50–100 | No |
| User rapidly searching | 100–200 | No |
| Bot scraping API systematically | 2,000+ | Yes |
| DDoS attempt | 10,000+ | Yes |

If legitimate users hit the rate limit (unlikely), increase the threshold in Terraform and re-apply.

### Cost

| Component | Monthly Cost |
|---|---|
| Web ACL (1) | $5.00 |
| Rate-based rule (1) | $1.00 |
| Request inspection (est. 1M requests/month) | $0.60 |
| **Total WAF cost** | **~$6.60/month** |

CloudFront does not charge for requests that WAF blocks, so blocked abuse traffic is free on the CloudFront side.

**Year 1 note:** WAF has no free tier. This $6.60/month applies from day one. If that feels steep for a platform that initially has no users, you can defer WAF and add it later when you make the frontend publicly known. The Terraform is ready — just uncomment and apply.

### CloudWatch Metrics

WAF automatically publishes metrics to CloudWatch:
- `BlockedRequests` — how many requests are being blocked (should be near zero normally)
- `AllowedRequests` — total traffic volume
- `CountedRequests` — requests matching count-only rules

Add a CloudWatch alarm for `BlockedRequests > 1000 in 5 minutes` to alert on active abuse via the existing SNS → Slack pipeline.

---

## Backup & Disaster Recovery

### What Needs Protecting

| Component | Data | Persistence | Risk |
|---|---|---|---|
| **RDS PostgreSQL** | All processed data, entity resolution, Dagster metadata | Persistent (EBS-backed) | Highest — months of scraped/processed data |
| **S3 raw snapshots** | Raw API/scraper responses | Persistent (S3) | Medium — audit trail, replay capability |
| **S3 static site** | Frontend build output | Rebuildable | Low — `npm run build` recreates it |
| **S3 vector tiles** | Pre-generated map tiles | Rebuildable | Low — regenerated from RDS data |
| **EC2 instance** | Dagster runtime, Python venv, config | Rebuildable | Low — user data script rebuilds from scratch |
| **Git repository** | All source code | GitHub (off-site) | Minimal — GitHub is the source of truth |

### RDS Backups (Already Configured)

RDS automated backups are enabled in the database Terraform module:

| Setting | Value |
|---|---|
| Backup retention | 7 days |
| Backup window | 06:00–06:30 UTC (2:00 AM ET — after all scraper jobs finish; matches RDS config in Module: Database) |
| Multi-AZ | No (single-AZ, cost optimization) |
| Storage type | gp3 (durable — replicated within AZ) |

**Point-in-time recovery:** AWS lets you restore the database to any second within the 7-day retention window. If you discover corrupted data on Wednesday, you can restore to Tuesday at 11:59 PM and lose almost nothing.

**Manual snapshots before risky operations:**

```bash
# Before running a major migration or bulk data operation:
aws rds create-db-snapshot \
  --db-instance-identifier york-county-db \
  --db-snapshot-identifier pre-migration-$(date +%Y%m%d)
```

Manual snapshots persist until you delete them (they don't expire with the 7-day window). Cost: $0.095/GB/month for snapshot storage beyond the free allocation.

### S3 Durability

S3 provides 99.999999999% (11 nines) durability. Data loss from S3 is effectively impossible. No additional backup strategy is needed for S3 buckets.

S3 versioning is enabled on the Terraform state bucket (critical — protects against accidental state corruption). Consider enabling it on `york-county-raw` as well for defense against accidental deletions:

```hcl
# infra/modules/database/s3_raw.tf (or wherever the raw data bucket is defined)
resource "aws_s3_bucket_versioning" "raw_data" {
  bucket = aws_s3_bucket.raw_data.id
  versioning_configuration {
    status = "Enabled"
  }
}
```

### EC2 Instance Recovery

The EC2 instance is **fully rebuildable** from the user data script (Bootstrap / User Data Script section). If the instance dies, corrupt, or needs to be replaced:

**Recovery steps:**

```bash
# Step 1: Terminate the broken instance (if still running)
aws ec2 terminate-instances --instance-ids <old-instance-id>

# Step 2: Terraform will detect the missing instance and recreate it
cd infra/
terraform plan    # Shows: 1 to add (EC2 instance)
terraform apply   # Creates new instance, runs user data script

# Step 3: User data script automatically:
#   - Installs Python, Dagster, Playwright, all dependencies
#   - Clones the git repo
#   - Configures systemd services
#   - Starts Dagster webserver + daemon
#   - Installs and configures CloudWatch agent

# Step 4: Verify Dagster is running
aws ssm start-session --target <new-instance-id>
sudo systemctl status dagster-webserver
sudo systemctl status dagster-daemon

# Step 5: Re-enable schedules in Dagster UI
# (Schedules default to OFF on fresh install — enable them manually)
```

**Time to recover:** ~10-15 minutes (instance launch + user data script execution).

**What's NOT lost:** All data is in RDS and S3 — the EC2 instance holds no persistent state. Git repo is on GitHub. Pipeline code is pulled fresh from the repo during bootstrap.

**What IS lost on instance replacement:**
- Dagster run history (stored in RDS `meta` schema — this survives)
- Schedule enabled/disabled state (must be re-enabled manually)
- Any uncommitted code changes on the instance (should not exist if CI/CD is used properly)

### Disaster Recovery Drill

Before go-live (Phase 5), validate the recovery path works:

```
1. Take a manual RDS snapshot
2. Note current record counts for key tables
3. Terminate the EC2 instance
4. Run terraform apply (recreates instance)
5. Verify Dagster starts and connects to RDS
6. Verify data is intact (compare record counts)
7. Enable schedules
8. Trigger one pipeline manually and verify it succeeds
9. Delete the manual snapshot (or keep it as the "known good" baseline)
```

This drill should be part of the Phase 5 validation checklist in the Implementation Guide.

### Recovery Time Summary

| Scenario | Recovery Method | RTO (Time to Recover) | Data Loss |
|---|---|---|---|
| EC2 instance dies | `terraform apply` (recreates) | ~15 minutes | None (no persistent data on EC2) |
| RDS corruption (bad migration, etc.) | Point-in-time restore | ~15-30 minutes | Seconds (restore to any point in last 7 days) |
| RDS instance failure | AWS automatic failover (single-AZ: manual restore from backup) | ~30 minutes | Up to 5 minutes (last backup transaction) |
| Accidental S3 deletion | S3 versioning (restore previous version) | Minutes | None (versioned) |
| Accidental Terraform state corruption | S3 versioning on state bucket | Minutes | None (versioned) |
| Complete AWS account compromise | Contact AWS support; RDS snapshots + S3 versioning + GitHub repo | Hours–days | Minimal (code is on GitHub, data is in backups) |
| Region-wide AWS outage | Wait for recovery (single-region deployment) | Hours | None (data persists through outages) |

### What's Intentionally NOT Included

| Approach | Why Skipped |
|---|---|
| Multi-AZ RDS | Doubles RDS cost (~$25/month). Not justified for a solo-operated platform. |
| Cross-region replication | Adds complexity and cost. York County data doesn't need geographic redundancy. |
| EC2 AMI snapshots | User data script is faster and always up-to-date. AMIs become stale. |
| Backup to non-AWS storage | S3 durability (11 nines) is sufficient. Offsite backup adds cost/complexity for negligible benefit. |

---

## Cost Breakdown

### Year 1 (Free Tier Active)

| Resource | Monthly Cost |
|---|---|
| EC2 t3.micro | $0.00 |
| RDS db.t3.micro (PostgreSQL 16) | $0.00 |
| EBS 20 GB gp3 (EC2) | $0.00 |
| RDS 20 GB gp3 storage | $0.00 |
| RDS automated backups (20 GB) | $0.00 |
| S3 (raw data + static site + tiles, < 5 GB) | $0.00 |
| CloudFront (< 1 TB transfer) | $0.00 (free tier: 1 TB/month) |
| API Gateway (< 1M calls) | $0.00 (free tier: 1M/month) |
| Lambda (< 1M requests) | $0.00 (permanent free tier) |
| Session Manager | $0.00 |
| CloudWatch Logs (~500 MB/month ingest) | $0.00 (free tier: 5 GB) |
| CloudWatch Alarms (5) | $0.00 (free tier: 10) |
| SNS (email) | $0.00 |
| Budgets (1) | $0.00 (free tier: 2) |
| DynamoDB (TF state lock) | $0.00 (free tier: 25 GB) |
| WAF (1 Web ACL + 1 rule + request inspection) | ~$6.60 (no free tier) |
| **Total** | **~$6.60/month** |

> **Note:** WAF is the only component with no free tier. If you prefer $0/month during initial development with no public users, defer WAF and add it when you make the frontend publicly known. The Terraform is ready to apply.

### Year 2+ (Post Free Tier)

| Resource | Monthly Cost |
|---|---|
| EC2 t3.micro (on-demand) | $7.49 |
| RDS db.t3.micro (on-demand) | $12.41 |
| EBS 20 GB gp3 (EC2) | $1.60 |
| RDS 20 GB gp3 storage | $1.60 |
| RDS backup storage (20 GB, beyond free allocation) | $0.00 (first 100% of DB size is free) |
| S3 (est. 10 GB across all buckets) | $0.23 |
| CloudFront (est. 10–50 GB transfer) | $0.85–4.25 |
| API Gateway (est. 10K–100K calls) | $0.04–0.35 |
| Lambda (within permanent free tier for low traffic) | $0.00 |
| CloudWatch Logs (~500 MB ingest + storage) | $0.25–0.50 |
| CloudWatch Alarms (5) | $0.50 |
| SNS | $0.00 |
| Budgets | $0.00 |
| DynamoDB | ~$0.00 (minimal reads) |
| WAF (1 Web ACL + 1 rule + request inspection) | ~$6.60 |
| **Total** | **~$32–36/month** |

### Year 2+ Cost Reduction Options

If $24–25/month feels steep after free tier expires, consider:

| Option | Savings | Notes |
|---|---|---|
| RDS Reserved Instance (1-year, no upfront) | ~35% on RDS compute | Drops RDS to ~$8/month |
| EC2 Reserved Instance (1-year, no upfront) | ~35% on EC2 compute | Drops EC2 to ~$5/month |
| Both reserved | Combined ~$13/month total | vs ~$20 on-demand for both |
| Migrate to db.t4g.micro (Graviton/ARM) | ~15% cheaper | $10.66/month on-demand |

**With both 1-year reserved instances: ~$22–24/month total for the entire platform (including WAF).**

---

## Privacy & Access Control

### Current State: No Auth for MVP

All data ingested in the MVP phase is **already publicly available** — GIS portal data, FEMA flood maps, PennDOT road data, PA Open Data Portal datasets, and assessment records are all published by government agencies for public consumption. CountyIQ aggregates and cross-references this data but does not create new privacy exposure because anyone can already access every individual record through the source agencies' own websites.

There is no authentication layer in the MVP. The frontend is publicly accessible via CloudFront, and the Lambda API serves data without requiring login.

### When Access Controls Become Necessary

Access controls should be introduced **before or alongside Phase 2 sources** that involve sensitive aggregated data:

| Phase 2 Source | Privacy Concern | Mitigation |
|---|---|---|
| Inmate Records (#20) | Aggregated booking/release history creates a de facto criminal record tracker | Require login; rate-limit queries; no bulk export |
| UJS Court Records (#6) | Case filings linked to property ownership and addresses | Same as above; consider excluding from public search, limit to authenticated civic/professional users |
| Sheriff Sales (#9) + Tax Claim (#14) | Financial distress signals tied to property addresses and owner names | Less sensitive individually (already posted publicly) but aggregated timeline creates risk |
| CRIMEWATCH (#19) | Incident data geolocated to neighborhoods; combined with property data creates crime overlay | Standard public safety data, but aggregation with ownership data warrants review |

### Recommended Phased Approach

**Phase 1 (MVP):** No auth. All data is public-record. Ship fast.

**Phase 2 (when court/inmate data arrives):**

- Add Cognito or Clerk authentication (see Future Enhancements: ALB + Cognito)
- Implement role-based tiers: `citizen` (default, rate-limited), `professional` (real estate, legal), `government` (municipal staff)
- Add query auditing: log all API requests with user identity, query parameters, and timestamp to `meta.query_audit_log`
- Rate-limit person-specific lookups (e.g., owner name search limited to 50/hour for citizen tier)

**Phase 3 (72 municipalities, full entity graph):**

- Formal data governance review before launch
- Consider FOIA/RTK compliance implications of aggregated entity graphs
- Monitor PA HB 1822 (Public Servant Data Privacy Act) — if enacted, may require redacting home addresses of law enforcement, judges, and other covered officials from public-facing views

### PA HB 1822 Awareness

The feasibility report (Section: Privacy & Legal Considerations) flags HB 1822, which would restrict public disclosure of home addresses for certain public servants. While not yet enacted as of this writing, the schema design accommodates this: the `staging.parcels` table stores owner data with SCD Type 2 history, making it possible to implement redaction filters as a PostgreSQL VIEW layer (e.g., `public.properties_public` that excludes covered individuals) without modifying underlying data.

### Infrastructure Implications

Adding authentication does not require architectural changes — it's an additive layer:

- **API:** FastAPI middleware for JWT verification (Cognito/Clerk tokens)
- **Frontend:** React auth wrapper (redirect to login for protected routes)
- **CloudFront:** No change needed (auth happens at API layer, not CDN)
- **Cost:** Cognito free tier covers 50,000 MAU (more than sufficient)

The API's flat package structure (`api/routes/`, `api/lib/`) makes it straightforward to add auth middleware without restructuring.

---

## Future Enhancements (Not Implemented)

These are documented for future reference. None are needed for the MVP.

### 1. Automated Cost Kill Switch

**Concept:** A Lambda function triggered by a Budget Action (via SNS) that automatically stops the EC2 instance when spend exceeds a threshold (e.g., $80). This provides a hard stop beyond email alerts.

**Implementation outline:**
- Budget Action triggers SNS topic at $80 threshold
- SNS triggers Lambda function
- Lambda calls `ec2:StopInstances` on the Dagster instance
- Optional: Lambda also attaches a deny-all IAM policy to freeze all resource access
- CloudWatch alarm detects instance stopped → sends notification email

**Why deferred:** Email alerts at $10/$25/$50/$75 provide adequate early warning. The $100 account credit and free tier make runaway costs unlikely in Year 1. Revisit if costs become less predictable.

### 2. NAIP Imagery Pipeline (Phase 2)

**Concept:** Download NAIP orthophotos for York County, store in S3, and serve as a tile layer for change detection analysis.

**Estimated storage:** 10–20 GB per year of coverage, 30–60 GB for multi-year comparison.

### 3. Upgrade to t3.small

**Trigger:** Consistent memory usage > 80% as reported by CloudWatch alarms, especially during concurrent Playwright jobs.

**Cost impact:** $14.98/month (vs $7.49 for t3.micro) post free tier.

### 4. Private VPC with NAT Gateway

**Trigger:** Security requirements demand the EC2 instance has no public IP at all.

**Cost impact:** NAT Gateway costs ~$32/month. Not justified for current scale.

### 5. Dagster Cloud Hybrid

**Trigger:** Need for multi-user access to Dagster UI, or desire to offload webserver/daemon hosting.

**Cost:** Free tier available (limited concurrent runs).

### 6. ALB + Cognito for Dagster UI

**Trigger:** Multiple users need browser access to Dagster UI without SSH/Session Manager.

**Cost:** ALB ~$16/month minimum + Cognito (free tier: 50,000 MAU).

---

## Bootstrap / User Data Script

The EC2 user data script runs on first boot and sets up the entire Dagster environment. This is referenced by the compute module as `user_data.sh`.

### What it installs

| Software | Purpose |
|---|---|
| Python 3.11+ | Dagster + pipeline code runtime |
| pip + venv | Python package management |
| Dagster (webserver, daemon, postgres client libs) | Orchestration |
| Playwright + Chromium | JavaScript-heavy scraping (eFACTS, CRIMEWATCH, PALS, Assessment) |
| pdfplumber | PDF table extraction (YCCD, commissioners minutes, YCPC reports) |
| BeautifulSoup4 + requests | HTML scraping + HTTP client |
| psycopg2-binary | PostgreSQL driver for RDS |
| Alembic | Schema migration management |
| CloudWatch Agent | Memory + disk metrics |
| SSM Agent | Already included in Amazon Linux 2023 |

### What it configures

1. Creates a `dagster` system user (non-root)
2. Sets up a Python virtual environment at `/opt/york-county/venv`
3. Retrieves RDS credentials from Parameter Store
4. Writes Dagster workspace and dagster.yaml configuration
5. Creates systemd services for `dagster-webserver` and `dagster-daemon`
6. Installs and configures CloudWatch Agent
7. Starts all services

### Dagster as systemd services

```ini
# /etc/systemd/system/dagster-webserver.service
[Unit]
Description=Dagster Webserver
After=network.target

[Service]
Type=simple
User=dagster
WorkingDirectory=/opt/york-county
Environment=DAGSTER_HOME=/opt/york-county
EnvironmentFile=/opt/york-county/.env
ExecStart=/opt/york-county/venv/bin/dagster-webserver -h 127.0.0.1 -p 3000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/dagster-daemon.service
[Unit]
Description=Dagster Daemon
After=network.target

[Service]
Type=simple
User=dagster
WorkingDirectory=/opt/york-county
Environment=DAGSTER_HOME=/opt/york-county
EnvironmentFile=/opt/york-county/.env
ExecStart=/opt/york-county/venv/bin/dagster-daemon run
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Note:** The webserver binds to `127.0.0.1:3000` (localhost only). It is not accessible from the network. Access is via Session Manager port forwarding.

### Accessing Dagster UI

```bash
# Start a port-forwarding session via Session Manager
aws ssm start-session \
  --target <instance-id> \
  --document-name AWS-StartPortForwardingSession \
  --parameters '{"portNumber":["3000"],"localPortNumber":["3000"]}'

# Then open in browser:
# http://localhost:3000
```

---

## Operational Runbook

### Daily operations (automated)

Dagster daemon evaluates schedules and sensors every 30 seconds. No manual intervention needed. Check Dagster UI periodically for failed runs.

### Checking Dagster status

```bash
# Connect to instance
aws ssm start-session --target <instance-id>

# Check services
sudo systemctl status dagster-webserver
sudo systemctl status dagster-daemon

# View recent logs
journalctl -u dagster-webserver --since "1 hour ago"
journalctl -u dagster-daemon --since "1 hour ago"
```

### Restarting Dagster

```bash
sudo systemctl restart dagster-webserver
sudo systemctl restart dagster-daemon
```

### Emergency stop (manual cost control)

```bash
# Stop the EC2 instance from your local machine
aws ec2 stop-instances --instance-ids <instance-id>

# Verify it stopped
aws ec2 describe-instances --instance-ids <instance-id> \
  --query 'Reservations[].Instances[].State.Name'
```

**Note:** Stopping the instance stops all Dagster jobs, scrapers, and scheduled runs. No data is lost — EBS volume persists. Restart with `aws ec2 start-instances`.

### Updating pipeline code

```bash
# Connect to instance
aws ssm start-session --target <instance-id>

# Pull latest code (assumes git repo on instance)
cd /opt/york-county/pipelines
git pull origin main

# Run any pending database migrations
source /opt/york-county/.env
alembic upgrade head

# Restart Dagster to pick up changes
sudo systemctl restart dagster-webserver
sudo systemctl restart dagster-daemon
```

### Monitoring RDS storage usage

```bash
# Check RDS storage from your local machine
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name FreeStorageSpace \
  --dimensions Name=DBInstanceIdentifier,Value=york-county-db \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Average \
  --query 'Datapoints[0].Average'
```

Or check the RDS console in AWS. Plan to increase storage (online, no downtime) when usage exceeds 15 GB of 20 GB allocated.

### Connecting to the database

```bash
# Port-forward RDS through EC2 via Session Manager
aws ssm start-session \
  --target <instance-id> \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters '{"host":["<rds-endpoint>"],"portNumber":["5432"],"localPortNumber":["5433"]}'

# In another terminal, connect with psql or any SQL client
psql -h localhost -p 5433 -U dagster_admin -d york_county_intel
```

### Rollback procedures

**Bad Lambda deploy (API broken):**

```bash
# Lambda keeps previous versions. Roll back to the last working version:
aws lambda update-function-code \
  --function-name york-county-api \
  --s3-bucket <if using S3 deploy> \
  # Or re-deploy from git:
cd api/
git checkout HEAD~1 -- .
pip install -r requirements.txt -t package/
cp -r *.py routes/ lib/ package/
cd package && zip -r ../lambda.zip .
aws lambda update-function-code \
  --function-name york-county-api \
  --zip-file fileb://lambda.zip
```

**Bad Dagster deploy (pipelines broken):**

```bash
# On EC2 via SSM:
aws ssm start-session --target <instance-id>

cd /opt/york-county
git log --oneline -5                    # Find the last good commit
git checkout <last-good-sha>            # Roll back
source venv/bin/activate
pip install -e pipelines/
sudo systemctl restart dagster-webserver dagster-daemon
```

**Bad migration (schema broken):**

```bash
# Alembic supports reversible migrations:
cd /opt/york-county/pipelines
source /opt/york-county/venv/bin/activate

# See current migration state
alembic current

# Roll back one migration
alembic downgrade -1

# If the downgrade itself fails, restore from RDS point-in-time recovery:
# AWS Console → RDS → Restore to point in time → pick a timestamp before the migration
```

**Corrupted pipeline data (bad scrape wrote garbage):**

```bash
# SCD Type 2 means bad records don't overwrite good ones — they create new rows.
# Fix by marking the bad rows as superseded:
UPDATE staging.<table>
SET valid_to = NOW()
WHERE valid_from > '<timestamp-of-bad-run>'
AND valid_to IS NULL;

# The previous good rows (with valid_to = timestamp of the bad run) are still there.
# Re-run the pipeline to get fresh data.
```

**Frontend broken (bad React build):**

```bash
# Re-deploy from the previous commit:
cd frontend
git checkout HEAD~1 -- .
npm run build
aws s3 sync dist/ s3://york-county-frontend --delete
aws cloudfront create-invalidation --distribution-id <dist-id> --paths "/*"
```

---

## Open Items

| Item | Status | Notes |
|---|---|---|
| RDS master password | Pending | Generate strong password, store in Parameter Store at `/york-county/rds-password` |
| PostGIS + extensions | Pending | Run `init.sql` after RDS provisioning (see Module: Database section) |
| Terraform state backend bootstrap | Pending | Create S3 bucket + DynamoDB table manually before first `terraform init` |
| Verify `inmatelocator.yorkcountypa.gov` | Pending | DNS failed during testing — check from local browser. Marked ❌ in daily schedule table. |
| Verify sheriff sales URLs | Pending | County website reorganized, old URLs redirect incorrectly. Marked ⚠️ in daily schedule table. |
| Live-test PennDOT Open Data (#5) | Pending | Same ArcGIS REST API pattern as GIS Portal (#1) but not live-tested. Marked ⚠️ in weekly schedule table. Should work — verify during Phase 3 Step 3.2 (source #6 in build order). |
| Schema migrations strategy | **Decided: Alembic** | Versioned migrations, local Docker Postgres for testing, LLM-generated migration files |
| Pipeline code repository structure | **Decided: Monorepo, assets by source type** | See Pipeline Code Structure section |
| Frontend | **Decided: React + MapLibre + Deck.gl, S3/CloudFront, Lambda API** | See Frontend Architecture section |
| Entity resolution approach | **Decided: Deterministic PostgreSQL (pg_trgm)** | Tiered matching, source-agnostic schema, Zingg upgrade path documented |
| Deployment pipeline (CI/CD) | **Decided: GitHub Actions + OIDC** | Path-filtered workflows; zero stored AWS credentials; see CI/CD section |
| Neon account | Created but no longer needed | Cancel/delete if desired — RDS replaces it |
