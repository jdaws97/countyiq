# Tax Claim Bureau Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingest the York County Delinquent Tax Claim Listing PDF into `staging.tax_claims` with one row per property-year-authority combination.

**Architecture:** HTTP GET downloads a 4.5 MB PDF (1,241 pages). pdfplumber extracts text per page. A state machine parser converts the report-style text into structured records. Records are SCD2 upserted with `expire_missing=True` so resolved delinquencies get expired.

**Tech Stack:** pdfplumber (already installed), requests, psycopg2, Dagster assets, Alembic migrations, pytest

**Spec:** `docs/superpowers/specs/2026-03-29-tax-claims-pipeline-design.md`

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `pipelines/tests/fixtures/tax_claims_sample.txt` | Create | Extracted text from 2 real PDF pages for parser tests |
| `pipelines/countyiq/lib/parsers/tax_claims.py` | Create | State machine parser + PIDN conversion |
| `pipelines/tests/test_tax_claims_parser.py` | Create | Parser unit tests |
| `pipelines/alembic/versions/008_tax_claims.py` | Create | Alembic migration for staging.tax_claims |
| `pipelines/countyiq/lib/county_config.py` | Modify | Add `tax_claims_pdf_url` and `tax_claims_min_records` |
| `pipelines/countyiq/assets/bulk/tax_claims.py` | Create | Dagster asset — download, archive, parse, upsert |

No changes needed to `definitions.py`, `jobs/__init__.py`, or `schedules/__init__.py` — the asset uses `group_name="bulk"` which is already selected by `bulk_refresh` job.

---

### Task 1: Create Test Fixture

**Files:**
- Create: `pipelines/tests/fixtures/tax_claims_sample.txt`

The fixture is extracted text from 2 pages of the real PDF. Page 1 covers: standard properties, multi-year delinquencies, condo units (C0001/C0002), negative payment values, district header. A second section covers alpha map codes (NC).

- [ ] **Step 1: Extract fixture text from the real PDF**

The PDF is already downloaded at `/tmp/tax_claim_listing.pdf`. Run:

```bash
cd pipelines && source .venv/bin/activate && python3 << 'PYEOF'
import pdfplumber

pdf = pdfplumber.open('/tmp/tax_claim_listing.pdf')

# Page 1: district header, multi-year, condo units, negative payments
text_p1 = pdf.pages[0].extract_text()

# Page 321: alpha map codes (NC), fully-paid properties ($0 totals)
text_p321 = pdf.pages[320].extract_text()

with open('tests/fixtures/tax_claims_sample.txt', 'w') as f:
    f.write(text_p1)
    f.write('\n')
    f.write(text_p321)

pdf.close()
print("Fixture written")
PYEOF
```

- [ ] **Step 2: Verify the fixture has good coverage**

```bash
grep -c '^[0-9][0-9]-[0-9][0-9][0-9]-' tests/fixtures/tax_claims_sample.txt
```

Expected: 10+ parcel ID lines across both pages.

- [ ] **Step 3: Commit**

```bash
git add tests/fixtures/tax_claims_sample.txt
git commit -m "test: add tax claims PDF text fixture for parser tests"
```

---

### Task 2: Write PIDN Conversion and Parser Skeleton

**Files:**
- Create: `pipelines/countyiq/lib/parsers/tax_claims.py`
- Create: `pipelines/tests/test_tax_claims_parser.py`

- [ ] **Step 1: Write the failing PIDN conversion tests**

Create `pipelines/tests/test_tax_claims_parser.py`:

```python
from pathlib import Path

from countyiq.lib.parsers.tax_claims import tax_claim_id_to_pidn

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_pidn_standard():
    pidn, unit = tax_claim_id_to_pidn("01-001-01-0002.00-00000")
    assert pidn == "0100101000200"
    assert unit == "00000"


def test_pidn_condo_unit():
    pidn, unit = tax_claim_id_to_pidn("01-001-01-0023.00-C0001")
    assert pidn == "0100101002300"
    assert unit == "C0001"


def test_pidn_alpha_map():
    pidn, unit = tax_claim_id_to_pidn("20-000-NC-0073.A0-00000")
    assert pidn == "20000NC0073A0"
    assert unit == "00000"


def test_pidn_mobile_home():
    pidn, unit = tax_claim_id_to_pidn("27-000-RE-0021.00-M0018")
    assert pidn == "27000RE002100"
    assert unit == "M0018"


def test_pidn_invalid():
    pidn, unit = tax_claim_id_to_pidn("INVALID")
    assert pidn == ""
    assert unit == ""
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd pipelines && source .venv/bin/activate && pytest tests/test_tax_claims_parser.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'countyiq.lib.parsers.tax_claims'`

