# FEMA Flood Zones Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Dagster pipeline that fetches FEMA NFHL flood hazard zone polygons for York County via the ArcGIS REST API, parses the GeoJSON, and upserts to `staging.flood_zones` with SCD Type 2 semantics.

**Architecture:** Query FEMA's NFHL MapServer Layer 28 (Flood Hazard Zones) filtered by `DFIRM_ID='42133C'` (York County) with `outSR=4326` for WGS84 coordinates. Paginate through ~5,238 records at 2,000/page as GeoJSON. Parse features, convert sentinel values (-9999) to NULL, wrap Polygon geometries as MultiPolygon for PostGIS, then SCD2 upsert into `staging.flood_zones`. The existing table (migration 001) has core columns; a new migration adds `static_bfe`, `depth`, `v_datum`, `source_cit`, and `dfirm_id`.

**Tech Stack:** Python 3.11, Dagster, requests, psycopg2 (execute_batch), PostGIS (ST_GeomFromGeoJSON, ST_Multi, ST_SetSRID)

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `pipelines/countyiq/lib/county_config.py` | Add FEMA config fields to `CountyConfig` |
| Create | `pipelines/countyiq/lib/parsers/fema.py` | Parse FEMA GeoJSON, clean sentinel values, map to staging columns |
| Create | `pipelines/tests/fixtures/fema_flood_sample.geojson` | Sample GeoJSON fixture (5 features with varied zone types + edge cases) |
| Create | `pipelines/tests/test_fema_parser.py` | Unit tests for parser |
| Create | `pipelines/alembic/versions/003_add_fema_flood_columns.py` | Add missing columns to `staging.flood_zones` |
| Create | `pipelines/countyiq/assets/bulk/fema_flood.py` | Dagster asset + asset checks |
| Modify | `pipelines/countyiq/schedules/__init__.py` | Add weekly Sunday 4 AM schedule |
| Modify | `pipelines/countyiq/jobs/__init__.py` | Add `fema_refresh` job |
| Modify | `pipelines/countyiq/definitions.py` | Register `fema_refresh` job |

---

### Task 1: Add FEMA fields to county config

**Files:**
- Modify: `pipelines/countyiq/lib/county_config.py`

- [ ] **Step 1: Add FEMA config fields to CountyConfig dataclass**

```python
# Add after the assessment fields in CountyConfig:

    # FEMA National Flood Hazard Layer
    fema_nfhl_url: str = ""          # MapServer base URL
    fema_flood_layer: int = 28       # S_Fld_Haz_Ar layer ID
    fema_dfirm_id: str = ""          # County DFIRM ID for filtering
    fema_min_records: int = 100      # Minimum expected records (truncation guard)
```

- [ ] **Step 2: Add FEMA values to York County config**

```python
# Add to the "york" CountyConfig entry:
        fema_nfhl_url="https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer",
        fema_flood_layer=28,
        fema_dfirm_id="42133C",
        fema_min_records=3000,
```

Note: 3000 is ~57% of the expected ~5,238 records — catches partial API failures while allowing natural dataset size changes.

- [ ] **Step 3: Verify import still works**

Run: `cd pipelines && source .venv/bin/activate && python3 -c "from countyiq.lib.county_config import get_county_config; c = get_county_config(); print(c.fema_dfirm_id)"`
Expected: `42133C`

- [ ] **Step 4: Commit**

```bash
git add pipelines/countyiq/lib/county_config.py
git commit -m "feat(config): add FEMA NFHL fields to county config"
```

---

### Task 2: Create FEMA GeoJSON parser

**Files:**
- Create: `pipelines/countyiq/lib/parsers/fema.py`
- Create: `pipelines/tests/fixtures/fema_flood_sample.geojson`
- Create: `pipelines/tests/test_fema_parser.py`

- [ ] **Step 1: Create test fixture**

