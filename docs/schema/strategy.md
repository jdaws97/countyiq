# Schema and Identifier Strategy

Alembic migrations under `pipelines/alembic/versions/` are the database
authority. Documentation describes intent; it does not replace deployed DDL.

## Schemas

| Schema | Purpose | Representative objects |
|---|---|---|
| `staging` | Parsed source records and version history | `parcels`, `tax_claims`, `zoning_overlays`, `economic_development_parks`, `soils`, `local_traffic_counts` |
| `public` | Product-facing entities, evidence, briefs, events, scores, and views | `owners`, `development_momentum`, `parcel_briefs`, `parcel_events`, `intelligence_events`, `properties` |
| `meta` | Intelligence-pass state, scraper state, and source governance | `intelligence_passes`, `scrape_checkpoints`, `scraper_http_cache`, `source_rights`, `source_rights_audit`, `municipality_source_rights`, `municipality_source_audit`, `municipality_source_health` |

Most mutable source tables use SCD2 timestamps: `valid_to IS NULL` identifies
the current version. Some product tables are upserted, append-oriented, or
fully rebuildable instead. The migration and owning asset define the behavior
for each table.

Raw source evidence is stored outside Postgres only when the ingestion asset
calls `S3StorageResource`; see `docs/pipelines/data-retention.md`. There is no
`raw` database schema. Dagster's internal run and schedule tables live in the
separate `dagster` database, not in `countyiq.meta`.

Migration 030 removes the unused early tables `meta.pipeline_status`,
`meta.infra_metrics`, and `meta.data_quality_checks`. Current operational state
comes from Dagster's separate database, source tables, and registered asset
checks rather than a second observability model.

Migration 031 adds executable source authorization and its append-only audit
receipts; adds the four site-readiness staging families; adds
`public.development_momentum.site_readiness_score`; expires the two paused York
layers; removes their rebuildable signals/evidence; and clears momentum rows so
no stale score survives until the next enrichment rebuild.

Migration 032 adds use-specific enforcement and municipal-source governance.
The policy table identifies one exact configured body/source, the audit table
records every allow/deny decision and is append-only, and the health table
stores current listing/document outcomes separately from permission. Health
never grants permission. The same revision records County Scout as paused.

Migrations 033 and 034 add exact municipal origin allowlists, record reviewed
same-organization HTTPS aliases, and pause paths whose useful documents depend
on restricted or unreviewed vendor delivery. Redirect destinations and browser
document/API requests must remain inside these allowlists; runtime health cannot
expand them.

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
