# Assessment Database Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Playwright-based scraper that extracts all ~176K property records from the York County iasWorld Assessment portal and loads them into `staging.assessment_properties`.

**Architecture:** Two-tier scrape (search results sweep + printable summary enrichment) with DB-based checkpointing for resumability. Prefix-based batching to work within the portal's 500-result display cap. SCD2 upsert with `expire_missing=False` for incremental loads.

**Tech Stack:** Dagster, Playwright (sync API), BeautifulSoup4, psycopg2, PostgreSQL

**Spec:** `docs/superpowers/specs/2026-03-21-assessment-pipeline-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `pipelines/alembic/versions/006_scrape_checkpoints.py` | Create | Alembic migration for `meta.scrape_checkpoints` |
| `pipelines/countyiq/lib/scd.py` | Modify | Add `expire_missing` parameter |
| `pipelines/countyiq/lib/county_config.py` | Modify | Add assessment scraper config fields |
| `pipelines/countyiq/lib/parsers/assessment.py` | Create | HTML parsing for search results + printable summary |
| `pipelines/tests/fixtures/assessment_search_results.html` | Create | Sample search results HTML |
| `pipelines/tests/fixtures/assessment_printable_summary.html` | Create | Sample printable summary HTML |
| `pipelines/tests/test_assessment_parser.py` | Create | Parser unit tests |
| `pipelines/countyiq/assets/scrapers/__init__.py` | Create | Package init for Dagster discovery |
| `pipelines/countyiq/assets/scrapers/assessment.py` | Create | Dagster asset + checks |

---

## Task 1: Alembic Migration — `meta.scrape_checkpoints`

**Files:**
- Create: `pipelines/alembic/versions/006_scrape_checkpoints.py`

- [ ] **Step 1: Create the migration file**

```python
"""meta.scrape_checkpoints for resumable scraper state

Revision ID: 006
Revises: 005
Create Date: 2026-03-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scrape_checkpoints",
        sa.Column("source_name", sa.Text, primary_key=True),
        sa.Column("checkpoint", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
        ),
        schema="meta",
    )


def downgrade() -> None:
    op.drop_table("scrape_checkpoints", schema="meta")
```

- [ ] **Step 2: Apply migration to local Docker Postgres**

```bash
cd pipelines && source .venv/bin/activate
docker compose up -d postgres-test
export DATABASE_URL="postgresql://dagster_admin:localtest@localhost:5433/countyiq"
alembic upgrade head
```

Expected: migration 006 applied successfully.

- [ ] **Step 3: Verify table exists**

```bash
PGPASSWORD=localtest psql -h localhost -p 5433 -U dagster_admin -d countyiq -c "\dt meta.*"
```

Expected: `meta.scrape_checkpoints` in output.

- [ ] **Step 4: Commit**

```bash
git add pipelines/alembic/versions/006_scrape_checkpoints.py
git commit -m "feat(schema): add meta.scrape_checkpoints for resumable scrapers"
```

---

## Task 2: Add `expire_missing` to SCD2 Helper

**Files:**
- Modify: `pipelines/countyiq/lib/scd.py`

- [ ] **Step 1: Write a test for expire_missing=False behavior**

Create a quick test in `pipelines/tests/test_scd_expire_missing.py`:

```python
"""Test SCD2 upsert with expire_missing=False for incremental loads."""

import psycopg2
import pytest

from countyiq.lib.scd import scd2_upsert


@pytest.fixture
def db_conn():
    """Connect to local Docker Postgres test database."""
    conn = psycopg2.connect(
        host="localhost",
        port=5433,
        dbname="countyiq",
        user="dagster_admin",
        password="localtest",
    )
    yield conn
    conn.close()


@pytest.fixture
def test_table(db_conn):
    """Create a temporary test table with SCD2 columns."""
    cur = db_conn.cursor()
    cur.execute("DROP TABLE IF EXISTS _test_scd2")
    cur.execute("""
        CREATE TABLE _test_scd2 (
            id TEXT NOT NULL,
            name TEXT,
            valid_from TIMESTAMPTZ DEFAULT NOW() NOT NULL,
            valid_to TIMESTAMPTZ,
            PRIMARY KEY (id, valid_from)
        )
    """)
    db_conn.commit()
    yield
    cur.execute("DROP TABLE IF EXISTS _test_scd2")
    db_conn.commit()
    cur.close()


def test_expire_missing_false_preserves_absent_records(db_conn, test_table):
    """When expire_missing=False, records NOT in the incoming batch stay current."""
    cur = db_conn.cursor()

    # Seed two records
    scd2_upsert(
        cursor=cur,
        schema="public",
        table="_test_scd2",
        records=[
            {"id": "A", "name": "Alice"},
            {"id": "B", "name": "Bob"},
        ],
        key_columns=["id"],
        value_columns=["name"],
    )

    # Incremental upsert: only update A, don't mention B
    scd2_upsert(
        cursor=cur,
        schema="public",
        table="_test_scd2",
        records=[{"id": "A", "name": "Alice Updated"}],
        key_columns=["id"],
        value_columns=["name"],
        expire_missing=False,
    )

    # B should still be current (valid_to IS NULL)
    cur.execute(
        "SELECT id, name FROM _test_scd2 WHERE valid_to IS NULL ORDER BY id"
    )
    current = cur.fetchall()
    assert len(current) == 2
    assert current[0] == ("A", "Alice Updated")
    assert current[1] == ("B", "Bob")

    cur.close()
```

- [ ] **Step 2: Run test — should fail**

```bash
cd pipelines && source .venv/bin/activate
python3 -m pytest tests/test_scd_expire_missing.py -v
```

Expected: FAIL — `scd2_upsert() got an unexpected keyword argument 'expire_missing'`

- [ ] **Step 3: Add `expire_missing` parameter to `scd2_upsert`**

In `pipelines/countyiq/lib/scd.py`, modify the function signature and the expire SQL:

```python
def scd2_upsert(
    cursor,
    schema: str,
    table: str,
    records: list[dict],
    key_columns: list[str],
    value_columns: list[str],
    expire_missing: bool = True,
):
```

And in `_scd2_upsert_inner`, change the expire SQL to conditionally include the "deleted" clause:

Replace the `expire_sql` block (current lines 91-106) with:

```python
    # Step 1: Expire current records that have changed (or been deleted, if expire_missing=True)
    if expire_missing:
        expire_sql = f"""
            UPDATE {fqn} c SET valid_to = NOW()
            WHERE c.valid_to IS NULL
            AND (
                EXISTS (
                    SELECT 1 FROM {temp_table} t
                    WHERE {key_join} AND ({value_diff})
                )
                OR
                NOT EXISTS (
                    SELECT 1 FROM {temp_table} t WHERE {key_join}
                )
            )
        """
    else:
        expire_sql = f"""
            UPDATE {fqn} c SET valid_to = NOW()
            WHERE c.valid_to IS NULL
            AND EXISTS (
                SELECT 1 FROM {temp_table} t
                WHERE {key_join} AND ({value_diff})
            )
        """
    cursor.execute(expire_sql)
    expired = cursor.rowcount
```

Also pass `expire_missing` through from `scd2_upsert` to `_scd2_upsert_inner`:

Change the call on the current line 53 to:
```python
return _scd2_upsert_inner(cursor, fqn, all_columns, key_columns, value_columns, records, log, expire_missing)
```

And update `_scd2_upsert_inner` signature:
```python
def _scd2_upsert_inner(cursor, fqn, all_columns, key_columns, value_columns, records, log, expire_missing):
```

- [ ] **Step 4: Run test — should pass**

```bash
python3 -m pytest tests/test_scd_expire_missing.py -v
```

Expected: PASS

- [ ] **Step 5: Run existing tests to verify no regressions**

```bash
python3 -m pytest tests/ -v
```

Expected: All existing tests still pass (default `expire_missing=True` preserves old behavior).

- [ ] **Step 6: Commit**

```bash
git add pipelines/countyiq/lib/scd.py pipelines/tests/test_scd_expire_missing.py
git commit -m "feat(scd): add expire_missing parameter for incremental upserts"
```

---

## Task 3: Add Assessment Config Fields to `county_config.py`

**Files:**
- Modify: `pipelines/countyiq/lib/county_config.py`

- [ ] **Step 1: Add new fields to `CountyConfig` dataclass**

After the existing `assessment_min_records` line (line 44), add:

```python
    assessment_max_per_run: int = 500         # Tier 2 properties per execution
    assessment_throttle_seconds: float = 5.0  # Delay between all requests
    assessment_session_refresh: int = 200     # Re-establish session after N detail pages
```

No changes needed to the York config in `COUNTY_CONFIGS` — these defaults are correct.

- [ ] **Step 2: Verify module still imports cleanly**

```bash
cd pipelines && source .venv/bin/activate
python3 -c "from countyiq.lib.county_config import get_county_config; c = get_county_config(); print(c.assessment_url, c.assessment_max_per_run)"
```

Expected: `https://assessmentpublic.yorkcountypa.gov/ 500`

- [ ] **Step 3: Commit**

```bash
git add pipelines/countyiq/lib/county_config.py
git commit -m "feat(config): add assessment scraper throttle/batch config fields"
```

---

## Task 4: Parser — `parid_to_pidn` + Search Results Parsing

**Files:**
- Create: `pipelines/countyiq/lib/parsers/assessment.py`
- Create: `pipelines/tests/fixtures/assessment_search_results.html`
- Create: `pipelines/tests/test_assessment_parser.py`

- [ ] **Step 1: Create the search results HTML fixture**

Save a minimal but representative HTML fixture from the portal. This needs to match the real structure observed via Playwright. Create `pipelines/tests/fixtures/assessment_search_results.html`:

```html
<html>
<body>
<div class="SearchResults">
  <table id="searchResults">
    <tr>
      <td class="TotalFound">
        <span id="totalCount">Total found: 9305 records, displayed: 500. Please refine your search.</span>
        <span>(You will not be able to select all records)</span>
      </td>
    </tr>
  </table>
  <table id="resultsTable">
    <tr>
      <th>Parcel</th><th>Owner</th><th>Location</th><th>Class</th>
    </tr>
    <tr class="SearchResults" onclick="selectSearchRow(this)">
      <td><span>460000100010000000</span></td>
      <td><span>PABON SOPHIA</span></td>
      <td><span>144 FINDLAY ST N</span></td>
      <td><span>R</span></td>
    </tr>
    <tr class="SearchResults" onclick="selectSearchRow(this)">
      <td><span>460000100020000000</span></td>
      <td><span>GORDON GREGORY R &amp; TAMMY J</span></td>
      <td><span>140 FINDLAY ST N</span></td>
      <td><span>R</span></td>
    </tr>
    <tr class="SearchResults" onclick="selectSearchRow(this)">
      <td><span>460000100240000000</span></td>
      <td><span>DRUMM TW II</span></td>
      <td><span>2040 MARKET ST E</span></td>
      <td><span>C</span></td>
    </tr>
  </table>
  <table>
    <tr>
      <td class="PagingResults">
        <span>Results Page:</span>
        <span class="PageLinks">
          <span>[1]</span>
          <a href="#">2</a>
          <a href="#">3</a>
        </span>
      </td>
    </tr>
  </table>
</div>
</body>
</html>
```

**Note:** The exact HTML structure will need to be refined during implementation by capturing real HTML from the portal with Playwright (`page.content()`). The fixture above is a reasonable approximation based on the snapshot structure seen during exploration. The parser tests should be updated if the real HTML differs.

- [ ] **Step 2: Write the parser tests**

Create `pipelines/tests/test_assessment_parser.py`:

```python
"""Unit tests for assessment portal HTML parser."""

import os
import pytest

from countyiq.lib.parsers.assessment import (
    parid_to_pidn,
    parse_search_results_page,
    get_total_found,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


class TestParidToPidn:
    def test_standard_conversion(self):
        assert parid_to_pidn("460000100010000000") == "4600001001000"

    def test_another_district(self):
        # District 01, different block/parcel
        assert parid_to_pidn("010002300450000000") == "0100023045000"

    def test_parid_with_letters(self):
        assert parid_to_pidn("24000KF0012A000000") == "2400KF012A000"

    def test_short_input_returns_empty(self):
        assert parid_to_pidn("123") == ""

    def test_none_returns_empty(self):
        assert parid_to_pidn(None) == ""

    def test_empty_string_returns_empty(self):
        assert parid_to_pidn("") == ""


class TestGetTotalFound:
    def test_extracts_total(self):
        with open(os.path.join(FIXTURES, "assessment_search_results.html")) as f:
            html = f.read()
        assert get_total_found(html) == 9305

    def test_no_results_returns_zero(self):
        assert get_total_found("<html><body>No records found</body></html>") == 0


class TestParseSearchResults:
    def test_parses_three_rows(self):
        with open(os.path.join(FIXTURES, "assessment_search_results.html")) as f:
            html = f.read()
        results = parse_search_results_page(html)
        assert len(results) == 3

    def test_first_row_fields(self):
        with open(os.path.join(FIXTURES, "assessment_search_results.html")) as f:
            html = f.read()
        row = parse_search_results_page(html)[0]
        assert row["parid"] == "460000100010000000"
        assert row["owner_name"] == "PABON SOPHIA"
        assert row["address"] == "144 FINDLAY ST N"
        assert row["property_class"] == "R"

    def test_commercial_class(self):
        with open(os.path.join(FIXTURES, "assessment_search_results.html")) as f:
            html = f.read()
        row = parse_search_results_page(html)[2]
        assert row["property_class"] == "C"

    def test_html_entity_decoded(self):
        """Ampersand in owner name should be decoded."""
        with open(os.path.join(FIXTURES, "assessment_search_results.html")) as f:
            html = f.read()
        row = parse_search_results_page(html)[1]
        assert row["owner_name"] == "GORDON GREGORY R & TAMMY J"
```

- [ ] **Step 3: Run tests — should fail**

```bash
cd pipelines && source .venv/bin/activate
python3 -m pytest tests/test_assessment_parser.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'countyiq.lib.parsers.assessment'`

- [ ] **Step 4: Implement the parser**

Create `pipelines/countyiq/lib/parsers/assessment.py`:

```python
"""Parser for York County Assessment portal (iasWorld Public Access).

