# Assessment Database Pipeline — Design Spec

**Date:** 2026-03-21
**Source:** #2 — York County Assessment Database (iasWorld Public Access)
**Phase:** MVP
**Schedule:** Weekly (Monday 03:00, `scraper_refresh` job)

---

## Overview

Scrape all ~176K property records from the York County Assessment portal (`assessmentpublic.yorkcountypa.gov`) and load into `staging.assessment_properties`. The portal is an ASP.NET Web Forms app (iasWorld by Tyler Technologies) with session-based navigation and a 500-result display cap per search.

The pipeline runs in two tiers within a single Dagster asset execution:
1. **Tier 1 — Search Results Sweep**: Prefix-based batch search to collect PARID, owner, address, class for all properties
2. **Tier 2 — Detail Enrichment**: Visit each property's Printable Summary page to extract assessed values, permits, delinquent taxes, and value history

Both tiers checkpoint progress to the database for resumability.

---

## Portal Behavior (Verified via Playwright)

| Aspect | Detail |
|---|---|
| URL | `https://assessmentpublic.yorkcountypa.gov/` |
| Platform | iasWorld Public Access (Tyler Technologies), ASP.NET Web Forms |
| Disclaimer | Must click "Agree" before any search — redirects to disclaimer page on first access |
| Basic Search fields | Parcel (18-digit), Owner Name, Address Number, Dir, Street |
| Results per page | Max 50 (dropdown: 15/20/25/30/50) |
| **Result cap** | **500 displayed** per search, even if more found. "Total found: N records, displayed: 500" |
| Result columns | Parcel (18-digit PARID), Owner, Location, Class |
| Detail page | Session-based: `Datalets/Datalet.aspx?sIndex=0&idx=N` |
| Detail tabs | Profile, Owner, Sales, Values, Value History, Land, Agricultural, Residential, Outbuildings, Permits, Commercial, Current Tax, Delinquent Taxes, Appeals, Photos, Sketch, Map |
| Printable Summary | `javascript:PrintDatalet('all')` — renders ALL tabs in one page |
| Record navigation | First/Previous/Next/Last buttons, "N of 500" counter |
| PARID format | `460000100010000000` (18-digit, unformatted in search) |
| Data currency | "Updated weekly" per footer disclaimer |
| Advanced Search | Has Municipality criteria — useful for sub-batching if needed |

---

## Architecture

### Files

| File | Purpose |
|---|---|
| `pipelines/countyiq/assets/scrapers/__init__.py` | Package init (required for Dagster asset discovery) |
| `pipelines/countyiq/assets/scrapers/assessment.py` | Dagster asset + asset checks |
| `pipelines/countyiq/lib/parsers/assessment.py` | HTML parsing for search results and detail pages |
| `pipelines/tests/test_assessment_parser.py` | Parser unit tests with fixture HTML |
| `pipelines/tests/fixtures/assessment_search_results.html` | Sample search results page HTML |
| `pipelines/tests/fixtures/assessment_printable_summary.html` | Sample Printable Summary HTML |

### Data Flow

```
[Browser Session]
    ├─ Accept Disclaimer
    ├─ Tier 1: For each PARID prefix
    │   ├─ Basic Search → results table (50/page, max 10 pages)
    │   ├─ Extract: PARID, owner_name, address, property_class
    │   └─ Checkpoint prefix to DB (meta.scrape_checkpoints)
    ├─ Tier 2: For each property from Tier 1
    │   ├─ Search by exact PARID → 1 result
    │   ├─ Click result → Printable Summary
    │   ├─ Extract: all detail fields + JSONB data
    │   └─ Checkpoint PARID to DB
    ├─ Archive raw data to S3
    ├─ Convert PARID→PIDN (Python: parid[0:2] + parid[3:6] + parid[7:9] + parid[10:16])
    └─ SCD2 upsert to staging.assessment_properties (expire_missing=False for incremental)
```

### Tier 1: Search Results Sweep

**Purpose:** Get PARID→owner/address/class mapping for all ~176K properties.

**Strategy:** Adaptive prefix search.

1. Get all unique 2-digit district prefixes from `staging.parcels` (first 2 chars of PIDN). There are ~72 districts.
2. For each prefix, search the Parcel field. If total found > 500, expand to longer prefixes (3-digit, 4-digit, etc.) until each sub-prefix returns ≤500 results.
3. For each valid prefix batch: page through all results (50/page, up to 10 pages), extracting table row data.
4. Throttle: 5-second delay between page loads.

