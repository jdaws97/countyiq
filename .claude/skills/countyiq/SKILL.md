---
name: countyiq
description: |
  CountyIQ development skill for building and extending the CountyIQ civic intelligence platform (York County, PA). Use this skill whenever the task involves: writing Dagster pipeline assets or sensors, creating or modifying FastAPI Lambda API routes, editing Terraform infrastructure modules, working with the PostgreSQL schema (staging/public/meta), building React frontend components, configuring GitHub Actions CI/CD workflows, or adding new data sources to the platform. Also trigger when the user references the CountyIQ monorepo, any of its architecture docs, York County data sources, entity resolution, vector tiles, or the /ops/health dashboard. If the user says "build the pipeline for X" or "add source Y" or "write the API route for Z" — this skill applies.
---

# CountyIQ Development Skill

You're working on **CountyIQ**, a civic intelligence platform that aggregates public data for York County, PA. It's a solo-dev project (Jarod) with a monorepo (`jarod/countyiq` on GitHub) containing Terraform infrastructure, Dagster pipelines, a FastAPI Lambda API, and a React frontend.

This skill exists because the architecture has a lot of cross-cutting constraints that are easy to violate. Rather than reading thousands of lines of docs every time, use this as your routing layer — it tells you the rules that matter for each task type and points you to the right doc file when you need detail.

## Docs Directory

All architecture docs live in `docs/`. Read individual files on-demand — never load the whole directory at once. The original monolith files still exist at the repo root but the `docs/` files are the working copies.

### Core Reference

| File | What it covers | When to read |
|---|---|---|
| `docs/architecture-overview.md` | System diagram, high-level flow | Starting any task — orient yourself |
| `docs/decisions.md` | Decision log + acknowledged tradeoffs | Before proposing architectural changes — check if it was already decided |
| `docs/cost.md` | Year 1/2 cost breakdown, cost traps | Before adding any AWS service |
| `docs/privacy.md` | Auth gate, Phase 2 sensitivity, PA HB 1822 | Before exposing person-level data |
| `docs/open-items.md` | Remaining TODOs | When looking for what to work on next |

### Infrastructure

| File | What it covers |
|---|---|
| `docs/infrastructure/services.md` | AWS services used (summary table) |
| `docs/infrastructure/database.md` | RDS config, free tier, storage, backups, local access |
| `docs/infrastructure/networking.md` | VPC, security groups, IAM roles/policies |
| `docs/infrastructure/compute.md` | EC2 instance, Elastic IP, CloudWatch alarms |
| `docs/infrastructure/terraform.md` | Terraform project structure, state backend |
| `docs/infrastructure/cicd.md` | GitHub Actions workflows, OIDC federation, deploy flows |
| `docs/infrastructure/waf.md` | WAF rate limiting config and tuning |
| `docs/infrastructure/backup-recovery.md` | RDS backups, S3 durability, EC2 recovery, DR drills |
| `docs/infrastructure/bootstrap.md` | EC2 user data script, systemd services |

### Schema

| File | What it covers |
|---|---|
| `docs/schema/meta.md` | Meta schema DDL (pipeline_status, infra_metrics, data_quality_checks), CHECK constraints, Dagster sensor code, database init SQL |
| `docs/schema/strategy.md` | Schema layout (staging/public/meta), `public.properties` VIEW definition, PIDN/PARID crosswalk |
| `docs/schema/migrations.md` | Alembic setup, migration patterns, testing with Docker Postgres |

### Pipelines

| File | What it covers |
|---|---|
| `docs/pipelines/dagster-config.md` | Dagster components, memory budget, schedules |
| `docs/pipelines/code-structure.md` | Monorepo layout, asset patterns, definitions.py, shared lib, jobs/schedules, pyproject.toml |
| `docs/pipelines/entity-resolution.md` | Matching logic, normalization, schema, Dagster asset, MVP vs Phase 2 scope |
| `docs/pipelines/data-retention.md` | S3 raw snapshots, SCD2 in RDS, log pruning, storage projections |
| `docs/pipelines/backfill.md` | Day 1 backfill strategy, source categories, execution order |

### API

| File | What it covers |
|---|---|
| `docs/api/lambda-api.md` | Lambda config, FastAPI app, CloudFront routing, connection pooling, cold start, deployment |

### Frontend

