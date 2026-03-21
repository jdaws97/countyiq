# Pipeline Code Structure

> **Note on code examples:** Code snippets in this document are **architectural sketches**, not production-ready implementations. Helper functions like `normalize_address()`, `get_all_source_asset_keys()`, and `scd2_upsert()` show the intended API surface and calling patterns — their implementations will be written at build time. Focus on the contracts (inputs, outputs, naming, file placement) rather than the function bodies.

## Dagster concepts in plain English

| Concept | What it is | Your example |
|---|---|---|
| **Asset** | A thing that exists (a database table, a file). You write a Python function that produces it, and Dagster tracks whether it's fresh or stale. | The `parcels` table, the `assessment` table |
| **Resource** | A shared connection that assets use. Configured once, shared everywhere. | Your RDS database connection, your S3 bucket |
| **Job** | A group of assets to build together. | "Build all ArcGIS source assets" |
| **Schedule** | A cron timer that triggers a job. | "Run the ArcGIS job every Monday at 2am" |
| **Sensor** | A trigger that watches for a condition, then kicks off a job. Optional — schedules work fine alone. | "When parcels_raw finishes, start the enrichment job" |
| **`definitions.py`** | The single entry point file that tells Dagster about all your assets, jobs, schedules, and resources. | See below |

## How assets relate to each other

```
ArcGIS REST API                 Playwright Scrapers           Bulk Downloads
─────────────                   ────────────────────          ──────────────
parcels_raw ─┐                  efacts_raw ───┐              plcb_raw ─────┐
zoning_raw ──┤                  crimewatch_raw┤              pa_open_raw ──┤
roads_raw ───┤  ┌──────────┐   pals_raw ─────┤              ujs_raw ──────┤
penndot_raw ─┤  │ staging  │   assessment_raw ┤                            │
             ├─▶│ (clean)  │                  │  ┌───────────────┐         │
             │  └────┬─────┘   ┌──────────┐   ├─▶│   staging     │         │
             │       │         │ staging  │   │  │   (clean)     │         │
             │       ▼         │ (clean)  │◀──┘  └───────┬───────┘         │
             │  ┌──────────┐   └────┬─────┘              │                 │
             │  │ public   │        │                     ▼                 │
             └─▶│ (final)  │        │         ┌───────────────────┐        │
                └────┬─────┘        └────────▶│   enrichment      │◀───────┘
                     │                        │   (entity res,    │
                     └───────────────────────▶│    joins, links)  │
                                              └───────────────────┘
```

Each box is one or more Dagster assets. Arrows show dependencies. Dagster sees this graph and knows the execution order automatically. If `parcels_raw` fails, nothing downstream of it runs.

## Monorepo layout

Since infrastructure (Terraform) and pipeline code (Dagster) live in the same repo:

```
countyiq/
│
├── infra/                              # Terraform (already designed)
│   ├── main.tf
│   ├── variables.tf
│   ├── terraform.tfvars                # GITIGNORED
│   ├── outputs.tf
│   ├── backend.tf
│   └── modules/
│       ├── networking/
│       ├── iam/
│       ├── database/
│       ├── compute/
│       └── monitoring/
│
├── pipelines/                          # Dagster project
│   ├── pyproject.toml                  # Python dependencies
│   ├── setup.py                        # Package installation
│   ├── docker-compose.yml              # Local Postgres for testing
│   │
│   ├── alembic/                        # Schema migrations
│   │   ├── alembic.ini
│   │   ├── env.py
│   │   └── versions/
│   │
│   └── countyiq/                    # Main Python package
│   │   ├── __init__.py
│   │   │
│   │   ├── definitions.py              # Dagster entry point
│   │   │
│   │   ├── resources/                  # Shared connections
│   │   │   ├── __init__.py
│   │   │   ├── database.py             # RDS connection (psycopg2)
│   │   │   └── storage.py              # S3 client for raw archival
│   │   │
│   │   ├── assets/                     # Data assets by source type
│   │   │   ├── __init__.py
│   │   │   │
│   │   │   ├── arcgis/                 # ArcGIS REST API sources
│   │   │   │   ├── __init__.py
│   │   │   │   ├── parcels.py
│   │   │   │   ├── zoning.py
│   │   │   │   ├── roads.py
│   │   │   │   ├── structures.py
│   │   │   │   └── penndot.py
│   │   │   │
│   │   │   ├── scrapers/               # Playwright + BeautifulSoup
│   │   │   │   ├── __init__.py
│   │   │   │   ├── efacts.py           # PA DEP eFACTS (Playwright)
│   │   │   │   ├── crimewatch.py       # CRIMEWATCH (Playwright)
│   │   │   │   ├── pals.py             # Professional licenses (Playwright)
│   │   │   │   ├── assessment.py       # Assessment portal (Playwright)
│   │   │   │   ├── county_bids.py      # County bids (BeautifulSoup)
│   │   │   │   ├── tax_claim.py        # Tax Claim Bureau (BeautifulSoup)
│   │   │   │   ├── commissioners.py    # Commissioners meetings (BS4)
│   │   │   │   └── york_city_rfp.py    # York City RFPs (BeautifulSoup)
│   │   │   │
│   │   │   ├── bulk/                   # Bulk download / API sources
│   │   │   │   ├── __init__.py
│   │   │   │   ├── plcb.py             # PLCB+ liquor licenses CSV
│   │   │   │   ├── pa_open_data.py     # SODA API datasets
│   │   │   │   └── ujs.py             # UJS Portal
│   │   │   │
│   │   │   ├── pdf/                    # PDF extraction sources
│   │   │   │   ├── __init__.py
│   │   │   │   ├── conservation.py     # YCCD plan review list
│   │   │   │   └── subdivision.py      # YCPC subdivision reports
│   │   │   │
│   │   │   └── enrichment/             # Derived / joined assets
│   │   │       ├── __init__.py
│   │   │       ├── owners.py           # Entity resolution across sources
│   │   │       └── parcel_enriched.py  # Parcel + assessment + zoning
│   │   │
│   │   ├── jobs/                       # Job definitions
│   │   │   ├── __init__.py
│   │   │   ├── arcgis_refresh.py       # All ArcGIS source assets
│   │   │   ├── scraper_refresh.py      # All scraper assets
│   │   │   ├── bulk_refresh.py         # All bulk download assets
│   │   │   └── enrichment.py           # Downstream enrichment assets
│   │   │
│   │   ├── schedules/                  # Schedule definitions
│   │   │   ├── __init__.py
│   │   │   └── daily.py                # Staggered cron schedules
│   │   │
│   │   └── lib/                        # Shared utilities
│   │       ├── __init__.py
│   │       ├── arcgis_client.py        # Reusable ArcGIS REST query + pagination
│   │       ├── playwright_utils.py     # Browser launch, anti-detection, screenshot
│   │       ├── s3_archive.py           # Archive raw responses to S3
│   │       └── scrape_utils.py         # Common HTML parsing helpers
│   │
│   └── tests/                          # Pipeline tests
│       ├── __init__.py
│       ├── test_arcgis_client.py
│       └── test_scrape_utils.py
│
├── frontend/                           # React + MapLibre + Deck.gl
│   ├── package.json
│   ├── vite.config.ts                  # Vite build tool
│   ├── tsconfig.json
│   ├── public/
│   │   └── favicon.ico
│   └── src/
│       ├── main.tsx                    # React entry point
│       ├── App.tsx                     # Root component
│       ├── components/
│       │   ├── Map.tsx                 # MapLibre + Deck.gl map
│       │   ├── ParcelPanel.tsx         # Side panel for parcel details
│       │   ├── SearchBar.tsx           # Owner/address/parcel search
│       │   ├── LayerControls.tsx       # Toggle map layers
│       │   └── EntityProfile.tsx       # Full entity view (owner details)
│       ├── api/
│       │   └── client.ts              # API client (fetch wrapper)
│       ├── layers/
│       │   ├── parcels.ts             # Deck.gl parcel polygon layer
│       │   ├── zoning.ts              # Zoning overlay layer
│       │   └── points.ts              # Points layer (businesses, permits)
│       ├── hooks/
│       │   ├── useMapView.ts          # Map state management
│       │   └── useSearch.ts           # Search state + API calls
│       └── types/
│           └── index.ts               # TypeScript interfaces
│
├── api/                                # FastAPI Lambda backend
│   ├── requirements.txt
│   ├── handler.py                      # Lambda entry point (Mangum adapter)
│   ├── main.py                         # FastAPI app definition
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── parcels.py                 # /api/parcels endpoints
│   │   ├── owners.py                  # /api/owners endpoints
│   │   ├── search.py                  # /api/search endpoints
│   ├── lib/
│   │   ├── database.py                # RDS connection pool
│   │   └── schemas.py                 # Pydantic response models
│   └── tests/
│       └── test_routes.py
│
├── .gitignore
├── .env.example                        # Template for environment variables
└── README.md
```

