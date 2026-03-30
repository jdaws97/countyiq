# Parcels Pipeline Augment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename parser/test files to match conventions, add asset checks, change schedule to Sunday 2 AM, fix geometry performance (execute_batch), and verify locally against ~176K live records.

**Architecture:** The parcels pipeline already exists — asset, parser, ArcGIS client, tests, schema, and fixture are all implemented. This plan renames files to `arcgis_parcels` convention, adds asset checks (record count > 150K, schema drift), switches geometry updates from `executemany` (176K individual UPDATEs) to `execute_batch` (batched), changes schedule to Sunday 2 AM, and runs the live integration test.

**Tech Stack:** Python 3.11, Dagster, psycopg2 (execute_batch), PostGIS, ArcGIS REST API

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Rename | `pipelines/countyiq/lib/parsers/parcels.py` → `arcgis_parcels.py` | Parser file rename |
| Rename | `pipelines/tests/test_parcels_parser.py` → `test_arcgis_parcels_parser.py` | Test file rename |
| Modify | `pipelines/countyiq/assets/arcgis/parcels.py` | Update import, add checks, fix geometry perf |
| Modify | `pipelines/tests/test_parcels_integration.py` | Update import path |
| Modify | `pipelines/countyiq/schedules/__init__.py` | Change arcgis schedule to Sunday 2 AM |

---

### Task 1: Rename parser and test files, update imports

**Files:**
- Rename: `pipelines/countyiq/lib/parsers/parcels.py` → `pipelines/countyiq/lib/parsers/arcgis_parcels.py`
- Rename: `pipelines/tests/test_parcels_parser.py` → `pipelines/tests/test_arcgis_parcels_parser.py`
- Modify: `pipelines/countyiq/assets/arcgis/parcels.py` (import path)
- Modify: `pipelines/tests/test_parcels_integration.py` (import path)
- Modify: `pipelines/tests/test_arcgis_parcels_parser.py` (import path)

- [ ] **Step 1: Rename parser file**

```bash
cd pipelines
git mv countyiq/lib/parsers/parcels.py countyiq/lib/parsers/arcgis_parcels.py
```

- [ ] **Step 2: Rename test file**

```bash
git mv tests/test_parcels_parser.py tests/test_arcgis_parcels_parser.py
```

- [ ] **Step 3: Update import in asset file**

In `pipelines/countyiq/assets/arcgis/parcels.py`, change:
```python
from countyiq.lib.parsers.parcels import parse_parcels_features
```
to:
```python
from countyiq.lib.parsers.arcgis_parcels import parse_parcels_features
```

- [ ] **Step 4: Update import in test file**

In `pipelines/tests/test_arcgis_parcels_parser.py`, change:
```python
from countyiq.lib.parsers.parcels import parse_parcels_features
```
to:
```python
from countyiq.lib.parsers.arcgis_parcels import parse_parcels_features
```

- [ ] **Step 5: Update import in integration test**

In `pipelines/tests/test_parcels_integration.py`, change:
```python
from countyiq.lib.parsers.parcels import parse_parcels_features
```
to:
```python
from countyiq.lib.parsers.arcgis_parcels import parse_parcels_features
```

- [ ] **Step 6: Run all tests**

Run: `cd pipelines && source .venv/bin/activate && pytest tests/ -v`
Expected: All 33 tests pass (imports resolve to new path).

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: rename parcels parser to arcgis_parcels for clarity"
```

---

### Task 2: Add asset checks to parcels

**Files:**
- Modify: `pipelines/countyiq/assets/arcgis/parcels.py`

Add two asset checks following the FEMA pattern (see `assets/bulk/fema_flood.py`):
1. `parcels_record_count` — verifies current record count > 150,000
2. `parcels_schema_drift` — verifies ArcGIS FeatureServer still has expected fields

- [ ] **Step 1: Add imports and constants**

At the top of `pipelines/countyiq/assets/arcgis/parcels.py`, add to the dagster import:
```python
from dagster import (
    asset,
    asset_check,
    AssetCheckResult,
    AssetCheckSeverity,
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
)
```

Add after `import requests` (new import):
```python
import requests
```

Add a constant for expected fields (after VALUE_COLUMNS):
```python
# Expected fields from ArcGIS FeatureServer (for schema drift check)
EXPECTED_FIELDS = {
    "PIDN", "OWNER_FULL", "PROPADR", "APRTOTAL", "SALEDT", "PRICE",
    "MUNICIPALITY", "SCHOOL_DIS", "ACRES", "CLASS", "DISTRICT", "BLOCK",
    "MAP", "PARCEL", "DEED_BK", "DEED_PG", "OWN_NAME1", "OWN_NAME2",
    "MAIL_ADDR_FULL", "PREV_OWNER", "LUC", "STYLE", "NUM_STORIE",
    "RES_LIVING_AREA", "YRBLT", "APRLAND", "APRBLDG", "PREV_PRICE",
}
```

- [ ] **Step 2: Add record count check**

Add after the `parcels_arcgis` function:

```python
@asset_check(asset=parcels_arcgis)
def parcels_record_count(database: DatabaseResource) -> AssetCheckResult:
    """Verify staging.parcels has > 150,000 current records."""
    county = get_county_config()
    result = database.execute(
        "SELECT COUNT(*) FROM staging.parcels WHERE valid_to IS NULL"
    )
    count = result[0][0] if result else 0
    return AssetCheckResult(
        passed=count > county.assessment_min_records,
        severity=AssetCheckSeverity.ERROR,
        metadata={"current_record_count": MetadataValue.int(count)},
    )