| File | What it covers |
|---|---|
| `docs/frontend/architecture.md` | React + MapLibre + Deck.gl stack, UI mockup, core views, tile strategy |

### Operations

| File | What it covers |
|---|---|
| `docs/operations/alerting.md` | Slack integration, Dagster sensors, retry policy, CloudWatch→Slack forwarder |
| `docs/operations/health-dashboard.md` | /ops/health page, status logic, API response structure, infra metrics sensor |
| `docs/operations/testing.md` | 3-layer testing strategy, schema validation, asset checks |
| `docs/operations/runbook.md` | Daily ops, restart procedures, emergency stop, rollback procedures |

### Implementation (Build Order)

| File | What it covers |
|---|---|
| `docs/implementation/README.md` | How to use the implementation guide |
| `docs/implementation/phase-0-1-setup.md` | Local env setup, AWS bootstrap, Terraform apply |
| `docs/implementation/phase-2-database.md` | Alembic setup, initial migration |
| `docs/implementation/phase-3-pipelines.md` | Dagster framework, MVP source assets, Day 1 backfill |
| `docs/implementation/phase-4-api-frontend.md` | FastAPI Lambda, React frontend, Slack setup |
| `docs/implementation/phase-5-cicd-golive.md` | GitHub Actions, validation, go-live |
| `docs/implementation/expansion-roadmap.md` | Phase 2/3 sources, platform upgrades, multi-county |
| `docs/implementation/file-inventory.md` | Quick reference of all repo files |

### Reference Appendices

| File | What it covers |
|---|---|
| `docs/data-source-feasibility.md` | All 22 data sources: URLs, formats, feasibility ratings |
| `docs/data-model-phase2-appendix.md` | **Phase 2/3 only** — future entity types, UUIDs, Cognito. Do NOT use for MVP decisions. |
| `docs/future-enhancements.md` | Potential upgrades (kill switch, NAIP, t3.small, NAT, Dagster Cloud, ALB+Cognito) |

## Hard Rules

These are the constraints that have caused bugs in every review round. Internalize them before writing any code.

### Identifiers

- **PIDN** (13-char, from GIS) is the canonical parcel identifier everywhere. Not PARID, not `parcel_id`.
- `owner_id` is `SERIAL`, not UUID. Internal-only, no cross-system federation.
- The PARID→PIDN conversion function is in `docs/schema/strategy.md`.

### Schema

- **No `raw` schema in RDS.** Raw data goes to `s3://york-county-raw/<source>/<date>/`. The first RDS schema is `staging`.
- `staging.*` — cleaned, normalized, SCD Type 2 (valid_from/valid_to). All source data lives here after parsing.
- `public.*` — entity-resolved output and views. `public.properties` is a **VIEW** (not a table) joining `staging.parcels` + `staging.assessment_properties` on PIDN. Both sides filter `valid_to IS NULL` (SCD Type 2 current records).
- `meta.*` — application metadata (pipeline_status, infra_metrics, data_quality_checks). App-owned, written by Dagster sensors, read by Lambda API. NOT Dagster internals.
- Dagster's internal tables live in a separate `dagster` database on the same RDS instance.
- CHECK constraints enforce valid values on meta columns. See `docs/schema/meta.md` for the DDL.

### Lambda Networking

Lambda runs in a VPC and can ONLY reach RDS on port 5432. It cannot call:
- Parameter Store / SSM
- CloudWatch API
- Any AWS service endpoint

This means:
- **DB credentials** come from Terraform-set encrypted environment variables, not runtime Parameter Store calls.
- **Infrastructure metrics** come from `meta.infra_metrics` (written by a Dagster sensor on EC2, which has internet access), not from CloudWatch API calls.
- The `api/lib/database.py` reads `DATABASE_HOST`, `DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD` from `os.environ`. That's it.

### Routing

All Lambda API routes live under `/api/*` because CloudFront only sends `/api/*` to API Gateway.

| CloudFront path | Origin | What serves it |
|---|---|---|
| `/api/*` | API Gateway → Lambda | FastAPI (dynamic queries) |
| `/tiles/*` | S3 tiles bucket | Pre-generated .pbf files (7-day cache) |
| `/*` (default) | S3 frontend bucket | React app (1-hour cache) |