- [ ] **Step 3: Write the parser module with PIDN conversion**

Create `pipelines/countyiq/lib/parsers/tax_claims.py`:

```python
"""Parse York County Delinquent Tax Claim Listing PDF text.

The PDF is a report-style layout (not tabular HTML). pdfplumber's
extract_text() returns clean text that this module parses line-by-line
using a state machine.

Two entry points:
  - tax_claim_id_to_pidn() — convert parcel ID to (pidn, unit_suffix)
  - parse_tax_claims_text() — parse full extracted text into records
"""

import re
from datetime import date, datetime


def tax_claim_id_to_pidn(parcel_id: str) -> tuple[str, str]:
    """Convert tax claim parcel ID to (pidn, unit_suffix).

    Format: DD-BBB-MM-PPPP.SS-UUUUU
    PIDN:   DD + BBB + MM + PPPP + SS  (13 chars)

    Examples:
        '01-001-01-0002.00-00000' → ('0100101000200', '00000')
        '20-000-NC-0073.A0-00000' → ('20000NC0073A0', '00000')
        '01-001-01-0023.00-C0001' → ('0100101002300', 'C0001')
    """
    m = re.match(r"(\d{2})-(\d{3})-(\w{2})-(\d{4})\.(\w{2})-(\w{5})", parcel_id)
    if not m:
        return ("", "")
    district, block, map_code, parcel, sub, unit = m.groups()
    pidn = district + block + map_code + parcel + sub
    return (pidn, unit)
```

- [ ] **Step 4: Run tests to verify PIDN conversion passes**

```bash
pytest tests/test_tax_claims_parser.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add pipelines/countyiq/lib/parsers/tax_claims.py pipelines/tests/test_tax_claims_parser.py
git commit -m "feat(parser): add tax claim parcel ID to PIDN conversion"
```

---

### Task 3: Write the Text Parser (TDD)

**Files:**
- Modify: `pipelines/countyiq/lib/parsers/tax_claims.py`
- Modify: `pipelines/tests/test_tax_claims_parser.py`

- [ ] **Step 1: Write failing parser tests**

Append to `pipelines/tests/test_tax_claims_parser.py`:

```python
from countyiq.lib.parsers.tax_claims import parse_tax_claims_text


def _fixture_text():
    return (FIXTURES_DIR / "tax_claims_sample.txt").read_text()


def test_parse_extracts_report_date():
    records = parse_tax_claims_text(_fixture_text())
    assert len(records) > 0
    # All records should have the same report date
    dates = {r["report_date"] for r in records}
    assert len(dates) == 1
    assert dates.pop() == date(2026, 3, 27)


def test_parse_extracts_district():
    records = parse_tax_claims_text(_fixture_text())
    district_01 = [r for r in records if r["tax_district_code"] == "01"]
    assert len(district_01) > 0
    assert district_01[0]["tax_district_name"] == "YORK CITY 1ST WARD"


def test_parse_standard_property():
    records = parse_tax_claims_text(_fixture_text())
    # 01-001-01-0006.00-00000 has a single year (2025), 3 authority rows
    hits = [r for r in records if r["parcel_id_raw"] == "01-001-01-0006.00-00000"]
    assert len(hits) == 3  # COUNTY, SCHOOL, MUNICIPAL
    county = next(r for r in hits if r["authority_name"] == "COUNTY")
    assert county["pidn"] == "0100101000600"
    assert county["tax_year"] == 2025
    assert county["tax_owed"] == 0.0
    assert county["fees_owed"] == 55.0


def test_parse_multi_year_property():
    records = parse_tax_claims_text(_fixture_text())
    # 01-001-01-0021.00-00000 has 2025 + 2024 = 6 authority rows
    hits = [r for r in records if r["parcel_id_raw"] == "01-001-01-0021.00-00000"]
    assert len(hits) == 6
    years = sorted({r["tax_year"] for r in hits})
    assert years == [2024, 2025]


def test_parse_condo_unit():
    records = parse_tax_claims_text(_fixture_text())
    hits = [r for r in records if r["parcel_id_raw"] == "01-001-01-0023.00-C0001"]
    assert len(hits) > 0
    assert hits[0]["unit_suffix"] == "C0001"
    assert hits[0]["pidn"] == "0100101002300"


def test_parse_negative_payments():
    records = parse_tax_claims_text(_fixture_text())
    # 01-001-01-0002.00-00000 COUNTY row has tax_paid = -2039.46
    hits = [r for r in records if r["parcel_id_raw"] == "01-001-01-0002.00-00000"
            and r["authority_name"] == "COUNTY"]
    assert len(hits) >= 1
    # fees_paid should be -55.0
    assert hits[0]["fees_paid"] == -55.0


def test_parse_owner_and_address():
    records = parse_tax_claims_text(_fixture_text())
    hits = [r for r in records if r["parcel_id_raw"] == "01-001-01-0006.00-00000"]
    assert hits[0]["owner_name"] == "BRATIC DUSAN & KATHLEEN M"
    assert hits[0]["property_address"] == "21 -25 S GEORGE ST"


def test_parse_alpha_map_code():
    records = parse_tax_claims_text(_fixture_text())
    hits = [r for r in records if r["parcel_id_raw"] == "20-000-NC-0073.A0-00000"]
    assert len(hits) > 0
    assert hits[0]["pidn"] == "20000NC0073A0"
    assert hits[0]["tax_district_code"] == "20"


def test_parse_skips_totals():
    records = parse_tax_claims_text(_fixture_text())
    # No record should have authority_name containing "TOTAL"
    for r in records:
        assert "TOTAL" not in r["authority_name"]


def test_parse_record_count():
    records = parse_tax_claims_text(_fixture_text())
    # Fixture has 2 pages of data. Should have a reasonable number of records.
    # Page 1 has ~8 properties, page 321 has more. Each has 3+ auth rows.
    assert len(records) > 20
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_tax_claims_parser.py -v -k "parse_"
```

Expected: FAIL — `ImportError: cannot import name 'parse_tax_claims_text'`

- [ ] **Step 3: Implement the text parser**

Add to `pipelines/countyiq/lib/parsers/tax_claims.py`:

```python
# Regex patterns
_REPORT_DATE = re.compile(r"AS OF BUSINESS DATE\s+(\d{2}/\d{2}/\d{4})")
_DISTRICT = re.compile(r"TAX DIST CODE/NAME\s*:\s*(\d+)\s*/\s*(.+)")
_PARCEL_LINE = re.compile(
    r"^(\d{2}-\d{3}-\w{2}-\d{4}\.\w{2}-\w{5})\s+"
    r"(\d{4})\s+"
    r"(COUNTY|SCHOOL|MUNICIPAL)\s+"
    r"([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+"
    r"([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+"
    r"([\d,.-]+)"
)
_YEAR_AUTH_LINE = re.compile(
    r"^\s+(\d{4})\s+"
    r"(COUNTY|SCHOOL|MUNICIPAL)\s+"
    r"([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+"
    r"([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+"
    r"([\d,.-]+)"
)
_AUTH_ONLY_LINE = re.compile(
    r"^\s+(COUNTY|SCHOOL|MUNICIPAL)\s+"
    r"([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+"
    r"([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+"
    r"([\d,.-]+)"
)
_SKIP = re.compile(
    r"^\s*\*+TOTAL:|^TOTAL FOR DISTRICT|^TOTAL PARCEL|"
    r"^YORK COUNTY|^PARCEL ID|^OWNER NAME|^---+|"
    r"^\s*$|^GRAND TOTAL|^PARID CNT|^\s+PRIM\s"
)


def _parse_amount(text: str) -> float:
    """Parse currency: '1,508.82' → 1508.82, '-2,039.46' → -2039.46"""
    return float(text.replace(",", ""))


def parse_tax_claims_text(text: str) -> list[dict]:
    """Parse extracted PDF text into tax claim records.

    Returns one dict per property-year-authority combination with keys:
        pidn, parcel_id_raw, unit_suffix, tax_district_code,
        tax_district_name, owner_name, property_address, tax_year,
        authority_name, tax_owed, penalty_owed, interest_owed, fees_owed,
        tax_paid, penalty_paid, interest_paid, fees_paid, total, report_date
    """
    records: list[dict] = []
    report_date: date | None = None
    district_code = ""
    district_name = ""

    # Current property state
    current_parcel_id = ""
    current_pidn = ""
    current_unit = ""
    current_year = 0
    owner_line_pending = False
    address_line_pending = False
    current_owner = ""
    current_address = ""

    for line in text.split("\n"):
        # Extract report date (once)
        if report_date is None:
            m = _REPORT_DATE.search(line)
            if m:
                report_date = datetime.strptime(m.group(1), "%m/%d/%Y").date()
                continue

        # Skip non-data lines
        if _SKIP.match(line):
            owner_line_pending = False
            address_line_pending = False
            continue

        # District header
        m = _DISTRICT.match(line)
        if m:
            district_code = m.group(1).strip()
            district_name = m.group(2).strip()
            owner_line_pending = False
            address_line_pending = False
            continue

        # New property (parcel ID + first data row)
        m = _PARCEL_LINE.match(line)
        if m:
            current_parcel_id = m.group(1)
            current_pidn, current_unit = tax_claim_id_to_pidn(current_parcel_id)
            current_year = int(m.group(2))
            current_owner = ""
            current_address = ""
            owner_line_pending = True
            address_line_pending = False
            records.append(_make_record(
                m, 3, current_parcel_id, current_pidn, current_unit,
                current_year, district_code, district_name,
                "", "", report_date,
            ))
            continue

        # Owner name line (first text line after parcel)
        if owner_line_pending:
            # Check it's not another data row
            if not _AUTH_ONLY_LINE.match(line) and not _YEAR_AUTH_LINE.match(line):
                current_owner = line.strip().split("  ")[0].strip()
                owner_line_pending = False
                address_line_pending = True
                # Backfill owner on the record we just added
                if records and records[-1]["parcel_id_raw"] == current_parcel_id:
                    records[-1]["owner_name"] = current_owner
                continue

        # Address line (second text line after parcel)
        if address_line_pending:
            if not _AUTH_ONLY_LINE.match(line) and not _YEAR_AUTH_LINE.match(line):
                current_address = line.strip().split("  ")[0].strip()
                address_line_pending = False
                # Backfill address on all records for this parcel so far
                for r in reversed(records):
                    if r["parcel_id_raw"] != current_parcel_id:
                        break
                    r["property_address"] = current_address
                continue

        # Year + authority continuation (new year for same property)
        m = _YEAR_AUTH_LINE.match(line)
        if m:
            current_year = int(m.group(1))
            records.append(_make_record(
                m, 2, current_parcel_id, current_pidn, current_unit,
                current_year, district_code, district_name,
                current_owner, current_address, report_date,
            ))
            continue

        # Authority-only continuation (same year, next authority)
        m = _AUTH_ONLY_LINE.match(line)
        if m:
            records.append(_make_record(
                m, 1, current_parcel_id, current_pidn, current_unit,
                current_year, district_code, district_name,
                current_owner, current_address, report_date,
            ))
            continue

    return records


def _make_record(
    m, auth_group: int,
    parcel_id: str, pidn: str, unit: str, year: int,
    dist_code: str, dist_name: str,
    owner: str, address: str, report_date: date | None,
) -> dict:
    """Build a record dict from a regex match.

    auth_group: the match group index where authority_name starts.
    The 9 numeric columns follow immediately after.
    """
    g = auth_group
    return {
        "pidn": pidn,
        "parcel_id_raw": parcel_id,
        "unit_suffix": unit,
        "tax_district_code": dist_code,
        "tax_district_name": dist_name,
        "owner_name": owner,
        "property_address": address,
        "tax_year": year,
        "authority_name": m.group(g),
        "tax_owed": _parse_amount(m.group(g + 1)),
        "penalty_owed": _parse_amount(m.group(g + 2)),
        "interest_owed": _parse_amount(m.group(g + 3)),
        "fees_owed": _parse_amount(m.group(g + 4)),
        "tax_paid": _parse_amount(m.group(g + 5)),
        "penalty_paid": _parse_amount(m.group(g + 6)),
        "interest_paid": _parse_amount(m.group(g + 7)),
        "fees_paid": _parse_amount(m.group(g + 8)),
        "total": _parse_amount(m.group(g + 9)),
        "report_date": report_date,
    }
```

