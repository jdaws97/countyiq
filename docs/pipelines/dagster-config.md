# Dagster Configuration

## Components (all on single EC2 instance)

| Component | Purpose | Resource Profile |
|---|---|---|
| `dagster-webserver` | UI + GraphQL API | ~100–150 MB RAM |
| `dagster-daemon` | Scheduler + sensor evaluation | ~100–150 MB RAM |
| Run workers | Execute pipeline code in-process | ~50–400 MB per run (varies) |

## Memory Budget (1 GB total on t3.micro)

| Consumer | Estimated Usage |
|---|---|
| OS + system processes | ~150 MB |
| Dagster webserver | ~150 MB |
| Dagster daemon | ~150 MB |
| **Available for jobs** | **~550 MB** |
| Typical requests/BS4 scraper | ~50–100 MB |
| Typical Playwright scraper | ~200–400 MB |

**Key constraint:** Only run one Playwright job at a time. Stagger all schedules so Playwright-based scrapers never overlap.

**⚠️ OOM risk with Playwright:** Headless Chromium can consume 500 MB+ per instance. With Dagster webserver (~150 MB) + daemon (~150 MB) + OS (~150 MB), a single Playwright scraper pushes the t3.micro to its 1 GB limit. Mitigations: (1) never run two Playwright scrapers concurrently (already enforced by staggered schedules), (2) close the browser after each scrape (don't persist sessions), (3) if OOM kills occur in practice, upgrade to t3.small ($7.60/month post-free-tier) — see `docs/future-enhancements.md`. This is an acknowledged risk in `docs/decisions.md` (Acknowledged Tradeoffs).

## Dagster Storage

Dagster needs a storage backend for run history, event logs, and schedule state. Two options:

1. **SQLite (default)** — stored on the EBS volume. Simplest, no additional config. Fine for a solo developer.
2. **RDS PostgreSQL** — use a separate database (`dagster`) on the same RDS instance. Better durability, no extra cost since RDS has 20 GB to spare.

**Recommendation:** Use RDS PostgreSQL. Since you're already running a 24/7 RDS instance with plenty of storage headroom, there's no reason to use SQLite. Dagster's metadata is small (a few MB), and having it in Postgres means run history survives if the EC2 EBS volume is ever rebuilt. Create a second database named `dagster` on the same RDS instance — keeps it isolated from your application data.

## Log Levels

- **Production:** `WARNING` for Dagster internals, `INFO` for pipeline code
- **Debug sessions:** Temporarily set to `DEBUG` via environment variable, revert after

## Schedules (staggered to avoid memory contention)

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
