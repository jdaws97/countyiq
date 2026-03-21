-- CountyIQ Database Initialization Script
-- Run once after terraform apply, via SSM into EC2:
--   psql -h <rds-endpoint> -U dagster_admin -d york_county_intel -f init.sql

-- Enable spatial extensions
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Create application schemas (public schema exists by default)
CREATE SCHEMA IF NOT EXISTS staging;   -- Cleaned, normalized, SCD Type 2 data
CREATE SCHEMA IF NOT EXISTS meta;      -- Pipeline status, infra metrics, data quality

-- Create Dagster's separate database (isolates internal metadata from app data)
-- Note: This will fail if run inside a transaction block. Run with psql -f or ON_ERROR_STOP=off.
SELECT 'CREATE DATABASE dagster' WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = 'dagster'
)\gexec

-- Meta schema tables
CREATE TABLE IF NOT EXISTS meta.pipeline_status (
    source_name         TEXT PRIMARY KEY,
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
    error_message       TEXT,
    next_scheduled_run  TIMESTAMPTZ,
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS meta.infra_metrics (
    id                  SERIAL PRIMARY KEY,
    checked_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metrics             JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_infra_metrics_checked
    ON meta.infra_metrics (checked_at);

CREATE TABLE IF NOT EXISTS meta.data_quality_checks (
    id                  SERIAL PRIMARY KEY,
    source_name         TEXT NOT NULL,
    check_name          TEXT NOT NULL
                        CHECK (check_name IN ('record_count_nonzero', 'schema_valid', 'freshness_ok', 'row_count_delta')),
    passed              BOOLEAN NOT NULL,
    details             TEXT,
    checked_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dq_checks_source
    ON meta.data_quality_checks (source_name, checked_at DESC);