Create `pipelines/tests/fixtures/fema_flood_sample.geojson` with 5 features:
1. AE zone with valid STATIC_BFE, DFIRM_ID present (SFHA_TF="T")
2. X zone with -9999 sentinels (SFHA_TF="F")
3. AE zone with ZONE_SUBTY="FLOODWAY" (SFHA_TF="T")
4. VE zone with valid DEPTH data
5. Feature with null geometry (annotation feature — edge case)

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[-76.38, 39.73], [-76.37, 39.73], [-76.37, 39.74], [-76.38, 39.74], [-76.38, 39.73]]]
      },
      "properties": {
        "DFIRM_ID": "42133C",
        "FLD_AR_ID": "42133C_5239",
        "FLD_ZONE": "AE",
        "ZONE_SUBTY": null,
        "SFHA_TF": "T",
        "STATIC_BFE": 450.5,
        "V_DATUM": "NAVD88",
        "DEPTH": -9999,
        "STUDY_TYP": "SFHAs WITH HIGH FLOOD RISK",
        "SOURCE_CIT": "42133C_STUDY1"
      }
    },
    {
      "type": "Feature",
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[-76.33, 39.73], [-76.32, 39.73], [-76.32, 39.74], [-76.33, 39.74], [-76.33, 39.73]]]
      },
      "properties": {
        "DFIRM_ID": "42133C",
        "FLD_AR_ID": "42133C_5240",
        "FLD_ZONE": "X",
        "ZONE_SUBTY": "0.2 PCT ANNUAL CHANCE FLOOD HAZARD",
        "SFHA_TF": "F",
        "STATIC_BFE": -9999,
        "V_DATUM": null,
        "DEPTH": -9999,
        "STUDY_TYP": "NOT APPLICABLE",
        "SOURCE_CIT": "42133C_STUDY1"
      }
    },
    {
      "type": "Feature",
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[-76.40, 39.75], [-76.39, 39.75], [-76.39, 39.76], [-76.40, 39.76], [-76.40, 39.75]]]
      },
      "properties": {
        "DFIRM_ID": "42133C",
        "FLD_AR_ID": "42133C_1001",
        "FLD_ZONE": "AE",
        "ZONE_SUBTY": "FLOODWAY",
        "SFHA_TF": "T",
        "STATIC_BFE": 520.0,
        "V_DATUM": "NAVD88",
        "DEPTH": -9999,
        "STUDY_TYP": "SFHAs WITH HIGH FLOOD RISK",
        "SOURCE_CIT": "42133C_STUDY2"
      }
    },
    {
      "type": "Feature",
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[-76.50, 39.80], [-76.49, 39.80], [-76.49, 39.81], [-76.50, 39.81], [-76.50, 39.80]]]
      },
      "properties": {
        "DFIRM_ID": "42133C",
        "FLD_AR_ID": "42133C_2001",
        "FLD_ZONE": "VE",
        "ZONE_SUBTY": null,
        "SFHA_TF": "T",
        "STATIC_BFE": 15.0,
        "V_DATUM": "NAVD88",
        "DEPTH": 3.5,
        "STUDY_TYP": "SFHAs WITH HIGH FLOOD RISK",
        "SOURCE_CIT": "42133C_STUDY3"
      }
    },
    {
      "type": "Feature",
      "geometry": null,
      "properties": {
        "DFIRM_ID": "42133C",
        "FLD_AR_ID": "42133C_9999",
        "FLD_ZONE": "X",
        "ZONE_SUBTY": null,
        "SFHA_TF": "F",
        "STATIC_BFE": -9999,
        "V_DATUM": null,
        "DEPTH": -9999,
        "STUDY_TYP": "NOT APPLICABLE",
        "SOURCE_CIT": "42133C_STUDY1"
      }
    }
  ],
  "exceededTransferLimit": true
}
```

- [ ] **Step 2: Write failing tests**

Create `pipelines/tests/test_fema_parser.py`:

```python
import json
from pathlib import Path

from countyiq.lib.parsers.fema import parse_fema_geojson, FEMA_SENTINEL

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_parse_returns_all_features():
    geojson = json.loads((FIXTURES_DIR / "fema_flood_sample.geojson").read_text())
    records = parse_fema_geojson(geojson)
    assert len(records) == 5