**Prefix refinement algorithm:**
```python
def generate_prefixes(prefix: str, session) -> list[str]:
    """Search with prefix; if >500 results, recurse with longer prefixes."""
    total = search_and_get_total(session, prefix)
    if total <= 500:
        return [prefix]
    # Expand: try prefix + "0" through prefix + "9", plus prefix + "A"-"Z"
    # (PARID can contain letters like "KF" in some formats)
    sub_prefixes = []
    for char in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        sub = prefix + char
        sub_total = search_and_get_total(session, sub)
        if sub_total > 0:
            if sub_total <= 500:
                sub_prefixes.append(sub)
            else:
                sub_prefixes.extend(generate_prefixes(sub, session))
    return sub_prefixes
```

**Estimated runtime:** ~72 district prefixes × ~10 sub-prefixes average × 11 page loads × 5s = ~11 hours.

### Tier 2: Detail Enrichment

**Purpose:** Get assessed values, permits, delinquent taxes, value history for each property.

**Strategy:** For each PARID collected in Tier 1:

1. Search by exact 18-digit PARID → returns exactly 1 result
2. Click the result row to enter detail view
3. Navigate to Printable Summary (all tabs rendered on one page)
4. Parse the summary HTML to extract all fields
5. Throttle: 5-second delay between properties
6. Refresh session every ~200 properties (re-accept disclaimer, start new search)

**Session management:**
- iasWorld uses ASP.NET session state with ViewState tokens
- Sessions may expire after inactivity
- On any navigation error or unexpected page, restart the session (new browser context, re-accept disclaimer)

**Estimated runtime:** 176K properties × 3 requests × ~7s (5s throttle + ~2s load) = ~1,025 hours for complete initial backfill. This is a multi-day operation. The asset is designed to run incrementally:
- Each execution processes a configurable batch (default 500 properties, ~1 hour)
- Subsequent executions resume from checkpoint, process next batch
- Full backfill completes over ~352 runs

**Practical acceleration:** Run multiple times with `dagster asset materialize` to complete backfill faster. At 500 properties per ~1-hour run, 3 runs per day completes in ~117 days. For faster backfill, increase batch size or run more frequently.

### Resumability via Database Checkpoint

Checkpoint state stored in `meta.scrape_checkpoints` table (new, added via Alembic migration):

```sql
CREATE TABLE meta.scrape_checkpoints (
    source_name TEXT PRIMARY KEY,          -- e.g. 'assessment'
    checkpoint  JSONB NOT NULL DEFAULT '{}',
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);
```

Checkpoint JSON structure:
```json
{
  "tier1": {
    "status": "complete",
    "completed_prefixes": ["01", "02", "03"],
    "total_properties_found": 176042
  },
  "tier2": {
    "status": "in_progress",
    "last_completed_parid": "240001234560000000",
    "properties_enriched": 4200
  }
}
```

**Why database, not S3:** The existing `S3StorageResource` only has an `archive()` method (writes to dated paths), with no `get()` method. The database is always available, works in local dev (Docker Postgres), and avoids silent checkpoint loss.

**Tier 2 ordering:** PARIDs are processed in sorted order. Only `last_completed_parid` and a count are stored — no need to store all 176K completed PARIDs. On resume, skip all PARIDs ≤ `last_completed_parid`.

On each execution:
1. Load checkpoint from `meta.scrape_checkpoints`
2. Skip completed work
3. Process next batch
4. Save updated checkpoint after each property (crash-safe)
5. Upsert batch results to staging at end of run

### SCD2 Upsert for Incremental Loads

**Critical:** The existing `scd2_upsert` helper expires records whose keys are NOT in the incoming batch. For incremental loads (500 properties out of 176K), this would incorrectly expire all 175.5K records not in the current batch.

**Solution:** Add an `expire_missing` parameter to `scd2_upsert`:

```python
def scd2_upsert(
    cursor, schema, table, records, key_columns, value_columns,
    expire_missing: bool = True,  # New parameter, default preserves existing behavior
):
```

When `expire_missing=False`, skip the "Deleted: key not in incoming data" clause in the expire SQL. Only expire records that exist in both the incoming batch AND the current table but have different values.

The assessment asset calls `scd2_upsert(..., expire_missing=False)` during backfill and incremental runs. After full backfill + weekly delta mode, it can optionally use `expire_missing=True` for full refresh runs.

### Weekly Refresh (After Initial Backfill)

Once Tier 2 is complete for all properties, weekly runs switch to **delta mode**:
1. Compare `staging.parcels` (GIS) against `staging.assessment_properties`
2. Identify properties with changed owner, sale price, or new PIDNs
3. Only re-scrape changed/new properties (typically hundreds, not 176K)
4. Full re-scrape triggered monthly via config flag or when delta exceeds threshold

