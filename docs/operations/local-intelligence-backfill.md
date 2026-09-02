# Local Intelligence Backfill and VPS Handoff

CountyIQ may perform the York intelligence backfill on a controlled PC before
the VPS exists. The portable unit is not the PostgreSQL database alone: it is
the exact reviewed Git commit, the application-database dump, the governed raw
source archives, the raw LLM transcripts, and the signed canary/backfill
receipts.

This workflow does not weaken `intelligence-rollout.md`. Human review, bounded
canaries, price ceilings, rejection review, and a separate full-backfill
authorization remain required. Pass 4 remains excluded.

## 1. Prepare persistent local storage

Use the development PostgreSQL service on port 5433, but keep archives outside
the container so rebuilding it cannot erase provenance:

```bash
cd /home/jdaws/countyiq
mkdir -p archives/raw archives/llm outputs/backfill-exports receipts
mkdir -p .dagster/storage/artifacts .dagster/storage/compute_logs

export DATABASE_HOST=localhost
export DATABASE_PORT=5433
export DATABASE_NAME=countyiq
export DATABASE_USER=dagster_admin
export DATABASE_PASSWORD=localtest
export DAGSTER_HOME="$PWD/pipelines"
export DAGSTER_LOCAL_ARTIFACT_STORAGE_DIR="$PWD/.dagster/storage/artifacts"
export DAGSTER_COMPUTE_LOGS_DIR="$PWD/.dagster/storage/compute_logs"
export COUNTYIQ_LOCAL_RAW_ARCHIVE_DIR="$PWD/archives/raw"
export COUNTYIQ_ARCHIVE_DIR="$PWD/archives/llm"
export COUNTYIQ_ARCHIVE_STRICT=true
```

`COUNTYIQ_LOCAL_RAW_ARCHIVE_DIR` is the explicit PC-only alternative to R2 for
source payloads. Production must leave it unset and use the reviewed R2
endpoint and credentials.

Keep the Dagster daemon running while launching refresh jobs so the success and
failure sensors can write authentic run receipts to `meta.job_run_status`:

```bash
cd /home/jdaws/countyiq/pipelines
.venv/bin/dagster-daemon run -m countyiq.definitions
```

In a second shell with the same environment, submit each refresh through the
daemon-managed run launcher:

```bash
cd /home/jdaws/countyiq/pipelines
.venv/bin/dagster job launch -m countyiq.definitions -j <job_name>
```

The daemon and job processes must use the same database and Dagster storage
environment. Do not use `dagster job execute` for receipt-bearing refreshes: a
direct CLI execution has no external run origin, so it is visible in Dagster's
run history but deliberately ignored by run-status sensors and cannot populate
the application's source-health receipt table.

Keep every `COUNTYIQ_PASS{0-4}_ENABLED` value false during migration, source
refresh, and deterministic enrichment. A funded key does not authorize spend.

Do not point `pytest` tests marked `integration` at the database being prepared
for export. Those tests deliberately exercise append-only inference ledgers and
therefore leave audit fixtures behind; run them only against a disposable test
database/volume. The normal pipeline verification command excludes them with
`-m "not integration"`; the pipeline pytest configuration applies that marker
filter by default as an additional fail-safe.

## 2. Back up, migrate, and refresh without inference

Create a custom-format dump before applying migrations. Record its SHA-256,
then upgrade to the repository's current Alembic head:

```bash
cd /home/jdaws/countyiq/pipelines
docker compose up -d postgres-test

DB_CONTAINER="$(docker compose ps -q postgres-test)"
docker exec -e PGPASSWORD=localtest "$DB_CONTAINER" \
  pg_dump -h localhost -p 5432 -U dagster_admin -d countyiq \
  --format=custom --file=/tmp/countyiq-before-041.dump
docker exec "$DB_CONTAINER" \
  pg_restore --list /tmp/countyiq-before-041.dump >/dev/null
docker cp "$DB_CONTAINER:/tmp/countyiq-before-041.dump" \
  ../outputs/countyiq-before-041.dump
docker exec "$DB_CONTAINER" rm -f -- /tmp/countyiq-before-041.dump
sha256sum ../outputs/countyiq-before-041.dump

DATABASE_URL=postgresql://dagster_admin:localtest@localhost:5433/countyiq \
  .venv/bin/alembic upgrade head
```