def test_parse_maps_columns_correctly():
    geojson = json.loads((FIXTURES_DIR / "fema_flood_sample.geojson").read_text())
    records = parse_fema_geojson(geojson)
    r = next(r for r in records if r["fld_ar_id"] == "42133C_5239")
    assert r["fld_zone"] == "AE"
    assert r["sfha_tf"] == "T"
    assert r["study_typ"] == "SFHAs WITH HIGH FLOOD RISK"
    assert r["source_cit"] == "42133C_STUDY1"
    assert r["static_bfe"] == 450.5
    assert r["v_datum"] == "NAVD88"
    assert r["dfirm_id"] == "42133C"


def test_parse_converts_sentinels_to_none():
    geojson = json.loads((FIXTURES_DIR / "fema_flood_sample.geojson").read_text())
    records = parse_fema_geojson(geojson)
    r = next(r for r in records if r["fld_ar_id"] == "42133C_5240")
    assert r["static_bfe"] is None
    assert r["depth"] is None
    assert r["fld_zone"] == "X"
    assert r["sfha_tf"] == "F"


def test_parse_preserves_valid_numeric_values():
    geojson = json.loads((FIXTURES_DIR / "fema_flood_sample.geojson").read_text())
    records = parse_fema_geojson(geojson)
    r = next(r for r in records if r["fld_ar_id"] == "42133C_2001")
    assert r["static_bfe"] == 15.0
    assert r["depth"] == 3.5
    assert r["fld_zone"] == "VE"


def test_parse_includes_geojson_geometry():
    geojson = json.loads((FIXTURES_DIR / "fema_flood_sample.geojson").read_text())
    records = parse_fema_geojson(geojson)
    r = next(r for r in records if r["fld_ar_id"] == "42133C_5239")
    assert "geojson" in r
    assert r["geojson"]["type"] == "Polygon"


def test_parse_handles_null_geometry():
    geojson = json.loads((FIXTURES_DIR / "fema_flood_sample.geojson").read_text())
    records = parse_fema_geojson(geojson)
    r = next(r for r in records if r["fld_ar_id"] == "42133C_9999")
    assert "geojson" not in r
    assert r["fld_zone"] == "X"


def test_parse_empty_feature_collection():
    geojson = {"type": "FeatureCollection", "features": []}
    records = parse_fema_geojson(geojson)
    assert records == []


def test_parse_skips_features_without_fld_ar_id():
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [[[-76.38, 39.73], [-76.37, 39.73], [-76.37, 39.74], [-76.38, 39.74], [-76.38, 39.73]]]},
                "properties": {"FLD_ZONE": "AE", "SFHA_TF": "T"},
            }
        ],
    }
    records = parse_fema_geojson(geojson)
    assert records == []


def test_sentinel_value():
    assert FEMA_SENTINEL == -9999
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd pipelines && source .venv/bin/activate && pytest tests/test_fema_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'countyiq.lib.parsers.fema'`

- [ ] **Step 4: Write parser implementation**

Create `pipelines/countyiq/lib/parsers/fema.py`:

```python
"""Parse FEMA NFHL GeoJSON features into staging.flood_zones records."""

FEMA_SENTINEL = -9999

# GeoJSON property → staging column name
COLUMN_MAP = {
    "DFIRM_ID": "dfirm_id",
    "FLD_AR_ID": "fld_ar_id",
    "FLD_ZONE": "fld_zone",
    "ZONE_SUBTY": "zone_subty",
    "SFHA_TF": "sfha_tf",
    "STATIC_BFE": "static_bfe",
    "V_DATUM": "v_datum",
    "DEPTH": "depth",
    "STUDY_TYP": "study_typ",
    "SOURCE_CIT": "source_cit",
}

# Numeric fields that use -9999 as "no data" sentinel
SENTINEL_FIELDS = {"STATIC_BFE", "DEPTH"}


