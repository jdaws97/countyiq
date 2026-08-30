# Initial Load and Backfill

CountyIQ has no separate `backfill` mode or `full_history` asset config. Most
source assets fetch the source's current complete snapshot, so their first
successful materialization establishes the baseline. SCD2 history starts from
that baseline and grows on later refreshes; CountyIQ cannot promise history a
source does not publish.

## Before the First Run

1. Apply the full Alembic chain.
2. Configure database and source credentials.
3. Configure Cloudflare R2 and set `COUNTYIQ_ARCHIVE_STRICT=true` so a missing
   raw-source archive fails visibly in production.
4. Confirm the separate Dagster database and persistent archive mount are
   healthy.
5. Leave model-backed enrichment until deterministic source loads and their
   asset checks have passed.

## Materialization Order

Use the registered jobs in the Dagster UI:

1. `arcgis_refresh` establishes parcels and reference layers.
2. `radar_refresh`, `scraper_refresh`, `pa_dos_refresh`, `bulk_refresh`, and
   `fema_refresh` load the remaining source groups. These groups are independent
   and may run in parallel within source rate and host-memory limits.
3. Run `deterministic_enrichment_refresh` after the source checks pass. It
   rebuilds municipality joins, deterministic signals, stable owner identity,
   parcel/feed events, and momentum without making a model call.
4. Estimate the paid work before enabling any model-backed asset:

   ```bash
   cd pipelines
   .venv/bin/python scripts/estimate_llm_backfill.py \
     --output /tmp/countyiq-backfill-estimate.json
   ```

   The estimator is read-only, uses the production selectors and prompt
   builders, and does not read an API key or call a model provider. Review its
   per-pass candidate counts, assumptions, and retry ceiling before launching
   a pass-specific job. Runtime pass gates are shown as status but do not zero
   the hypothetical estimate: the purpose is to price work while those gates
   are still safely disabled. Explicit runs default to 25 outer work items via
   `COUNTYIQ_PASS{N}_MAX_ITEMS`; raise that finite cap only for an approved batch.
5. Run model-backed passes individually in dependency order after approving a
   budget and inspecting a capped pilot: `proceedings_extraction_refresh`,
   `entity_verification_refresh`, `signal_validation_refresh`, then
   `brief_generation_refresh`. `county_narratives_refresh` remains outside the
   alpha backfill. All passes are disabled by default and must be enabled one at
   a time for the approved operator run.

Do not use `enrichment_refresh` for the initial load. It selects the entire
`enrichment` group, which mixes the seven deterministic assets with Passes 0-4.
It remains registered for an explicitly funded full-group rebuild, but is not
a cost-isolated path.

County Scout discovery and monitoring do not block the initial product data
load. The manual jobs in `pipelines/countyiq/jobs/__init__.py` rerun a specific
source or intelligence pass; they are not a second backfill implementation.

Public-proceedings history is limited to documents reachable through each
configured municipal archive. Each run is bounded (250 document requests total
and 25 per governing body by default), processes likely-newer documents first,
and resumes from persisted URL/content-hash rows. Run metadata reports deferred
documents. An interrupted, capped, or partial source run still makes the LLM
estimate a lower bound for not-yet-retrieved history even though its counts are
exact for rows currently in PostgreSQL.

## Acceptance

An initial load is not complete merely because the Dagster run is green:

- review asset-check results and source row counts;
- inspect warnings for partial pagination, skipped archives, robots rules, and
  scraper failures;
- sample parcel, owner, development, and proceeding records through the API;
- review the first model-backed outputs before enabling their weekly schedule;
- record actual duration, row counts, archive volume, and model spend for the
  next capacity estimate.

There is no supported vector-tile generation phase. The current map consumes
bounded API GeoJSON as documented in `docs/frontend/architecture.md`.
