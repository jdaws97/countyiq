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
# SSH to VPS and stop all running project containers without removing them
ssh countyiq
cd /opt/countyiq/docker
docker compose stop -t 60
```

Stopping all containers interrupts in-flight requests and jobs. Named volumes
remain attached, but an in-flight operation may not have committed. Restart
with `docker compose up -d --wait`. Never use `docker compose down -v` in
production; `-v` deletes the named database volume.

### Deploying a reviewed release

```bash
# Connect to VPS
ssh countyiq

# Fetch and inspect the exact reviewed commit that will be deployed
cd /opt/countyiq
git fetch --prune origin
git log --oneline --decorate HEAD..origin/main
export COUNTYIQ_DEPLOY_REF=<reviewed-40-character-commit-sha>
git checkout --detach "$COUNTYIQ_DEPLOY_REF"

# Preflight is read-only. It validates the exact checkout, environment,
# Compose graph, pass gates, role separation, R2 target, and bucket-lock receipt.
env COUNTYIQ_DEPLOY_REF="$COUNTYIQ_DEPLOY_REF" \
  COUNTYIQ_ENV_FILE=/opt/countyiq/.env \
  /opt/countyiq/docker/deploy.sh --check

# The release command owns build, quiescence, backup, migration, readiness,
# and the receipt. Use --initial only before the first recorded release.
sudo env COUNTYIQ_DEPLOY_REF="$COUNTYIQ_DEPLOY_REF" \
  COUNTYIQ_ENV_FILE=/opt/countyiq/.env \
  /opt/countyiq/docker/deploy.sh
```

The script refuses a dirty tree or backward release, tags the API and Dagster
images with the exact commit, stops API/Dagster writers, verifies that their
database sessions are gone, uploads and reads back the R2 completion manifest,
then runs Alembic. A migration-started failure leaves application services
stopped for review. Success atomically updates
`COUNTYIQ_IMAGE_TAG` in the protected environment and
`/var/lib/countyiq/releases/current.env`; retain every timestamped receipt.
The persisted tag keeps later Compose restarts on the recorded images. Keep the
checkout detached at the reviewed commit.

Before an ordinary release, a successful off-host restore drill must be no
older than `COUNTYIQ_RESTORE_DRILL_MAX_AGE_DAYS`. The first release uses
`deploy.sh --initial`, followed immediately by a post-deploy backup and restore
drill before the daily timer is enabled. See
[Backup and restore](backup-and-restore.md).

Paid intelligence rollout is a separate manual procedure. Follow
`docs/operations/intelligence-rollout.md`; do not enable a pass or use the full
pipeline job during an ordinary deploy.

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
docker system df

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
# Only after reviewing that the last-good API is compatible with schema_after
# in the current release receipt, reuse its retained commit-tagged image.
# Do not run deploy.sh from an older checkout: it intentionally rejects a
# backward migration path.
ssh countyiq
cd /opt/countyiq/docker
export COUNTYIQ_IMAGE_TAG=<recorded-last-good-40-character-sha>
docker image inspect "countyiq-api:$COUNTYIQ_IMAGE_TAG"
docker compose --env-file /opt/countyiq/.env up -d --no-deps --wait api
curl --fail --silent --show-error https://api.countyiq.com/api/ready
```

**Bad Dagster deploy (pipelines broken):**

```bash
# Apply the same schema-compatibility review, then reuse the retained image for
# both processes so the daemon and code server cannot drift.
ssh countyiq
cd /opt/countyiq/docker
export COUNTYIQ_IMAGE_TAG=<recorded-last-good-40-character-sha>
docker image inspect "countyiq-dagster:$COUNTYIQ_IMAGE_TAG"
docker compose --env-file /opt/countyiq/.env up -d --no-deps --wait \
  dagster-webserver dagster-daemon
```

**Bad migration (schema broken):**

```bash
# Inspect the stopped failure state and both receipt revisions first:
ssh countyiq
cd /opt/countyiq/docker

# See current migration state
docker compose run --rm migrate \
  alembic -c /opt/pipelines/alembic.ini current

# Do not automatically downgrade. Many production data migrations are
# intentionally not safely reversible. Keep writers stopped and restore the
# receipt's pre-deploy backup into a new database or volume. Verify the new
# target and cut over only under an incident plan; never use pg_restore --clean
# against the only production database.
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
