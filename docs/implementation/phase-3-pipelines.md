# Phase 3: Dagster Pipelines & MVP Data Sources

**Goal:** All 6 MVP data sources (per Feasibility Report: #1, #2, #3, #4, #5, #13) are ingesting data, plus PLCB (#22, technically Phase 2 but trivially easy — CSV download — so it's built here to validate the pipeline framework). Entity resolution is running. The database is populated with real data.

**Time estimate:** 1.5–2 weeks solo. This is the bulk of the project. Framework setup ~4 hours, each source 2–16 hours depending on complexity (Assessment is the hardest at 12–16 hours), entity resolution ~8 hours, vector tile generation ~4 hours, Day 1 backfill ~4–6 hours. Assessment DB is critical path — RTK request takes 5–35 business days; Playwright scraping is the fallback.

**Prerequisites:** Phase 2 complete. All tables exist in local Docker Postgres (migrations applied). No AWS resources needed — pipelines fetch from live public APIs and write to local Postgres.

### Step 3.1: Build the Pipeline Framework

Before writing individual source assets, **use Context7 to pull current Dagster API docs**. The Dagster API changes between versions (e.g., `get_all_asset_keys()` was deprecated in favor of `resolve_all_asset_specs()`). Check the installed version and verify the API surface before writing definitions.py or resource classes.

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

> **Checkpoint:** `python -c "from york_county.definitions import defs; print(len(list(defs.resolve_all_asset_specs())))"` runs without import errors (even though no source assets exist yet).

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

#### Per-Source Workflow

**For API sources (ArcGIS, SODA, CSV downloads):**

```
1. Check library docs:         Use Context7 for Dagster asset/resource API
2. Write the asset file:       pipelines/york_county/assets/<type>/<source>.py
3. Write the parser:           pipelines/york_county/lib/parsers/<source>.py
4. Write the schema test:      pipelines/tests/test_<source>_parser.py
5. Save a test fixture:        pipelines/tests/fixtures/<source>_sample.json
6. Write asset checks:         (in the asset file or lib/checks.py)
7. Add the schedule:           pipelines/york_county/schedules/
8. Run pytest locally:         pytest tests/test_<source>_parser.py -v
9. Test against live API:      dagster asset materialize -a <asset_name>  (local Dagster)
10. Verify data in Postgres:   psql → SELECT COUNT(*) FROM staging.<table>;
11. Code review:               Use superpowers:requesting-code-review
12. Commit and push
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
3. Write the asset file:       pipelines/york_county/assets/scrapers/<source>.py
4. Write the parser:           pipelines/york_county/lib/parsers/<source>.py
5. Write the schema test:      pipelines/tests/test_<source>_parser.py
6. Save a test fixture:        pipelines/tests/fixtures/<source>_sample.html
7. Write asset checks:         (in the asset file or lib/checks.py)
8. Add the schedule:           pipelines/york_county/schedules/
9. Run pytest locally:         pytest tests/test_<source>_parser.py -v
10. Test against live site:    dagster asset materialize -a <asset_name>  (local Dagster)
11. Verify data in Postgres:   psql → SELECT COUNT(*) FROM staging.<table>;
12. Code review:               Use superpowers:requesting-code-review
13. Commit and push
```

> **Why explore first for scrapers:** The Assessment portal (Source #2) is ASP.NET Web Forms with session-based navigation — no RESTful URLs, no stable selectors without inspecting the live DOM. Going in blind wastes hours. The Playwright MCP lets you interactively explore the page, test selectors, and verify the navigation flow before writing any code.

#### Parallelization

Sources that share no code dependencies can be built in parallel using `superpowers:dispatching-parallel-agents`:

- **Parallel batch 1:** PLCB (#22) + FEMA (#3) — both are simple downloads, no shared code
- **Parallel batch 2:** PA Open Data (#4) + PennDOT (#5, #13) — different API patterns, independent
- **Sequential:** Assessment (#2) must be built after parcels (#1) since entity resolution needs both

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