---

## Schema Mapping

### SCD2 Column Constants

```python
KEY_COLUMNS = ["pidn"]

VALUE_COLUMNS = [
    "parid", "owner_name", "address", "municipality", "school_district",
    "property_class", "land_use_code", "assessed_land", "assessed_building",
    "assessed_total", "sale_date", "sale_price", "permits",
    "delinquent_taxes", "value_history",
]
```

### From Search Results (Tier 1)

| Search Result Column | staging.assessment_properties Column |
|---|---|
| Parcel (18-digit) | `parid` |
| — (computed) | `pidn` via `parid_to_pidn(parid)` |
| Owner | `owner_name` |
| Location | `address` |
| Class | `property_class` |

### From Printable Summary (Tier 2)

| Portal Field | staging Column | Source Tab |
|---|---|---|
| MUNICIPALITY | `municipality` | Profile header |
| SCHOOL | `school_district` | Profile header |
| LUC | `land_use_code` | Profile body |
| Appraised Land | `assessed_land` | Values |
| Appraised Building | `assessed_building` | Values |
| Appraised Total | `assessed_total` | Values |
| Sale Date (most recent) | `sale_date` | Sales |
| Sale Price (most recent) | `sale_price` | Sales |
| All permits | `permits` (JSONB array) | Permits |
| All delinquent tax records | `delinquent_taxes` (JSONB array) | Delinquent Taxes |
| Historical assessment values | `value_history` (JSONB array) | Value History |

### PARID→PIDN Conversion

The `staging.parid_to_pidn(parid)` SQL function already exists in migration 001:
```sql
-- PARID: 460000100010000000 → PIDN: 4600001001000 (13-char)
SELECT CONCAT(
    SUBSTRING(parid FROM 1 FOR 2),   -- district: "46"
    SUBSTRING(parid FROM 4 FOR 3),   -- "000"
    SUBSTRING(parid FROM 8 FOR 2),   -- "01"
    SUBSTRING(parid FROM 11 FOR 6)   -- "001000"
);
```

**Python implementation** (0-based indexing):
```python
def parid_to_pidn(parid: str) -> str:
    """Convert 18-digit PARID to 13-char PIDN.

    SQL uses 1-based SUBSTRING; Python uses 0-based slicing.
    PARID: 460000100010000000
           ^^ ^^^ ^^ ^^^^^^
           01 345 78 10-15    (0-based)
    PIDN:  46 000 01 001000  = 4600001001000 (13 chars)
    """
    if not parid or len(parid) < 16:
        return ""
    return parid[0:2] + parid[3:6] + parid[7:9] + parid[10:16]
```

**Decimal precision:** Assessed values are parsed as integers (the portal displays them with commas but no cents, e.g., "28,530"). Currency fields use `Decimal` with 0 decimal places for consistent SCD2 comparison.

---

## Parser Design

### `parsers/assessment.py`

```python
# Key functions:

def parid_to_pidn(parid: str) -> str:
    """Convert 18-digit PARID to 13-char PIDN.
    Uses 0-based slicing: parid[0:2] + parid[3:6] + parid[7:9] + parid[10:16]
    """

def parse_search_results_page(html: str) -> list[dict]:
    """Extract property rows from search results HTML.
    Returns: [{"parid": str, "owner_name": str, "address": str, "property_class": str}]
    """

def get_total_found(html: str) -> int:
    """Extract 'Total found: N records' from results page."""

def parse_printable_summary(html: str) -> dict:
    """Extract all fields from Printable Summary HTML.
    Returns: {
        "municipality": str, "school_district": str, "land_use_code": str,
        "assessed_land": int, "assessed_building": int, "assessed_total": int,
        "sale_date": str, "sale_price": int,
        "permits": list[dict], "delinquent_taxes": list[dict], "value_history": list[dict]
    }
    """
```

**HTML parsing:** Use `BeautifulSoup` (already a project dependency via other parsers). The portal uses table-based layouts with predictable cell label→value patterns.

---

## Asset Design

### `assets/scrapers/assessment.py`

```python
@asset(
    group_name="scrapers",
    description=f"{get_county_config().name} assessment data from iasWorld portal → staging.assessment_properties",
    kinds={"postgres", "playwright"},
)
def assessment_scrape(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Two-tier scrape: search results sweep + detail enrichment."""
```

**Configuration via county_config:**
- `county.assessment_url` — portal base URL (exists)
- `county.assessment_min_records` — truncation guard, 150,000 (exists)

**New county_config fields:**

