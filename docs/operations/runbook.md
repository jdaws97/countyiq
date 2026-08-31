# Operational Runbook

### Daily operations (automated)

Dagster daemon evaluates schedules and sensors every 30 seconds. No manual intervention needed. Check Dagster UI periodically for failed runs.

### Checking Dagster status

```bash
# Connect to VPS
ssh countyiq

# Check services
cd /opt/countyiq/docker
docker compose ps
docker compose logs dagster-webserver dagster-daemon --tail=100
```

### Restarting Dagster

```bash
ssh countyiq
cd /opt/countyiq/docker
docker compose restart dagster-webserver dagster-daemon
```

### Emergency stop (all services)

```bash
# SSH to VPS and stop all containers
ssh countyiq
cd /opt/countyiq/docker
docker compose down
```

**Note:** Stopping all containers stops Dagster jobs, scrapers, and scheduled runs. No data is lost — Postgres data is on a Docker volume. Restart with `cd /opt/countyiq/docker && docker compose up -d`.

### Updating pipeline code

```bash
# Connect to VPS
ssh countyiq

# Fetch and inspect the exact reviewed commit that will be deployed
cd /opt/countyiq
git fetch --prune origin
git log --oneline --decorate HEAD..origin/main
export COUNTYIQ_DEPLOY_REF=<reviewed-40-character-commit-sha>
git checkout --detach "$COUNTYIQ_DEPLOY_REF"
cd /opt/countyiq/docker

# Build first. Leave the currently running release intact if a build fails.
docker compose build

# Back up the database before applying migrations.
sudo /opt/countyiq/docker/backup.sh

# Start the database, apply migrations with the new image, and refresh the
# non-superuser runtime roles' grants before replacing application containers.
docker compose up -d postgres
docker compose run --rm migrate
docker compose exec postgres /docker-entrypoint-initdb.d/02-runtime-role.sh
docker compose exec postgres /docker-entrypoint-initdb.d/03-api-role.sh

# Replace application containers only after migrations succeed.
docker compose up -d --remove-orphans
docker compose ps
curl --fail --silent --show-error https://api.countyiq.com/api/ready
```

Record the deployed commit and the backup object in the release log. Keep the
checkout detached at the reviewed commit; do not deploy an unreviewed moving
branch tip.

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
# Check out the previously recorded commit, rebuild only the affected service,
# and wait for its health check before considering the rollback complete.
ssh countyiq
cd /opt/countyiq
git checkout --detach <recorded-last-good-40-character-sha>
cd /opt/countyiq/docker
docker compose build api
docker compose up -d --no-deps --wait api
curl --fail --silent --show-error https://api.countyiq.com/api/ready
```

**Bad Dagster deploy (pipelines broken):**

```bash
# On VPS via SSH:
ssh countyiq

cd /opt/countyiq
git checkout --detach <recorded-last-good-40-character-sha>
cd /opt/countyiq/docker
docker compose build dagster-webserver dagster-daemon
docker compose up -d --no-deps --wait dagster-webserver dagster-daemon
```

**Bad migration (schema broken):**

```bash
# Alembic supports reversible migrations:
ssh countyiq
cd /opt/countyiq/docker

# See current migration state
docker compose run --rm migrate \
  alembic -c /opt/pipelines/alembic.ini current

# Review the migration's downgrade implementation before running it. Many
# production data migrations are intentionally not safely reversible.
docker compose run --rm migrate \
  alembic -c /opt/pipelines/alembic.ini downgrade -1

# If downgrade is unsafe or fails, stop writers and restore the pre-deploy
# backup into a new database/volume. Verify its SHA-256 sidecar and run
# pg_restore --list before the destructive cutover. Do not use pg_restore -c
# against the only production database while application services are active.
```

See [Backup and restore](backup-and-restore.md) for the tested restore and
cutover procedure.

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
