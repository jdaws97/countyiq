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

The current head is revision 050. Revision 031 adds executable source-rights
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
portable deterministic parcel screening. Revision 037 adds the bounded
`meta.job_run_status` projection used by application health; Dagster retains
the full run history in its separate database. Revision 038 adds append-only
LLM inference history, contradiction and resolution ledgers, and
`active_inference_id` provenance links on the five model-backed serving or
staging projections.

Revision 039 closes PostgreSQL's statement-level `TRUNCATE` path on all three
append-only intelligence audit tables.

Revision 040 adds atomic human contradiction resolution, resolution provenance,
and the aggregate integrity-health view. Existing model-backed rows with no
`active_inference_id` are copied into immutable history as
`legacy_unverified` and retracted from serving; source tables and accepted
history are untouched. This data retraction is intentionally fail-closed and
is not automatically reversed by `downgrade()`.

Revision 041 adds the append-only
`meta.intelligence_validation_rejections` ledger and its 24-hour aggregate
status view. Deterministic evidence, identity-membership, and citation gate
failures are now durable operator evidence rather than log-only events.

Revision 042 records explicit product-owner risk acceptance for the three
official municipal listings that deliver documents through GoDaddy. It enables
Franklintown Borough, Newberry Township, and Washington Township collection,
allowlists only the exact `https://img1.wsimg.com` document origin, retains raw
archives privately, and keeps person-level display and raw export disabled.

Revision 043 records a source-row-scoped exception for the nonresponsive robots
endpoints on those same three official listing origins. It does not allow an
explicit disallow and does not extend to the GoDaddy PDF CDN, whose live robots
policy remains mandatory.

Revision 044 adds the trigram expression index used by mapped-address search.
Revision 045 removes the unused County Scout runtime and its empty registry
tables and policy row. The migration aborts if Scout data or policy audit
receipts exist so retirement cannot silently delete evidence.

Revision 046 records PA DOS refresh timestamps. Revision 047 adds the
rule-first contradiction auto-resolution and sampled-review audit ledgers.
Revision 048 adds radar history, normalized address matching, and Pass 2
configuration fingerprints. Revision 049 distinguishes refused automatic
resolutions in the review queue. Revision 050 closes the TRUNCATE path on the
new audit ledgers and provides a forward-safe downgrade bridge for revision
049's outcome normalization.

## Production

Production runs migrations only through the release orchestrator, inside the
commit-tagged Dagster image that contains the lockfile and Alembic
configuration:

```bash
cd /opt/countyiq/docker
sudo env COUNTYIQ_DEPLOY_REF=<reviewed-40-character-commit-sha> \
  COUNTYIQ_ENV_FILE=/opt/countyiq/.env ./deploy.sh
```

The orchestrator stops API and Dagster, verifies their database sessions are
gone, creates and remotely verifies the pre-deploy backup, and only then runs
the chain. Once migration execution starts, any failure leaves application
services stopped for reviewed recovery—even if `alembic_version` did not
advance. Rollback is not assumed safe merely because `downgrade()` exists;
data loss, partial application, and PostgreSQL locks are reviewed per revision.

## Creating a Revision

```bash
cd pipelines
.venv/bin/alembic revision -m "short description"
```

Use the next repository naming convention, set `down_revision` to the current
head, and add a focused migration or contract test when behavior can regress.
