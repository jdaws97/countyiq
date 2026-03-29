# Tax Claim Bureau Pipeline Design

**Source:** #14 — York County Tax Claim Bureau
**URL:** https://yorkcountypa.gov/528/Tax-Sale-Information
**Data:** Delinquent Tax Claim Listing PDF at `/DocumentCenter/View/1911/Delinquent-Tax-Claim-Listing-PDF`
**Legal basis:** PA Real Estate Tax Sale Law (Act 542 of 1947) — legally required public notice
**Date:** 2026-03-29

---

## Purpose

Ingest the York County Delinquent Tax Claim Listing PDF into `staging.tax_claims` with one row per property-year-authority combination. This provides delinquent tax data for:

- Delinquent property map overlay on the frontend
- Financial distress analysis (properties delinquent 3+ years)
- Entity resolution — owner names from tax claims cross-referenced against GIS `owner_full` and PLCB licensees
- Tax delinquency by municipality/school district aggregations

This source was originally Phase 2 priority 5 but is pulled forward because the assessment scraper (Source #2) is deferred due to commercial-use ambiguity, and delinquent tax data was one of the three unique fields the assessment scraper provided.

---

## Exploration Findings (2026-03-29)

### Page Structure

The Tax Sale Information page at `yorkcountypa.gov/528/Tax-Sale-Information` is a CivicPlus CMS page with:

- Main content: sale type descriptions, upcoming sale dates, contact info
- Sidebar links:
  - **Delinquent Tax Claim Listing (PDF)** — the core data source (`/DocumentCenter/View/1911`)
  - **Online Payment For Delinquent Taxes** — external payment portal (not relevant)
  - **Tax Sale Information** — self-link

Other documents examined:
- **Upset Tax Sale 2026** (`/DocumentCenter/View/5223`) — Word doc, sale terms/procedures only
- **Repository Sale Procedures** (`/DocumentCenter/View/1918`) — PDF, bidding rules only (actual property list costs $50 from the office)

None of the other documents contain parseable property-level data. The Delinquent Tax Claim Listing PDF is the sole data source.

### PDF Structure

- **Size:** 4.5 MB, 1,241 pages
- **Title:** "YORK COUNTY, PA — TAX CLAIM LISTING FOR TAX YEAR: 2026"
- **Report date:** "AS OF BUSINESS DATE 03/27/2026"
- **Report ID:** DT510PAYOR
- **Grand total:** 9,030 PARIDs, $34.4M total delinquent
- **pdfplumber:** `extract_text()` returns clean, structured text; `extract_tables()` returns nothing (report layout, not tabular HTML)

### Record Layout

Each page has a consistent header:

```
YORK COUNTY, PA
MAR 27, 2026    TAX CLAIM LISTING FOR TAX YEAR: 2026    PAGE: 1
07:32 AM        AS OF BUSINESS DATE 03/27/2026           DT510PAYOR

                          -- TAXES --                    -- PAYMENTS --
PARCEL ID/              YEAR
OWNER NAME / LOCATION   BILLROLL  AUTH NAME  TAX  PENALTY  INTEREST  FEES  TAX  PENALTY  INTEREST  FEES  TOTAL
```

Properties are grouped by **Tax District Code/Name** (e.g., `TAX DIST CODE/NAME : 01 / YORK CITY 1ST WARD`).

Each property record:

```
01-001-01-0021.00-00000  2025  COUNTY    1,508.82   150.88    24.90   70.00     0.00    0.00    0.00    0.00   1,754.60
2 E MARKET STREET LLC          SCHOOL    8,240.01   824.00   135.96    0.00     0.00    0.00    0.00    0.00   9,199.97
2 E MARKET ST                  MUNICIPAL 4,148.17   414.82    68.44    0.00     0.00    0.00    0.00    0.00   4,631.43
                               *TOTAL:  13,897.00 1,389.70   229.30   70.00     0.00    0.00    0.00    0.00  15,586.00
                         2024  COUNTY    1,508.82   150.88   174.30  968.83     0.00    0.00    0.00    0.00   2,802.83
                               SCHOOL    8,158.42   815.84   942.34    0.00     0.00    0.00    0.00    0.00   9,916.60
                               MUNICIPAL 4,148.17   414.82   479.08    0.00     0.00    0.00    0.00    0.00   5,042.07
                               *TOTAL:  13,815.41 1,381.54 1,595.72  968.83     0.00    0.00    0.00    0.00  17,761.50
                              **TOTAL:  27,712.41 2,771.24 1,825.02 1,038.83    0.00    0.00    0.00    0.00  33,347.50
```

Key observations:
- First line of a property has: parcel ID, year, first authority row (COUNTY)
- Owner name on the second line, address on the third
- SCHOOL and MUNICIPAL rows follow under the same year
- Additional years appear below with no parcel ID prefix
- `*TOTAL:` = year subtotal, `**TOTAL:` = property grand total
- Some properties have partial payments (negative values in PAYMENTS columns)

### Parcel ID Format and PIDN Conversion

**Tax claim format:** `DD-BBB-MM-PPPP.SS-UUUUU`
- DD = district (2 digits)
- BBB = block (3 digits)
- MM = map (2 chars — can be alpha: `RE`, `AD`, `SF`, etc.)
- PPPP = parcel (4 digits)
- SS = sub-parcel (2 digits)
- UUUUU = unit suffix (5 chars — `00000` for standard, `C0001` for condo, `M0018` for mobile home, `L0001` for lot, `T0001` for other)

**PIDN conversion:** `DD + BBB + MM + PPPP + SS` = 13 characters

This is mathematically consistent with the existing `parid_to_pidn` function in the assessment parser, which extracts the same components from the 18-digit PARID format (DD_BBB_MM_PPPPSS__ where _ are zero-padded separators).

**Verified:** The GIS test fixture confirms PIDN = DISTRICT + BLOCK + MAP + PARCEL (e.g., `43` + `000` + `06` + `006500` = `4300006006500`). The tax claim format encodes the same components with dashes and a dot separator.

**Note:** GIS server was down during exploration (`Service OPEN_DATA/Parcels/MapServer not started`). Live cross-check of converted PIDNs against GIS parcels is deferred to implementation testing.

**Unit suffixes:** Multiple tax claim records can share one PIDN when a parcel has condo units (e.g., `01-001-01-0023.00-C0001` and `01-001-01-0023.00-C0002` both map to PIDN `0100101002300`). The unit suffix is stored as a separate column to distinguish these.

### Statistics

- **Map field values:** 55 numeric (01-66) + ~180 alpha codes (AD through SF)
- **Unit suffix types:** 931 of 6,542 captured IDs have alpha suffixes (C=condo, M=mobile home, L=lot, T=other)
- **Captured vs reported:** regex captured 6,542 unique IDs; report grand total says 9,030 PARIDs — difference likely due to regex not matching all format edge cases (will be refined during implementation)

---

## Architecture

### Data Flow

```
Weekly schedule (Sunday, bulk_refresh job)
  → HTTP GET /DocumentCenter/View/1911/Delinquent-Tax-Claim-Listing-PDF
  → PDF bytes (4.5 MB)
  → Archive to S3 (s3://countyiq-raw/york/bulk/tax_claims/<date>/listing.pdf)
  → pdfplumber.open() → iterate pages → extract_text()
  → Line-by-line state machine parser → list[dict]
  → SCD2 upsert → staging.tax_claims (expire_missing=True, scoped to report_date)
```

### Files

| File | Purpose |
|---|---|
| `pipelines/countyiq/assets/bulk/tax_claims.py` | Dagster asset — download, archive, parse, upsert |
| `pipelines/countyiq/lib/parsers/tax_claims.py` | State machine parser + PIDN conversion |
| `pipelines/tests/test_tax_claims_parser.py` | Parser unit tests |
| `pipelines/tests/fixtures/tax_claims_sample.txt` | Extracted text from 2-3 real PDF pages |
| `pipelines/alembic/versions/008_tax_claims.py` | Migration for staging.tax_claims |

### County Config Additions

```python
# In CountyConfig dataclass
tax_claims_pdf_url: str = ""          # DocumentCenter PDF URL
tax_claims_min_records: int = 5000    # Truncation guard

# In york config
tax_claims_pdf_url="https://yorkcountypa.gov/DocumentCenter/View/1911/Delinquent-Tax-Claim-Listing-PDF",
tax_claims_min_records=5000,
```

---

## Data Model

### Table: `staging.tax_claims`

**Composite key:** `pidn + unit_suffix + tax_year + authority_name`

| Column | Type | Notes |
|---|---|---|
| `pidn` | `VARCHAR(13) NOT NULL` | Converted from tax claim parcel ID |
| `parcel_id_raw` | `VARCHAR(30) NOT NULL` | Original formatted ID for audit trail |
| `unit_suffix` | `VARCHAR(10) DEFAULT '00000'` | Unit identifier (`00000`, `C0001`, `M0018`, etc.) |
| `tax_district_code` | `VARCHAR(5)` | District code (e.g., `01`) |
| `tax_district_name` | `VARCHAR(100)` | District name (e.g., `YORK CITY 1ST WARD`) |
| `owner_name` | `TEXT` | Owner name as listed |
| `property_address` | `TEXT` | Property location |
| `tax_year` | `INTEGER NOT NULL` | Delinquent tax year |
| `authority_name` | `VARCHAR(20) NOT NULL` | `COUNTY`, `SCHOOL`, or `MUNICIPAL` |
| `tax_owed` | `NUMERIC(12,2)` | Tax amount owed |
| `penalty_owed` | `NUMERIC(12,2)` | Penalty owed |
| `interest_owed` | `NUMERIC(12,2)` | Interest owed |
| `fees_owed` | `NUMERIC(12,2)` | Fees owed |
| `tax_paid` | `NUMERIC(12,2)` | Tax payments (negative = payment made) |
| `penalty_paid` | `NUMERIC(12,2)` | Penalty payments |
| `interest_paid` | `NUMERIC(12,2)` | Interest payments |
| `fees_paid` | `NUMERIC(12,2)` | Fee payments |
| `total` | `NUMERIC(12,2)` | Net total per authority-year |
| `report_date` | `DATE NOT NULL` | "AS OF BUSINESS DATE" from PDF header |
| `valid_from` | `TIMESTAMPTZ DEFAULT NOW()` | SCD2 |
| `valid_to` | `TIMESTAMPTZ` | SCD2 (NULL = current) |

**SCD2 behavior:** `expire_missing=True` — when a property disappears from the listing (taxes paid), its records get `valid_to = NOW()`. This means current delinquencies always have `valid_to IS NULL`.

---

## Parser Design

### State Machine

The parser processes `extract_text()` output line by line with these states:

1. **HEADER** — Look for report date in `AS OF BUSINESS DATE MM/DD/YYYY`
2. **DISTRICT** — `TAX DIST CODE/NAME : DD / NAME` → set current district code and name
3. **PARCEL_START** — Line matching `DD-BBB-MM-PPPP.SS-UUUUU  YYYY  AUTH  num num num num num num num num num` → start new property, capture parcel ID + first authority row
4. **OWNER** — First non-numeric, non-total text line after parcel start → owner name
5. **ADDRESS** — Second text line → property address
6. **AUTHORITY_ROW** — Line with `COUNTY|SCHOOL|MUNICIPAL` + 9 numbers → additional year/authority row for current property
7. **YEAR_ROW** — Line starting with a 4-digit year → new year block for current property
8. **SKIP** — Lines matching `*TOTAL:`, `**TOTAL:`, `TOTAL FOR DISTRICT`, column headers, page headers

### Key Regex Patterns

```python
# Parcel ID + first data row
PARCEL_LINE = re.compile(
    r'^(\d{2}-\d{3}-\w{2}-\d{4}\.\d{2}-\w{5})\s+'  # parcel ID
    r'(\d{4})\s+'                                     # year
    r'(COUNTY|SCHOOL|MUNICIPAL)\s+'                   # authority
    r'([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+'  # taxes owed (4 cols)
    r'([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+'  # payments (4 cols)
    r'([\d,.-]+)'                                     # total
)

# Continuation authority row (no parcel ID, has authority name)
AUTH_ROW = re.compile(
    r'^\s+(COUNTY|SCHOOL|MUNICIPAL)\s+'
    r'([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+'
    r'([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+'
    r'([\d,.-]+)'
)

# Year continuation (new year for same property)
YEAR_LINE = re.compile(
    r'^\s+(\d{4})\s+'
    r'(COUNTY|SCHOOL|MUNICIPAL)\s+'
    r'([\d,.-]+)\s+'  # ... same numeric pattern
)

# District header
DISTRICT_LINE = re.compile(r'TAX DIST CODE/NAME\s*:\s*(\d+)\s*/\s*(.+)')

# Report date
REPORT_DATE = re.compile(r'AS OF BUSINESS DATE\s+(\d{2}/\d{2}/\d{4})')

# Lines to skip
SKIP_LINES = re.compile(r'^\s*\*+TOTAL:|^TOTAL FOR DISTRICT|^YORK COUNTY|^PARCEL ID|^---')
```

### PIDN Conversion

```python
def tax_claim_id_to_pidn(parcel_id: str) -> tuple[str, str]:
    """Convert tax claim parcel ID to (pidn, unit_suffix).

    Args:
        parcel_id: e.g., '01-001-01-0002.00-00000'

    Returns:
        ('0100101000200', '00000')  — 13-char PIDN + unit suffix
    """
    m = re.match(r'(\d{2})-(\d{3})-(\w{2})-(\d{4})\.(\d{2})-(\w{5})', parcel_id)
    if not m:
        return ('', '')
    district, block, map_code, parcel, sub, unit = m.groups()
    pidn = district + block + map_code + parcel + sub
    return (pidn, unit)
```

### Number Parsing

```python
def parse_amount(text: str) -> float:
    """Parse currency amount: '1,508.82' → 1508.82, '-2,039.46' → -2039.46"""
    return float(text.replace(',', ''))
```

---

## Schedule and Integration

### Schedule

Add to existing `weekly_bulk` or `bulk_refresh` job. Weekly on Sunday is sufficient — the PDF updates periodically (the report date was March 27 for a report accessed March 29, suggesting it updates every few days or weekly).

### County Config

Add `tax_claims_pdf_url` and `tax_claims_min_records` to `CountyConfig` dataclass and the `york` config entry.

### Jobs

Add `tax_claims` asset to the `bulk_refresh` job's asset selection.

### Definitions

No changes to `definitions.py` — `load_assets_from_package_module(assets)` auto-discovers new assets.

---

## Asset Checks

1. **Record count:** `staging.tax_claims` current records > `tax_claims_min_records` (5,000)
2. **Row count delta:** Current count vs previous run < 50% change
3. **Report date freshness:** `report_date` within 90 days of current date (catches stale/broken PDF URL)

---

## Testing

### Parser Unit Tests

1. `test_parse_parcel_line` — full parcel + first authority row
2. `test_parse_continuation_authority` — SCHOOL/MUNICIPAL rows after COUNTY
3. `test_parse_multi_year` — property with 2025 + 2024 data
4. `test_parse_district_header` — district code and name extraction
5. `test_parse_report_date` — date extraction from header
6. `test_skip_totals` — `*TOTAL:` and `**TOTAL:` lines skipped
7. `test_tax_claim_id_to_pidn` — standard parcel ID conversion
8. `test_tax_claim_id_to_pidn_alpha_map` — alpha map code (e.g., `RE`)
9. `test_tax_claim_id_to_pidn_condo_unit` — condo suffix extraction
10. `test_parse_negative_payments` — negative values in payment columns
11. `test_parse_full_page` — end-to-end parse of sample page text

### Test Fixture

Extract text from 2-3 pages of the real PDF covering:
- A district header
- Properties with single-year and multi-year delinquencies
- A condo unit (alpha suffix)
- Negative payment values
- District total lines (to verify they're skipped)

---

## Edge Cases

1. **Page breaks mid-property:** A property's authority rows may span two pages. The parser carries state across pages — it processes all pages sequentially, so a property started on page N continues on page N+1.

2. **Alpha map codes:** 180+ alpha codes (AD, AE, RE, etc.) are valid in PIDN. The parser handles `\w{2}` for the map field.

3. **Condo units sharing a PIDN:** Multiple tax claim records (e.g., `C0001`, `C0002`) map to the same PIDN. The `unit_suffix` column differentiates them. The composite key includes `unit_suffix`.

4. **Properties with $0 balance:** Some properties show all taxes paid (negative payments equal positive charges, total = 0). These are still included — they represent resolved delinquencies within the current report period.

5. **PDF URL stability:** The DocumentCenter URL (`/DocumentCenter/View/1911`) is a CivicPlus permalink. If the county publishes a new PDF, it may get a new document ID. The `tax_claims_pdf_url` config allows updating without code changes. The asset check for report date freshness will catch a stale URL.

6. **PRIM vs standard authority names:** Some pages show `PRIM SCHOOL` instead of `SCHOOL` on district total lines. The parser handles this in the skip pattern. Individual property rows consistently use `SCHOOL`.

7. **Regex capture gap (6,542 vs 9,030):** The initial regex captured ~72% of the reported PARID count. During implementation, the regex will be refined to catch remaining edge cases — likely wider digit ranges, whitespace variations, or line-wrapping on long owner names.