Handles two page types:
  1. Search results page — table of PARID, Owner, Location, Class
  2. Printable Summary page — all tabs rendered on one page (Task 5)

HTML parsing uses BeautifulSoup with the portal's table-based layout.
"""

import re

from bs4 import BeautifulSoup


def parid_to_pidn(parid: str | None) -> str:
    """Convert 18-digit PARID to 13-char PIDN.

    SQL equivalent (1-based): SUBSTRING(1,2) + SUBSTRING(4,3) + SUBSTRING(8,2) + SUBSTRING(11,6)
    Python (0-based):         parid[0:2]     + parid[3:6]     + parid[7:9]     + parid[10:16]

    Example: 460000100010000000 → 4600001001000
    """
    if not parid or len(parid) < 16:
        return ""
    return parid[0:2] + parid[3:6] + parid[7:9] + parid[10:16]


def get_total_found(html: str) -> int:
    """Extract total record count from search results page.

    Looks for text like "Total found: 9305 records" in the page.
    Returns 0 if no match found.
    """
    match = re.search(r"Total found:\s*([\d,]+)\s*records", html)
    if match:
        return int(match.group(1).replace(",", ""))
    return 0


def parse_search_results_page(html: str) -> list[dict]:
    """Extract property rows from search results HTML.

    The results table has clickable rows with 4 cells: Parcel, Owner, Location, Class.
    Header rows and empty rows are skipped.

    Returns:
        List of dicts with keys: parid, owner_name, address, property_class
    """
    soup = BeautifulSoup(html, "html.parser")
    records = []

    # Find all table rows that look like result rows
    # Result rows have exactly 4 cells and the first cell contains an 18-digit PARID
    for tr in soup.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) != 4:
            continue

        parid_text = cells[0].get_text(strip=True)
        # PARIDs are 18 digits (possibly with letters)
        if not parid_text or len(parid_text) < 16:
            continue
        # Skip header-like rows
        if parid_text.lower() in ("parcel", "sort by parcel"):
            continue

        records.append({
            "parid": parid_text,
            "owner_name": cells[1].get_text(strip=True),
            "address": cells[2].get_text(strip=True),
            "property_class": cells[3].get_text(strip=True),
        })

    return records
```

- [ ] **Step 5: Run tests — should pass**

```bash
python3 -m pytest tests/test_assessment_parser.py -v
```

Expected: All 9 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add pipelines/countyiq/lib/parsers/assessment.py pipelines/tests/test_assessment_parser.py pipelines/tests/fixtures/assessment_search_results.html
git commit -m "feat(parser): assessment search results parser with parid_to_pidn"
```

---

## Task 5: Parser — Printable Summary Parsing

**Files:**
- Create: `pipelines/tests/fixtures/assessment_printable_summary.html`
- Modify: `pipelines/countyiq/lib/parsers/assessment.py`
- Modify: `pipelines/tests/test_assessment_parser.py`

- [ ] **Step 1: Capture real Printable Summary HTML**

Before writing the fixture, use Playwright MCP to navigate to a property and capture the Printable Summary HTML. This is critical because the Printable Summary format is not yet verified.

Steps via Playwright:
1. Navigate to `https://assessmentpublic.yorkcountypa.gov/search/commonsearch.aspx?mode=realprop`
2. Accept disclaimer (click "Agree")
3. Search for a specific PARID (e.g., `460000100010000000`)
4. Click the result row
5. Click "Printable Summary" link
6. Capture `page.content()` and save as the fixture

**If Printable Summary opens a popup:** Intercept with `page.on("popup", ...)` or use `page.evaluate("PrintDatalet('all')")` and capture the resulting page.

Save captured HTML to `pipelines/tests/fixtures/assessment_printable_summary.html`.

- [ ] **Step 2: Write tests for printable summary parser**

Add to `pipelines/tests/test_assessment_parser.py`:

```python
from countyiq.lib.parsers.assessment import parse_printable_summary


class TestParsePrintableSummary:
    @pytest.fixture
    def summary_html(self):
        with open(os.path.join(FIXTURES, "assessment_printable_summary.html")) as f:
            return f.read()

    def test_extracts_municipality(self, summary_html):
        result = parse_printable_summary(summary_html)
        assert "SPRINGETTSBURY" in result["municipality"]

    def test_extracts_school_district(self, summary_html):
        result = parse_printable_summary(summary_html)
        assert "YORK SUBURBAN" in result["school_district"]

    def test_extracts_assessed_values(self, summary_html):
        result = parse_printable_summary(summary_html)
        assert result["assessed_land"] is not None
        assert result["assessed_building"] is not None
        assert result["assessed_total"] is not None
        assert isinstance(result["assessed_total"], int)

    def test_extracts_land_use_code(self, summary_html):
        result = parse_printable_summary(summary_html)
        assert result["land_use_code"] is not None

    def test_permits_is_list(self, summary_html):
        result = parse_printable_summary(summary_html)
        assert isinstance(result["permits"], list)

    def test_delinquent_taxes_is_list(self, summary_html):
        result = parse_printable_summary(summary_html)
        assert isinstance(result["delinquent_taxes"], list)

    def test_value_history_is_list(self, summary_html):
        result = parse_printable_summary(summary_html)
        assert isinstance(result["value_history"], list)
```

- [ ] **Step 3: Run tests — should fail**

```bash
python3 -m pytest tests/test_assessment_parser.py::TestParsePrintableSummary -v
```

Expected: FAIL — `ImportError: cannot import name 'parse_printable_summary'`

- [ ] **Step 4: Implement `parse_printable_summary`**

Add to `pipelines/countyiq/lib/parsers/assessment.py`:

```python
def parse_printable_summary(html: str) -> dict:
    """Extract all fields from the Printable Summary page.

    The Printable Summary renders all detail tabs in a single page.
    Data is in label-value table rows throughout the page.

    Returns dict with keys matching staging.assessment_properties columns:
        municipality, school_district, land_use_code,
        assessed_land, assessed_building, assessed_total,
        sale_date, sale_price,
        permits (list[dict]), delinquent_taxes (list[dict]), value_history (list[dict])
    """
    soup = BeautifulSoup(html, "html.parser")

    result = {
        "municipality": _extract_header_field(soup, "MUNICIPALITY"),
        "school_district": _extract_header_field(soup, "SCHOOL"),
        "land_use_code": _extract_label_value(soup, "LUC"),
        "assessed_land": _parse_currency(_extract_label_value(soup, "Appraised Land")),
        "assessed_building": _parse_currency(_extract_label_value(soup, "Appraised Building")),
        "assessed_total": _parse_currency(_extract_label_value(soup, "Appraised Total")),
        "sale_date": None,
        "sale_price": None,
        "permits": _extract_permits_table(soup),
        "delinquent_taxes": _extract_delinquent_taxes(soup),
        "value_history": _extract_value_history(soup),
    }

    # Extract most recent sale from sales section
    sales = _extract_sales(soup)
    if sales:
        result["sale_date"] = sales[0].get("sale_date")
        result["sale_price"] = sales[0].get("sale_price")

    return result


def _extract_header_field(soup: BeautifulSoup, label: str) -> str | None:
    """Extract a field from the property header (e.g., 'MUNICIPALITY: 46I - SPRINGETTSBURY').

    The header contains cells with text like 'MUNICIPALITY: 46I - SPRINGETTSBURY I-DST'.
    """
    for cell in soup.find_all("td"):
        text = cell.get_text(strip=True)
        if text.startswith(f"{label}:"):
            value = text.split(":", 1)[1].strip()
            # Remove district code prefix (e.g., "46I - " from "46I - SPRINGETTSBURY I-DST")
            if " - " in value:
                value = value.split(" - ", 1)[1].strip()
            # Remove trailing district suffix (e.g., " I-DST")
            value = re.sub(r"\s+[IV]+-DST$", "", value)
            return value
    return None


def _extract_label_value(soup: BeautifulSoup, label: str) -> str | None:
    """Extract value from a label-value table row.

    Rows are structured as: <tr><td>Label</td><td>Value</td></tr>
    """
    for cell in soup.find_all("td"):
        text = cell.get_text(strip=True)
        if text == label:
            next_cell = cell.find_next_sibling("td")
            if next_cell:
                return next_cell.get_text(strip=True) or None
    return None


def _parse_currency(value: str | None) -> int | None:
    """Parse currency string like '28,530' to int 28530."""
    if not value:
        return None
    cleaned = re.sub(r"[,$\s]", "", value)
    try:
        return int(cleaned)
    except ValueError:
        return None


def _extract_sales(soup: BeautifulSoup) -> list[dict]:
    """Extract sale records from the Sales section.

    Returns list sorted by date descending (most recent first).
    """
    sales = []
    # Sales section has rows with Sale Date, Sale Price columns
    # Look for the Sales header, then parse the following table
    in_sales = False
    for cell in soup.find_all("td"):
        text = cell.get_text(strip=True)
        if text == "Sales":
            in_sales = True
            continue
        if in_sales and text in ("Values", "Land", "Permits", "Value History"):
            break
        if in_sales and re.match(r"\d{2}-\d{2}-\d{4}", text):
            price_cell = cell.find_next_sibling("td")
            price = _parse_currency(price_cell.get_text(strip=True)) if price_cell else None
            sales.append({"sale_date": text, "sale_price": price})
    return sales


def _extract_permits_table(soup: BeautifulSoup) -> list[dict]:
    """Extract permits from the Permits section as a list of dicts."""
    return _extract_section_table(soup, "Permits")


def _extract_delinquent_taxes(soup: BeautifulSoup) -> list[dict]:
    """Extract delinquent tax records from the Delinquent Taxes section."""
    return _extract_section_table(soup, "Delinquent Taxes")


def _extract_value_history(soup: BeautifulSoup) -> list[dict]:
    """Extract historical assessment values from the Value History section."""
    return _extract_section_table(soup, "Value History")


def _extract_section_table(soup: BeautifulSoup, section_name: str) -> list[dict]:
    """Generic extractor for a named section's data table.

    Finds a cell containing the section name as a header,
    then reads the following table rows as header→value dicts.
    """
    rows = []
    in_section = False
    headers = []

    for cell in soup.find_all("td"):
        text = cell.get_text(strip=True)
        if text == section_name:
            in_section = True
            continue
        # Stop at the next section header
        if in_section and text in (
            "Profile", "Owner", "Sales", "Values", "Value History",
            "Land", "Agricultural", "Residential", "Outbuildings",
            "Permits", "Commercial", "Current Tax Information",
            "Delinquent Taxes", "Appeals",
        ) and text != section_name:
            break

    # If we found the section, look for tables after it
    if in_section:
        # Find all tables and look for one that follows our section header
        for table in soup.find_all("table"):
            table_text = table.get_text(strip=True)
            if section_name in table_text:
                trs = table.find_all("tr")
                if len(trs) < 2:
                    continue
                # First row with content = headers
                header_cells = trs[0].find_all(["th", "td"])
                headers = [c.get_text(strip=True) for c in header_cells]
                if not headers or headers[0] == section_name:
                    # Skip the section title row, use next row as headers
                    if len(trs) > 1:
                        header_cells = trs[1].find_all(["th", "td"])
                        headers = [c.get_text(strip=True) for c in header_cells]
                        trs = trs[2:]
                    else:
                        continue
                else:
                    trs = trs[1:]
                # Parse data rows
                for tr in trs:
                    cells = tr.find_all("td")
                    if len(cells) == len(headers):
                        row = {}
                        for i, h in enumerate(headers):
                            if h:
                                row[h.lower().replace(" ", "_")] = cells[i].get_text(strip=True)
                        if any(row.values()):
                            rows.append(row)
                break

    return rows
```

**Important implementation note:** The `parse_printable_summary` function above is a best-effort implementation based on the observed portal structure. The exact HTML structure of the Printable Summary page needs to be verified during Step 1 of this task. The parser will likely need adjustments once the real HTML is captured. The key principle: extract label-value pairs from table cells. The actual selectors may need tuning.

- [ ] **Step 5: Run tests — should pass**

```bash
python3 -m pytest tests/test_assessment_parser.py -v
```

Expected: All tests PASS (contingent on fixture HTML matching the parser's expectations — adjust either as needed).

- [ ] **Step 6: Commit**

```bash
git add pipelines/countyiq/lib/parsers/assessment.py pipelines/tests/test_assessment_parser.py pipelines/tests/fixtures/assessment_printable_summary.html
git commit -m "feat(parser): add printable summary parser for assessment detail data"
```

---

## Task 6: Dagster Asset — Scraper Skeleton + Tier 1

**Files:**
- Create: `pipelines/countyiq/assets/scrapers/__init__.py`
- Create: `pipelines/countyiq/assets/scrapers/assessment.py`

- [ ] **Step 1: Create the scrapers package init**

Create `pipelines/countyiq/assets/scrapers/__init__.py` (empty file — required for Dagster discovery):

```python
```

- [ ] **Step 2: Create the asset file with Tier 1 logic**

Create `pipelines/countyiq/assets/scrapers/assessment.py`:

```python
"""Assessment data from iasWorld Public Access portal → staging.assessment_properties.

