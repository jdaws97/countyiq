# Phase 3: Dagster Pipelines & MVP Data Sources

**Goal:** All 6 MVP data sources (per Feasibility Report: #1, #2, #3, #4, #5, #13) are ingesting data, plus PLCB (#22, technically Phase 2 but trivially easy — CSV download — so it's built here to validate the pipeline framework). Entity resolution is running. The database is populated with real data.

**Time estimate:** 1.5–2 weeks solo. This is the bulk of the project. Framework setup ~4 hours, each source 2–16 hours depending on complexity (Assessment is the hardest at 12–16 hours), entity resolution ~8 hours, vector tile generation ~4 hours, Day 1 backfill ~4–6 hours. Assessment DB is critical path — RTK request takes 5–35 business days; Playwright scraping is the fallback.

**Prerequisites:** Phase 2 complete. All tables exist in RDS.

### Step 3.1: Build the Pipeline Framework

Before writing individual source assets, build the shared infrastructure:

| File | Purpose | Infra Plan Reference |
|---|---|---|
| `pipelines/york_county/definitions.py` | Dagster top-level definitions | Pipeline Code Structure → definitions.py |
| `pipelines/york_county/resources/database.py` | PostgreSQL connection helper | Pipeline Code Structure → lib/ utilities |
| `pipelines/york_county/resources/storage.py` | S3 client for raw archival | Pipeline Code Structure → lib/ utilities |
| `pipelines/york_county/lib/arcgis_client.py` | ArcGIS REST API pagination helper | Pipeline Code Structure → lib/ utilities |
| `pipelines/york_county/lib/playwright_utils.py` | Playwright browser session manager | Pipeline Code Structure → lib/ utilities |
| `pipelines/york_county/lib/parsers/` | Per-source parsing functions | Pipeline Code Structure → asset examples |
| `pipelines/york_county/lib/slack.py` | Slack webhook integration | Error Handling → Dagster Slack Integration Code |
| `pipelines/york_county/lib/scd.py` | SCD Type 2 upsert helper | Build-time (see docs/open-items.md) |
| `pipelines/york_county/sensors/alerting.py` | Success/failure Slack sensors | Error Handling → Dagster Sensors |

> **Checkpoint:** `python -c "from definitions import defs; print(len(defs.get_all_asset_keys()))"` runs without import errors (even though no source assets exist yet).

### Step 3.2: Implement MVP Source Assets (One at a Time)

Build each source, test it locally, then move to the next. Start with the simplest (bulk API) and progress to the hardest (Playwright scrapers).

**Recommended order:**

| Order | Source | # | Type | Difficulty | Notes |
|---|---|---|---|---|---|
| 1 | PLCB Liquor Licenses | 22 | CSV download | Easy | Bulk CSV; simplest possible pipeline. Good first test. |
| 2 | FEMA Flood Hazard Layer | 3 | Direct download | Easy | Single file download + PostGIS import |
| 3 | York County GIS Portal (Parcels) | 1 | ArcGIS REST API | Medium | Pagination, coordinate transform, 176K records. Core dataset. |
| 4 | York County GIS Portal (Other layers) | 1 | ArcGIS REST API | Medium | Same pattern as parcels, just different endpoints |
| 5 | PA Open Data Portal | 4 | SODA API | Medium | Different API pattern (SODA vs ArcGIS) |
| 6 | PennDOT Open Data | 5 | ArcGIS REST API | Medium | Same ArcGIS pattern as #3. ⚠️ Not live-tested — verify the endpoint responds before building. If it's down, skip and revisit; the other 5 MVP sources are sufficient for launch. |
| 7 | PennDOT Projects | 13 | ArcGIS MapServer | Medium | MapServer (slightly different from FeatureServer) |
| 8 | Assessment Database | 2 | Playwright scraper | Hard | ASP.NET Web Forms, session-based, 176K properties, throttling needed |
| 9 | Entity Resolution (MVP scope) | — | SQL enrichment | Medium | MVP: parcels + assessment only. Matches GIS owner_full against assessment owner_name using PIDN join + pg_trgm fallback. Phase 2 sources added incrementally. |
| 10 | Vector Tile Generation | — | PostGIS → S3 | Medium | ST_AsMVT, upload to S3 |

**For each source, the workflow is:**

```
1. Write the asset file:        pipelines/assets/<type>/<source>.py
2. Write the parser:            pipelines/lib/parsers/<source>.py
3. Write the schema test:       pipelines/tests/test_<source>_parser.py
4. Save a test fixture:         pipelines/tests/fixtures/<source>_sample.json
5. Write asset checks:          (in the asset file or lib/checks.py)
6. Add the schedule:            pipelines/jobs/schedules.py
7. Run pytest locally:          pytest pipelines/tests/test_<source>_parser.py -v
8. Test against live API:       dagster asset materialize -a <asset_name>  (local Dagster)
9. Verify data in RDS:          psql → SELECT COUNT(*) FROM staging.<table>;
10. Commit and push
```

### Step 3.3: Run Day 1 Backfill

Once all MVP sources are implemented and tested individually:

Reference: Infrastructure Plan, Backfill Strategy section.

```
Phase 1 (parallel where possible):
  - GIS Portal (all 49 layers)       ~30 min
  - FEMA Flood Layer                  ~2 min
  - PA Open Data                      ~5 min
  - PennDOT (Open Data + Projects)    ~10 min
  - PLCB Licenses                     ~1 min

Phase 2 (sequential — Playwright memory):
  - Assessment Database               ~2-4 hours

Phase 3 (enrichment):
  - Entity Resolution                 ~20 min

Phase 4 (frontend data):
  - Vector Tile Generation            ~15 min
```

Trigger from the Dagster UI with `full_history: true` config.

> **Checkpoint:** `SELECT COUNT(*) FROM staging.parcels WHERE valid_to IS NULL;` returns ~176,000. Entity resolution `owners` table is populated. Vector tiles are in S3. All Dagster runs show SUCCESS in the UI.

---
