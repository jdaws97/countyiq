# Backup and Restore

`docker/backup.sh` creates PostgreSQL custom-format dumps for the CountyIQ and
Dagster databases, validates their archives, writes portable SHA-256 sidecars,
and uploads both files to the configured private R2 remote. It also backs up
the intelligence archive under the configured retention policy.

## Daily verification

The cron monitor must alert when the command exits nonzero or when no new dump
and checksum objects appear for either database. A successful upload is not a
restore test.

## Non-destructive restore drill

Run this at least quarterly and after material PostgreSQL, PostGIS, or backup
changes. Use a recent dump and a disposable database name; never restore over
the live database.

```bash
ssh countyiq
sudo -i
set -a
source /opt/countyiq/.env
set +a
install -d -m 700 /var/lib/countyiq-restore
cd /var/lib/countyiq-restore
rclone copyto r2:countyiq-backups/postgres/countyiq-YYYY-MM-DD.dump countyiq.dump
rclone copyto r2:countyiq-backups/postgres/countyiq-YYYY-MM-DD.dump.sha256 countyiq.dump.sha256
sed -i 's/countyiq-YYYY-MM-DD.dump/countyiq.dump/' countyiq.dump.sha256
sha256sum --check countyiq.dump.sha256
pg_restore --list countyiq.dump >/dev/null

docker exec countyiq-postgres dropdb -U "$DATABASE_USER" --if-exists countyiq_restore_drill
docker exec countyiq-postgres createdb -U "$DATABASE_USER" countyiq_restore_drill
docker cp countyiq.dump countyiq-postgres:/tmp/countyiq-restore.dump
docker exec countyiq-postgres pg_restore \
  -U "$DATABASE_USER" --exit-on-error --no-owner \
  -d countyiq_restore_drill /tmp/countyiq-restore.dump
docker exec countyiq-postgres psql \
  -U "$DATABASE_USER" -d countyiq_restore_drill \
  -c "SELECT COUNT(*) AS current_properties FROM public.properties;"
docker exec countyiq-postgres rm -f /tmp/countyiq-restore.dump
docker exec countyiq-postgres dropdb -U "$DATABASE_USER" countyiq_restore_drill
rm -f countyiq.dump countyiq.dump.sha256
```

Record the dump date, restore duration, row-count sanity checks, and operator in
the operations log.

## Production recovery

1. Preserve the failed volume and take a snapshot when storage is healthy.
2. Stop API, Dagster daemon, and Dagster webserver so there are no writers.
3. Verify and restore the selected dump to a new database or volume using the
   same procedure as the drill.
4. Run Alembic only to the application revision that will be deployed, refresh
   the API role grants, and execute the API contract smoke tests against the
   restored database.
5. Switch the stack to the restored database only after those checks pass.
6. Retain the old database until the recovery is accepted and a new verified
   backup has completed.

Do not use `pg_restore --clean` against the only production database. The exact
cutover depends on whether recovery uses a sibling database, a new volume, or a
replacement host and requires an approved incident plan.
