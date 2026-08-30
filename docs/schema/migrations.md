# Schema Migrations

Alembic is the sole authority for application table, index, view, function,
and constraint changes. The ordered chain lives in
`pipelines/alembic/versions/`; `alembic_version` records the deployed revision.

## Rules

- Never edit a migration that may already have run. Add a new revision.
- Write explicit `upgrade()` and `downgrade()` behavior and review the emitted
  SQL for locks, destructive changes, and data conversion risk.
- Do not run migrations from API startup or Dagster module import. Deployment
  applies them explicitly before code that depends on the new schema is used.
- Test the complete chain against the dedicated PostGIS test database. Never
  point destructive tests at development or production data.
- An LLM may help draft or review a migration, but generated DDL is not an
  acceptance oracle. The author owns the schema design and database test.

## Local Chain Check

The dedicated Compose file is `pipelines/docker-compose.yml` and exposes
`postgres-test` on port 5433:

```bash
cd pipelines
docker compose up -d postgres-test

DATABASE_URL=postgresql://dagster_admin:localtest@localhost:5433/countyiq \
  .venv/bin/alembic upgrade head

.venv/bin/alembic current
.venv/bin/alembic history
```

The container runs the ordered scripts under `pipelines/init-db/` on a new test
volume before Alembic. Use `docker compose down -v` only for an intentional
reset of that specific test volume.

Contract tests create their own `countyiq_test` database and apply the full
migration chain. The exact command is maintained in
`docs/operations/testing.md`.

The current head is revision 036. Revision 031 adds executable source-rights
policy and audit tables, four site-readiness staging families, and the serving
score column; it also expires the two paused York project-service layers and
clears rebuildable score rows. Revision 032 adds per-municipal-body rights,
append-only decision receipts, collection-health state, use-specific
authorization, and a paused County Scout policy. Its 122 municipal policies
cover all 72 municipalities. Revision 033 adds exact origin allowlists and
pauses Rep'd-, Google Drive-, and explicit-robots-backed municipal paths.
Revision 034 records reviewed same-organization redirect/document origins and
pauses three GoDaddy-CDN-only paths. The resulting registry has 110 conditional
and 12 paused municipal policies. Revision 035 is a forward reconciliation for
databases that applied revision 032 before the County Scout seed was added; it
restores the explicit paused policy so upgraded and fresh databases converge.
Revision 036 adds immutable policy snapshots/fingerprints, county policy scope,
the governed PA DEP source, and `staging.environmental_diligence_sites` for
portable deterministic parcel screening.

## Production

Production runs migrations inside the Dagster image, which contains the
pipeline lockfile and Alembic configuration:

```bash
cd /opt/countyiq/docker
docker compose exec dagster-daemon \
  alembic -c /opt/countyiq/pipelines/alembic.ini upgrade head
```

Before applying a destructive or long-running revision, take a verified
backup and inspect the current revision. Rollback is not assumed safe merely
because a `downgrade()` function exists; data loss and PostgreSQL locks must be
considered per migration.

## Creating a Revision

```bash
cd pipelines
.venv/bin/alembic revision -m "short description"
```

Use the next repository naming convention, set `down_revision` to the current
head, and add a focused migration or contract test when behavior can regress.