```python
# Add to CountyConfig dataclass:
assessment_max_per_run: int = 500          # Tier 2 properties per execution
assessment_throttle_seconds: float = 5.0   # Delay between all requests
assessment_session_refresh: int = 200      # Re-establish session after N detail pages
```

These are added to the `CountyConfig` dataclass with defaults, so the York config only needs to override if the defaults are wrong.

### Asset Checks

```python
@asset_check(asset=assessment_scrape)
def assessment_record_count(database: DatabaseResource) -> AssetCheckResult:
    """Verify staging.assessment_properties has records.

    During backfill: passes if count > 0 (any progress).
    After backfill: passes if count > assessment_min_records (150K).
    Uses the checkpoint to determine which mode applies.
    """

@asset_check(asset=assessment_scrape)
def assessment_row_count_delta(database: DatabaseResource) -> AssetCheckResult:
    """Verify record count hasn't dropped by more than 50% vs. previous run."""
```

**Backfill-aware logic:** The record count check queries `meta.scrape_checkpoints` to determine if Tier 2 is complete. If not, it only verifies count > 0 (any progress). Once backfill is complete, it enforces the full 150K threshold.

---

## Throttling and Politeness

| Setting | Value | Rationale |
|---|---|---|
| Inter-request delay | 5 seconds | All requests — consistent, safe for ASP.NET session |
| Session refresh | Every 200 detail pages | Prevent ASP.NET session timeout |
| Max retries per request | 3 | With exponential backoff (10s, 30s, 90s) |
| Max properties per run | 500 (configurable) | ~1 hour per execution |
| User-Agent | Standard Chrome UA | Already set in `playwright_utils.py` |

---

## Error Handling

| Scenario | Action |
|---|---|
| Disclaimer page appears mid-session | Re-accept and retry current operation |
| "No records found" for a prefix | Skip prefix, log warning |
| Page load timeout | Retry with backoff (max 3 attempts) |
| Session expired (unexpected page) | Close browser, reopen, re-accept disclaimer, resume from checkpoint |
| HTML structure changed (parser fails) | Log error with raw HTML sample, skip property, continue |
| Total properties < 150,000 after Tier 1 | Fail asset check, alert via Dagster sensor |
| Network error | Retry with backoff; after 3 failures, save checkpoint and exit gracefully |

---

## Testing Strategy

### Unit Tests (`test_assessment_parser.py`)

1. `test_parid_to_pidn` — verify conversion with known PARID/PIDN pairs
2. `test_parid_to_pidn_short_input` — returns empty string for invalid input
3. `test_parse_search_results` — parse sample search results HTML fixture
4. `test_get_total_found` — extract record count from results page
5. `test_parse_printable_summary` — parse sample Printable Summary HTML fixture
6. `test_parse_empty_permits` — handle properties with no permits
7. `test_parse_empty_delinquent_taxes` — handle properties with no delinquent taxes
8. `test_parse_multiple_sales` — extract most recent sale from sale history

### Integration Test (manual, local)

1. Start Docker Postgres, apply schema
2. Run asset with `assessment_max_per_run=10`
3. Verify 10 records in `staging.assessment_properties`
4. Verify PIDN matches GIS parcels data
5. Verify JSONB columns contain valid JSON arrays

---

## Migration Required

New Alembic migration to add the checkpoint table:

```python
# alembic/versions/NNN_add_scrape_checkpoints.py

def upgrade():
    op.create_table(
        "scrape_checkpoints",
        sa.Column("source_name", sa.Text, primary_key=True),
        sa.Column("checkpoint", JSONB, nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        schema="meta",
    )

def downgrade():
    op.drop_table("scrape_checkpoints", schema="meta")
```

---

## Dependencies

- `playwright` (already installed — `playwright_utils.py` exists)
- `beautifulsoup4` (for HTML parsing)
- No new infrastructure — uses existing Playwright browser on EC2, existing S3 bucket, existing Postgres

---

## Open Questions / Risks

1. **Printable Summary URL pattern:** Need to verify during implementation whether `PrintDatalet('all')` opens in the same window or a popup. May need to intercept the popup or find a direct URL.
2. **PARID character set:** Most PARIDs appear numeric, but some may contain letters (e.g., "24000KF0012A000000"). The prefix refinement algorithm includes A-Z to handle this.
3. **Rate limiting by the portal:** No evidence of rate limiting during exploration, but sustained scraping may trigger Tyler Technologies' infrastructure. The 5s delay should be safe.
4. **Full backfill timeline:** At 500 properties/run (weekly), complete Tier 2 takes ~352 weeks. Must run daily during initial period — at 3 runs/day, ~117 days.
