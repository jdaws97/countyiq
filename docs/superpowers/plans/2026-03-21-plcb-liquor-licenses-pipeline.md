# PLCB Liquor Licenses Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first real data pipeline on the Dagster framework — PLCB liquor licenses CSV download, filtered to York County, SCD2 upserted into `staging.plcb_licenses`.

**Architecture:** HTTP GET a statewide CSV from `https://plcbplus.pa.gov/pub/LicenseExport.aspx`, parse with Python `csv` module, filter to `County == "York County"`, archive raw CSV to S3 (gracefully skipped locally), SCD2 upsert to Postgres. Runs on the existing `monthly_bulk` schedule (1st of month 05:00). Asset checks validate record count > 0 and CSV headers haven't drifted.

**Tech Stack:** Dagster 1.12, psycopg2, Python csv module, Alembic, Docker Postgres 16 + PostGIS

**Local testing:** S3 archival already gracefully skips when no AWS creds are present (logs a warning). Database resource defaults to `localhost:5433` (Docker Postgres). All testing uses the local Docker Postgres — no AWS resources needed.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `pipelines/york_county/assets/bulk/__init__.py` | Package init (empty) |
| Create | `pipelines/york_county/assets/bulk/plcb.py` | Dagster asset + asset checks |
| Create | `pipelines/york_county/lib/parsers/plcb.py` | CSV parsing + York County filtering |
| Create | `pipelines/tests/fixtures/plcb_sample.csv` | Test fixture from real CSV data |
| Create | `pipelines/tests/test_plcb_parser.py` | Unit tests for parser |
| Create | `pipelines/alembic/versions/002_plcb_licenses.py` | Alembic migration for `staging.plcb_licenses` |
No changes needed to `definitions.py` — `load_assets_from_package_module` auto-discovers `@asset` functions. The `bulk_refresh` job already selects `AssetSelection.groups("bulk")` and the existing `monthly_bulk` schedule (1st of month 05:00) triggers it automatically. No schedule changes needed.

---

## Task 1: Alembic Migration for `staging.plcb_licenses`

**Files:**
- Create: `pipelines/alembic/versions/002_plcb_licenses.py`

- [ ] **Step 1: Write the migration**

```python
"""add staging.plcb_licenses

Revision ID: 002
Revises: 001
Create Date: 2026-03-21
"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plcb_licenses",
        sa.Column("lid", sa.Text, nullable=False),
        sa.Column("license_number", sa.Text),
        sa.Column("license_type", sa.Text),
        sa.Column("status", sa.Text),
        sa.Column("licensee", sa.Text),
        sa.Column("premises_name", sa.Text),
        sa.Column("premises_address", sa.Text),
        sa.Column("premises_mailing_address", sa.Text),
        sa.Column("premises_owner", sa.Text),
        sa.Column("premises_manager", sa.Text),
        sa.Column("municipality", sa.Text),
        sa.Column("last_issue_date", sa.Text),
        sa.Column("expiration_date", sa.Text),
        sa.Column("valid_from", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("lid", "valid_from"),
        schema="staging",
    )
    op.create_index("idx_plcb_current", "plcb_licenses", ["lid"], schema="staging", postgresql_where=sa.text("valid_to IS NULL"))
    op.create_index("idx_plcb_municipality", "plcb_licenses", ["municipality"], schema="staging")
    op.create_index("idx_plcb_licensee", "plcb_licenses", ["licensee"], schema="staging")


def downgrade() -> None:
    op.drop_table("plcb_licenses", schema="staging")
```

- [ ] **Step 2: Start Docker Postgres and run migration**

```bash
cd pipelines
docker compose up -d postgres-test
# Wait for Postgres to be ready
sleep 3
DATABASE_URL="postgresql://dagster_admin:localtest@localhost:5433/york_county_intel" \
  uv run alembic upgrade head
```

Expected: `INFO [alembic.runtime.migration] Running upgrade 001 -> 002, add staging.plcb_licenses`

- [ ] **Step 3: Verify table exists**

```bash
PGPASSWORD=localtest psql -h localhost -p 5433 -U dagster_admin -d york_county_intel \
  -c "\d staging.plcb_licenses"
```

Expected: Table with 15 columns (lid through valid_to)

- [ ] **Step 4: Commit**

```bash
git add pipelines/alembic/versions/002_plcb_licenses.py
git commit -m "feat: add staging.plcb_licenses migration (PLCB Source #22)"
```

---

## Task 2: Parser — `lib/parsers/plcb.py`