Run the governed source jobs needed by the backfill and then
`deterministic_enrichment_refresh`. Local raw archival must be strict and every
source-policy denial remains a denial. Do not run paid passes merely because a
source refresh completed.

## 3. Estimate and canary locally

Follow `intelligence-rollout.md` exactly. Run one manual job at a time:

| Stage | Job |
|---|---|
| Pass 0 | `proceedings_extraction_refresh` |
| Pass 1 + deterministic bridge | `entity_verification_refresh` |
| Pre-Pass 2 safety rebuild | `deterministic_enrichment_refresh` |
| Pass 2 | `signal_validation_refresh` |
| Post-Pass 2 projection rebuild | `deterministic_enrichment_refresh` |
| Pass 3 | `brief_generation_refresh` |
| Pass 3b | `owner_briefs_refresh` |

The Pass 1 job now rebuilds both Pass 0-derived development signals and the
Pass 1-derived owner projection. Keep the explicit deterministic safety rebuild
before Pass 2 anyway; it costs no model tokens and prevents validation of a
stale signal snapshot.

For every canary and full backfill, create the separate durable authorization
described in `intelligence-rollout.md` while the pass is disabled, store it
under `receipts/`, and configure
`COUNTYIQ_PASS{N}_BACKFILL_AUTHORIZATION_FILE` before enabling the pass. Pass
3 and Pass 3b share the Pass 3 authorization balance unless the operator
explicitly approves and creates separate authorization files. Disable the
selected pass immediately after each job and preserve the preflight,
provider-cost, authorization, and review receipts.

If preflight reports `test_history_count` or `test_rejection_count`, do not
delete those append-only rows in place. Preserve a fresh dump of the current
database, restore the last verified pre-test snapshot into a disposable sibling
database, migrate and run deterministic refreshes there, and promote it only
after the no-spend preflight is clean.

## 4. Export the accepted local backfill

Stop local Dagster writers, disable all paid passes, and require a clean exact
commit. The exporter refuses a database schema that differs from the
repository's single Alembic head, any unresolved integrity issue, a validation
rejection in the preceding 24 hours, a dirty worktree, or a missing raw/LLM
archive tree.

```bash
cd /home/jdaws/countyiq
docker/export-local-backfill.sh \
  --output-dir "$PWD/outputs/backfill-exports" \
  --archive-root "$PWD/archives" \
  --database-container "$(docker compose -f pipelines/docker-compose.yml ps -q postgres-test)" \
  --confirm-quiesced

docker/verify-local-backfill-export.sh \
  --bundle "$PWD/outputs/backfill-exports/<export-id>" \
  --database-container "$(docker compose -f pipelines/docker-compose.yml ps -q postgres-test)"
```

The container option deliberately uses the PostgreSQL 16 client bundled with
the database service. This avoids creating an unreadable or incomplete handoff
when the PC's host `pg_dump`/`pg_restore` major version is older than the
server. Omit the option only when the host clients match the server major
version.

Copy the complete bundle and the exact commit SHA to independent storage. Do
not commit the dump, archive tarball, API keys, or review receipts to Git.

## 5. Import on the first VPS

Import is deliberately a reviewed first-host operation, not an automatic
deployment side effect:

1. Check out the bundle's exact `code_ref` and verify the bundle again.
2. Configure the new VPS environment and R2 buckets, but do not start API or
   Dagster writers.
3. Start only PostgreSQL on a new volume and take a baseline backup.
4. Restore the dump into a disposable database first with `pg_restore
   --exit-on-error --no-owner --no-privileges`; verify that the database is at
   the checked-out repository's Alembic head, then verify row counts, integrity
   views, citations, and API contracts against that database.
5. Promote only the verified restored database, rerun the pipeline/API role
   grant scripts, and upload `raw/` to the raw-archive R2 bucket.
6. Place `llm/` under `/opt/countyiq/archives`, run the normal R2 backup, and
   complete a restore drill.
7. Only then run the exact-SHA initial deployment and verify `/api/ready` and
   `/api/ops/health` before exposing traffic.

Never use `pg_restore --clean` against the only database. The live import
procedure should be finalized against the actual VPS and its fresh volume;
until that host exists, the verified portable bundle is the handoff boundary.