def parse_fema_geojson(geojson: dict) -> list[dict]:
    """Parse a FEMA NFHL GeoJSON FeatureCollection into staging records.

    Args:
        geojson: Parsed GeoJSON dict (FeatureCollection from FEMA MapServer).

    Returns:
        List of dicts with staging column names + "geojson" key containing
        the raw geometry dict for PostGIS insertion via ST_GeomFromGeoJSON.
    """
    records = []
    for feature in geojson.get("features", []):
        props = feature.get("properties", {})

        # FLD_AR_ID is the primary key — skip if missing
        if not props.get("FLD_AR_ID"):
            continue

        record = {}
        for src_col, db_col in COLUMN_MAP.items():
            val = props.get(src_col)
            # Convert sentinel values to None
            if src_col in SENTINEL_FIELDS and val == FEMA_SENTINEL:
                val = None
            # Convert empty strings to None
            if isinstance(val, str) and not val.strip():
                val = None
            record[db_col] = val

        # Attach raw geometry for PostGIS insertion
        geom = feature.get("geometry")
        if geom:
            record["geojson"] = geom

        records.append(record)

    return records
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd pipelines && source .venv/bin/activate && pytest tests/test_fema_parser.py -v`
Expected: All 9 tests PASS

- [ ] **Step 6: Commit**

```bash
git add pipelines/countyiq/lib/parsers/fema.py pipelines/tests/fixtures/fema_flood_sample.geojson pipelines/tests/test_fema_parser.py
git commit -m "feat(fema): add FEMA NFHL GeoJSON parser with tests"
```

---

### Task 3: Alembic migration — add columns to staging.flood_zones

**Files:**
- Create: `pipelines/alembic/versions/003_add_fema_flood_columns.py`

The table already exists in migration 001 with: `fld_zone`, `zone_subty`, `sfha_tf`, `fld_ar_id`, `study_typ`, `geom`, `valid_from`, `valid_to`. This migration adds the extra FEMA fields.

- [ ] **Step 1: Create migration file**

Create `pipelines/alembic/versions/003_add_fema_flood_columns.py`:

```python
"""add fema flood zone columns

Revision ID: 003
Revises: 002
Create Date: 2026-03-21
"""
from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("flood_zones", sa.Column("dfirm_id", sa.Text), schema="staging")
    op.add_column("flood_zones", sa.Column("static_bfe", sa.Float), schema="staging")
    op.add_column("flood_zones", sa.Column("depth", sa.Float), schema="staging")
    op.add_column("flood_zones", sa.Column("v_datum", sa.Text), schema="staging")
    op.add_column("flood_zones", sa.Column("source_cit", sa.Text), schema="staging")
    op.create_index(
        "idx_flood_zones_dfirm",
        "flood_zones",
        ["dfirm_id"],
        schema="staging",
    )
    op.create_index(
        "idx_flood_zones_current",
        "flood_zones",
        ["fld_ar_id"],
        schema="staging",
        postgresql_where=sa.text("valid_to IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_flood_zones_current", table_name="flood_zones", schema="staging")
    op.drop_index("idx_flood_zones_dfirm", table_name="flood_zones", schema="staging")
    op.drop_column("flood_zones", "source_cit", schema="staging")
    op.drop_column("flood_zones", "v_datum", schema="staging")
    op.drop_column("flood_zones", "depth", schema="staging")
    op.drop_column("flood_zones", "static_bfe", schema="staging")
    op.drop_column("flood_zones", "dfirm_id", schema="staging")
```

- [ ] **Step 2: Start Docker Postgres and run migration**

Run:
```bash
cd pipelines && docker compose up -d postgres-test
export DATABASE_URL="postgresql://dagster_admin:localtest@localhost:5433/countyiq"
source .venv/bin/activate && alembic upgrade head
```
Expected: Migration 003 applies successfully.

- [ ] **Step 3: Verify columns exist**

Run:
```bash
PGPASSWORD=localtest psql -h localhost -p 5433 -U dagster_admin -d countyiq -c "\d staging.flood_zones"
```
Expected: Table shows `dfirm_id`, `static_bfe`, `depth`, `v_datum`, `source_cit` columns.

- [ ] **Step 4: Commit**

```bash
git add pipelines/alembic/versions/003_add_fema_flood_columns.py
git commit -m "feat(schema): add FEMA flood columns to staging.flood_zones"
```

---

### Task 4: Create FEMA flood asset + asset checks

**Files:**
- Create: `pipelines/countyiq/assets/bulk/fema_flood.py`

Note: `bulk/__init__.py` does NOT need modification. Dagster's `load_assets_from_package_module` auto-discovers `@asset` and `@asset_check` decorators by walking the package tree, consistent with how PLCB is loaded (its `__init__.py` is empty).

- [ ] **Step 1: Write the asset module**

Create `pipelines/countyiq/assets/bulk/fema_flood.py`:

```python
"""FEMA NFHL flood hazard zones → staging.flood_zones.

Source: FEMA National Flood Hazard Layer (NFHL) MapServer
Layer 28: S_Fld_Haz_Ar (Flood Hazard Zones)
Records: ~5,238 polygons for York County (DFIRM_ID=42133C)
Schedule: Weekly (Sunday 04:00)
"""

import json

import requests
from psycopg2.extras import execute_batch
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
from countyiq.lib.parsers.fema import parse_fema_geojson
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

PAGE_SIZE = 2000
REQUEST_TIMEOUT = 120

KEY_COLUMNS = ["fld_ar_id"]
VALUE_COLUMNS = [
    "dfirm_id",
    "fld_zone",
    "zone_subty",
    "sfha_tf",
    "static_bfe",
    "v_datum",
    "depth",
    "study_typ",
    "source_cit",
]

# Expected fields from FEMA MapServer layer metadata (for schema drift check)
EXPECTED_FIELDS = {
    "DFIRM_ID", "FLD_AR_ID", "FLD_ZONE", "ZONE_SUBTY", "SFHA_TF",
    "STATIC_BFE", "V_DATUM", "DEPTH", "STUDY_TYP", "SOURCE_CIT",
}


def _fetch_all_pages(base_url: str, layer_id: int, dfirm_id: str, context) -> dict:
    """Paginate through FEMA MapServer and return a merged GeoJSON FeatureCollection."""
    all_features = []
    offset = 0
    while True:
        url = (
            f"{base_url}/{layer_id}/query"
            f"?where=DFIRM_ID%3D%27{dfirm_id}%27"
            f"&outFields=*"
            f"&outSR=4326"
            f"&resultRecordCount={PAGE_SIZE}"
            f"&resultOffset={offset}"
            f"&f=geojson"
        )
        context.log.info(f"Fetching page at offset {offset}")
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        page = resp.json()
        features = page.get("features", [])
        all_features.extend(features)
        context.log.info(f"  Got {len(features)} features (total: {len(all_features)})")

        if not page.get("exceededTransferLimit"):
            break
        offset += PAGE_SIZE

    return {"type": "FeatureCollection", "features": all_features}


@asset(
    group_name="bulk",
    description="FEMA NFHL flood hazard zones → staging.flood_zones",
    kinds={"postgres", "geojson"},
)
def fema_flood_zones(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Fetch FEMA flood zone polygons, parse, and SCD2 upsert."""

    county = get_county_config()

    # 1. Fetch all pages from FEMA MapServer
    geojson = _fetch_all_pages(
        county.fema_nfhl_url,
        county.fema_flood_layer,
        county.fema_dfirm_id,
        context,
    )
    context.log.info(f"Total features fetched: {len(geojson['features'])}")

    # 2. Archive raw GeoJSON to S3
    s3.archive(
        f"{county.s3_prefix}/bulk/fema_flood",
        geojson,
        filename="flood_zones.geojson",
    )

    # 3. Parse features
    records = parse_fema_geojson(geojson)
    context.log.info(f"Parsed {len(records)} flood zone records")

    if not records:
        context.log.warning("No flood zone records parsed — skipping upsert")
        return MaterializeResult(metadata={"record_count": MetadataValue.int(0)})

    # 3b. Truncation guard
    if len(records) < county.fema_min_records:
        raise RuntimeError(
            f"Only {len(records)} flood zone records parsed "
            f"(expected >= {county.fema_min_records}). "
            f"Possible truncated response — aborting."
        )

    # 4. Upsert with PostGIS geometry handling (scoped to this county's DFIRM)
    cur = database.cursor()
    try:
        stats = _geom_scd2_upsert(cur, records, dfirm_id=county.fema_dfirm_id)
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


def _geom_scd2_upsert(cursor, records: list[dict], dfirm_id: str) -> dict:
    """SCD2 upsert with PostGIS geometry support, scoped by DFIRM ID.

    Uses the same expire/insert pattern as lib/scd.py but handles
    geometry via ST_SetSRID(ST_Multi(ST_GeomFromGeoJSON()), 4326).
    Uses execute_batch for performance with 5K+ geometry rows.

    The expire query is scoped to dfirm_id so that running for one county
    does not expire another county's records in the same table.
    """
    conn = cursor.connection
    was_autocommit = conn.autocommit
    if was_autocommit:
        conn.autocommit = False

    try:
        all_cols = KEY_COLUMNS + VALUE_COLUMNS
        fqn = "staging.flood_zones"

        # Create temp table
        cursor.execute("DROP TABLE IF EXISTS _tmp_flood_zones")
        cursor.execute(f"CREATE TEMP TABLE _tmp_flood_zones (LIKE {fqn} INCLUDING DEFAULTS)")

        # Bulk insert into temp table with geometry — execute_batch for performance
        insert_sql = f"""
            INSERT INTO _tmp_flood_zones ({', '.join(all_cols)}, geom)
            VALUES ({', '.join(['%s'] * len(all_cols))},
                    ST_SetSRID(ST_Multi(ST_GeomFromGeoJSON(%s)), 4326))
        """
        rows = []
        for rec in records:
            row = [rec.get(c) for c in all_cols]
            geom = rec.get("geojson")
            row.append(json.dumps(geom) if geom else None)
            rows.append(row)
        execute_batch(cursor, insert_sql, rows, page_size=500)

        # Expire changed/deleted — scoped to this county's DFIRM ID
        key_join = "c.fld_ar_id = t.fld_ar_id"
        value_diff = " OR ".join(
            f"c.{v}::text IS DISTINCT FROM t.{v}::text" for v in VALUE_COLUMNS
        )
        cursor.execute(f"""
            UPDATE {fqn} c SET valid_to = NOW()
            WHERE c.valid_to IS NULL
            AND c.dfirm_id = %s
            AND (
                EXISTS (
                    SELECT 1 FROM _tmp_flood_zones t
                    WHERE {key_join} AND ({value_diff})
                )
                OR NOT EXISTS (
                    SELECT 1 FROM _tmp_flood_zones t WHERE {key_join}
                )
            )
        """, (dfirm_id,))
        expired = cursor.rowcount

        # Insert new/changed
        col_list = ', '.join(all_cols)
        cursor.execute(f"""
            INSERT INTO {fqn} ({col_list}, geom, valid_from)
            SELECT {', '.join(f't.{c}' for c in all_cols)}, t.geom, NOW()
            FROM _tmp_flood_zones t
            WHERE NOT EXISTS (
                SELECT 1 FROM {fqn} c
                WHERE c.valid_to IS NULL AND {key_join}
            )
        """)
        inserted = cursor.rowcount

        cursor.execute("DROP TABLE IF EXISTS _tmp_flood_zones")
        conn.commit()

        if was_autocommit:
            conn.autocommit = True

        unchanged = len(records) - inserted
        return {"inserted": inserted, "expired": expired, "unchanged": unchanged}
    except Exception:
        conn.rollback()
        if was_autocommit:
            conn.autocommit = True
        raise


@asset_check(asset=fema_flood_zones)
def fema_record_count_nonzero(database: DatabaseResource) -> AssetCheckResult:
    """Verify staging.flood_zones has at least one current record."""
    result = database.execute(
        "SELECT COUNT(*) FROM staging.flood_zones WHERE valid_to IS NULL"
    )
    count = result[0][0] if result else 0
    return AssetCheckResult(
        passed=count > 0,
        severity=AssetCheckSeverity.ERROR,
        metadata={"current_record_count": MetadataValue.int(count)},
    )


@asset_check(asset=fema_flood_zones)
def fema_schema_drift() -> AssetCheckResult:
    """Verify FEMA MapServer still has the expected fields."""
    county = get_county_config()
    try:
        url = f"{county.fema_nfhl_url}/{county.fema_flood_layer}?f=json"
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        layer_meta = resp.json()
        actual_fields = {f["name"] for f in layer_meta.get("fields", [])}
        missing = EXPECTED_FIELDS - actual_fields
        extra = actual_fields - EXPECTED_FIELDS
        return AssetCheckResult(
            passed=len(missing) == 0,
            severity=AssetCheckSeverity.WARN,
            metadata={
                "missing_fields": MetadataValue.text(str(missing) if missing else "none"),
                "extra_fields": MetadataValue.text(str(extra) if extra else "none"),
            },
        )
    except requests.exceptions.RequestException as e:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.WARN,
            metadata={"error": MetadataValue.text(f"Network error: {e}")},
        )
```

- [ ] **Step 2: Verify Dagster can load definitions**

Run: `cd pipelines && source .venv/bin/activate && dagster definitions validate -m countyiq.definitions`
Expected: Definitions valid. `fema_flood_zones` appears in asset list.

- [ ] **Step 3: Commit**

```bash
git add pipelines/countyiq/assets/bulk/fema_flood.py
git commit -m "feat(fema): add FEMA flood zones Dagster asset with checks"
```

---

### Task 5: Add weekly schedule (Sunday 4 AM)

**Files:**
- Modify: `pipelines/countyiq/jobs/__init__.py`
- Modify: `pipelines/countyiq/schedules/__init__.py`
- Modify: `pipelines/countyiq/definitions.py`

- [ ] **Step 1: Add FEMA job**

Modify `pipelines/countyiq/jobs/__init__.py` — add at the end:

```python
fema_refresh = define_asset_job(
    name="fema_refresh",
    selection=AssetSelection.assets("fema_flood_zones"),
    description="Refresh FEMA flood hazard zone data",
)
```

- [ ] **Step 2: Add FEMA schedule**

Modify `pipelines/countyiq/schedules/__init__.py`:

Update the import line:
```python
from countyiq.jobs import arcgis_refresh, scraper_refresh, bulk_refresh, fema_refresh
```

Add to `all_schedules` list:
```python
    ScheduleDefinition(
        job=fema_refresh,
        cron_schedule="0 4 * * 0",  # Sunday 04:00
        name="weekly_fema",
    ),
```

- [ ] **Step 3: Register job in definitions.py**

Modify `pipelines/countyiq/definitions.py`:

Update the import line:
```python
from countyiq.jobs import arcgis_refresh, scraper_refresh, bulk_refresh, enrichment_refresh, fema_refresh
```

Update the jobs list:
```python
    jobs=[arcgis_refresh, scraper_refresh, bulk_refresh, enrichment_refresh, fema_refresh],
```

- [ ] **Step 4: Verify definitions still load**

Run: `cd pipelines && source .venv/bin/activate && dagster definitions validate -m countyiq.definitions`
Expected: Definitions valid with `weekly_fema` schedule.

- [ ] **Step 5: Commit**

```bash
git add pipelines/countyiq/jobs/__init__.py pipelines/countyiq/schedules/__init__.py pipelines/countyiq/definitions.py
git commit -m "feat(fema): add weekly Sunday 4 AM schedule for FEMA flood zones"
```

---

### Task 6: Local integration test

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
dagster asset materialize --select fema_flood_zones -m countyiq.definitions
```

Expected: Asset materializes successfully. Logs show ~3 pages fetched, ~5,238 records parsed and inserted.

- [ ] **Step 3: Verify data in Postgres**

```bash
PGPASSWORD=localtest psql -h localhost -p 5433 -U dagster_admin -d countyiq -c "
  SELECT fld_zone, sfha_tf, COUNT(*), COUNT(static_bfe) AS has_bfe
  FROM staging.flood_zones
  WHERE valid_to IS NULL
  GROUP BY fld_zone, sfha_tf
  ORDER BY count DESC;
"
```

Expected: Multiple flood zone types (A, AE, X, etc.) with record counts summing to ~5,238.

- [ ] **Step 4: Verify geometry is valid**

```bash
PGPASSWORD=localtest psql -h localhost -p 5433 -U dagster_admin -d countyiq -c "
  SELECT COUNT(*), COUNT(geom) AS has_geom, ST_SRID(geom) AS srid
  FROM staging.flood_zones
  WHERE valid_to IS NULL
  GROUP BY ST_SRID(geom);
"
```

Expected: All records have geometry, SRID = 4326.

- [ ] **Step 5: Run all tests**

```bash
cd pipelines && source .venv/bin/activate && pytest tests/ -v
```

Expected: All tests pass (existing + new FEMA parser tests).
