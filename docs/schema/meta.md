# Meta Schema & Database Initialization

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
