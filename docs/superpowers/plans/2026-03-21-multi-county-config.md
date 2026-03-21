# Multi-County Configuration Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract all county-specific hardcoded values (URLs, county name filters, record count thresholds) into a single config module so pipelines become plug-and-play for any PA county.

**Architecture:** A `county_config.py` module defines a `CountyConfig` dataclass with per-county source URLs, filter strings, and thresholds. Each asset/parser reads from the active county config instead of hardcoded constants. The active county is set via a `COUNTY` env var (default: `york`). Existing tests continue to work unchanged — they test parsers with fixture data, not county-specific config.

**Tech Stack:** Python dataclasses, existing Dagster resource pattern, pytest

**Local testing:** `uv` for Python 3.11, Docker Postgres on localhost:5433, same as current setup. Set `COUNTY=york` (or omit — it's the default).

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `pipelines/york_county/lib/county_config.py` | CountyConfig dataclass + registry of county configs |
| Modify | `pipelines/york_county/lib/parsers/plcb.py` | Accept `county_filter` param instead of hardcoded `"York County"` |
| Modify | `pipelines/york_county/assets/bulk/plcb.py` | Read URL + threshold + county filter from config |
| Modify | `pipelines/york_county/assets/arcgis/parcels.py` | Read parcels URL from config |
| Modify | `pipelines/york_county/definitions.py` | (No change needed — auto-discovery still works) |
| Modify | `pipelines/tests/test_plcb_parser.py` | Pass county_filter to parser |
| Create | `pipelines/tests/test_county_config.py` | Tests for config loading and validation |
| Modify | `pipelines/tests/test_plcb_integration.py` | Pass county_filter to parser |

---

## Task 1: Create `county_config.py`

**Files:**
- Create: `pipelines/york_county/lib/county_config.py`
- Create: `pipelines/tests/test_county_config.py`

- [ ] **Step 1: Write tests for the config module**

```python
# pipelines/tests/test_county_config.py
from york_county.lib.county_config import CountyConfig, get_county_config, COUNTY_CONFIGS


def test_york_config_exists():
    config = get_county_config("york")
    assert config.name == "York County"
    assert config.plcb_filter == "York County"
    assert config.plcb_min_records == 500
    assert "arcweb1.ycpc.org" in config.arcgis_parcels_url


def test_default_county_is_york():
    config = get_county_config()
    assert config.name == "York County"


def test_unknown_county_raises():
    import pytest
    with pytest.raises(KeyError):
        get_county_config("nonexistent")


def test_all_configs_have_required_fields():
    for key, config in COUNTY_CONFIGS.items():
        assert config.name, f"{key} missing name"
        assert config.plcb_filter, f"{key} missing plcb_filter"
        assert config.arcgis_parcels_url, f"{key} missing arcgis_parcels_url"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd pipelines && source .venv/bin/activate && pytest tests/test_county_config.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'york_county.lib.county_config'`

- [ ] **Step 3: Write the config module**

```python
# pipelines/york_county/lib/county_config.py
"""County-specific configuration for multi-county pipeline support.

Each county has its own config with source URLs, filter strings, and thresholds.
The active county is selected by the COUNTY env var (default: "york").

To add a new county:
  1. Add a CountyConfig entry to COUNTY_CONFIGS
  2. Fill in the source URLs and thresholds for that county
  3. Set COUNTY=<key> when running pipelines
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class CountyConfig:
    """Configuration for a single county's data sources."""

    # Identity
    name: str                       # e.g. "York County"
    state: str = "PA"

    # PLCB liquor licenses (statewide CSV, filtered by county name)
    plcb_filter: str = ""           # Value in the "County" CSV column
    plcb_min_records: int = 100     # Minimum expected records (truncation guard)

    # ArcGIS GIS Portal
    arcgis_parcels_url: str = ""    # FeatureServer/0 URL for parcels layer
    arcgis_base_url: str = ""       # Base REST services URL

    # Assessment portal
    assessment_url: str = ""        # Assessment portal base URL
    assessment_min_records: int = 1000

    # S3 archive prefix (raw data goes to s3://york-county-raw/<prefix>/...)
    s3_prefix: str = ""


COUNTY_CONFIGS: dict[str, CountyConfig] = {
    "york": CountyConfig(
        name="York County",
        plcb_filter="York County",
        plcb_min_records=500,
        arcgis_parcels_url="https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/Parcels/FeatureServer/0",
        arcgis_base_url="https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA",
        assessment_url="https://assessmentpublic.yorkcountypa.gov/",
        assessment_min_records=150000,
        s3_prefix="york",
    ),
}


def get_county_config(county_key: str | None = None) -> CountyConfig:
    """Get the config for a county. Defaults to COUNTY env var, then 'york'."""
    if county_key is None:
        county_key = os.environ.get("COUNTY", "york")
    return COUNTY_CONFIGS[county_key]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd pipelines && source .venv/bin/activate && pytest tests/test_county_config.py -v
```

Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pipelines/york_county/lib/county_config.py pipelines/tests/test_county_config.py
git commit -m "feat: add county_config module for multi-county pipeline support"
```

---

## Task 2: Refactor PLCB parser to accept county filter

**Files:**
- Modify: `pipelines/york_county/lib/parsers/plcb.py`
- Modify: `pipelines/tests/test_plcb_parser.py`

- [ ] **Step 1: Update parser to accept county_filter parameter**

Change `parse_plcb_csv` signature from:
```python
def parse_plcb_csv(csv_text: str) -> list[dict]:
```
to:
```python
def parse_plcb_csv(csv_text: str, county_filter: str = "York County") -> list[dict]:
```

And change the filter line from:
```python
if row.get("County", "").strip() != "York County":
```
to:
```python
if row.get("County", "").strip() != county_filter:
```

- [ ] **Step 2: Run existing tests — they should still pass (default param)**

```bash
cd pipelines && source .venv/bin/activate && pytest tests/test_plcb_parser.py -v
```

Expected: All 8 tests PASS (the default `county_filter="York County"` preserves backward compatibility)

- [ ] **Step 3: Add a test for custom county filter**

Add to `tests/test_plcb_parser.py`:

```python
def test_parse_with_different_county_filter():
    csv_text = (FIXTURES_DIR / "plcb_sample.csv").read_text()
    records = parse_plcb_csv(csv_text, county_filter="Allegheny County")
    assert len(records) == 1  # Only the Pittsburgh Shake Shack row
    assert records[0]["lid"] == "128829"
```

- [ ] **Step 4: Run all parser tests**

```bash
cd pipelines && source .venv/bin/activate && pytest tests/test_plcb_parser.py -v
```

Expected: 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pipelines/york_county/lib/parsers/plcb.py pipelines/tests/test_plcb_parser.py
git commit -m "refactor: plcb parser accepts county_filter param for multi-county support"
```

---

## Task 3: Refactor PLCB asset to use county config

**Files:**
- Modify: `pipelines/york_county/assets/bulk/plcb.py`

- [ ] **Step 1: Replace hardcoded constants with config lookups**

Replace:
```python
PLCB_CSV_URL = "https://plcbplus.pa.gov/pub/LicenseExport.aspx"
MIN_EXPECTED_RECORDS = 500
```

With:
```python
from york_county.lib.county_config import get_county_config

# PLCB CSV URL is statewide (same for all counties)
PLCB_CSV_URL = "https://plcbplus.pa.gov/pub/LicenseExport.aspx"
```

And inside the asset function, replace:
```python
records = parse_plcb_csv(csv_text)
```
with:
```python
county = get_county_config()
records = parse_plcb_csv(csv_text, county_filter=county.plcb_filter)
context.log.info(f"Parsed {len(records)} {county.name} license records")
```

And replace:
```python
if len(records) < MIN_EXPECTED_RECORDS:
```
with:
```python
if len(records) < county.plcb_min_records:
```

Update the error message and description similarly.

- [ ] **Step 2: Update S3 archive path to use county prefix**

Replace:
```python
s3.archive("bulk/plcb", csv_text, filename="licenses.csv")
```
with:
```python
s3.archive(f"{county.s3_prefix}/bulk/plcb", csv_text, filename="licenses.csv")
```

- [ ] **Step 3: Verify import still works**

```bash
cd pipelines && source .venv/bin/activate && \
  DATABASE_HOST=localhost DATABASE_PORT=5433 DATABASE_PASSWORD=localtest \
  python -c "from york_county.definitions import defs; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add pipelines/york_county/assets/bulk/plcb.py
git commit -m "refactor: plcb asset reads from county_config instead of hardcoded values"
```

---

## Task 4: Refactor parcels asset to use county config

**Files:**
- Modify: `pipelines/york_county/assets/arcgis/parcels.py`

- [ ] **Step 1: Replace hardcoded URL with config lookup**

Replace:
```python
PARCELS_URL = (
    "https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/Parcels/FeatureServer/0"
)
```

With config lookup inside the asset function:
```python
from york_county.lib.county_config import get_county_config
```

And in the function body:
```python
county = get_county_config()
context.log.info(f"Querying ArcGIS parcels for {county.name}: {county.arcgis_parcels_url}")
raw_features = query_all_features(
    url=county.arcgis_parcels_url,
    ...
)
```

- [ ] **Step 2: Update S3 archive path**

Replace:
```python
s3.archive("arcgis/parcels", raw_features)
```
with:
```python
s3.archive(f"{county.s3_prefix}/arcgis/parcels", raw_features)
```

- [ ] **Step 3: Run existing tests — parser tests don't touch the asset, should pass**

```bash
cd pipelines && source .venv/bin/activate && pytest tests/test_parcels_parser.py -v
```

Expected: All 5 PASS

- [ ] **Step 4: Verify Dagster loads**

```bash
cd pipelines && source .venv/bin/activate && \
  DATABASE_HOST=localhost DATABASE_PORT=5433 DATABASE_PASSWORD=localtest \
  python -c "from york_county.definitions import defs; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add pipelines/york_county/assets/arcgis/parcels.py
git commit -m "refactor: parcels asset reads URL from county_config"
```

---

## Task 5: Update integration test and run full suite

**Files:**
- Modify: `pipelines/tests/test_plcb_integration.py`

- [ ] **Step 1: Update PLCB integration test to use county config**

The integration test calls `parse_plcb_csv(fixture)` directly. Update it to pass the county filter explicitly (so it doesn't depend on env var):

Replace:
```python
records = parse_plcb_csv(fixture)
```
with:
```python
records = parse_plcb_csv(fixture, county_filter="York County")
```

- [ ] **Step 2: Start Docker Postgres and run full test suite**

```bash
cd pipelines
docker compose up -d postgres-test
sleep 3
PGPASSWORD=localtest psql -h localhost -p 5433 -U dagster_admin -d york_county_intel \
  -f /home/jdaws/countyiq/infra/modules/database/init.sql 2>&1 | tail -3
DATABASE_URL="postgresql://dagster_admin:localtest@localhost:5433/york_county_intel" \
  source .venv/bin/activate && alembic upgrade head
```

```bash
source .venv/bin/activate && pytest tests/ -v
```

Expected: All tests PASS (17 existing + 4 new county_config tests = 21+ tests)

- [ ] **Step 3: Stop Docker**

```bash
docker compose down -v
```

- [ ] **Step 4: Commit**

```bash
git add pipelines/tests/test_plcb_integration.py
git commit -m "refactor: integration test uses explicit county_filter"
```

---

## Task 6: Update docs

**Files:**
- Modify: `docs/implementation/expansion-roadmap.md` (Multi-County Expansion Notes)
- Modify: `docs/pipelines/code-structure.md` (add county_config to lib/ table)

- [ ] **Step 1: Update expansion roadmap**

Replace the "Multi-County Expansion Notes" section with updated instructions that reference `county_config.py` and the `COUNTY` env var. The key change: "Copy the Dagster asset templates" becomes "Add a CountyConfig entry and set COUNTY env var."

- [ ] **Step 2: Update code structure doc**

Add `county_config.py` to the `lib/` utilities table in `docs/pipelines/code-structure.md`.

- [ ] **Step 3: Commit**

```bash
git add docs/implementation/expansion-roadmap.md docs/pipelines/code-structure.md
git commit -m "docs: update multi-county expansion notes for county_config pattern"
```
