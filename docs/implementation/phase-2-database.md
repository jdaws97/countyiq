# Phase 2: Database Schema & Migrations

**Goal:** All database tables exist. Alembic is configured. The schema matches what the pipelines expect.

**Time estimate:** 1-2 hours

**Prerequisites:** Phase 1 complete (VPS provisioned, Docker Compose ready). Docker Postgres running locally (`docker compose up -d postgres-test`).

### Schema Ownership

| Owner | What it creates |
|---|---|
| `init.sql` | Extensions (postgis, pg_trgm, pg_stat_statements), schemas (staging, meta), `dagster` database |
| **Alembic** | **All table-level objects** — staging.\*, public.\*, meta.\*, views, functions, indexes |

`init.sql` runs first (via `initialize.sh`), then Alembic runs on top. This split exists because extensions and cross-database DDL can't be managed by Alembic.

### Step 2.1: Set Up Alembic

Alembic is already configured in the repo:

```
pipelines/
├── alembic.ini                          # Config (DATABASE_URL override from env)
├── alembic/
│   ├── env.py                           # Migration environment
│   ├── script.py.mako                   # Template for new migrations
│   └── versions/
│       └── 001_initial_schema_mvp_sources.py
├── docker-compose.yml                   # Local PostGIS for testing
└── pyproject.toml                       # Dependencies
```

```bash
cd pipelines/

# Install dependencies
pip install -e ".[dev]"
```

### Step 2.2: Create the Initial Migration

The baseline migration (`001_initial_schema_mvp_sources.py`) is already written. It creates:

**`staging` schema:** (Cleaned, normalized, change-tracked — NO `raw` schema; raw data goes to R2 only)
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
- `infra_metrics` — VPS/Postgres system metrics, written by Dagster sensor every 5 min
- `data_quality_checks` — Pass/fail results from Dagster asset checks

**Functions:** `staging.parid_to_pidn()`, `public.normalize_name()`, `public.normalize_address()`

### Step 2.2b: Test Locally with Docker Postgres

```bash
cd pipelines/

# Start local PostGIS 16
docker compose up -d postgres-test

# Run migration against local DB
export DATABASE_URL="postgresql://dagster_admin:localtest@localhost:5433/countyiq"
alembic upgrade head

# Verify reversibility
alembic downgrade base
alembic upgrade head

# Inspect
PGPASSWORD=localtest psql -h localhost -p 5433 -U dagster_admin -d countyiq \
  -c "\dt staging.*" -c "\dt public.*" -c "\dv public.*" -c "\dt meta.*"

# Clean up
docker compose down -v
```

### Step 2.3: Apply Migration to Production

On the VPS, the init script handles this automatically — it runs `init.sql` then `alembic upgrade head` in sequence. No manual step needed.

For subsequent migrations (after initial setup), apply via SSH:

```bash
# Option 1: Run directly on the VPS
ssh countyiq 'docker exec countyiq-dagster alembic upgrade head'

# Option 2: Via SSH tunnel + local alembic
ssh -L 5433:localhost:5432 countyiq
# In another terminal:
cd pipelines/
DATABASE_URL="postgresql://dagster_admin:<password>@localhost:5433/countyiq" \
  alembic upgrade head
```

> **Checkpoint:** Connect to Postgres. `\dt staging.*` shows 9 staging tables. `\dt public.*` shows owners, owner_source_links. `\dv public.*` shows the properties view. `\dt meta.*` shows 3 meta tables. All tables have the expected columns including `valid_from`/`valid_to` on SCD Type 2 tables.

---
