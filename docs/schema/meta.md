# Meta Schema

Alembic migrations are the schema authority. The ordered scripts under
`pipelines/init-db/` enable PostgreSQL extensions, create the `staging` and
`meta` schemas, and create the separate Dagster database; they do not own
application tables.

Migration `001_initial_schema_mvp_sources.py` created three speculative
observability tables:

- `meta.pipeline_status`
- `meta.infra_metrics`
- `meta.data_quality_checks`

No asset, sensor, API route, or frontend page ever read or wrote them, so
migration `030_remove_unused_meta_tables.py` removes them. Its upgrade refuses
to drop any table containing unexpected deployed rows. Revision 037 later adds
the narrowly scoped `job_run_status` projection that has an explicit writer
and reader; full Dagster run history remains in the separate `dagster`
database. See `docs/operations/health-dashboard.md` for the actual health
contract.

Current operational governance and audit state is deliberately stored in `meta`:

- `source_rights` and append-only `source_rights_audit` govern source-wide
  acquisition, retention, derived serving, person display, and export. The
  audit table's legacy `acquisition_method` field records both collection
  methods and explicit downstream actions such as `use:derived_product`.
  Revision 036 adds county scope plus a policy version, canonical JSON snapshot,
  and SHA-256 fingerprint to each new receipt;
- `municipality_source_rights` and append-only
  `municipality_source_audit` apply the same fail-closed model to each
  exact municipal body/listing. `allowed_origins` bounds redirects, document
  downloads, browser documents, and XHR/fetch endpoints to separately reviewed
  origins;
- `municipality_source_health` records current access/document health without
  changing or implying permission;
- `job_run_status` records only the latest outcome per Dagster job and latest
  successful completion for application health. It is not a replacement for
  Dagster's full event log; and
- `intelligence_inference_history`, `intelligence_contradictions`, and
  `intelligence_contradiction_resolutions` form the append-only audit boundary
  for model-backed decisions. Serving projections link to an accepted history
  row with `active_inference_id`; unchanged-evidence decision flips remain
  quarantined for explicit review, and any human resolution is itself recorded
  append-only. `intelligence_integrity_status` aggregates unresolved age,
  provenance coverage, and projection/history mismatches without exposing
  source payloads. Migration 040 labels pre-gate rows `legacy_unverified`,
  archives them, and retracts them from serving.
- `intelligence_validation_rejections` records every model output rejected by
  deterministic evidence, membership, or citation validation. The table is
  update/delete/truncate protected; `intelligence_validation_rejection_status`
  exposes only total, last-24-hour count, and latest timestamp.

Migrations 031 through 036 own the governance tables and current policy;
migrations 038 through 041 own the intelligence integrity ledgers and operator
resolution path. Runtime code may
update health and append decisions, but it must not invent policy rows, expand
origins, or update audit history.

## Database Separation

The production Postgres container initializes two databases:

- `countyiq`: application schemas and data
- `dagster`: Dagster run, event-log, and schedule storage

The API never queries the `dagster` database. Existing run-status sensors
project the minimum latest-job state into `meta.job_run_status`; operators use
the loopback-bound Dagster webserver or container logs for step-level and
historical detail.

## Initialization

From `docker/`, after the Postgres container is healthy:

```bash
docker compose exec dagster-daemon \
  alembic -c /opt/countyiq/pipelines/alembic.ini upgrade head
```

For clean test-database instructions, use `docs/operations/testing.md`.
