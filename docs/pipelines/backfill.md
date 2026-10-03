# Initial Load and Backfill

CountyIQ source ingestion has no separate `full_history` asset config. Most
source assets fetch the source's current complete snapshot, so their first
successful materialization establishes the baseline. SCD2 history starts from
that baseline and grows on later refreshes; CountyIQ cannot promise history a
source does not publish. Paid Passes 0-3 do have an explicit cost-only backfill
mode so an approved historical run need not be split into 25-item launches.

## Before the First Run

1. Apply the full Alembic chain.
2. Configure database and source credentials.
3. Configure Cloudflare R2 and set `COUNTYIQ_ARCHIVE_STRICT=true` so a missing
   raw-source archive fails visibly in production.
4. Prepare the private PC state directory and protected SSH session described
   in [Local pipeline commands](../operations/local-pipelines.md).
5. Leave model-backed enrichment until deterministic source loads and their
   asset checks have passed.

## Materialization Order

Use the registered jobs through the local command wrapper. The production
wrapper keeps paid Passes 0–4 disabled. The paid-mode contracts below remain
relevant to development and separately reviewed execution policies; they do
not enable paid production work through the source runner.

1. `arcgis_refresh` establishes parcels and reference layers.
2. `radar_refresh`, `scraper_refresh`, `pa_dos_refresh`, `bulk_refresh`, and
   `fema_refresh` load the remaining source groups. Invoke these independent
   groups explicitly, one protected session at a time.
3. Run `deterministic_enrichment_refresh` after the source checks pass. It
   rebuilds municipality joins, deterministic signals, stable owner identity,
   parcel/feed events, and momentum without making a model call.
4. Estimate the paid work before enabling any model-backed asset:

   ```bash
   cd pipelines
   .venv/bin/python scripts/run_pipeline.py \
     --ssh-target ubuntu@YOUR_HOST --identity-file /absolute/path/to/ssh-key \
     --script estimate-backfill -- \
     --output /tmp/countyiq-backfill-estimate.json
   ```

   The estimator is read-only, uses the production selectors and prompt
   builders, and does not read an API key or call a model provider. Review its
   per-pass candidate counts, assumptions, and retry ceiling before launching
   a pass-specific job. Runtime pass gates are shown as status but do not zero
   the hypothetical estimate: the purpose is to price work while those gates
   are still safely disabled. Explicit runs default to 25 outer work items via
   `COUNTYIQ_PASS{N}_MAX_ITEMS`.

   After the capped pilot is accepted, an approved Pass 0-3 backfill may set
   `COUNTYIQ_PASS{N}_BACKFILL_MODE=true`. That removes only the item cap. The
   run still requires `COUNTYIQ_PASS{N}_MAX_COST_USD`, the global prompt and
   completion price ceilings, and a matching durable authorization file. With
   the pass disabled, create it once:

   ```bash
   .venv/bin/python scripts/create_intelligence_backfill_authorization.py \
     --pass-number <N> \
     --output ~/.local/state/countyiq/pipeline/intelligence/pass-<N>-authorization.json
   ```

   Set `COUNTYIQ_PASS{N}_BACKFILL_AUTHORIZATION_FILE` to that path before
   enabling the pass. Every call reserves its worst case in the file before
   dispatch and settles the provider-reported cost afterward. Reservations
   survive Dagster retries and process restarts, so the approved cumulative
   allowance cannot reset with each asset launch.

5. Run the paid work in this order after approving each budget and inspecting
   its capped pilot:

   1. `proceedings_extraction_refresh` (Pass 0).
   2. `entity_verification_refresh` (Pass 1; this refreshes candidate pairs
      from the Pass 0 output first).
   3. `deterministic_enrichment_refresh` again. This is required to consume
      Pass 0 into development signals and Pass 1 into the serving owner graph.
   4. `signal_validation_refresh` (Pass 2).
   5. `deterministic_enrichment_refresh` again to rebuild events and momentum
      from validated evidence.
   6. `brief_generation_refresh` and, if in scope, `owner_briefs_refresh`.

   Do not launch Pass 2 against the deterministic snapshot from before Passes
   0 and 1; doing so can pay to validate stale contexts that immediately become
   eligible again after the next rebuild. `county_narratives_refresh` remains
   outside the alpha backfill. All passes are disabled by default and must be
   enabled one at a time for the approved operator run.

Do not use `enrichment_refresh` for the initial load. It selects the entire
`enrichment` group, which mixes the seven deterministic assets with Passes 0-4.
It remains registered for an explicitly funded full-group rebuild, but is not
a cost-isolated path.

The manual jobs in `pipelines/countyiq/jobs/__init__.py` rerun a specific
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
- review the first model-backed outputs before approving larger manual runs;
- record actual duration, row counts, archive volume, and model spend for the
  next capacity estimate.

There is no supported vector-tile generation phase. The current map consumes
bounded API GeoJSON as documented in `docs/frontend/architecture.md`.
