# Dagster Configuration

## Components (all in Docker containers on the production VPS)

| Component | Purpose | Runs as |
|---|---|---|
| `dagster-webserver` | UI + GraphQL API | Docker container |
| `dagster-daemon` | Scheduler + sensor evaluation | Docker container (same image, different entrypoint) |
| Run workers | Execute pipeline code in-process | Execute within the Dagster container |

## Memory Budget (current working assumption: 4 GB VPS baseline)

| Component | Memory |
|---|---|
| OS + Docker engine | ~200 MB |
| PostgreSQL container | ~500 MB |
| Dagster containers | ~500 MB |
| FastAPI + Uvicorn | ~100 MB |
| Caddy + Watchtower | ~50 MB |
| **Available for pipeline jobs** | **~2.5 GB** |

With 2.5 GB available for jobs, multiple Playwright browsers can run simultaneously. Staggered scheduling is still good practice (avoids CPU contention and keeps logs clean) but is no longer a hard memory constraint.

## Dagster Storage

Dagster needs a storage backend for run history, event logs, and schedule state.

**Configuration:** Use a separate database (`dagster`) on the same PostgreSQL container that serves application data. Same Docker Compose network, zero latency. Dagster's metadata is small (a few MB), and having it in Postgres means run history is durable and backed up alongside application data. Create a second database named `dagster` on the same Postgres instance — keeps it isolated from your application data.

## Log Levels

- **Production:** `WARNING` for Dagster internals, `INFO` for pipeline code
- **Debug sessions:** Temporarily set to `DEBUG` via environment variable, revert after

## Schedules (staggered to avoid CPU contention)

```
02:00  ArcGIS REST sources (parcels, municipalities, address_points, structures, zoning, PennDOT)
02:30  SODA API sources (PA Open Data Portal datasets)
03:00  Playwright scrapers — sequential:
         03:00  eFACTS
         03:15  CRIMEWATCH
         03:30  PALS
         03:45  Assessment portal
04:00  HTML/PDF scrapers (BS4/pdfplumber):
         04:00  YCCD Conservation District
         04:10  County Bids
         04:20  Tax Claim Bureau
         04:30  Commissioners meetings
         04:40  YCPC subdivision reports
         04:50  York City RFPs
05:00  Bulk downloads:
         05:00  PLCB+ CSV
         05:10  UJS Portal
--:--  Entity resolution / enrichment (sensor-triggered, not cron)
         Runs after all upstream weekly sources complete successfully.
         See docs/pipelines/entity-resolution.md for the sensor.
```

**Assessment Database (#3):** The assessment data is a one-time bulk import at launch (Day 1 backfill), not a recurring schedule. Annual reassessment data will be imported manually or via a triggered run when York County publishes updated assessments (typically once per year). This is why there are 6 MVP sources but only 5 weekly schedules.

**Note:** These are starting points. Actual frequencies vary by source (daily, weekly, monthly). Dagster cron expressions will reflect the real update cadence — not every source runs every night.
