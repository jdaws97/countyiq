# Meta Schema

Alembic migrations are the schema authority. The ordered scripts under
`pipelines/init-db/` enable PostgreSQL extensions, create the `staging` and
`meta` schemas and database roles; they do not own
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
and reader; full Dagster run history now remains in SQLite under the PC's
`DAGSTER_HOME`. See `docs/operations/health-dashboard.md` for the actual health
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

## Runtime state separation

The primary `countyiq` PostgreSQL database holds application schemas and data.
Dagster run history, events, and compute logs live locally beneath
`~/.local/state/countyiq/pipeline/dagster` by default.

The local runner synchronously projects completed outcomes into
`meta.job_run_status` and source-refresh ledgers. The API reads those compact
tables, while operators use the PC's run/event history for step-level detail.
No running sensor or server-side Dagster database is required. Historical
Dagster state retained during a host transition is outside the active schema
and daily primary-database backup model.

## Initialization

Production migrations run through `docker/deploy.sh` using the one-shot
`migrate` image. For a reviewed operator inspection, use the protected Compose
environment from the [runbook](../operations/runbook.md):

```bash
ciq run --rm migrate alembic -c /opt/pipelines/alembic.ini current
```

For clean test-database instructions, use `docs/operations/testing.md`.
