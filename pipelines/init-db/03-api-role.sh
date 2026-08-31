#!/usr/bin/env bash
set -euo pipefail

# Idempotently create/refresh the API login and read grants.  The Postgres
# entrypoint runs this on a new volume; the deployment runbook invokes it again
# after migrations so existing volumes and newly-created tables stay covered.
api_user="${DATABASE_API_USER:-}"
api_password="${DATABASE_API_PASSWORD:-}"
database_owner="${POSTGRES_USER:-dagster_admin}"
database_name="${POSTGRES_DB:-countyiq}"

if [[ ! "$api_user" =~ ^[a-z_][a-z0-9_]{0,62}$ ]]; then
    echo "DATABASE_API_USER must be a simple PostgreSQL identifier" >&2
    exit 1
fi
if [[ ${#api_password} -lt 32 || "$api_password" == *CHANGE_ME* ]]; then
    echo "DATABASE_API_PASSWORD must be a non-placeholder value of at least 32 characters" >&2
    exit 1
fi

psql \
    --set=ON_ERROR_STOP=1 \
    --username "$database_owner" \
    --dbname "$database_name" \
    --set=api_user="$api_user" \
    --set=api_password="$api_password" \
    --set=database_owner="$database_owner" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN', :'api_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'api_user') \gexec

SELECT format(
    'ALTER ROLE %I WITH LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS',
    :'api_user',
    :'api_password'
) \gexec
SELECT format('ALTER ROLE %I SET default_transaction_read_only = on', :'api_user') \gexec
SELECT format('ALTER ROLE %I SET statement_timeout = %L', :'api_user', '15s') \gexec
SELECT format(
    'ALTER ROLE %I SET idle_in_transaction_session_timeout = %L',
    :'api_user',
    '15s'
) \gexec

SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'api_user') \gexec
SELECT format('GRANT USAGE ON SCHEMA public, staging, meta TO %I', :'api_user') \gexec
SELECT format('REVOKE CREATE ON SCHEMA public, staging, meta FROM %I', :'api_user') \gexec
SELECT format(
    'GRANT SELECT ON ALL TABLES IN SCHEMA public, staging, meta TO %I',
    :'api_user'
) \gexec

SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT SELECT ON TABLES TO %I',
    :'database_owner',
    :'api_user'
) \gexec
SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA staging GRANT SELECT ON TABLES TO %I',
    :'database_owner',
    :'api_user'
) \gexec
SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA meta GRANT SELECT ON TABLES TO %I',
    :'database_owner',
    :'api_user'
) \gexec
SQL