```

Note: `county.assessment_min_records` is 150,000 for York County — reuses the existing threshold. If parcels needs its own threshold, add `arcgis_parcels_min_records` to CountyConfig later.

- [ ] **Step 3: Add schema drift check**

```python
@asset_check(asset=parcels_arcgis)
def parcels_schema_drift() -> AssetCheckResult:
    """Verify ArcGIS FeatureServer still has expected parcel fields."""
    county = get_county_config()
    try:
        resp = requests.get(f"{county.arcgis_parcels_url}?f=json", timeout=30)
        resp.raise_for_status()
        layer_meta = resp.json()
        actual_fields = {f["name"] for f in layer_meta.get("fields", [])}
        missing = EXPECTED_FIELDS - actual_fields
        return AssetCheckResult(
            passed=len(missing) == 0,
            severity=AssetCheckSeverity.WARN,
            metadata={
                "missing_fields": MetadataValue.text(str(missing) if missing else "none"),
                "total_fields": MetadataValue.int(len(actual_fields)),
            },
        )
    except requests.exceptions.RequestException as e:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.WARN,
            metadata={"error": MetadataValue.text(f"Network error: {e}")},
        )
```

- [ ] **Step 4: Verify Dagster loads definitions**

Run: `cd pipelines && source .venv/bin/activate && python3 -c "from countyiq.definitions import defs; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add pipelines/countyiq/assets/arcgis/parcels.py
git commit -m "feat(parcels): add record count and schema drift asset checks"
```

---

### Task 3: Fix geometry update performance

**Files:**
- Modify: `pipelines/countyiq/assets/arcgis/parcels.py`

The existing `_update_geometries` uses `cursor.executemany()` to UPDATE 176K records individually — this will take 30+ minutes. Replace with `psycopg2.extras.execute_batch` (page_size=500) for ~10x speedup.

- [ ] **Step 1: Add execute_batch import**

Add at top of file:
```python
from psycopg2.extras import execute_batch
```

- [ ] **Step 2: Replace _update_geometries function**

Replace the existing `_update_geometries` function with:

```python
def _update_geometries(cursor, raw_features: list[dict]):
    """Set geometry on newly inserted records (valid_to IS NULL, geom IS NULL).

    Uses execute_batch for performance with 176K+ records.
    """
    import json

    update_sql = """
        UPDATE staging.parcels
        SET geom = ST_SetSRID(ST_Multi(ST_GeomFromGeoJSON(%s)), 4326)
        WHERE pidn = %s AND valid_to IS NULL AND geom IS NULL
    """
    batch = []
    for feat in raw_features:
        geom = feat.get("geometry")
        attrs = feat.get("attributes", {})
        pidn = attrs.get("PIDN")
        if geom and pidn:
            geojson = _arcgis_geom_to_geojson(geom)
            if geojson:
                batch.append((json.dumps(geojson), pidn))

    if batch:
        execute_batch(cursor, update_sql, batch, page_size=500)
