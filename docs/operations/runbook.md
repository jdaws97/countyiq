# Operational Runbook

## Operational Runbook

### Daily operations (automated)

Dagster daemon evaluates schedules and sensors every 30 seconds. No manual intervention needed. Check Dagster UI periodically for failed runs.

### Checking Dagster status

```bash
# Connect to VPS
ssh countyiq

# Check services
cd /opt/countyiq
docker compose ps
docker compose logs dagster --tail=100
```

### Restarting Dagster

```bash
ssh countyiq
cd /opt/countyiq
docker compose restart dagster
```

### Emergency stop (all services)

```bash
# SSH to VPS and stop all containers
ssh countyiq
cd /opt/countyiq
docker compose down
```

**Note:** Stopping all containers stops Dagster jobs, scrapers, and scheduled runs. No data is lost — Postgres data is on a Docker volume. Restart with `cd /opt/countyiq && docker compose up -d`.

### Updating pipeline code

```bash
# Connect to VPS
ssh countyiq

# Pull latest code
cd /opt/countyiq
git pull origin main

# Rebuild and restart containers (picks up code + dependency changes)
docker compose build
docker compose up -d

# Run any pending database migrations
docker compose exec dagster alembic -c /opt/countyiq/pipelines/alembic.ini upgrade head
```

### Monitoring Postgres storage usage

```bash
# Check database size from VPS
ssh countyiq
docker exec countyiq-postgres psql -U dagster_admin -d countyiq -c "SELECT pg_size_pretty(pg_database_size('countyiq'));"
```

### Monitoring system resources

```bash
# Quick overview of container resource usage
ssh countyiq
docker stats --no-stream

# Disk usage
df -h

# Memory usage
free -m
```

### Connecting to the database

```bash
# SSH tunnel from your local machine to Postgres on the VPS
ssh -L 5433:localhost:5432 countyiq

# In another terminal, connect with psql or any SQL client
psql -h localhost -p 5433 -U dagster_admin -d countyiq
```

### Rollback procedures

**Bad API deploy (API broken):**

```bash
# Roll back API container to the previous image:
ssh countyiq
cd /opt/countyiq
docker compose pull api
docker compose up -d api
```

If the latest image is the broken one, check out the previous commit and rebuild:

```bash
ssh countyiq
cd /opt/countyiq
git log --oneline -5                    # Find the last good commit
git checkout <last-good-sha>
docker compose build api
docker compose up -d api
```

**Bad Dagster deploy (pipelines broken):**

```bash
# On VPS via SSH:
ssh countyiq

cd /opt/countyiq
git log --oneline -5                    # Find the last good commit
git checkout <last-good-sha>            # Roll back
docker compose build dagster
docker compose up -d dagster
```

**Bad migration (schema broken):**

```bash
# Alembic supports reversible migrations:
ssh countyiq
cd /opt/countyiq

# See current migration state
docker compose exec dagster alembic -c /opt/countyiq/pipelines/alembic.ini current

# Roll back one migration
docker compose exec dagster alembic -c /opt/countyiq/pipelines/alembic.ini downgrade -1

# If the downgrade itself fails, restore from backup:
rclone copy r2:countyiq-backups/postgres/countyiq-YYYY-MM-DD.dump /tmp/
docker exec -i countyiq-postgres pg_restore -c -d countyiq /tmp/countyiq-YYYY-MM-DD.dump
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

Cloudflare Pages keeps all previous deployments. Roll back via the Cloudflare dashboard:

Cloudflare Pages -> Deployments -> select previous deployment -> Rollback
