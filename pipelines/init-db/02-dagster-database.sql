-- Dagster run, event, and schedule history is isolated from product data.
SELECT 'CREATE DATABASE dagster'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'dagster')\gexec