- [ ] **Step 4: Run tests and iterate until all pass**

```bash
pytest tests/test_tax_claims_parser.py -v
```

Expected: All tests PASS. If any fail, examine the fixture text and adjust regex patterns or parser logic. Common issues:
- Whitespace variations between columns
- Owner name on the same line as SCHOOL/MUNICIPAL authority (owner text before authority keyword)
- Lines where the owner name has multiple spaces in it

- [ ] **Step 5: Commit**

```bash
git add pipelines/countyiq/lib/parsers/tax_claims.py pipelines/tests/test_tax_claims_parser.py
git commit -m "feat(parser): tax claims PDF text parser with state machine"
```

---

### Task 4: Validate Parser Against Full PDF

**Files:**
- Modify: `pipelines/tests/test_tax_claims_parser.py` (add integration-style test)

This is the critical validation step. Run the parser against ALL 1,241 pages and verify coverage.

- [ ] **Step 1: Write a full-PDF validation script**

```bash
cd pipelines && source .venv/bin/activate && python3 << 'PYEOF'
import pdfplumber
from countyiq.lib.parsers.tax_claims import parse_tax_claims_text

pdf = pdfplumber.open('/tmp/tax_claim_listing.pdf')

# Extract all text
all_text = ""
for i, page in enumerate(pdf.pages):
    page_text = page.extract_text() or ""
    all_text += page_text + "\n"
    if (i + 1) % 200 == 0:
        print(f"  Extracted {i + 1}/{len(pdf.pages)} pages...")

pdf.close()
print(f"Total text length: {len(all_text)} chars")

# Parse
records = parse_tax_claims_text(all_text)
print(f"Total records parsed: {len(records)}")

# Stats
unique_parcels = len({r["parcel_id_raw"] for r in records})
unique_pidns = len({r["pidn"] for r in records})
years = sorted({r["tax_year"] for r in records})
authorities = sorted({r["authority_name"] for r in records})
districts = len({r["tax_district_code"] for r in records})
with_owner = sum(1 for r in records if r["owner_name"])
with_address = sum(1 for r in records if r["property_address"])

print(f"Unique parcel IDs: {unique_parcels}")
print(f"Unique PIDNs: {unique_pidns}")
print(f"Tax years: {years}")
print(f"Authorities: {authorities}")
print(f"Districts: {districts}")
print(f"Records with owner: {with_owner}/{len(records)}")
print(f"Records with address: {with_address}/{len(records)}")
print(f"Report date: {records[0]['report_date'] if records else 'none'}")

# Check for empty PIDNs (failed conversions)
empty_pidns = [r for r in records if not r["pidn"]]
if empty_pidns:
    print(f"\nWARNING: {len(empty_pidns)} records with empty PIDN")
    for r in empty_pidns[:5]:
        print(f"  raw: {r['parcel_id_raw']}")

# Target: report says 9,030 PARIDs. We should get close.
print(f"\nTarget: 9,030 PARIDs (from PDF grand total)")
print(f"Coverage: {unique_parcels / 9030 * 100:.1f}%")
PYEOF
```

Expected output: 7,000+ unique parcels (>75% coverage). If significantly lower, the regex needs refinement.

- [ ] **Step 2: If coverage is below 90%, debug and fix**

Identify missed parcel IDs by comparing against raw text patterns:

```bash
python3 << 'PYEOF'
import pdfplumber, re

pdf = pdfplumber.open('/tmp/tax_claim_listing.pdf')

# Find lines that look like parcel IDs but weren't caught
uncaught = []
parcel_re = re.compile(r"^(\d{2}-\d{3}-\w{2}-\d{4}\.\w{2}-\w+)")

for page in pdf.pages:
    text = page.extract_text() or ""
    for line in text.split("\n"):
        m = parcel_re.match(line)
        if m:
            pid = m.group(1)
            # Check if it matches our strict regex
            strict = re.match(r"\d{2}-\d{3}-\w{2}-\d{4}\.\w{2}-\w{5}$", pid)
            if not strict:
                uncaught.append(pid)

pdf.close()
print(f"Uncaught parcel IDs: {len(set(uncaught))}")
for pid in sorted(set(uncaught))[:20]:
    print(f"  {pid}")
PYEOF
```

Fix the regex in the parser to handle any new patterns discovered. Re-run the validation script until coverage is >90%.

