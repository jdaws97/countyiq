# Phase 2: Database Schema & Migrations

**Goal:** All database tables exist. Alembic is configured. The schema matches what the pipelines expect.

**Time estimate:** 1-2 hours

**Prerequisites:** Phase 1 complete. RDS is available. Extensions and schemas are created.

### Step 2.1: Set Up Alembic

Reference: Infrastructure Plan, Schema Migrations (Alembic) section.

```bash
cd pipelines/

# Alembic is already in pyproject.toml dependencies
pip install -e ".[dev]"

# Initialize Alembic
alembic init migrations
```

Configure `alembic.ini` and `migrations/env.py` as specified in the Infrastructure Plan.

### Step 2.2: Create the Initial Migration

This is the "baseline" migration that creates all tables needed for MVP sources.

**Tables to create (in this migration):**

**`staging` schema:** (Cleaned, normalized, change-tracked — NO `raw` schema; raw data goes to S3 only)
- `parcels` — GIS parcel data with SCD Type 2 (valid_from/valid_to)
- `assessment_properties` — Assessment database records (SCD Type 2)
- `flood_zones` — FEMA flood hazard boundaries
- `pa_open_data` — State-level datasets
- `penndot_roads` — PennDOT road/bridge data
- `penndot_projects` — PennDOT project records
- `municipalities` — Municipal boundaries from GIS
- `school_districts` — School district boundaries from GIS
- `zoning_districts` — Zoning boundaries from GIS

**`public` schema:** (Entity-resolved, query-ready)
- `owners` — Resolved owner entities (entity resolution output)
- `owner_source_links` — Links between owners and source records
- `properties` — **VIEW** (not a table) joining staging.parcels + staging.assessment_properties on PIDN

**`meta` schema:** (Application metadata — NOT Dagster internals. Dagster has its own `dagster` database.)
- `pipeline_status` — One row per source, updated by Dagster sensor after each run
- `infra_metrics` — EC2/RDS CloudWatch metrics, written by Dagster sensor every 5 min
- `data_quality_checks` — Pass/fail results from Dagster asset checks
- See Infrastructure Plan, **Meta Schema DDL** section for full CREATE TABLE statements

```bash
# Generate the migration
alembic revision -m "initial_schema_mvp_sources"

# Edit the generated file with the table definitions
# (reference Infrastructure Plan: Entity Resolution schema + Pipeline Code Structure)

# Test locally first with Docker Postgres
docker compose up -d postgres
alembic upgrade head
alembic downgrade base
alembic upgrade head
docker compose down
```

### Step 2.3: Apply Migration to RDS

```bash
# Set up SSM port forwarding to RDS
aws ssm start-session \
  --target <instance-id> \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters '{"host":["<rds-endpoint>"],"portNumber":["5432"],"localPortNumber":["5433"]}'

# In another terminal:
cd pipelines/
DATABASE_URL="postgresql://dagster_admin:<password>@localhost:5433/york_county_intel" \
  alembic upgrade head
```

> **Checkpoint:** Connect to RDS. `\dt staging.*` shows all staging tables. `\dt public.*` shows owners, owner_source_links, properties. All tables have the expected columns including `valid_from`/`valid_to` on SCD Type 2 tables.

---