Records: ~176K properties scraped via Playwright
Schedule: Weekly (Monday 03:00, scraper_refresh job)
Strategy: Two-tier — search results sweep + printable summary enrichment
"""

import json
import time

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
from countyiq.lib.parsers.assessment import (
    parid_to_pidn,
    parse_search_results_page,
    get_total_found,
    parse_printable_summary,
)
from countyiq.lib.playwright_utils import browser_context
from countyiq.lib.scd import scd2_upsert
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

KEY_COLUMNS = ["pidn"]

VALUE_COLUMNS = [
    "parid", "owner_name", "address", "municipality", "school_district",
    "property_class", "land_use_code", "assessed_land", "assessed_building",
    "assessed_total", "sale_date", "sale_price", "permits",
    "delinquent_taxes", "value_history",
]


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
    county = get_county_config()

    # Load checkpoint
    checkpoint = _load_checkpoint(database, "assessment")
    tier1_stats = {"inserted": 0, "expired": 0}

    with browser_context() as page:
        _accept_disclaimer(page, county.assessment_url)

        # --- Tier 1: Search results sweep ---
        tier1 = checkpoint.get("tier1", {})
        if tier1.get("status") != "complete":
            context.log.info("Starting Tier 1: search results sweep")
            tier1_results, tier1 = _run_tier1(
                page, context, database, county, tier1
            )

            if not tier1_results:
                context.log.warning("No properties found in Tier 1")
                return MaterializeResult(metadata={"record_count": MetadataValue.int(0)})

            # Upsert Tier 1 results (basic fields only, expire_missing=False)
            records_t1 = _prepare_tier1_records(tier1_results)
            cur = database.cursor()
            try:
                tier1_stats = scd2_upsert(
                    cursor=cur,
                    schema="staging",
                    table="assessment_properties",
                    records=records_t1,
                    key_columns=KEY_COLUMNS,
                    value_columns=VALUE_COLUMNS,
                    expire_missing=False,
                )
            finally:
                cur.close()

            # Save Tier 1 checkpoint (only prefixes + counts, NOT full results)
            checkpoint["tier1"] = tier1
            _save_checkpoint(database, "assessment", checkpoint)
        else:
            context.log.info("Tier 1 already complete — skipping to Tier 2")

        # Load all PARIDs from staging for Tier 2 (works for both fresh + resumed runs)
        tier1_results = _load_tier1_results_from_staging(database)
        if not tier1_results:
            context.log.warning("No properties in staging.assessment_properties")
            return MaterializeResult(metadata={"record_count": MetadataValue.int(0)})

        # --- Tier 2: Detail enrichment ---
        tier2 = checkpoint.get("tier2", {})
        enriched_count = _run_tier2(
            page, context, database, s3, county, tier1_results, tier2, checkpoint
        )

    total_count = _get_current_count(database)

    return MaterializeResult(
        metadata={
            "record_count": MetadataValue.int(total_count),
            "tier1_properties": MetadataValue.int(len(tier1_results)),
            "tier2_enriched_this_run": MetadataValue.int(enriched_count),
            "tier1_inserted": MetadataValue.int(tier1_stats.get("inserted", 0)),
            "tier1_expired": MetadataValue.int(tier1_stats.get("expired", 0)),
        }
    )


# ---------------------------------------------------------------------------
# Disclaimer
# ---------------------------------------------------------------------------

def _accept_disclaimer(page, base_url: str):
    """Navigate to search page, accepting disclaimer if shown."""
    page.goto(f"{base_url}search/commonsearch.aspx?mode=realprop")
    if "Disclaimer" in page.title():
        page.click("button:has-text('Agree')")
        page.wait_for_load_state("networkidle")


# ---------------------------------------------------------------------------
# Tier 1: Search results sweep
# ---------------------------------------------------------------------------

def _run_tier1(page, context, database, county, tier1_state: dict):
    """Search by prefix, page through results, collect all PARIDs.

    Results are NOT stored in the checkpoint (would be 20+ MB JSONB).
    Only completed prefixes and counts are checkpointed. Results are
    returned in-memory for the current run's Tier 1 upsert.
    """
    completed_prefixes = set(tier1_state.get("completed_prefixes", []))
    all_results = []
    total_found = tier1_state.get("total_properties_found", 0)

    # Get district prefixes from staging.parcels
    prefixes = _get_district_prefixes(database)
    context.log.info(f"Found {len(prefixes)} district prefixes to search")

    for prefix in prefixes:
        if prefix in completed_prefixes:
            continue
        context.log.info(f"Tier 1: searching prefix '{prefix}'")
        refined = _refine_prefix(page, prefix, county, max_depth=6)
        for rp in refined:
            if rp in completed_prefixes:
                continue
            batch = _search_all_pages(page, rp, county)
            all_results.extend(batch)
            total_found += len(batch)
            completed_prefixes.add(rp)
            context.log.info(f"  prefix '{rp}': {len(batch)} results")
        completed_prefixes.add(prefix)

        # Periodic checkpoint (prefixes + counts only, no results)
        tier1_state = {
            "completed_prefixes": list(completed_prefixes),
            "total_properties_found": total_found,
        }

    tier1_state["status"] = "complete"
    return all_results, tier1_state


def _get_district_prefixes(database: DatabaseResource) -> list[str]:
    """Get unique 2-char district prefixes from staging.parcels PIDNs."""
    rows = database.execute(
        "SELECT DISTINCT SUBSTRING(pidn FROM 1 FOR 2) AS prefix "
        "FROM staging.parcels WHERE valid_to IS NULL ORDER BY prefix"
    )
    return [r[0] for r in rows if r[0]]


def _refine_prefix(page, prefix: str, county, max_depth: int = 6) -> list[str]:
    """If prefix yields >500 results, subdivide into longer prefixes.

    max_depth prevents infinite recursion on extremely dense data ranges.
    """
    if len(prefix) >= max_depth:
        # At depth limit — accept truncation, log warning
        return [prefix]

    total = _search_and_count(page, prefix, county)
    if total <= 500:
        return [prefix]

    sub_prefixes = []
    for char in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        sub = prefix + char
        sub_total = _search_and_count(page, sub, county)
        if sub_total == 0:
            continue
        if sub_total <= 500:
            sub_prefixes.append(sub)
        else:
            sub_prefixes.extend(_refine_prefix(page, sub, county, max_depth))
    return sub_prefixes


def _search_and_count(page, prefix: str, county) -> int:
    """Perform a search and return the total found count."""
    _navigate_to_search(page, county.assessment_url)
    page.fill('input[name*="Parcel"], [aria-label="Parcel:"]', prefix)
    page.select_option('select[name*="PageSize"], [aria-label="Results/page:"]', "50")
    page.click('button:has-text("Search"), input[value="Search"]')
    page.wait_for_load_state("networkidle")
    time.sleep(county.assessment_throttle_seconds)
    return get_total_found(page.content())


def _search_all_pages(page, prefix: str, county) -> list[dict]:
    """Search a prefix and page through all results (max 500 = 10 pages of 50)."""
    _navigate_to_search(page, county.assessment_url)
    page.fill('input[name*="Parcel"], [aria-label="Parcel:"]', prefix)
    page.select_option('select[name*="PageSize"], [aria-label="Results/page:"]', "50")
    page.click('button:has-text("Search"), input[value="Search"]')
    page.wait_for_load_state("networkidle")
    time.sleep(county.assessment_throttle_seconds)

    all_rows = []
    for page_num in range(10):  # max 10 pages of 50 = 500
        html = page.content()
        rows = parse_search_results_page(html)
        if not rows:
            break
        all_rows.extend(rows)

        # Check for next page link
        next_link = page.query_selector('a:has-text("Next >>")')
        if not next_link:
            break
        next_link.click()
        page.wait_for_load_state("networkidle")
        time.sleep(county.assessment_throttle_seconds)

    return all_rows


def _navigate_to_search(page, base_url: str):
    """Navigate to search page, handle disclaimer if it reappears."""
    page.goto(f"{base_url}search/commonsearch.aspx?mode=realprop")
    if "Disclaimer" in page.title():
        page.click("button:has-text('Agree')")
        page.wait_for_load_state("networkidle")


# ---------------------------------------------------------------------------
# Tier 2: Detail enrichment
# ---------------------------------------------------------------------------

def _run_tier2(page, context, database, s3, county, tier1_results, tier2_state, checkpoint):
    """Visit detail pages for each property, extract full data."""
    last_parid = tier2_state.get("last_completed_parid", "")
    enriched = tier2_state.get("properties_enriched", 0)
    max_per_run = county.assessment_max_per_run
    processed_this_run = 0

    # Build dict lookup for O(1) access (instead of O(n) per property)
    t1_by_parid = {r["parid"]: r for r in tier1_results}

    # Sort PARIDs for deterministic ordering
    sorted_parids = sorted(t1_by_parid.keys())

    # Resume from checkpoint
    start_idx = 0
    if last_parid:
        for i, p in enumerate(sorted_parids):
            if p > last_parid:
                start_idx = i
                break
        else:
            # All done
            context.log.info("Tier 2 already complete")
            tier2_state["status"] = "complete"
            checkpoint["tier2"] = tier2_state
            _save_checkpoint(database, "assessment", checkpoint)
            return 0

    context.log.info(
        f"Tier 2: starting at index {start_idx}/{len(sorted_parids)}, "
        f"max {max_per_run} this run"
    )

    session_count = 0
    batch_records = []

    for parid in sorted_parids[start_idx:]:
        if processed_this_run >= max_per_run:
            break

        # Refresh session periodically
        if session_count >= county.assessment_session_refresh:
            context.log.info("Refreshing browser session")
            _accept_disclaimer(page, county.assessment_url)
            session_count = 0

        try:
            detail = _scrape_property_detail(page, parid, county)
            if detail:
                # Merge Tier 1 basic data with Tier 2 detail
                t1_data = t1_by_parid.get(parid, {})
                record = _merge_record(parid, t1_data, detail)
                batch_records.append(record)
        except Exception as e:
            context.log.warning(f"Failed to scrape {parid}: {e}")

        enriched += 1
        processed_this_run += 1
        session_count += 1

        # Update checkpoint every 10 properties
        if processed_this_run % 10 == 0:
            tier2_state["last_completed_parid"] = parid
            tier2_state["properties_enriched"] = enriched
            checkpoint["tier2"] = tier2_state
            _save_checkpoint(database, "assessment", checkpoint)

    # Final checkpoint
    if sorted_parids[start_idx:] and processed_this_run > 0:
        last = sorted_parids[min(start_idx + processed_this_run - 1, len(sorted_parids) - 1)]
        tier2_state["last_completed_parid"] = last
        tier2_state["properties_enriched"] = enriched
        if start_idx + processed_this_run >= len(sorted_parids):
            tier2_state["status"] = "complete"
        checkpoint["tier2"] = tier2_state
        _save_checkpoint(database, "assessment", checkpoint)

    # Upsert enriched records
    if batch_records:
        cur = database.cursor()
        try:
            scd2_upsert(
                cursor=cur,
                schema="staging",
                table="assessment_properties",
                records=batch_records,
                key_columns=KEY_COLUMNS,
                value_columns=VALUE_COLUMNS,
                expire_missing=False,
            )
        finally:
            cur.close()

        # Archive to S3
        s3.archive(
            f"{county.s3_prefix}/scrapers/assessment",
            batch_records,
            filename="enriched_batch.json",
        )

    context.log.info(f"Tier 2: enriched {processed_this_run} properties this run")
    return processed_this_run


def _scrape_property_detail(page, parid: str, county) -> dict | None:
    """Search for exact PARID, navigate to Printable Summary, parse."""
    _navigate_to_search(page, county.assessment_url)
    page.fill('input[name*="Parcel"], [aria-label="Parcel:"]', parid)
    page.click('button:has-text("Search"), input[value="Search"]')
    page.wait_for_load_state("networkidle")
    time.sleep(county.assessment_throttle_seconds)

    # Click first result row
    result_rows = page.query_selector_all("tr.SearchResults, tr[onclick]")
    if not result_rows:
        return None
    result_rows[0].click()
    page.wait_for_load_state("networkidle")
    time.sleep(county.assessment_throttle_seconds)

    # Click Printable Summary
    summary_link = page.query_selector('a:has-text("Printable Summary")')
    if summary_link:
        # May open popup — handle both cases
        with page.expect_popup() as popup_info:
            summary_link.click()
        popup = popup_info.value
        popup.wait_for_load_state("networkidle")
        html = popup.content()
        popup.close()
    else:
        # Try evaluating the JavaScript directly
        page.evaluate("PrintDatalet('all')")
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        html = page.content()

    time.sleep(county.assessment_throttle_seconds)
    return parse_printable_summary(html)


# ---------------------------------------------------------------------------
# Record merging
# ---------------------------------------------------------------------------

def _prepare_tier1_records(tier1_results: list[dict]) -> list[dict]:
    """Convert Tier 1 search results to staging records with PIDN."""
    records = []
    for r in tier1_results:
        pidn = parid_to_pidn(r["parid"])
        if not pidn:
            continue
        records.append({
            "pidn": pidn,
            "parid": r["parid"],
            "owner_name": r.get("owner_name"),
            "address": r.get("address"),
            "property_class": r.get("property_class"),
            # Tier 2 fields default to None
            "municipality": None,
            "school_district": None,
            "land_use_code": None,
            "assessed_land": None,
            "assessed_building": None,
            "assessed_total": None,
            "sale_date": None,
            "sale_price": None,
            "permits": None,
            "delinquent_taxes": None,
            "value_history": None,
        })
    return records


def _merge_record(parid: str, t1_data: dict, detail: dict) -> dict:
    """Merge Tier 1 basic data with Tier 2 detail data."""
    pidn = parid_to_pidn(parid)
    return {
        "pidn": pidn,
        "parid": parid,
        "owner_name": t1_data.get("owner_name"),
        "address": t1_data.get("address"),
        "property_class": t1_data.get("property_class"),
        "municipality": detail.get("municipality"),
        "school_district": detail.get("school_district"),
        "land_use_code": detail.get("land_use_code"),
        "assessed_land": detail.get("assessed_land"),
        "assessed_building": detail.get("assessed_building"),
        "assessed_total": detail.get("assessed_total"),
        "sale_date": detail.get("sale_date"),
        "sale_price": detail.get("sale_price"),
        "permits": detail.get("permits", []),
        "delinquent_taxes": detail.get("delinquent_taxes", []),
        "value_history": detail.get("value_history", []),
    }


# ---------------------------------------------------------------------------
# Checkpoint (meta.scrape_checkpoints)
# ---------------------------------------------------------------------------

def _load_checkpoint(database: DatabaseResource, source_name: str) -> dict:
    """Load checkpoint from meta.scrape_checkpoints."""
    rows = database.execute(
        "SELECT checkpoint FROM meta.scrape_checkpoints WHERE source_name = %s",
        (source_name,),
    )
    if rows:
        return rows[0][0] or {}
    return {}


def _save_checkpoint(database: DatabaseResource, source_name: str, data: dict):
    """Save checkpoint to meta.scrape_checkpoints (upsert)."""
    cur = database.cursor()
    try:
        cur.execute(
            """
            INSERT INTO meta.scrape_checkpoints (source_name, checkpoint, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (source_name) DO UPDATE
            SET checkpoint = EXCLUDED.checkpoint, updated_at = NOW()
            """,
            (source_name, json.dumps(data, default=str)),
        )
        cur.connection.commit()
    finally:
        cur.close()


def _load_tier1_results_from_staging(database: DatabaseResource) -> list[dict]:
    """Load all PARIDs from staging.assessment_properties for Tier 2 processing.

    This replaces storing Tier 1 results in the checkpoint JSONB (which would
    be 20+ MB for 176K properties). The staging table is the source of truth
    after Tier 1 upsert completes.
    """
    rows = database.execute(
        "SELECT parid, owner_name, address, property_class "
        "FROM staging.assessment_properties WHERE valid_to IS NULL"
    )
    return [
        {"parid": r[0], "owner_name": r[1], "address": r[2], "property_class": r[3]}
        for r in rows if r[0]
    ]


def _get_current_count(database: DatabaseResource) -> int:
    """Get current record count in staging.assessment_properties."""
    rows = database.execute(
        "SELECT COUNT(*) FROM staging.assessment_properties WHERE valid_to IS NULL"
    )
    return rows[0][0] if rows else 0


# ---------------------------------------------------------------------------
# Asset checks
# ---------------------------------------------------------------------------

@asset_check(asset=assessment_scrape)
def assessment_record_count(database: DatabaseResource) -> AssetCheckResult:
    """Verify assessment data is present.

    During backfill: passes if count > 0.
    After backfill: passes if count > assessment_min_records.
    """
    county = get_county_config()
    count = _get_current_count(database)
    checkpoint = _load_checkpoint(database, "assessment")
    tier2_status = checkpoint.get("tier2", {}).get("status", "")

    if tier2_status == "complete":
        passed = count > county.assessment_min_records
        description = f"{count} records (threshold: {county.assessment_min_records})"
    else:
        passed = count > 0
        description = f"{count} records (backfill in progress)"

    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.ERROR,
        metadata={
            "current_record_count": MetadataValue.int(count),
            "description": MetadataValue.text(description),
        },
    )


@asset_check(asset=assessment_scrape)
def assessment_row_count_delta(database: DatabaseResource) -> AssetCheckResult:
    """Verify record count hasn't dropped by more than 50% vs checkpoint.

    Compares current staging count against the checkpoint's
    total_properties_found (set during Tier 1). This avoids needing
    meta.pipeline_status which the assessment asset doesn't write to.
    """
    count = _get_current_count(database)
    checkpoint = _load_checkpoint(database, "assessment")
    prev = checkpoint.get("tier1", {}).get("total_properties_found", 0)

    if prev == 0:
        return AssetCheckResult(passed=True, severity=AssetCheckSeverity.WARN)

    delta_pct = abs(count - prev) / prev
    return AssetCheckResult(
        passed=delta_pct < 0.5,
        severity=AssetCheckSeverity.ERROR,
        metadata={
            "current": MetadataValue.int(count),
            "tier1_total": MetadataValue.int(prev),
            "delta_pct": MetadataValue.float(delta_pct),
        },
    )
```

- [ ] **Step 3: Verify Dagster can load the asset**

```bash
cd pipelines && source .venv/bin/activate
python3 -c "from countyiq.assets.scrapers.assessment import assessment_scrape; print(assessment_scrape)"
```

Expected: `<dagster.AssetDefinition ...>` (no import errors)

- [ ] **Step 4: Commit**

```bash
git add pipelines/countyiq/assets/scrapers/__init__.py pipelines/countyiq/assets/scrapers/assessment.py
git commit -m "feat(asset): assessment scraper with tier 1 sweep and tier 2 enrichment"
```

---

## Task 7: Local Integration Test

**Files:** None new — this task validates the pipeline end-to-end.

- [ ] **Step 1: Ensure Docker Postgres is running with latest schema**

```bash
cd pipelines
docker compose up -d postgres-test
source .venv/bin/activate
export DATABASE_URL="postgresql://dagster_admin:localtest@localhost:5433/countyiq"
alembic upgrade head
```

- [ ] **Step 2: Seed staging.parcels with a few test PIDNs**

The assessment scraper needs district prefixes from `staging.parcels`. Insert a few test rows:

```bash
PGPASSWORD=localtest psql -h localhost -p 5433 -U dagster_admin -d countyiq -c "
INSERT INTO staging.parcels (pidn, owner_full, propadr)
VALUES
  ('4600001001000', 'PABON SOPHIA', '144 N FINDLAY ST'),
  ('4600001002000', 'GORDON GREGORY R', '140 N FINDLAY ST'),
  ('4600001003000', 'FERRENTINO ANGELA', '136 N FINDLAY ST')
ON CONFLICT DO NOTHING;
"
```

- [ ] **Step 3: Run the asset with small batch size**

```bash
export DATABASE_HOST=localhost
export DATABASE_PORT=5433
export DATABASE_NAME=countyiq
export DATABASE_USER=dagster_admin
export DATABASE_PASSWORD=localtest
export COUNTY=york

python3 -c "
from countyiq.assets.scrapers.assessment import assessment_scrape
from countyiq.resources.database import make_database_resource
from countyiq.resources.storage import make_s3_resource
from unittest.mock import MagicMock

# Override max_per_run for testing
import countyiq.lib.county_config as cc
cc.COUNTY_CONFIGS['york'] = cc.CountyConfig(
    **{**vars(cc.get_county_config()), 'assessment_max_per_run': 3}
)

# Create a mock context
context = MagicMock()
context.log = MagicMock()
context.log.info = print
context.log.warning = print

db = make_database_resource()
s3 = make_s3_resource()
result = assessment_scrape(context, db, s3)
print(f'Result metadata: {result.metadata}')
"
```

Expected: The scraper runs Tier 1 (searches prefix "46"), collects results, upserts to staging, then runs Tier 2 for up to 3 properties.

- [ ] **Step 4: Verify data in staging**

```bash
PGPASSWORD=localtest psql -h localhost -p 5433 -U dagster_admin -d countyiq -c "
SELECT pidn, parid, owner_name, property_class, assessed_total
FROM staging.assessment_properties
WHERE valid_to IS NULL
LIMIT 5;
"
```

Expected: At least 1 row with populated fields.

- [ ] **Step 5: Verify checkpoint was saved**

```bash
PGPASSWORD=localtest psql -h localhost -p 5433 -U dagster_admin -d countyiq -c "
SELECT source_name, updated_at,
       checkpoint->>'tier1' IS NOT NULL AS has_tier1,
       checkpoint->'tier2'->>'properties_enriched' AS enriched
FROM meta.scrape_checkpoints
WHERE source_name = 'assessment';
"
```

Expected: Row exists with tier1 data and enriched count.

- [ ] **Step 6: Run all parser tests**

```bash
python3 -m pytest tests/test_assessment_parser.py tests/test_scd_expire_missing.py -v
```

Expected: All tests PASS.

- [ ] **Step 7: Commit any test fixes**

If any adjustments were needed during integration testing, commit them:

```bash
git add -u
git commit -m "fix: adjust assessment scraper based on integration testing"
```

---

## Task 8: Dagster UI Verification

- [ ] **Step 1: Start Dagster dev**

```bash
cd pipelines && source .venv/bin/activate
export DATABASE_HOST=localhost
export DATABASE_PORT=5433
export DATABASE_NAME=countyiq
export DATABASE_USER=dagster_admin
export DATABASE_PASSWORD=localtest
dagster dev -m countyiq.definitions
```

- [ ] **Step 2: Verify asset appears in UI**

Open `http://localhost:3000` in browser. Check:
- `assessment_scrape` asset appears in the "scrapers" group
- Asset checks `assessment_record_count` and `assessment_row_count_delta` are listed
- The `scraper_refresh` job includes `assessment_scrape`
- The `weekly_scrapers` schedule (Monday 03:00) is visible

- [ ] **Step 3: Trigger a test materialization from UI**

Click "Materialize" on `assessment_scrape`. Watch the logs in the Dagster UI. Verify it:
1. Accepts disclaimer
2. Runs Tier 1 search sweep
3. Begins Tier 2 enrichment
4. Completes without errors (or gracefully handles any portal issues)

- [ ] **Step 4: Stop Dagster, commit if any fixes needed**

```bash
# Ctrl+C to stop dagster dev
git add -u
git commit -m "fix: dagster UI verification adjustments"
```

---

## Summary

| Task | What it does | Files |
|---|---|---|
| 1 | Alembic migration for `meta.scrape_checkpoints` | 1 new |
| 2 | `expire_missing` parameter on `scd2_upsert` | 1 modified, 1 new test |
| 3 | Assessment config fields in `county_config.py` | 1 modified |
| 4 | Parser: `parid_to_pidn` + search results | 3 new |
| 5 | Parser: printable summary | 1 new fixture, 2 modified |
| 6 | Dagster asset: full scraper + checks | 2 new |
| 7 | Local integration test | validation only |
| 8 | Dagster UI verification | validation only |