- [ ] **Step 3: Commit any parser fixes**

```bash
git add pipelines/countyiq/lib/parsers/tax_claims.py
git commit -m "fix(parser): improve tax claims regex coverage"
```

---

### Task 5: Create Alembic Migration

**Files:**
- Create: `pipelines/alembic/versions/008_tax_claims.py`

- [ ] **Step 1: Write the migration**

Create `pipelines/alembic/versions/008_tax_claims.py`:

```python
"""add staging.tax_claims

Revision ID: 008
Revises: 007
Create Date: 2026-03-29
"""
from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tax_claims",
        sa.Column("pidn", sa.String(13), nullable=False),
        sa.Column("parcel_id_raw", sa.String(30), nullable=False),
        sa.Column("unit_suffix", sa.String(10), server_default="00000"),
        sa.Column("tax_district_code", sa.String(5)),
        sa.Column("tax_district_name", sa.String(100)),
        sa.Column("owner_name", sa.Text),
        sa.Column("property_address", sa.Text),
        sa.Column("tax_year", sa.Integer, nullable=False),
        sa.Column("authority_name", sa.String(20), nullable=False),
        sa.Column("tax_owed", sa.Numeric(12, 2)),
        sa.Column("penalty_owed", sa.Numeric(12, 2)),
        sa.Column("interest_owed", sa.Numeric(12, 2)),
        sa.Column("fees_owed", sa.Numeric(12, 2)),
        sa.Column("tax_paid", sa.Numeric(12, 2)),
        sa.Column("penalty_paid", sa.Numeric(12, 2)),
        sa.Column("interest_paid", sa.Numeric(12, 2)),
        sa.Column("fees_paid", sa.Numeric(12, 2)),
        sa.Column("total", sa.Numeric(12, 2)),
        sa.Column("report_date", sa.Date, nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("pidn", "unit_suffix", "tax_year", "authority_name", "valid_from"),
        schema="staging",
    )
    op.create_index(
        "idx_tax_claims_current", "tax_claims",
        ["pidn"], schema="staging",
        postgresql_where=sa.text("valid_to IS NULL"),
    )
    op.create_index(
        "idx_tax_claims_district", "tax_claims",
        ["tax_district_code"], schema="staging",
    )
    op.create_index(
        "idx_tax_claims_owner", "tax_claims",
        ["owner_name"], schema="staging",
    )


def downgrade() -> None:
    op.drop_table("tax_claims", schema="staging")
```

- [ ] **Step 2: Test migration against Docker Postgres**

```bash
cd pipelines && docker compose up -d postgres-test
sleep 3
# Apply init.sql for schemas, then all migrations
PGPASSWORD=localtest psql -h localhost -p 5433 -U dagster_admin -d countyiq -f ../init.sql 2>/dev/null
source .venv/bin/activate && DATABASE_URL="postgresql://dagster_admin:localtest@localhost:5433/countyiq" alembic upgrade head
```

Expected: Migration applies without errors.

- [ ] **Step 3: Verify table exists**

```bash
PGPASSWORD=localtest psql -h localhost -p 5433 -U dagster_admin -d countyiq -c "\d staging.tax_claims"
```

Expected: Table with all columns listed.

- [ ] **Step 4: Commit**

```bash
git add pipelines/alembic/versions/008_tax_claims.py
git commit -m "feat(migration): add staging.tax_claims table"
```

---

### Task 6: Add County Config Fields

**Files:**
- Modify: `pipelines/countyiq/lib/county_config.py`

- [ ] **Step 1: Add fields to CountyConfig dataclass**

In `pipelines/countyiq/lib/county_config.py`, add after the FEMA fields:

```python
    # Tax Claim Bureau (Delinquent Tax Listing PDF)
    tax_claims_pdf_url: str = ""       # DocumentCenter PDF URL
    tax_claims_min_records: int = 5000  # Truncation guard
```

- [ ] **Step 2: Add values to york config**

In the `"york"` entry of `COUNTY_CONFIGS`, add after the FEMA values:

```python
        tax_claims_pdf_url="https://yorkcountypa.gov/DocumentCenter/View/1911/Delinquent-Tax-Claim-Listing-PDF",
        tax_claims_min_records=5000,
```

- [ ] **Step 3: Run existing config test**

```bash
pytest tests/test_county_config.py -v
```

Expected: PASS (existing tests still work).