```

Key changes:
- `executemany` → `execute_batch` with `page_size=500`
- `ST_GeomFromGeoJSON` → `ST_SetSRID(ST_Multi(ST_GeomFromGeoJSON(...)), 4326)` for explicit SRID + MULTI wrapping (consistent with FEMA pattern)

- [ ] **Step 3: Run tests**

Run: `cd pipelines && source .venv/bin/activate && pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add pipelines/countyiq/assets/arcgis/parcels.py
git commit -m "perf(parcels): use execute_batch for geometry updates (176K records)"
```

---

### Task 4: Change schedule to Sunday 2 AM

**Files:**
- Modify: `pipelines/countyiq/schedules/__init__.py`

- [ ] **Step 1: Change cron schedule**

In `pipelines/countyiq/schedules/__init__.py`, change:
```python
    ScheduleDefinition(
        job=arcgis_refresh,
        cron_schedule="0 2 * * 1",  # Monday 02:00
        name="weekly_arcgis",
    ),
```
to:
```python
    ScheduleDefinition(
        job=arcgis_refresh,
        cron_schedule="0 2 * * 0",  # Sunday 02:00
        name="weekly_arcgis",
    ),
```

- [ ] **Step 2: Verify no schedule conflicts**

Current schedules after change:
- `weekly_arcgis`: Sunday 02:00
- `weekly_scrapers`: Monday 03:00
- `monthly_bulk`: 1st of month 05:00
- `weekly_fema`: Sunday 04:00

Sunday: arcgis at 02:00, then FEMA at 04:00. No overlap (parcels takes ~15-20 min, 2-hour gap).

- [ ] **Step 3: Verify Dagster loads**

Run: `cd pipelines && source .venv/bin/activate && python3 -c "from countyiq.definitions import defs; print('OK')"`

- [ ] **Step 4: Commit**

```bash
git add pipelines/countyiq/schedules/__init__.py
git commit -m "feat(parcels): change arcgis schedule to Sunday 2 AM"
```

---

### Task 5: Local integration test — live 176K records

**Files:** None (manual verification against Docker Postgres)

- [ ] **Step 1: Ensure Docker Postgres is running with schema**

```bash
cd pipelines && docker compose up -d postgres-test
export DATABASE_URL="postgresql://dagster_admin:localtest@localhost:5433/countyiq"
source .venv/bin/activate && alembic upgrade head
```

- [ ] **Step 2: Materialize the asset via Dagster CLI**

```bash
cd pipelines && source .venv/bin/activate
export DATABASE_HOST=localhost DATABASE_PORT=5433 DATABASE_NAME=countyiq DATABASE_USER=dagster_admin DATABASE_PASSWORD=localtest
dagster asset materialize --select parcels_arcgis -m countyiq.definitions
```

Expected: Asset materializes successfully. Logs show pagination through ~88 pages of 2000 records each.

**Note:** This will take several minutes due to 176K records + geometry conversion. Watch for:
- Pagination completing without errors
- S3 archive warning (expected locally without AWS creds)
- SCD2 upsert inserting ~176K records
- Geometry updates completing (should be faster now with execute_batch)

- [ ] **Step 3: Checkpoint — verify record count**

```bash
PGPASSWORD=localtest psql -h localhost -p 5433 -U dagster_admin -d countyiq -c "
  SELECT COUNT(*) FROM staging.parcels WHERE valid_to IS NULL;
"
```

Expected: ~176,000 (the exact number may vary slightly from the Oct 2025 snapshot).

- [ ] **Step 4: Verify data quality**

```bash
PGPASSWORD=localtest psql -h localhost -p 5433 -U dagster_admin -d countyiq -c "
  SELECT
    COUNT(*) as total,
    COUNT(geom) as has_geom,
    COUNT(owner_full) as has_owner,
    COUNT(DISTINCT municipality) as municipalities,
    COUNT(DISTINCT school_dis) as school_districts
  FROM staging.parcels
  WHERE valid_to IS NULL;
"
```

Expected: Most records have geometry, owner_full populated, 70+ municipalities, 15+ school districts.

- [ ] **Step 5: Verify geometry SRID**

```bash
PGPASSWORD=localtest psql -h localhost -p 5433 -U dagster_admin -d countyiq -c "
  SELECT ST_SRID(geom) AS srid, COUNT(*)
  FROM staging.parcels
  WHERE valid_to IS NULL AND geom IS NOT NULL
  GROUP BY ST_SRID(geom);
"
```

Expected: All geometry SRID = 4326.

- [ ] **Step 6: Run full test suite**

```bash
cd pipelines && source .venv/bin/activate && pytest tests/ -v
```

Expected: All tests pass.