**Files:**
- Create: `pipelines/tests/fixtures/plcb_sample.csv`
- Create: `pipelines/york_county/lib/parsers/plcb.py`
- Create: `pipelines/tests/test_plcb_parser.py`

- [ ] **Step 1: Create test fixture from real CSV data**

Save to `pipelines/tests/fixtures/plcb_sample.csv` — 6 rows: 4 York County (2 active, 1 expired, 1 with empty fields), 1 non-York County, plus header:

```csv
LID,License Number,License Type,Status,Licensee,Premises,Premises Address,Premises Mailing Address,Premises Owner,Premises Manager,County,Municipality,Last Issue Date,Expiration Date
54316,C5721,Club (Liquor),Active,SUSQUEHANNA FISH AND GAME ASSOCIATION INC,SUSQUEHANNA FISH AND GAME ASSOCIATION INC,"7084 ROUND TOP LANE, WRIGHTSVILLE PA 17368","PO BOX 175, WRIGHTSVILLE PA 17368-0175",SUSQUEHANNA FISH AND GAME ASSOCIATION INC,DENNIS STONESIFER II,York County,Hellam Twp,"Dec 15,2025","Feb 28,2027"
2441,C5296,Club (Liquor),Active,GIRARD ATHLETIC ASSN.,GIRARD ATHLETIC ASSN.,"720 E SOUTH ST, YORK PA 17403-2830","720 E SOUTH ST, YORK PA 17403-2830",GIRARD ATHLETIC ASSN.,MARK KINARD,York County,York City,"Jan 5,2026","Feb 28,2027"
100809,AL44096,Limited Distillery,Expired,CLOONAUGHILL CELTIC MALTS INC,CLOONAUGHILL CELTIC MALTS,"1940A BANK LN, YORK PA 17408-4066","247 BISHOP RD, POTTSTOWN PA 19465-8252",HILLSIDE COMMERCIAL LLC,PATRICK W SHORB,York County,West Manchester Twp,"Dec 26,2023","Dec 31,2023"
99999,R99999,Restaurant (Liquor),Active,TEST EMPTY FIELDS LLC,TEST EMPTY FIELDS,"100 MARKET ST, YORK PA 17401",,,,York County,York City,"Jan 1,2026","Dec 31,2026"
128829,AR61374,Airport Restaurant (Liquor),Active,SSP AMERICA PIT LLC,SHAKE SHACK,"1000 AIRPORT BLVD SPACE #AC-2E, PITTSBURGH PA 15231-1001","20408 BASHAN DR STE 300, ASHBURN VA 20147-5553",,JOSHUA S SPEER,Allegheny County,Findlay Twp,"Oct 16,2025","May 31,2026"
```

- [ ] **Step 2: Write failing tests**

```python
# pipelines/tests/test_plcb_parser.py
import csv
from io import StringIO
from pathlib import Path

from york_county.lib.parsers.plcb import parse_plcb_csv, EXPECTED_HEADERS

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_parse_filters_to_york_county():
    csv_text = (FIXTURES_DIR / "plcb_sample.csv").read_text()
    records = parse_plcb_csv(csv_text)
    assert len(records) == 4  # 4 York County rows, 1 non-York excluded


def test_parse_maps_columns_correctly():
    csv_text = (FIXTURES_DIR / "plcb_sample.csv").read_text()
    records = parse_plcb_csv(csv_text)
    r = next(r for r in records if r["lid"] == "54316")
    assert r["license_number"] == "C5721"
    assert r["license_type"] == "Club (Liquor)"
    assert r["status"] == "Active"
    assert r["licensee"] == "SUSQUEHANNA FISH AND GAME ASSOCIATION INC"
    assert r["premises_name"] == "SUSQUEHANNA FISH AND GAME ASSOCIATION INC"
    assert r["premises_address"] == "7084 ROUND TOP LANE, WRIGHTSVILLE PA 17368"
    assert r["municipality"] == "Hellam Twp"


def test_parse_includes_expired_york_county():
    csv_text = (FIXTURES_DIR / "plcb_sample.csv").read_text()
    records = parse_plcb_csv(csv_text)
    expired = next(r for r in records if r["lid"] == "100809")
    assert expired["status"] == "Expired"
    assert expired["license_type"] == "Limited Distillery"


def test_parse_converts_empty_fields_to_none():
    csv_text = (FIXTURES_DIR / "plcb_sample.csv").read_text()
    records = parse_plcb_csv(csv_text)
    r = next(r for r in records if r["lid"] == "99999")
    assert r["premises_mailing_address"] is None
    assert r["premises_owner"] is None
    assert r["premises_manager"] is None
    # Non-empty fields still populated
    assert r["licensee"] == "TEST EMPTY FIELDS LLC"


def test_parse_empty_csv_returns_empty():
    csv_text = "LID,License Number,License Type,Status,Licensee,Premises,Premises Address,Premises Mailing Address,Premises Owner,Premises Manager,County,Municipality,Last Issue Date,Expiration Date\n"
    records = parse_plcb_csv(csv_text)
    assert records == []


def test_validate_headers_detects_drift():
    csv_text = "BAD_COL,License Number\nfoo,bar\n"
    reader = csv.DictReader(StringIO(csv_text))
    actual = set(reader.fieldnames)
    assert not EXPECTED_HEADERS.issubset(actual)
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd pipelines && uv run pytest tests/test_plcb_parser.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'york_county.lib.parsers.plcb'`