## What `definitions.py` does

This is the single file Dagster reads on startup. It registers all assets, jobs, schedules, and resources. Think of it as the "table of contents" for your entire data platform:

```python
from dagster import Definitions, load_assets_from_package_module

from countyiq import assets
from countyiq.jobs import arcgis_refresh, scraper_refresh, bulk_refresh, enrichment_refresh
from countyiq.schedules import all_schedules
from countyiq.sensors.alerting import success_reporter, failure_alerter
from countyiq.resources.database import make_database_resource
from countyiq.resources.storage import make_s3_resource

defs = Definitions(
    assets=load_assets_from_package_module(assets),
    jobs=[arcgis_refresh, scraper_refresh, bulk_refresh, enrichment_refresh],
    schedules=all_schedules,
    sensors=[success_reporter, failure_alerter],
    resources={
        "database": make_database_resource(),
        "s3": make_s3_resource(),
    },
)
```

`load_assets_from_package_module` auto-discovers all `@asset`-decorated functions under `countyiq/assets/`. As new source assets are added, they're picked up automatically without editing `definitions.py`.

When Dagster starts, it loads this file and knows about every asset, every dependency, every schedule. The Dagster UI then renders the full graph and lets you monitor everything.

## What a typical asset file looks like

**Simple example — ArcGIS parcels (HTTP/JSON, no browser needed):**

```python
# pipelines/countyiq/assets/arcgis/parcels.py
# Example of an ArcGIS source asset — follows the standard asset pattern.

from dagster import asset, AssetExecutionContext

@asset(
    group_name="arcgis",
    description="York County parcel boundaries from YCPC ArcGIS REST API → staging.parcels",
)
def parcels_arcgis(context: AssetExecutionContext, database, s3):
    """Fetch all York County parcels, archive raw to S3, upsert to staging.parcels (SCD2)."""

    # 1. Query ArcGIS REST API (uses shared lib for pagination)
    from countyiq.lib.arcgis_client import query_all_features
    features = query_all_features(
        url="https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/...",
        where="1=1",  # all records
    )
    context.log.info(f"Fetched {len(features)} parcels")

    # 2. Archive raw response to S3 (audit trail / replay source)
    s3.archive("arcgis/parcels", features)

    # 3. SCD Type 2 upsert to staging.parcels
    #    - Expire changed records (set valid_to = NOW())
    #    - Insert new/changed records (valid_from = NOW(), valid_to = NULL)
    database.scd2_upsert("staging.parcels", features, key="pidn")

    return len(features)  # metadata visible in Dagster UI


# Export for definitions.py
assets = [parcels_arcgis]
```

**Key things to notice:**
- Single asset per source — fetches, archives to S3, and upserts to staging in one step
- `database.scd2_upsert()` handles SCD Type 2 logic (expire changed records, insert new)
- Raw response archived to S3 first (audit trail), then parsed into `staging.*`
- The `context.log` calls show up in the Dagster UI so you can see what happened
- `load_assets_from_package_module` auto-discovers `@asset` functions, so no manual `assets` list export needed

## What the shared `lib/` utilities do

| File | Purpose | Used by |
|---|---|---|
| `lib/county_config.py` | `CountyConfig` dataclass + registry. Per-county source URLs, filter strings, thresholds. Active county set via `COUNTY` env var (default: `york`). | All assets — `get_county_config()` replaces hardcoded URLs and filter values |
| `lib/arcgis_client.py` | Handles ArcGIS REST API pagination (queries return max 1000–2000 records at a time, so it loops until all records are fetched) and GeoJSON conversion | All `arcgis/` assets |
| `lib/playwright_utils.py` | Launches Playwright Chromium with consistent settings (headless, timeout, viewport), captures screenshots for debugging | All `scrapers/` assets that need Playwright |
| `lib/scd.py` | SCD Type 2 upsert helper — expire changed records, insert new/changed, skip unchanged, detect deletes. Runs inside an explicit transaction for crash safety. | All assets that write to `staging.*` |
| `lib/slack.py` | 3-channel Slack webhook helper (critical/warning/pipeline), reads URLs from SSM Parameter Store, caches them | Sensors (`sensors/alerting.py`) |
| `lib/parsers/` | Per-source parsing functions (e.g. `parcels.py`, `plcb.py`) — extract and normalize fields from raw API responses. Parsers accept county-specific params (e.g. `county_filter`) rather than hardcoding values. | All assets |
| `resources/database.py` | PostgreSQL connection resource using psycopg2, reads `DATABASE_*` env vars | All assets via Dagster resource injection |
| `resources/storage.py` | S3 client for archiving raw responses to `s3://countyiq-raw/<prefix>/<source>/<date>/` | All assets via Dagster resource injection |

