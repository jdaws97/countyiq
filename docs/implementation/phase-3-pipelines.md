# Phase 3: Dagster Pipelines & MVP Data Sources

**Goal:** All 6 MVP data sources (per Feasibility Report: #1, #2, #3, #4, #5, #13) are ingesting data, plus PLCB (#22, technically Phase 2 but trivially easy — CSV download — so it's built here to validate the pipeline framework). Source #1 includes not just Parcels but also the **Municipal_Boundary, AddressPts, and BLDG_Footprint** GIS layers — these are MVP because municipalities, search, and map quality depend on them. Entity resolution is running. The database is populated with real data.

**Time estimate:** 1.5–2 weeks solo. This is the bulk of the project. Framework setup ~4 hours, each source 2–16 hours depending on complexity (Assessment is the hardest at 12–16 hours), entity resolution ~8 hours, vector tile generation ~4 hours, Day 1 backfill ~4–6 hours. Assessment DB is critical path — RTK request takes 5–35 business days; Playwright scraping is the fallback.

**Prerequisites:** Phase 2 complete. All tables exist in local Docker Postgres (migrations applied). No AWS resources needed — pipelines fetch from live public APIs and write to local Postgres.

### Step 3.1: Build the Pipeline Framework

Before writing individual source assets, **use Context7 to pull current Dagster API docs**. The Dagster API changes between versions (e.g., `get_all_asset_keys()` was deprecated in favor of `resolve_all_asset_specs()`). Check the installed version and verify the API surface before writing definitions.py or resource classes.

| File | Purpose | Infra Plan Reference |
|---|---|---|
| `pipelines/countyiq/definitions.py` | Dagster top-level definitions | Pipeline Code Structure → definitions.py |
| `pipelines/countyiq/resources/database.py` | PostgreSQL connection helper | Pipeline Code Structure → lib/ utilities |
| `pipelines/countyiq/resources/storage.py` | S3 client for raw archival | Pipeline Code Structure → lib/ utilities |
| `pipelines/countyiq/lib/arcgis_client.py` | ArcGIS REST API pagination helper | Pipeline Code Structure → lib/ utilities |
| `pipelines/countyiq/lib/playwright_utils.py` | Playwright browser session manager | Pipeline Code Structure → lib/ utilities |
| `pipelines/countyiq/lib/parsers/` | Per-source parsing functions | Pipeline Code Structure → asset examples |
| `pipelines/countyiq/lib/slack.py` | Slack webhook integration | Error Handling → Dagster Slack Integration Code |
| `pipelines/countyiq/lib/scd.py` | SCD Type 2 upsert helper | Build-time (see docs/open-items.md) |
| `pipelines/countyiq/sensors/alerting.py` | Success/failure Slack sensors | Error Handling → Dagster Sensors |

> **Checkpoint:** `python -c "from countyiq.definitions import defs; print(len(list(defs.resolve_all_asset_specs())))"` runs without import errors (even though no source assets exist yet).

### Step 3.2: Implement MVP Source Assets (One at a Time)

Build each source, test it locally, then move to the next. Start with the simplest (bulk API) and progress to the hardest (Playwright scrapers).

**Recommended order:**

| Order | Source | # | Type | Difficulty | Notes |
|---|---|---|---|---|---|
| 1 | PLCB Liquor Licenses | 22 | CSV download | Easy | Bulk CSV; simplest possible pipeline. Good first test. |
| 2 | FEMA Flood Hazard Layer | 3 | Direct download | Easy | Single file download + PostGIS import |
| 3 | York County GIS Portal (Parcels) | 1 | ArcGIS REST API | Medium | Pagination, coordinate transform, 176K records. Core dataset. |
| 4a | GIS: Municipal_Boundary | 1 | ArcGIS REST API | Easy | 72 polygons. **Blocks municipality on parcels** — spatial join enrichment populates `staging.parcels.municipality`. Must run before entity resolution. Table: `staging.municipalities` (migration 001). |
| 4b | GIS: AddressPts | 1 | ArcGIS REST API | Easy | ~100K+ geocoded points. Backend-only (not a map layer). Entity resolution fallback when PROPADR is messy. Canonical address list for `/api/search`. **Needs new Alembic migration for `staging.address_points`.** |
| 4c | GIS: BLDG_Footprint | 1 | ArcGIS REST API | Easy | ~213K building polygons. Biggest visual upgrade to the map. Vacancy detection (parcel with no footprint). Assessment discrepancy analysis (footprint sqft vs assessed area). Table: `staging.structures` (migration 004). |
| 4d | GIS: Other layers (zoning, school districts) | 1 | ArcGIS REST API | Easy | Same pattern as above, different endpoints |
| 5 | PA Open Data Portal | 4 | SODA API | Medium | Different API pattern (SODA vs ArcGIS) |
| 6 | PennDOT Open Data | 5 | ArcGIS REST API | Medium | Same ArcGIS pattern as #3. ⚠️ Not live-tested — verify the endpoint responds before building. If it's down, skip and revisit; the other 5 MVP sources are sufficient for launch. |
| 7 | PennDOT Projects | 13 | ArcGIS MapServer | Medium | MapServer (slightly different from FeatureServer) |
| 8 | Assessment Database | 2 | Playwright scraper | Hard | ASP.NET Web Forms, session-based, 176K properties, throttling needed |
| 9 | Entity Resolution (MVP scope) | — | SQL enrichment | Medium | MVP: parcels + assessment only. Matches GIS owner_full against assessment owner_name using PIDN join + pg_trgm fallback. Phase 2 sources added incrementally. |
| 10 | Vector Tile Generation | — | PostGIS → S3 | Medium | ST_AsMVT, upload to S3 |

#### Per-Source Workflow

> **County config rule:** Every new asset MUST use `get_county_config()` for URLs, filter strings, and thresholds. Every parser MUST accept county-specific params (e.g., `county_filter`) rather than hardcoding values. See `pipelines/countyiq/lib/county_config.py`. Add any new source-specific config fields to `CountyConfig` if needed (e.g., a new URL for the source). We are building for York County but the code must be county-agnostic.

**For API sources (ArcGIS, SODA, CSV downloads):**

```
1. Check library docs:         Use Context7 for Dagster asset/resource API
2. Add config fields:          Add any new source URLs/thresholds to CountyConfig in county_config.py
3. Write the asset file:       pipelines/countyiq/assets/<type>/<source>.py (use get_county_config())
4. Write the parser:           pipelines/countyiq/lib/parsers/<source>.py (accept county params, don't hardcode)
5. Write the schema test:      pipelines/tests/test_<source>_parser.py
6. Save a test fixture:        pipelines/tests/fixtures/<source>_sample.json
7. Write asset checks:         (in the asset file or lib/checks.py)
8. Add the schedule:           pipelines/countyiq/schedules/
9. Run pytest locally:         pytest tests/test_<source>_parser.py -v
10. Test against live API:     dagster asset materialize -a <asset_name>  (local Dagster)
11. Verify data in Postgres:   psql → SELECT COUNT(*) FROM staging.<table>;
12. Code review:               Use superpowers:requesting-code-review
13. Commit and push
```

**For Playwright scraper sources (Assessment, eFACTS, CRIMEWATCH, PALS):**

```
1. Explore the live site:      Use Playwright MCP to navigate, screenshot, inspect DOM
   - Navigate to the target URL
   - Take a snapshot of the page structure
   - Identify form fields, search controls, result containers
   - Test the navigation flow (search → results → detail page)
   - Document selectors that work
   - Check for anti-bot measures (Cloudflare, CAPTCHAs)
2. Check library docs:         Use Context7 for Playwright + Dagster APIs
3. Add config fields:          Add source URL/thresholds to CountyConfig in county_config.py
4. Write the asset file:       pipelines/countyiq/assets/scrapers/<source>.py (use get_county_config())
5. Write the parser:           pipelines/countyiq/lib/parsers/<source>.py (accept county params)
6. Write the schema test:      pipelines/tests/test_<source>_parser.py
7. Save a test fixture:        pipelines/tests/fixtures/<source>_sample.html
8. Write asset checks:         (in the asset file or lib/checks.py)
9. Add the schedule:           pipelines/countyiq/schedules/
10. Run pytest locally:        pytest tests/test_<source>_parser.py -v
11. Test against live site:    dagster asset materialize -a <asset_name>  (local Dagster)
12. Verify data in Postgres:   psql → SELECT COUNT(*) FROM staging.<table>;
13. Code review:               Use superpowers:requesting-code-review
14. Commit and push
```

> **Why explore first for scrapers:** The Assessment portal (Source #2) is ASP.NET Web Forms with session-based navigation — no RESTful URLs, no stable selectors without inspecting the live DOM. Going in blind wastes hours. The Playwright MCP lets you interactively explore the page, test selectors, and verify the navigation flow before writing any code.

#### Parallelization

Sources that share no code dependencies can be built in parallel using `superpowers:dispatching-parallel-agents`:

- **Parallel batch 1:** PLCB (#22) + FEMA (#3) — both are simple downloads, no shared code
- **Parallel batch 2:** GIS supplemental layers (Municipal_Boundary + AddressPts + BLDG_Footprint) — same ArcGIS pattern, independent datasets
- **Parallel batch 3:** PA Open Data (#4) + PennDOT (#5, #13) — different API patterns, independent
- **Sequential:** Municipality spatial join must run after parcels + municipalities are loaded. Assessment (#2) must be built after parcels (#1) since entity resolution needs both.

### Step 3.3: Run Day 1 Backfill

Once all MVP sources are implemented and tested individually:

Reference: Infrastructure Plan, Backfill Strategy section.

```
Phase 1 (parallel where possible):
  - GIS: Parcels (176K polygons)      ~4 min
  - GIS: Municipal_Boundary (72)      ~10 sec
  - GIS: AddressPts (~100K+ points)   ~2 min
  - GIS: BLDG_Footprint (~213K)       ~4 min
  - GIS: Other layers (zoning, etc.)  ~5 min
  - FEMA Flood Layer                  ~30 sec
  - PA Open Data                      ~5 min
  - PennDOT (Open Data + Projects)    ~10 min
  - PLCB Licenses                     ~1 min

Phase 2 (enrichment — must run after Phase 1):
  - Spatial join: municipalities → parcels  ~2 min
  - Spatial join: footprints → parcels      ~5 min

Phase 3 (sequential — Playwright memory):
  - Assessment Database               ~2-4 hours

Phase 4 (enrichment):
  - Entity Resolution                 ~20 min

Phase 5 (frontend data):
  - Vector Tile Generation            ~15 min
    (parcels, footprints, flood zones, municipalities)
```

Trigger from the Dagster UI with `full_history: true` config.

> **Checkpoint:** `SELECT COUNT(*) FROM staging.parcels WHERE valid_to IS NULL;` returns ~176,000. Entity resolution `owners` table is populated. Vector tiles are in S3. All Dagster runs show SUCCESS in the UI.

---