- [ ] **Step 4: Write parser implementation**

```python
# pipelines/york_county/lib/parsers/plcb.py
"""Parse PLCB liquor license CSV and filter to York County."""

import csv
from io import StringIO

EXPECTED_HEADERS = {
    "LID",
    "License Number",
    "License Type",
    "Status",
    "Licensee",
    "Premises",
    "Premises Address",
    "Premises Mailing Address",
    "Premises Owner",
    "Premises Manager",
    "County",
    "Municipality",
    "Last Issue Date",
    "Expiration Date",
}

# CSV header → staging column name
COLUMN_MAP = {
    "LID": "lid",
    "License Number": "license_number",
    "License Type": "license_type",
    "Status": "status",
    "Licensee": "licensee",
    "Premises": "premises_name",
    "Premises Address": "premises_address",
    "Premises Mailing Address": "premises_mailing_address",
    "Premises Owner": "premises_owner",
    "Premises Manager": "premises_manager",
    "Municipality": "municipality",
    "Last Issue Date": "last_issue_date",
    "Expiration Date": "expiration_date",
}


def parse_plcb_csv(csv_text: str) -> list[dict]:
    """Parse PLCB CSV text and return York County records.

    Args:
        csv_text: Raw CSV string (full statewide file).

    Returns:
        List of dicts with staging column names, filtered to York County.
    """
    reader = csv.DictReader(StringIO(csv_text))
    records = []

    for row in reader:
        if row.get("County", "").strip() != "York County":
            continue

        record = {}
        for csv_col, db_col in COLUMN_MAP.items():
            val = row.get(csv_col, "").strip()
            record[db_col] = val if val else None
        records.append(record)

    return records
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd pipelines && uv run pytest tests/test_plcb_parser.py -v
```

Expected: All 6 tests PASS

- [ ] **Step 6: Commit**

```bash
git add pipelines/york_county/lib/parsers/plcb.py pipelines/tests/test_plcb_parser.py pipelines/tests/fixtures/plcb_sample.csv
git commit -m "feat: add PLCB CSV parser with York County filtering + tests"
```

---

## Task 3: Dagster Asset + Asset Checks

**Files:**
- Create: `pipelines/york_county/assets/bulk/__init__.py`
- Create: `pipelines/york_county/assets/bulk/plcb.py`

- [ ] **Step 1: Create bulk package init**

```python
# pipelines/york_county/assets/bulk/__init__.py
```

(Empty file — just makes `bulk/` a Python package so `load_assets_from_package_module` discovers it.)

- [ ] **Step 2: Write the asset + checks**

