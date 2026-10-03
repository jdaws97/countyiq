# Schema and Identifier Strategy

Alembic migrations under `pipelines/alembic/versions/` are the database
authority. Documentation describes intent; it does not replace deployed DDL.

## Schemas

| Schema    | Purpose                                                                                                           | Representative objects                                                                                                                                                                                                                                                                                                          |
| --------- | ----------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `staging` | Parsed source records and version history                                                                         | `parcels`, `tax_claims`, `zoning_overlays`, `economic_development_parks`, `soils`, `local_traffic_counts`                                                                                                                                                                                                                       |
| `public`  | Product-facing entities, evidence, briefs, events, scores, and views                                              | `owners`, `development_momentum`, `parcel_briefs`, `parcel_events`, `intelligence_events`, `properties`                                                                                                                                                                                                                         |
| `meta`    | Intelligence-pass state and immutable inference history, scraper state, source governance, and application health | `intelligence_passes`, `intelligence_inference_history`, `intelligence_contradictions`, `intelligence_contradiction_resolutions`, `scrape_checkpoints`, `scraper_http_cache`, `source_rights`, `source_rights_audit`, `municipality_source_rights`, `municipality_source_audit`, `municipality_source_health`, `job_run_status` |

Most mutable source tables use SCD2 timestamps: `valid_to IS NULL` identifies
the current version. Some product tables are upserted, append-oriented, or
fully rebuildable instead. The migration and owning asset define the behavior
for each table.

Raw source evidence is stored outside Postgres only when the ingestion asset
calls `S3StorageResource`; see `docs/pipelines/data-retention.md`. There is no
`raw` database schema. Dagster's internal run and event tables live in SQLite
under the PC's `DAGSTER_HOME`, separate from `countyiq.meta`.

Migration 030 removes the unused early tables `meta.pipeline_status`,
`meta.infra_metrics`, and `meta.data_quality_checks`. Current operational state
comes from local Dagster history, source tables, and registered asset checks.
The local runner publishes completed job and per-asset source outcomes
synchronously to the application health ledgers.

Migration 031 adds executable source authorization and its append-only audit
receipts; adds the four site-readiness staging families; adds
`public.development_momentum.site_readiness_score`; expires the two paused York
layers; removes their rebuildable signals/evidence; and clears momentum rows so
no stale score survives until the next enrichment rebuild.

Migration 032 adds use-specific enforcement and municipal-source governance.
The policy table identifies one exact configured body/source, the audit table
records every allow/deny decision and is append-only, and the health table
stores current listing/document outcomes separately from permission. Health
never grants permission.

Migrations 033 and 034 add exact municipal origin allowlists, record reviewed
same-organization HTTPS aliases, and pause paths whose useful documents depend
on restricted or unreviewed vendor delivery. Redirect destinations and browser
document/API requests must remain inside these allowlists; runtime health cannot
expand them.

Migration 045 removes the unused County Scout API/pipeline prototype and its
empty registry tables. Its upgrade fails closed if any Scout data or policy
audit receipts exist, preventing retirement from silently discarding records.

Migration 037 adds `meta.job_run_status`, a deliberately small projection of
the latest Dagster outcome per job and its latest successful completion. The
full run/event history stays in the PC's local Dagster storage; this projection
lets the source-data read-only API fail closed on stale or failed refreshes.

Migration 038 separates model history from current serving state. Every gated
Pass 0–3 result is appended to `meta.intelligence_inference_history`; current
rows in proceeding extractions, entity graph, evidence, parcel briefs, and
owner briefs point to the accepted record through `active_inference_id`. A
semantic decision that changes while its evidence-only `source_hash` is
unchanged is appended as quarantined and recorded in
`meta.intelligence_contradictions`; it cannot overwrite the active projection.
New source evidence may create a new accepted version. History, contradictions,
and explicit human resolutions are database-enforced append-only tables.

Migration 039 adds statement-level truncate guards to that boundary.

Migration 040 makes the boundary operable. It adds explicit model,
human-resolution, and legacy-unverified origins; links every human resolution
to the accepted version it creates; archives and retracts pre-gate projections;
and exposes the aggregate `meta.intelligence_integrity_status` view used by
health checks and alerts. Resolution and projection mutation occur in one
writer transaction; the read-only API cannot adjudicate model output.

Migration 041 makes deterministic gate failures durable. Rejected model output
metadata and validator errors are appended to
`meta.intelligence_validation_rejections`; the rejected payload is never
served, and the aggregate 24-hour rejection status feeds health, alerting, and
the no-spend canary preflight.

## Serving Objects

`public.properties` is a view over current parcel rows with nullable legacy
assessment fields. The removed assessment scraper does not populate new data;
parcel values and sale attributes come from the county GIS source, delinquency
comes from `staging.tax_claims`, and parcel change history comes from SCD2
versions plus `public.parcel_events`.

`public.intelligence_events` is a rebuildable serving ledger. It combines
parcel events, tax-claim transitions, and cached proceeding interpretations.
Rebuilding the ledger does not invoke a model.

## Identifiers

- `pidn` is the canonical parcel identifier and the cross-source parcel join
  key. Keep it as text; leading zeroes and source formatting matter.
- `owner_id` is the API identifier for a row in `public.owners`.
  `owner_resolution` upserts by `canonical_name`, so the ID remains stable
  across ordinary rebuilds while that owner remains present. If an owner is
  removed and later recreated, or cluster identity changes, a new ID is
  possible.
- `canonical_name` is the durable semantic owner key used by owner briefs and
  entity-resolution reconciliation. It is not a substitute for source-name
  provenance; raw aliases remain linked separately.
- `entity_id` identifies a verified `public.entity_graph` row and must not be
  conflated with `owner_id` until the planned entity-profile API defines that
  contract.

Legacy PARID conversion helpers remain because the initial schema included the
now-retired assessment source. New product code should use PIDN and should not
revive the assessment ingestion path without a new source decision.
