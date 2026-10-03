#!/usr/bin/env bash
set -euo pipefail

# Give local pipeline work the DML it needs without exposing the PostgreSQL
# bootstrap superuser. Run this after every Alembic upgrade to cover new tables.
pipeline_user="${DATABASE_PIPELINE_USER:-}"
pipeline_password="${DATABASE_PIPELINE_PASSWORD:-}"
database_owner="${POSTGRES_USER:-dagster_admin}"
database_name="${POSTGRES_DB:-countyiq}"

for identifier in "$pipeline_user" "$database_owner" "$database_name"; do
    if ! [[ "$identifier" =~ ^[a-z_][a-z0-9_]{0,62}$ ]]; then
        echo "Database names and users must be simple PostgreSQL identifiers" >&2
        exit 1
    fi
done
if [[ ${#pipeline_password} -lt 32 || "$pipeline_password" == *CHANGE_ME* ]]; then
    echo "DATABASE_PIPELINE_PASSWORD must be a non-placeholder value of at least 32 characters" >&2
    exit 1
fi

psql \
    --set=ON_ERROR_STOP=1 \
    --username "$database_owner" \
    --dbname "$database_name" \
    --set=pipeline_user="$pipeline_user" \
    --set=pipeline_password="$pipeline_password" \
    --set=database_owner="$database_owner" <<'SQL'
SELECT format('CREATE ROLE %I NOLOGIN', :'pipeline_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'pipeline_user') \gexec

SELECT format(
    'ALTER ROLE %I WITH NOLOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS',
    :'pipeline_user',
    :'pipeline_password'
) \gexec
SELECT format(
    'GRANT CONNECT, TEMPORARY ON DATABASE %I TO %I',
    current_database(),
    :'pipeline_user'
) \gexec
SELECT format('GRANT USAGE ON SCHEMA public, staging, meta TO %I', :'pipeline_user') \gexec
SELECT format('REVOKE CREATE ON SCHEMA public, staging, meta FROM %I', :'pipeline_user') \gexec
-- Login is lent only during a protected local pipeline session.
-- PostgreSQL 16 requires ownership to refresh a materialized view. Scheduled
-- enrichment owns this rebuildable result only, not its source tables.
SELECT format('ALTER MATERIALIZED VIEW public.entity_candidate_pairs OWNER TO %I', :'pipeline_user')
WHERE to_regclass('public.entity_candidate_pairs') IS NOT NULL \gexec
SELECT format(
    'GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public, staging, meta TO %I',
    :'pipeline_user'
) \gexec
SELECT format(
    'GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public, staging, meta TO %I',
    :'pipeline_user'
) \gexec

SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public, staging, meta '
    'GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO %I',
    :'database_owner',
    :'pipeline_user'
) \gexec
SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public, staging, meta '
    'GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO %I',
    :'database_owner',
    :'pipeline_user'
) \gexec
SQL
