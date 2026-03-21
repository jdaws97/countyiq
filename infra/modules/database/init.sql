-- CountyIQ Database Initialization Script
-- Run once after terraform apply via: sudo /opt/york-county/initialize.sh
--
-- This script handles ONLY what Alembic cannot:
--   1. Extensions (require superuser-like privileges, run before migrations)
--   2. Schemas (Alembic also creates these idempotently, but init.sql ensures
--      they exist before the first migration runs)
--   3. The separate 'dagster' database (cross-database DDL, not migration-scoped)
--
-- All table-level objects (staging.*, public.*, meta.*) are owned by Alembic.
-- See pipelines/alembic/versions/001_initial_schema_mvp_sources.py

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Create application schemas (public schema exists by default)
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS meta;

-- Create Dagster's separate database (isolates internal metadata from app data)
-- Note: \gexec runs the generated SQL; safe to re-run (no-op if DB exists)
SELECT 'CREATE DATABASE dagster' WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = 'dagster'
)\gexec