## How jobs and schedules connect

A **job** selects which assets to build. A **schedule** triggers that job on a cron timer:

```python
# countyiq/jobs/__init__.py

from dagster import define_asset_job, AssetSelection

arcgis_refresh = define_asset_job(
    name="arcgis_refresh",
    selection=AssetSelection.groups("arcgis"),
    description="Refresh all ArcGIS REST API data sources",
)

scraper_refresh = define_asset_job(
    name="scraper_refresh",
    selection=AssetSelection.groups("scrapers"),
    description="Refresh all Playwright/BeautifulSoup scraper sources",
)

bulk_refresh = define_asset_job(
    name="bulk_refresh",
    selection=AssetSelection.groups("bulk"),
    description="Refresh all bulk download / API sources",
)

enrichment_refresh = define_asset_job(
    name="enrichment_refresh",
    selection=AssetSelection.groups("enrichment"),
    description="Run entity resolution and enrichment assets",
)
```

```python
# countyiq/schedules/__init__.py

from dagster import ScheduleDefinition
from countyiq.jobs import arcgis_refresh, scraper_refresh, bulk_refresh

all_schedules = [
    ScheduleDefinition(
        job=arcgis_refresh,
        cron_schedule="0 2 * * 1",      # Monday 02:00
        name="weekly_arcgis",
    ),
    ScheduleDefinition(
        job=scraper_refresh,
        cron_schedule="0 3 * * 1",      # Monday 03:00
        name="weekly_scrapers",
    ),
    ScheduleDefinition(
        job=bulk_refresh,
        cron_schedule="0 5 1 * *",      # 1st of month 05:00
        name="monthly_bulk",
    ),
]
```

**Why enrichment uses a sensor, not a cron schedule:** Entity resolution should run only after ALL upstream sources have completed successfully. A cron schedule can't guarantee that — if a source runs late or fails, enrichment would process stale data. The sensor checks Dagster's run history and triggers only when all MVP deps have fresh materialization events. See `docs/pipelines/entity-resolution.md` for the sensor pattern. If the sensor approach proves too complex at build time, fall back to a Sunday 6 AM cron as a simpler alternative.

## Python dependencies (`pyproject.toml`)

```toml
[project]
name = "countyiq-pipelines"
version = "0.1.0"
requires-python = ">=3.11"

dependencies = [
    # Dagster core
    "dagster",
    "dagster-webserver",
    "dagster-postgres",          # For Dagster storage on RDS

    # Database
    "psycopg2-binary",
    "sqlalchemy>=2.0",
    "alembic",
    "geoalchemy2",               # PostGIS integration with SQLAlchemy

    # Scraping
    "requests",
    "beautifulsoup4",
    "lxml",                      # Fast HTML parser for BS4
    "playwright",
    "pdfplumber",

    # Data processing
    "geojson",
    "shapely",                   # Geometry manipulation
    "pyproj",                    # Coordinate system transforms

    # AWS
    "boto3",                     # S3 + Parameter Store access

    # Utilities
    "python-dotenv",             # .env file loading for local dev
]

[project.optional-dependencies]
dev = [
    "pytest",
    "ruff",                      # Linter
]
```

## Local development workflow

To work on pipelines on your own machine:

```bash
# 1. Clone the repo
git clone <repo-url>
cd countyiq/pipelines

# 2. Create a virtual environment (Python 3.11 via uv)
uv venv .venv --python 3.11
source .venv/bin/activate

# 3. Install dependencies
uv pip install -e ".[dev]"
playwright install chromium

# 4. Start local Postgres (for testing)
docker compose up -d postgres-test

# 5. Run migrations against local DB
export DATABASE_URL="postgresql://dagster_admin:localtest@localhost:5433/countyiq"
alembic upgrade head

# 6. Start Dagster UI (local dev mode)
dagster dev -m countyiq.definitions

# 7. Open http://localhost:3000 — full Dagster UI with all your assets
#    You can trigger individual assets, view the dependency graph, etc.
```

This gives you the full Dagster experience locally — same UI, same asset graph, same everything — just pointed at a local database instead of RDS. When you're happy with changes, commit, push, deploy to EC2.