```python
# pipelines/york_county/assets/bulk/plcb.py
"""PLCB liquor licenses bulk CSV → staging.plcb_licenses.

Source: https://plcbplus.pa.gov/pub/LicenseExport.aspx
Records: ~1,400 York County licenses (filtered from statewide CSV)
Schedule: Monthly (1st of month, 05:00)
"""

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

from york_county.lib.parsers.plcb import parse_plcb_csv, EXPECTED_HEADERS
from york_county.lib.scd import scd2_upsert
from york_county.resources.database import DatabaseResource
from york_county.resources.storage import S3StorageResource

PLCB_CSV_URL = "https://plcbplus.pa.gov/pub/LicenseExport.aspx"

KEY_COLUMNS = ["lid"]
VALUE_COLUMNS = [
    "license_number",
    "license_type",
    "status",
    "licensee",
    "premises_name",
    "premises_address",
    "premises_mailing_address",
    "premises_owner",
    "premises_manager",
    "municipality",
    "last_issue_date",
    "expiration_date",
]


@asset(
    group_name="bulk",
    description="PLCB liquor licenses for York County → staging.plcb_licenses",
    kinds={"postgres", "csv"},
)
def plcb_licenses(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Download PLCB CSV, filter to York County, SCD2 upsert."""

    # 1. Download CSV
    context.log.info(f"Downloading PLCB CSV from {PLCB_CSV_URL}")
    resp = requests.get(PLCB_CSV_URL, timeout=120)
    resp.raise_for_status()
    csv_text = resp.text
    context.log.info(f"Downloaded {len(csv_text)} bytes")

    # 2. Archive raw CSV to S3 (skipped locally if no AWS creds)
    s3.archive("bulk/plcb", csv_text, filename="licenses.csv")

    # 3. Parse and filter to York County
    records = parse_plcb_csv(csv_text)
    context.log.info(f"Parsed {len(records)} York County license records")

    if not records:
        context.log.warning("No York County records found — skipping upsert")
        return MaterializeResult(
            metadata={"record_count": MetadataValue.int(0)}
        )

    # 4. SCD2 upsert to staging.plcb_licenses
    cur = database.cursor()
    try:
        stats = scd2_upsert(
            cursor=cur,
            schema="staging",
            table="plcb_licenses",
            records=records,
            key_columns=KEY_COLUMNS,
            value_columns=VALUE_COLUMNS,
        )
    finally:
        cur.close()

    return MaterializeResult(
        metadata={
            "record_count": MetadataValue.int(len(records)),
            "inserted": MetadataValue.int(stats["inserted"]),
            "expired": MetadataValue.int(stats["expired"]),
            "unchanged": MetadataValue.int(stats["unchanged"]),
        }
    )


@asset_check(asset=plcb_licenses)
def plcb_record_count_nonzero(database: DatabaseResource) -> AssetCheckResult:
    """Verify staging.plcb_licenses has at least one current record."""
    result = database.execute(
        "SELECT COUNT(*) FROM staging.plcb_licenses WHERE valid_to IS NULL"
    )
    count = result[0][0] if result else 0
    return AssetCheckResult(
        passed=count > 0,
        severity=AssetCheckSeverity.ERROR,
        metadata={"current_record_count": MetadataValue.int(count)},
    )


@asset_check(asset=plcb_licenses)
def plcb_no_schema_drift() -> AssetCheckResult:
    """Verify PLCB CSV headers haven't changed."""
    import csv as csv_mod
    from io import StringIO

    try:
        resp = requests.get(PLCB_CSV_URL, timeout=30, stream=True)
        resp.raise_for_status()
        # Read just the first line (header), strip BOM if present
        first_line = next(resp.iter_lines(decode_unicode=True)).lstrip("\ufeff")
        reader = csv_mod.reader(StringIO(first_line))
        actual_headers = {h.strip() for h in next(reader)}
        missing = EXPECTED_HEADERS - actual_headers
        extra = actual_headers - EXPECTED_HEADERS
        passed = len(missing) == 0
        return AssetCheckResult(
            passed=passed,
            severity=AssetCheckSeverity.WARN,
            metadata={
                "missing_headers": MetadataValue.text(str(missing) if missing else "none"),
                "extra_headers": MetadataValue.text(str(extra) if extra else "none"),
            },
        )
    except Exception as e:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.WARN,
            metadata={"error": MetadataValue.text(str(e))},
        )
```

- [ ] **Step 3: Verify import works**

```bash
cd pipelines && uv run python -c "from york_county.definitions import defs; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add pipelines/york_county/assets/bulk/
git commit -m "feat: add plcb_licenses Dagster asset with SCD2 upsert + asset checks"
```

---

## Task 4: Integration Test — Local Docker Postgres

**Files:**
- Create: `pipelines/tests/test_plcb_integration.py`

- [ ] **Step 1: Write integration test**

