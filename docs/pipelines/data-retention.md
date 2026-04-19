# Data Retention & Archival Policy

## Design Principle

CountyIQ's value comes from connecting data across time, not just across sources. A zoning variance filed in 2024, a building permit in 2025, and an ownership transfer in 2026 might all relate to the same development — the platform needs to answer "what happened here over time," not just "what's happening now."

**Policy: Keep everything. No deletions. No archival tiers.**

## Layer 1: Raw Snapshots (Cloudflare R2) — Keep Forever

Every pipeline run dumps its raw response to R2 with a timestamped path:

```
r2:countyiq-raw/
├── arcgis/parcels/2026-03-20/response.json
├── arcgis/parcels/2026-03-27/response.json
├── crimewatch/2026-03-20/page-1.html
├── crimewatch/2026-03-20/page-2.html
├── assessment/2026-03-20/batch-001.html
├── plcb/2026-04-01/licenses.csv
└── ...
```

**Why keep raw data:**
- If a scraper bug corrupts processed data, you can replay from raw
- If you improve parsing logic later, you can re-process historical snapshots
- Audit trail — proves what the source looked like at a given time
- If a source disappears or changes format, you still have the original data

**Storage cost estimate:**

| Timeframe | Estimated Raw Data | Cloudflare R2 Cost |
|---|---|---|
| Year 1 | ~10 GB | $0.00/month (10 GB free tier) |
| Year 3 | ~30 GB | $0.30/month ($0.015/GB/mo, first 10 GB free) |
| Year 5 | ~50 GB | $0.60/month ($0.015/GB/mo, first 10 GB free) |

At these volumes, R2 Infrequent Access (if available) saves cents while adding retrieval complexity. Not worth it. R2 Standard forever.

## Layer 2: Processed Records (Postgres) — Change-Tracked, Keep All Versions

Tables that represent entities with mutable attributes use **Slowly Changing Dimensions (Type 2)** — every row has `valid_from` and `valid_to` timestamps. When data changes, the old row gets closed and a new row opens.

**Change-tracked tables (SCD Type 2):**

| Table | Why Track Changes | Example |
|---|---|---|
| `parcels` | Ownership transfers, assessment value changes, sale history | "Who owned this property in 2024?" |
| `businesses` | Status changes, officer changes, address changes | "This LLC was active when the permit was filed" |
| `permits` | Status updates (applied → approved → completed → expired) | "Permit issued 2024, never completed" |
| `zoning` | Variance applications, rezoning decisions | "Rezoned from residential to commercial in 2025" |
| `environmental` | Inspection results, violation status changes | "DEP violation opened 2024, resolved 2025" |
| `licenses` | Professional and liquor license status changes | "License revoked in 2025" |
| `owners` (entity resolution) | Resolved entity attributes change as new sources are linked | "Entity gained a new business association" |

**Schema pattern:**

```sql
-- Example: parcels table with change tracking
CREATE TABLE staging.parcels (
    id              SERIAL PRIMARY KEY,
    pidn            TEXT NOT NULL,          -- Parcel ID (natural key)
    owner_full      TEXT,
    aprtotal        NUMERIC,
    sale_date       DATE,
    price           NUMERIC,
    -- ... other fields ...

    -- Change tracking columns
    valid_from      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to        TIMESTAMPTZ,            -- NULL = current record
    source_run_id   TEXT,                   -- Dagster run ID that created this row
    raw_snapshot    TEXT,                   -- R2 key to the raw data

    -- Indexes for common queries
    CONSTRAINT current_record UNIQUE (pidn) WHERE (valid_to IS NULL)
);

-- Current snapshot (fast):
-- SELECT * FROM staging.parcels WHERE valid_to IS NULL;

-- Historical query (what did this parcel look like on a date):
-- SELECT * FROM staging.parcels
-- WHERE pidn = '46000060065000000'
--   AND valid_from <= '2024-06-15'
--   AND (valid_to IS NULL OR valid_to > '2024-06-15');
```

**Append-only tables (no change tracking needed):**

| Table | Why Append-Only | Notes |
|---|---|---|
| `court_records` | New filings are added; existing records don't change | Naturally grows over time |
| `crimewatch_incidents` | Incidents are posted once | Deduplication on insert |
| `sheriff_sales` | Each sale is a distinct event | Historical sales are valuable context |
| `meeting_minutes` | Published once per meeting | PDF reference stored in R2 |
| `bids_rfps` | Posted once, may close but don't change | Track status if needed |

## Layer 3: Operational Logs — Pruned

| Log Type | Retention | Rationale |
|---|---|---|
| Dagster run history (`dagster` database) | Kept indefinitely | Dagster's internal schema is small footprint; stored separately from business data |
| App-owned pipeline status (`meta.pipeline_status`) | Current state only | One row per source, overwritten each run (not historical) |
| Docker container logs | 7 days (logrotate) | Infra logs are transient |
| Slack message history | 90 days (free tier limit) | Sufficient for operational troubleshooting |

## Storage Growth Projections (Postgres)

| Timeframe | Estimated DB Size | Notes |
|---|---|---|
| Initial load | ~2 GB | 176K parcels + geometry, initial scraper data |
| Year 1 | ~4-6 GB | Change tracking adds rows gradually; most records don't change every pull |
| Year 3 | ~8-12 GB | Court records and incidents are the main growth drivers |
| Year 5 | ~15-18 GB | Well within VPS disk allocation |

VPS disk is included in the host plan. If more space is needed, either move to a larger VPS tier or attach additional storage. The second lever is partitioning historical data by year. But at these growth rates, the base VPS disk should last 5+ years.

## What This Enables

With full history retained, CountyIQ can answer questions like:
- "Show me all ownership changes for this parcel in the last 3 years"
- "Which properties had permits filed but never completed?"
- "This business was registered in 2024 — what properties did its officers own at that time?"
- "How has the assessed value of properties in this neighborhood trended?"
- "When did this environmental violation first appear, and is it resolved?"

This is what makes CountyIQ an intelligence platform rather than just a data viewer.