Consequences:
- The ops health endpoint is `GET /api/ops/health`, not `/ops/health`. The React page at `/ops/health` is a client-side route that calls `/api/ops/health`.
- **Tiles are NOT served by Lambda.** They're pre-generated by the Dagster tile pipeline and uploaded to S3. The API has no tile routes.
- FastAPI's `main.py` mounts routers at `/api/parcels`, `/api/owners`, `/api/search`, `/api/ops`. No `/api/tiles` router.

### Entity Resolution

- **MVP scope:** parcels + assessment only (2 sources). Match GIS `owner_full` against assessment `owner_name` using PIDN join + pg_trgm fuzzy fallback.
- **Phase 2:** each new source gets added to the resolution graph incrementally. The Dagster asset dynamically detects which staging tables have data.
- The deps list in the Dagster asset should only include sources that actually exist. Don't reference `deeds`, `business_filings`, etc. until those pipelines are built.
- Full detail: `docs/pipelines/entity-resolution.md`

### Data Freshness

- All 6 MVP sources run on **weekly** schedules. There are no daily schedules at MVP launch.
- Daily schedules are defined in code but **disabled** — they're Phase 2 target configurations.
- Entity resolution runs after weekly sources complete (Sunday).

### Phase 2 Auth Gate

Before exposing person-level or sensitive data (CRIMEWATCH, Sheriff Sales, Tax Claim, Inmate Records, UJS Court Records), implement:
- Cognito/Clerk authentication
- Role-based tiers (citizen, professional, government)
- Query audit logging (`meta.query_audit_log`)
- Rate-limited person lookups

Sources 1–2 in the Phase 2 build order (PA DOS Business Entities, PLCB Liquor Licenses) are safe without auth. The auth gate sits between priority 2 and priority 3 in `docs/implementation/expansion-roadmap.md`.

## Task-Specific Guidance

### Building a New Pipeline

1. **Read:** `docs/pipelines/code-structure.md` (monorepo layout, asset patterns) → `docs/implementation/expansion-roadmap.md` (13-step checklist)

2. **County config (MANDATORY):** All county-specific values (URLs, filter strings, thresholds) MUST come from `pipelines/york_county/lib/county_config.py`. Never hardcode county names, source URLs, or record count thresholds in assets or parsers.
   - Add any new source-specific fields to `CountyConfig` dataclass if needed
   - Asset functions call `get_county_config()` at runtime (not import time)
   - Parsers accept county-specific params (e.g., `county_filter`) with a default for backward compatibility
   - S3 archive paths use `county.s3_prefix` (e.g., `york/bulk/plcb/`)

3. **File placement:**
   - Asset: `pipelines/assets/<type>/<source>.py` (type = `arcgis/`, `scrapers/`, `bulk/`, `pdf/`, `enrichment/`)
   - Parser: `pipelines/lib/parsers/<source>.py`
   - Test fixture: `pipelines/tests/fixtures/<source>_sample.json`
   - Test: `pipelines/tests/test_<source>_parser.py`

4. **Schema rules:**
   - Target table is always `staging.<source_name>` (e.g., `staging.liquor_licenses`)
   - Include SCD Type 2 columns: `valid_from TIMESTAMPTZ DEFAULT NOW()`, `valid_to TIMESTAMPTZ` (NULL = current)
   - Raw response goes to `s3://york-county-raw/<prefix>/<source>/<date>/` before any parsing

5. **Schedule:** Add to `pipelines/jobs/schedules.py`. Check `docs/pipelines/dagster-config.md` for the assigned time slot and whether it's MVP or Phase 2.

6. **Checks to add:** record count > 0, no schema drift, row count delta < 50%.