- [ ] **Step 4: Commit**

```bash
git add pipelines/countyiq/lib/county_config.py
git commit -m "feat(config): add tax_claims_pdf_url and min_records to county config"
```

---

### Task 7: Write the Dagster Asset

**Files:**
- Create: `pipelines/countyiq/assets/bulk/tax_claims.py`

- [ ] **Step 1: Write the asset**

Create `pipelines/countyiq/assets/bulk/tax_claims.py`:

```python
"""Tax Claim Bureau delinquent tax listing → staging.tax_claims.

Source: York County Tax Claim Bureau PDF
URL: /DocumentCenter/View/1911/Delinquent-Tax-Claim-Listing-PDF
Records: ~9,000 delinquent parcels (~30K+ authority-year rows)
Schedule: Weekly (Sunday, bulk_refresh job)
"""

import io
from datetime import date, timedelta

import pdfplumber
import requests
from dagster import (
    asset,
    asset_check,
    AssetCheckResult,
    AssetCheckSeverity,
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
)

from countyiq.lib.county_config import get_county_config
from countyiq.lib.parsers.tax_claims import parse_tax_claims_text
from countyiq.lib.scd import scd2_upsert
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

REQUEST_TIMEOUT = 120

KEY_COLUMNS = ["pidn", "unit_suffix", "tax_year", "authority_name"]

VALUE_COLUMNS = [
    "parcel_id_raw",
    "tax_district_code",
    "tax_district_name",
    "owner_name",
    "property_address",
    "tax_owed",
    "penalty_owed",
    "interest_owed",
    "fees_owed",
    "tax_paid",
    "penalty_paid",
    "interest_paid",
    "fees_paid",
    "total",
    "report_date",
]


@asset(
    group_name="bulk",
    description="Delinquent tax claims from York County Tax Claim Bureau PDF → staging.tax_claims",
    kinds={"postgres", "pdf"},
)
def tax_claims(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Download tax claim PDF, parse all pages, SCD2 upsert."""
    county = get_county_config()

    # 1. Download PDF
    context.log.info(f"Downloading tax claim PDF from {county.tax_claims_pdf_url}")
    resp = requests.get(county.tax_claims_pdf_url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    pdf_bytes = resp.content
    context.log.info(f"Downloaded {len(pdf_bytes)} bytes")

    # 2. Archive raw PDF to S3
    s3.archive(
        f"{county.s3_prefix}/bulk/tax_claims",
        pdf_bytes,
        filename="listing.pdf",
        binary=True,
    )

    # 3. Extract text from all pages
    context.log.info("Extracting text from PDF pages...")
    all_text = ""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for i, page in enumerate(pdf.pages):
            all_text += (page.extract_text() or "") + "\n"
            if (i + 1) % 200 == 0:
                context.log.info(f"  Extracted {i + 1}/{len(pdf.pages)} pages")
        context.log.info(f"Extracted text from {len(pdf.pages)} pages")

    # 4. Parse
    records = parse_tax_claims_text(all_text)
    context.log.info(f"Parsed {len(records)} tax claim records")

    if not records:
        context.log.warning("No tax claim records parsed — skipping upsert")
        return MaterializeResult(metadata={"record_count": MetadataValue.int(0)})

    # 4b. Truncation guard
    unique_parcels = len({r["parcel_id_raw"] for r in records})
    if unique_parcels < county.tax_claims_min_records:
        raise RuntimeError(
            f"Only {unique_parcels} unique parcels parsed "
            f"(expected >= {county.tax_claims_min_records}). "
            f"Possible truncated or changed PDF — aborting."
        )

    # 5. SCD2 upsert
    cur = database.cursor()
    try:
        stats = scd2_upsert(
            cursor=cur,
            schema="staging",
            table="tax_claims",
            records=records,
            key_columns=KEY_COLUMNS,
            value_columns=VALUE_COLUMNS,
        )
    finally:
        cur.close()

    return MaterializeResult(
        metadata={
            "record_count": MetadataValue.int(len(records)),
            "unique_parcels": MetadataValue.int(unique_parcels),
            "report_date": MetadataValue.text(str(records[0]["report_date"])),
            "inserted": MetadataValue.int(stats["inserted"]),
            "expired": MetadataValue.int(stats["expired"]),
            "unchanged": MetadataValue.int(stats["unchanged"]),
        }
    )


@asset_check(asset=tax_claims)
def tax_claims_record_count(database: DatabaseResource) -> AssetCheckResult:
    """Verify staging.tax_claims has enough current records."""
    county = get_county_config()
    result = database.execute(
        "SELECT COUNT(DISTINCT pidn) FROM staging.tax_claims WHERE valid_to IS NULL"
    )
    count = result[0][0] if result else 0
    passed = count >= county.tax_claims_min_records
    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.ERROR,
        metadata={
            "unique_pidns": MetadataValue.int(count),
            "threshold": MetadataValue.int(county.tax_claims_min_records),
        },
    )


@asset_check(asset=tax_claims)
def tax_claims_report_freshness(database: DatabaseResource) -> AssetCheckResult:
    """Verify report_date is within 90 days (catches stale PDF URL)."""
    result = database.execute(
        "SELECT MAX(report_date) FROM staging.tax_claims WHERE valid_to IS NULL"
    )
    if not result or result[0][0] is None:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.WARN,
            metadata={"error": MetadataValue.text("No records found")},
        )
    report_date = result[0][0]
    age_days = (date.today() - report_date).days
    return AssetCheckResult(
        passed=age_days <= 90,
        severity=AssetCheckSeverity.WARN,
        metadata={
            "report_date": MetadataValue.text(str(report_date)),
            "age_days": MetadataValue.int(age_days),
        },
    )
```

