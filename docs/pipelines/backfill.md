# Backfill Strategy

On Day 1, every pipeline runs in "backfill mode" to populate the database with as much data as possible. After that, scheduled runs maintain freshness.

## Full Snapshot Sources (No Backfill Problem)

These sources return the complete dataset on every pull. The first run IS the backfill.

| Source | # | What You Get on First Run |
|---|---|---|
| York County GIS Portal (49 layers) | 1 | All 176K+ parcels with full attribute history (sale dates, previous owners, previous prices) |
| FEMA Flood Hazard Layer | 3 | Complete flood zone boundaries |
| PA Open Data Portal | 4 | Full datasets via SODA API |
| PennDOT Open Data | 5 | Full road/bridge/infrastructure datasets |
| PennDOT Projects | 13 | All project records with status history |
| PA DOS Business Entities | 8 | Full business registry via data.pa.gov |
| PLCB Liquor Licenses | 22 | Complete bulk CSV of all licenses |
| PALS Professional Licenses | 21 | Searchable — can pull everything |
| Assessment Database | 2 | Current records (value history available per-property via scraping) |
| PA DEP eFACTS | 17 | Searchable by county — can pull all York County records |

**Dagster approach:** Each asset has a `backfill` config option:

```python
from dagster import asset, Config

class SourceConfig(Config):
    full_history: bool = False   # True on first run (backfill), False on scheduled runs

@asset
def parcels_arcgis(config: SourceConfig):
    if config.full_history:
        # Paginate through ALL 176K records
        return fetch_all_records(offset=0, limit=None)
    else:
        # Fetch only records modified since last run
        last_run = get_last_materialization_time()
        return fetch_records_modified_since(last_run)
```

To trigger backfill from the Dagster UI: select the asset → Materialize → set `full_history: true`.

## Archive-Scrapeable Sources (One-Time Deep Scrape)

These sources have archive pages that go back months or years. The Day 1 backfill scrapes ALL available archive pages, not just the first page.

| Source | # | Archive Depth | Backfill Approach |
|---|---|---|---|
| Commissioners Meetings | 15 | Meeting archives going back years | Scrape all archive pages; download all available PDFs |
| YCPC Subdivision Activity | 16 | Activity logs with historical entries | Scrape full activity list |
| Conservation District (YCCD) | 11 | PDF reports archive | Download all available PDFs |
| County Bids | 12 | Archive of past bids | Scrape all pages including closed/expired bids |
| York City RFPs | 18 | Past RFP listings | Scrape full listing history |

## Current-Only Sources (History Starts at Launch)

These sources only show what's currently posted. There's no practical way to retrieve historical data. History builds forward from Day 1.

| Source | # | What You Miss | Acceptable? |
|---|---|---|---|
| CRIMEWATCH | 19 | Incidents older than what's currently displayed | Yes — police blotter value is in recent patterns, not 2-year-old incidents |
| Sheriff Sales | 9 | Past sales that have already been removed from the site | Yes — GIS parcel data includes sale history (dates + prices) as a partial substitute |
| Tax Claim Bureau | 14 | Previously resolved delinquencies | Yes — current delinquencies are what matter |
| Inmate Records | 20 | Past bookings/releases | Yes — current status is primary use case |

## Formal Request Sources (Their Timeline)

| Source | # | Action | Backfill Depends On |
|---|---|---|---|
| Recorder of Deeds | 7 | File RTK request | Whatever format/timespan they provide |
| UJS Court Records | 6 | File AOPC application | Scope of access granted |

## Day 1 Execution Order

The backfill should run in a specific order because of asset dependencies (entity resolution needs source data first):

```
Phase 1: Full snapshot sources (parallel where memory allows)
  ├── GIS Portal (all 49 layers)     ~30 min (176K parcels + geometry)
  ├── FEMA Flood Layer                ~2 min
  ├── PA Open Data                    ~5 min
  ├── PennDOT (Open Data + Projects)  ~10 min
  ├── PA DOS Business                 ~5 min
  ├── PLCB Licenses (CSV)             ~1 min
  └── PALS Licenses                   ~15 min

Phase 2: Scraper sources (sequential — respect source rate limits)
  ├── Assessment Database             ~2-4 hours (176K properties, throttled)
  ├── CRIMEWATCH                      ~10 min
  ├── DEP eFACTS                      ~20 min
  ├── Sheriff Sales + Tax Claim       ~10 min
  ├── County Bids + York City RFPs    ~5 min
  └── Commissioners + YCPC + YCCD     ~15 min

Phase 3: Enrichment (after all sources complete)
  └── Entity Resolution               ~20 min

Phase 4: Frontend data generation
  └── Vector tile generation           ~15 min

Total estimated Day 1 backfill: ~4-6 hours
```

Run this on a weekday morning so you can monitor via the Dagster UI and Slack. Trigger Phase 1 assets manually, let Dagster's dependency graph handle the rest.