7. **Unverified sources:** PennDOT (#5) is not live-tested. Sheriff Sales (#9) has changed URLs. Inmate Records (#20) has DNS failure. Verify before building these.

### Building an API Route

1. **Read:** `docs/api/lambda-api.md` → `docs/implementation/phase-4-api-frontend.md` (Step 4.1)

2. **Rules:**
   - All routes under `/api/*` (CloudFront constraint)
   - Router file goes in `api/routes/<name>.py`
   - Mount in `api/main.py` with `app.include_router(router, prefix="/api/<name>")`
   - Query `public.properties` (the VIEW) for property data, not `staging.parcels` directly
   - Use `pidn` as the parcel identifier in all endpoints, not `parcel_id`
   - Column names from the view: `pidn`, `owner_full`, `propadr`, `aprtotal`, `municipality`, `school_dis`, `acres`, `class`, `geom` (from parcels) + `permits`, `delinquent_taxes`, `value_history` (from assessment)
   - Database connection via `os.environ` (DATABASE_HOST, etc.) — no Parameter Store, no CloudWatch calls

3. **Health endpoint pattern:** See `docs/operations/health-dashboard.md`. Queries `meta.pipeline_status` and `meta.infra_metrics` only.

### Modifying Terraform Infrastructure

1. **Read:** `docs/infrastructure/terraform.md` + the specific `docs/infrastructure/<module>.md` for what you're changing.

2. **Rules:**
   - State backend: `countyiq-terraform-state` S3 bucket + `countyiq-terraform-locks` DynamoDB table
   - All EC2 paths use `/opt/york-county` (not `/opt/dagster`)
   - S3 bucket names: `york-county-frontend`, `york-county-tiles`, `york-county-raw`
   - Lambda env vars for DB creds are set in Terraform (not runtime Parameter Store)
   - OIDC federation for GitHub Actions — no stored AWS credentials
   - Default VPC, no NAT Gateway

3. **CI/CD context:** See `docs/infrastructure/cicd.md` for the three deployment workflows and the OIDC trust policy.

### Working with Entity Resolution

1. **Read:** `docs/pipelines/entity-resolution.md` (full section including schema, matching tiers, Dagster asset, and known limitations).

2. **MVP contract:** Only `staging.parcels` and `staging.assessment_properties`. The Dagster asset checks `information_schema.tables` to detect available sources dynamically.

3. **Adding a source to resolution:** Add the source to the deps list in `enrichment/owners.py`, add a matching block to the SQL that joins the new staging table on PIDN or name+address similarity, and add the source_type to `owner_source_links`.

4. **Key tables:** `public.owners` (resolved entities, SERIAL PK) and `public.owner_source_links` (links to every source record with confidence scores).

### Frontend Development

1. **Read:** `docs/frontend/architecture.md` for the stack, UI mockup, and core views.

2. **Stack:** React + MapLibre GL JS + Deck.gl. Static site hosted on S3, served via CloudFront.

3. **API calls:** All fetch to `/api/*` (same CloudFront domain, no CORS issues). Tiles loaded from `/tiles/parcels/{z}/{x}/{y}.pbf` (MapLibre vector tile source pointing at CloudFront).

4. **Ops Health page:** React route at `/ops/health`, fetches `GET /api/ops/health`, renders green/yellow/red status grid.

## Quick Reference

### Meta Schema

DDL with CHECK constraints: `docs/schema/meta.md`

- `meta.pipeline_status` — one row per source, CHECK on `status` and `schedule_type`, non-negative counts/durations
- `meta.infra_metrics` — JSONB metrics blob, auto-pruned to 24 hours
- `meta.data_quality_checks` — CHECK on `check_name`

### Connection Pooling

Lambda reuses a module-level connection (`_conn`) across warm invocations. Reserved concurrency capped at 10. Connection budget: Lambda 10, Dagster 3–5, sensors 2–3, migrations 1, psql 1–2 = ~20 of 50 max. Details: `docs/api/lambda-api.md`

### Rollback Procedures

Five scenarios in `docs/operations/runbook.md`: bad Lambda deploy (alias swap), bad Dagster deploy (git revert + restart), bad migration (reverse SQL), corrupted pipeline data (SCD2 valid_to expiry + re-run), broken frontend (S3 previous version restore).

### Cost Awareness

Year 1: ~$6.60/month (WAF only; RDS + EC2 on free tier). Year 2+: ~$32–36/month.

Don't add NAT Gateways (~$32/mo), VPC Endpoints (~$7/mo each), ALBs (~$16/mo), or multi-AZ RDS unless there's a strong reason. See `docs/cost.md` and `docs/decisions.md` (Acknowledged Tradeoffs).

### Slack Integration

Workspace: `CountyIQ` (countyiq.slack.com). Three channels, three webhooks:
- `#alerts-critical` → `/york-county/slack-webhook-critical` (phone notifications ON)
- `#alerts-warning` → `/york-county/slack-webhook-warning`
- `#pipeline-runs` → `/york-county/slack-webhook-pipeline`

Webhook URLs in Parameter Store, read by EC2/Dagster only (NOT Lambda). Details: `docs/operations/alerting.md`