```python
# pipelines/tests/test_plcb_integration.py
"""Integration test: materialize plcb_licenses against local Docker Postgres.

Requires: docker compose up -d postgres-test && alembic upgrade head
"""
import os
import pytest
import psycopg2

# Skip if Docker Postgres is not running
def _pg_available():
    try:
        conn = psycopg2.connect(
            host="localhost", port=5433, dbname="york_county_intel",
            user="dagster_admin", password="localtest", connect_timeout=3,
        )
        conn.close()
        return True
    except Exception:
        return False

pytestmark = pytest.mark.skipif(
    not _pg_available(),
    reason="Local Docker Postgres not running on port 5433",
)


def test_plcb_parser_to_staging():
    """Parse real fixture CSV and SCD2 upsert to staging.plcb_licenses."""
    from pathlib import Path
    from york_county.lib.parsers.plcb import parse_plcb_csv
    from york_county.lib.scd import scd2_upsert

    fixture = (Path(__file__).parent / "fixtures" / "plcb_sample.csv").read_text()
    records = parse_plcb_csv(fixture)
    assert len(records) == 4

    conn = psycopg2.connect(
        host="localhost", port=5433, dbname="york_county_intel",
        user="dagster_admin", password="localtest",
    )
    conn.autocommit = False
    cur = conn.cursor()
    try:
        stats = scd2_upsert(
            cursor=cur,
            schema="staging",
            table="plcb_licenses",
            records=records,
            key_columns=["lid"],
            value_columns=[
                "license_number", "license_type", "status", "licensee",
                "premises_name", "premises_address", "premises_mailing_address",
                "premises_owner", "premises_manager", "municipality",
                "last_issue_date", "expiration_date",
            ],
        )
        conn.commit()

        assert stats["inserted"] == 4
        assert stats["expired"] == 0

        # Verify data landed
        cur.execute("SELECT COUNT(*) FROM staging.plcb_licenses WHERE valid_to IS NULL")
        count = cur.fetchone()[0]
        assert count >= 4

        # Verify a specific record
        cur.execute(
            "SELECT licensee, municipality FROM staging.plcb_licenses WHERE lid = '54316' AND valid_to IS NULL"
        )
        row = cur.fetchone()
        assert row[0] == "SUSQUEHANNA FISH AND GAME ASSOCIATION INC"
        assert row[1] == "Hellam Twp"

    finally:
        # Clean up test data (rollback clears failed transaction state if needed)
        conn.rollback()
        cur.execute("DELETE FROM staging.plcb_licenses")
        conn.commit()
        cur.close()
        conn.close()
```

- [ ] **Step 2: Ensure Docker Postgres is running with migrations**

```bash
cd pipelines
docker compose up -d postgres-test
sleep 3
DATABASE_URL="postgresql://dagster_admin:localtest@localhost:5433/york_county_intel" \
  uv run alembic upgrade head
```

- [ ] **Step 3: Run all tests**

```bash
cd pipelines && uv run pytest tests/test_plcb_parser.py tests/test_plcb_integration.py -v
```

Expected: All tests PASS (unit + integration)

- [ ] **Step 4: Commit**

```bash
git add pipelines/tests/test_plcb_integration.py
git commit -m "test: add PLCB integration test against local Docker Postgres"
```

---

## Task 5: End-to-End — Materialize via Dagster

This task uses Dagster's Python API to materialize the asset programmatically (no UI needed).

- [ ] **Step 1: Materialize the asset**

```bash
cd pipelines && DATABASE_HOST=localhost DATABASE_PORT=5433 DATABASE_NAME=york_county_intel \
  DATABASE_USER=dagster_admin DATABASE_PASSWORD=localtest \
  uv run dagster asset materialize --select plcb_licenses -m york_county.definitions
```

Expected: Dagster downloads the full PLCB CSV, filters to ~1,400 York County rows, SCD2 upserts to staging.

- [ ] **Step 2: Verify data in Postgres**

```bash
PGPASSWORD=localtest psql -h localhost -p 5433 -U dagster_admin -d york_county_intel \
  -c "SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE status = 'Active') AS active FROM staging.plcb_licenses WHERE valid_to IS NULL;"
```

Expected: ~1,400 total, majority Active.

- [ ] **Step 3: Run asset checks**

```bash
cd pipelines && DATABASE_HOST=localhost DATABASE_PORT=5433 DATABASE_NAME=york_county_intel \
  DATABASE_USER=dagster_admin DATABASE_PASSWORD=localtest \
  uv run python -c "
from york_county.resources.database import make_database_resource
db = make_database_resource()
db._conn = None
result = db.execute('SELECT COUNT(*) FROM staging.plcb_licenses WHERE valid_to IS NULL')
print(f'Current records: {result[0][0]}')
assert result[0][0] > 0, 'No records in staging.plcb_licenses!'
print('Asset check: record_count_nonzero PASSED')
"
```

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: PLCB liquor licenses pipeline complete — asset, parser, migration, tests"
```
