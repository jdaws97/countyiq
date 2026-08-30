# County onboarding runbook

CountyIQ is configuration-driven across counties, but “plug and play” means no
product-code fork—not zero source work. Pennsylvania counties and
municipalities publish different schemas, sites, rights statements, and update
cadences. A county is ready only after those differences are inventoried and
tested.

## Isolation model

For the alpha, run one stack and one database per county from the same code and
schema. Select the county with `COUNTY=<key>`. This prevents records with
county-local identifiers from mixing and avoids a premature multi-tenant schema
migration. A future cross-county product will require an explicit `county_key`
on natural keys and tables; do not simulate it by loading two counties into the
same current database.

## Add a county

1. Copy `pipelines/countyiq/counties/county.toml.example` to
   `pipelines/countyiq/counties/<county-key>.toml`.
2. Inventory the official parcel anchor and statewide/federal filters. Record
   the source URL, schema, update cadence, record count, provenance, and reuse
   status before enabling it.
3. Give the county GIS an `open_data_source_key` in the manifest and add a
   matching, reviewed row to `meta.source_rights` before the first asset run.
   The key is the join between ingestion authorization and API display policy;
   a missing, expired, or disallowed row fails closed.
4. Calibrate every configured `*_min_records` truncation guard from at least one
   successful full fetch.
5. Survey official planning commissions, zoning hearing boards, governing
   bodies, and county proceedings. Add only verified document/archive pages to
   `municipality_websites`, create an exact `municipality_source_rights` policy
   for every configured body, and create explicit paused gap rows so missing
   coverage cannot masquerade as no activity.
6. Run the county in a fresh database and bucket/prefix. Never point an
   unvalidated county at York's database or raw archive prefix.
7. Set API presentation metadata for the deployment:

   ```text
   COUNTY=<county-key>
   COUNTYIQ_OPEN_DATA_SOURCE_KEY=<the manifest open_data_source_key>
   COUNTYIQ_COUNTY_NAME=<Human County Name>
   COUNTYIQ_COUNTY_STATE=PA
   COUNTYIQ_PRODUCT_STAGE=alpha
   ```

   The source-rights key must exactly match the county manifest and database
   policy row. The display name defaults from the key, so only unusual names
   need an override.

## Required checks

From `pipelines`:

```text
.venv/bin/python -m pytest tests/test_county_config.py tests/test_county_config_attrs.py -q
.venv/bin/python -c "from countyiq.definitions import defs; repo = defs.get_repository_def(); print(len(defs.jobs), len(repo.asset_graph.get_all_asset_keys()))"
```

The selected county identity is also injected into Passes 1–4 and the API's
constrained search prompt. County Scout catalog generation can use York's
curated catalog or a manifest-derived starter catalog for another county, but
Scout probing and promotion are currently policy-paused. Add deeper
county-specific discovery seeds only after verifying the county, endpoint,
method, robots/terms evidence, retention, and reuse decision and then recording
a deliberate policy change.

Then run source-specific asset checks against the fresh county database. A
manifest is not accepted merely because it parses. Verify at minimum:

- parcel count and stable identifier uniqueness;
- geometry validity and expected CRS;
- municipality coverage and names;
- source freshness and truncation guard behavior;
- absence of wrong-county records;
- proceedings positive and negative controls;
- exact agreement between configured municipal bodies and their policy rows;
- paused records for every known municipal coverage gap;
- source URLs/evidence opening from API responses;
- API `/api/meta` and homepage county identity;
- one full Playwright feed → case file → watch flow.

## Reuse gate

Public reachability is not permission. Classify each source before activation:

- **green:** official open-data source with terms/metadata supporting reuse;
- **yellow:** public documents or ambiguous source-specific terms—derived facts
  only, preserve evidence, and seek clarification for exports/retention;
- **red:** restricted viewer/vendor surface, source-equivalent resale, sensitive
  person data, or unclear internal service—do not ingest.

Keep the county's source register under `docs/research/`. It is the admission
control ledger for the pipeline, not an analytics dataset.

## South-Central Pennsylvania sequence

Prioritize adjacent counties by customer overlap and source feasibility, not by
county size alone. Adams, Cumberland, Dauphin, Lancaster, and Lebanon are
reasonable discovery candidates, but none should be committed as supported
until its parcel rights, municipal proceedings coverage, and source maintenance
cost clear the gates above.