- [ ] **Step 2: Verify Dagster can load the asset**

```bash
cd pipelines && source .venv/bin/activate && python3 -c "
from countyiq.definitions import defs
assets = list(defs.get_asset_graph().all_asset_keys)
tax = [a for a in assets if 'tax' in str(a)]
print(f'Tax claim assets found: {tax}')
print(f'Total assets: {len(assets)}')
"
```

Expected: `tax_claims` appears in the asset list.

- [ ] **Step 3: Commit**

```bash
git add pipelines/countyiq/assets/bulk/tax_claims.py
git commit -m "feat(asset): tax claims PDF download, parse, and SCD2 upsert"
```

---

### Task 8: End-to-End Test Against Real PDF + Database

**Files:** None (validation only)

- [ ] **Step 1: Ensure Docker Postgres is running with schema**

```bash
cd pipelines && docker compose up -d postgres-test
sleep 3
PGPASSWORD=localtest psql -h localhost -p 5433 -U dagster_admin -d countyiq -f ../init.sql 2>/dev/null
source .venv/bin/activate && DATABASE_URL="postgresql://dagster_admin:localtest@localhost:5433/countyiq" alembic upgrade head
```

- [ ] **Step 2: Run the full parser against the real PDF and verify counts**

```bash
source .venv/bin/activate && python3 << 'PYEOF'
import pdfplumber
from countyiq.lib.parsers.tax_claims import parse_tax_claims_text

pdf = pdfplumber.open('/tmp/tax_claim_listing.pdf')
all_text = ""
for page in pdf.pages:
    all_text += (page.extract_text() or "") + "\n"
pdf.close()

records = parse_tax_claims_text(all_text)
unique_parcels = len({r["parcel_id_raw"] for r in records})
empty_pidns = sum(1 for r in records if not r["pidn"])
no_owner = sum(1 for r in records if not r["owner_name"])

print(f"Records: {len(records)}")
print(f"Unique parcels: {unique_parcels}")
print(f"Empty PIDNs: {empty_pidns}")
print(f"No owner: {no_owner}")
print(f"Report date: {records[0]['report_date'] if records else 'N/A'}")
print(f"Coverage: {unique_parcels/9030*100:.1f}% of 9,030 target")

# Sanity checks
assert len(records) > 15000, f"Too few records: {len(records)}"
assert unique_parcels > 5000, f"Too few parcels: {unique_parcels}"
assert empty_pidns == 0, f"Empty PIDNs: {empty_pidns}"
print("\nAll sanity checks passed!")
PYEOF
```

- [ ] **Step 3: Run all parser tests one final time**

```bash
pytest tests/test_tax_claims_parser.py -v
```

Expected: All tests PASS.

- [ ] **Step 4: Final commit if any fixes were made**

```bash
git add -u && git status
# Only commit if there are changes
git diff --cached --quiet || git commit -m "fix(parser): final tax claims parser refinements from full-PDF validation"
```
