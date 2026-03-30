# GIS Layers (Zoning, Roads, Structures) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Dagster pipelines for three additional York County GIS layers (Zoning, Roads, Building Footprints) using the same ArcGIS REST pattern as the existing parcels pipeline, with SCD2 upsert and geometry support.

**Architecture:** Each layer follows the parcels pattern: `query_all_features()` → S3 archive → parse → SCD2 upsert with PostGIS geometry. Parsers map ArcGIS field names to lowercase staging columns. A new `gis_layers_refresh` job groups these assets separately from parcels (which stays on Monday 2 AM), scheduled for Sunday 2 AM.

**Tech Stack:** Dagster assets, ArcGIS REST API (`arcweb1.ycpc.org`), psycopg2 + PostGIS, Alembic migrations, pytest

**Conflict note:** Another agent is concurrently working on phase 3 source 3 (FEMA). Avoid modifying shared files (`county_config.py`, `schedules/__init__.py`, `jobs/__init__.py`, `definitions.py`) until that agent's work is committed. If migration `004` already exists when you reach Task 2, use `005` instead.

---

## ArcGIS API Field Inventories (from live queries 2026-03-21)

### Zoning — 1,694 records, esriGeometryPolygon
| ArcGIS Field | Type | → staging.zoning column |
|---|---|---|
| ZRECID | Integer | `zrecid` (PK) |
| MUNI_NAME | String(50) | `muni_name` |
| DISTRICT | String(2) | `district` |
| ZCODE | String(5) | `zcode` |
| ZNAME | String(50) | `zname` |
| ZTYPE | String(1) | `ztype` |
| GEN_ZCODE | String(5) | `gen_zcode` |
| GEN_ZNAME | String(50) | `gen_zname` |
| CHANGETYPE | String(255) | `changetype` |
| PRJ_NUM | String(7) | `prj_num` |
| MUNI_ORD | String(12) | `muni_ord` |
| ADPT_DATE | Date | `adpt_date` |
| PREV_ZCODE | String(8) | `prev_zcode` |
| PREV_ZNAME | String(50) | `prev_zname` |
| *Skipped:* OBJECTID, GlobalID, JOIN_FIELD, HTML_COLOR, CREATE_DATE, MODIFY_DATE, EDIT_NAME, EDIT_TYPE, Shape__Area, Shape__Length ||

### Roads — 33,748 records, esriGeometryPolyline
| ArcGIS Field | Type | → staging.roads column |
|---|---|---|
| RCL_NGUID | String(254) | `rcl_nguid` (PK) |
| StreetName | String(60) | `street_name` |
| St_PreDir | String(9) | `st_pre_dir` |
| St_PreTyp | String(50) | `st_pre_typ` |
| St_PosTyp | String(50) | `st_pos_typ` |
| St_PosDir | String(20) | `st_pos_dir` |
| RoadClass | String(15) | `road_class` |
| SpeedLimit | SmallInteger | `speed_limit` |
| OneWay | String(2) | `one_way` |
| RTE_NUM | String(5) | `rte_num` |
| FromAddr_L | SmallInteger | `from_addr_l` |
| ToAddr_L | SmallInteger | `to_addr_l` |
| FromAddr_R | SmallInteger | `from_addr_r` |
| ToAddr_R | SmallInteger | `to_addr_r` |
| IncMuni_L | String(100) | `inc_muni_l` |
| IncMuni_R | String(100) | `inc_muni_r` |
| PostCode_L | String(7) | `post_code_l` |
| PostCode_R | String(7) | `post_code_r` |
| *Skipped:* OBJECTID, Source, DateUpdate, Effective, Expire, AdNumPre_L/R, Parity_L/R, St_PreMod/Sep/PosMod, LSt_* (legacy), MSAGComm_*, Country_*, State_*, County_*, AddCode_*, UnincCom_*, NbrhdCom_*, PostComm_*, Valid_L/R, L_DISTRICT/R_DISTRICT, TRAVEL_TIME, Z_VALUE, JOIN_ID, EDIT_*, PRETYPE, STDIR, STSUF, STTYPE, RDNAME, GC_Exception, Shape__Length ||

### Structures (BLDG_Footprint) — 213,041 records, esriGeometryPolygon
| ArcGIS Field | Type | → staging.structures column |
|---|---|---|
| INDEX_ | String(20) | `index_id` (PK) |
| BUILDING_TYPE | String(512) | `building_type` |
| *Skipped:* OBJECTID, CREATE_DATE, MODIFY_DATE, EDIT_NAME, EDIT_TYPE, Shape__Area, Shape__Length ||

---

## File Structure

### New Files
| File | Responsibility |
|---|---|
| `pipelines/countyiq/lib/parsers/zoning.py` | Map ArcGIS zoning fields → staging columns |
| `pipelines/countyiq/lib/parsers/roads.py` | Map ArcGIS roads fields → staging columns |
| `pipelines/countyiq/lib/parsers/structures.py` | Map ArcGIS structures fields → staging columns |
| `pipelines/countyiq/assets/arcgis/zoning.py` | Zoning asset + asset checks |
| `pipelines/countyiq/assets/arcgis/roads.py` | Roads asset + asset checks |
| `pipelines/countyiq/assets/arcgis/structures.py` | Structures asset + asset checks |
| `pipelines/alembic/versions/004_gis_layers.py` | Migration: staging.zoning, staging.roads, staging.structures |
| `pipelines/tests/fixtures/zoning_sample.json` | 2 sample ArcGIS features |
| `pipelines/tests/fixtures/roads_sample.json` | 2 sample ArcGIS features |
| `pipelines/tests/fixtures/structures_sample.json` | 2 sample ArcGIS features |
| `pipelines/tests/test_zoning_parser.py` | Parser unit tests |
| `pipelines/tests/test_roads_parser.py` | Parser unit tests |
| `pipelines/tests/test_structures_parser.py` | Parser unit tests |

### Modified Files
| File | Change |
|---|---|
| `pipelines/countyiq/lib/county_config.py` | Add 6 new fields: URLs + min_records for each layer |
| `pipelines/countyiq/jobs/__init__.py` | Add `gis_layers_refresh` job |
| `pipelines/countyiq/schedules/__init__.py` | Add `weekly_gis_layers` schedule (Sunday 02:00) |
| `pipelines/countyiq/definitions.py` | Import + register new job |

---

### Task 1: Update County Config

**Files:**
- Modify: `pipelines/countyiq/lib/county_config.py`

- [ ] **Step 1: Add config fields to CountyConfig dataclass**

Add after the existing `arcgis_base_url` field:

```python
# ArcGIS GIS layers (Source 1: additional layers beyond parcels)
arcgis_zoning_url: str = ""
arcgis_roads_url: str = ""
arcgis_structures_url: str = ""
arcgis_zoning_min_records: int = 100
arcgis_roads_min_records: int = 1000
arcgis_structures_min_records: int = 10000
```

- [ ] **Step 2: Add York County values to COUNTY_CONFIGS**

Add after `arcgis_base_url` value in the York config:

```python
arcgis_zoning_url="https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/Zoning/FeatureServer/0",
arcgis_roads_url="https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/Roads/FeatureServer/0",
arcgis_structures_url="https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/BLDG_Footprint/FeatureServer/0",
arcgis_zoning_min_records=500,
arcgis_roads_min_records=10000,
arcgis_structures_min_records=100000,
```

- [ ] **Step 3: Verify config loads**

Run: `cd pipelines && source .venv/bin/activate && python3 -c "from countyiq.lib.county_config import get_county_config; c = get_county_config(); print(c.arcgis_zoning_url)"`
Expected: `https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/Zoning/FeatureServer/0`

- [ ] **Step 4: Commit**

```bash
git add pipelines/countyiq/lib/county_config.py
git commit -m "feat(config): add ArcGIS zoning, roads, structures URLs to county config"
```

---

### Task 2: Alembic Migration for Three Staging Tables

**Files:**
- Create: `pipelines/alembic/versions/004_gis_layers.py`

**Pre-check:** Verify no migration `004` exists (another agent may have created one). If `004` exists, use `005` and set `down_revision = "004"`.

- [ ] **Step 1: Write migration file**

```python
"""staging tables for GIS layers: zoning, roads, structures

Revision ID: 004
Revises: 003
Create Date: 2026-03-21
"""
from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- staging.zoning (Source 1: GIS Portal — Zoning layer) ---
    op.create_table(
        "zoning",
        sa.Column("zrecid", sa.Integer, nullable=False),
        sa.Column("muni_name", sa.String(50)),
        sa.Column("district", sa.String(2)),
        sa.Column("zcode", sa.String(5)),
        sa.Column("zname", sa.String(50)),
        sa.Column("ztype", sa.String(1)),
        sa.Column("gen_zcode", sa.String(5)),
        sa.Column("gen_zname", sa.String(50)),
        sa.Column("changetype", sa.String(255)),
        sa.Column("prj_num", sa.String(7)),
        sa.Column("muni_ord", sa.String(12)),
        sa.Column("adpt_date", sa.DateTime(timezone=True)),
        sa.Column("prev_zcode", sa.String(8)),
        sa.Column("prev_zname", sa.String(50)),
        sa.Column("valid_from", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("zrecid", "valid_from"),
        schema="staging",
    )
    op.execute("SELECT AddGeometryColumn('staging', 'zoning', 'geom', 4326, 'MULTIPOLYGON', 2)")
    op.create_index("idx_zoning_geom", "zoning", ["geom"], schema="staging", postgresql_using="gist")
    op.create_index("idx_zoning_muni", "zoning", ["muni_name"], schema="staging")
    op.create_index("idx_zoning_current", "zoning", ["zrecid"], schema="staging",
                     postgresql_where=sa.text("valid_to IS NULL"))

    # --- staging.roads (Source 1: GIS Portal — Roads layer) ---
    op.create_table(
        "roads",
        sa.Column("rcl_nguid", sa.String(254), nullable=False),
        sa.Column("street_name", sa.String(60)),
        sa.Column("st_pre_dir", sa.String(9)),
        sa.Column("st_pre_typ", sa.String(50)),
        sa.Column("st_pos_typ", sa.String(50)),
        sa.Column("st_pos_dir", sa.String(20)),
        sa.Column("road_class", sa.String(15)),
        sa.Column("speed_limit", sa.SmallInteger),
        sa.Column("one_way", sa.String(2)),
        sa.Column("rte_num", sa.String(5)),
        sa.Column("from_addr_l", sa.SmallInteger),
        sa.Column("to_addr_l", sa.SmallInteger),
        sa.Column("from_addr_r", sa.SmallInteger),
        sa.Column("to_addr_r", sa.SmallInteger),
        sa.Column("inc_muni_l", sa.String(100)),
        sa.Column("inc_muni_r", sa.String(100)),
        sa.Column("post_code_l", sa.String(7)),
        sa.Column("post_code_r", sa.String(7)),
        sa.Column("valid_from", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("rcl_nguid", "valid_from"),
        schema="staging",
    )
    op.execute("SELECT AddGeometryColumn('staging', 'roads', 'geom', 4326, 'MULTILINESTRING', 2)")
    op.create_index("idx_roads_centerline_geom", "roads", ["geom"], schema="staging", postgresql_using="gist")
    op.create_index("idx_roads_street", "roads", ["street_name"], schema="staging")
    op.create_index("idx_roads_current", "roads", ["rcl_nguid"], schema="staging",
                     postgresql_where=sa.text("valid_to IS NULL"))

    # --- staging.structures (Source 1: GIS Portal — BLDG_Footprint layer) ---
    op.create_table(
        "structures",
        sa.Column("index_id", sa.String(20), nullable=False),
        sa.Column("building_type", sa.String(512)),
        sa.Column("valid_from", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("index_id", "valid_from"),
        schema="staging",
    )
    op.execute("SELECT AddGeometryColumn('staging', 'structures', 'geom', 4326, 'MULTIPOLYGON', 2)")
    op.create_index("idx_structures_geom", "structures", ["geom"], schema="staging", postgresql_using="gist")
    op.create_index("idx_structures_type", "structures", ["building_type"], schema="staging")
    op.create_index("idx_structures_current", "structures", ["index_id"], schema="staging",
                     postgresql_where=sa.text("valid_to IS NULL"))


def downgrade() -> None:
    op.drop_table("structures", schema="staging")
    op.drop_table("roads", schema="staging")
    op.drop_table("zoning", schema="staging")
```

- [ ] **Step 2: Start Docker Postgres**

Run: `cd pipelines && docker compose up -d postgres-test`

- [ ] **Step 3: Apply migration**

Run: `cd pipelines && source .venv/bin/activate && DATABASE_URL="postgresql://dagster_admin:localtest@localhost:5433/countyiq" alembic upgrade head`
Expected: `INFO  [alembic.runtime.migration] Running upgrade 003 -> 004, staging tables for GIS layers: zoning, roads, structures`

- [ ] **Step 4: Verify tables exist**

Run: `PGPASSWORD=localtest psql -h localhost -p 5433 -U dagster_admin -d countyiq -c "SELECT table_name FROM information_schema.tables WHERE table_schema = 'staging' AND table_name IN ('zoning', 'roads', 'structures') ORDER BY table_name;"`
Expected: 3 rows (roads, structures, zoning)

- [ ] **Step 5: Commit**

```bash
git add pipelines/alembic/versions/004_gis_layers.py
git commit -m "feat(schema): add staging.zoning, staging.roads, staging.structures tables"
```

---

### Task 3: Zoning Parser + Tests

**Files:**
- Create: `pipelines/countyiq/lib/parsers/zoning.py`
- Create: `pipelines/tests/fixtures/zoning_sample.json`
- Create: `pipelines/tests/test_zoning_parser.py`

- [ ] **Step 1: Save test fixture**

Fetch 2 real records from the API and save as fixture:

```bash
cd pipelines && curl -s "https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/Zoning/FeatureServer/0/query?where=1%3D1&outFields=*&resultRecordCount=2&outSR=4326&f=json" | python3 -m json.tool > tests/fixtures/zoning_sample.json
```

- [ ] **Step 2: Write parser**

```python
"""Parser for ArcGIS Zoning FeatureServer response.

Maps ArcGIS field names to staging.zoning column names.
"""


FIELD_MAP = {
    "ZRECID": "zrecid",
    "MUNI_NAME": "muni_name",
    "DISTRICT": "district",
    "ZCODE": "zcode",
    "ZNAME": "zname",
    "ZTYPE": "ztype",
    "GEN_ZCODE": "gen_zcode",
    "GEN_ZNAME": "gen_zname",
    "CHANGETYPE": "changetype",
    "PRJ_NUM": "prj_num",
    "MUNI_ORD": "muni_ord",
    "PREV_ZCODE": "prev_zcode",
    "PREV_ZNAME": "prev_zname",
}


def parse_zoning_features(raw_features: list[dict]) -> list[dict]:
    """Parse ArcGIS Zoning features into staging.zoning records.

    Args:
        raw_features: ArcGIS feature dicts with 'attributes' key.

    Returns:
        List of flat dicts with staging.zoning column names.
    """
    records = []
    for feat in raw_features:
        attrs = feat.get("attributes", {})
        zrecid = attrs.get("ZRECID")
        if zrecid is None:
            continue

        record = {}
        for src, dest in FIELD_MAP.items():
            val = attrs.get(src)
            record[dest] = str(val) if val is not None and val != "" else None

        # Keep zrecid as int (not string)
        record["zrecid"] = zrecid

        # ADPT_DATE comes as epoch milliseconds from ArcGIS
        adpt_raw = attrs.get("ADPT_DATE")
        if adpt_raw and isinstance(adpt_raw, (int, float)):
            from datetime import datetime, timezone
            record["adpt_date"] = datetime.fromtimestamp(adpt_raw / 1000, tz=timezone.utc).isoformat()
        else:
            record["adpt_date"] = None

        records.append(record)

    return records
```

- [ ] **Step 3: Write test**

```python
"""Tests for zoning parser."""

import json
import pathlib

from countyiq.lib.parsers.zoning import parse_zoning_features

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "zoning_sample.json"


def test_parse_zoning_returns_records():
    raw = json.loads(FIXTURE.read_text())
    records = parse_zoning_features(raw["features"])
    assert len(records) > 0


def test_parse_zoning_field_mapping():
    raw = json.loads(FIXTURE.read_text())
    records = parse_zoning_features(raw["features"])
    rec = records[0]
    assert "zrecid" in rec
    assert "muni_name" in rec
    assert "zcode" in rec
    assert "zname" in rec
    assert "ztype" in rec
    assert "gen_zcode" in rec
    # Should not contain raw ArcGIS field names
    assert "ZRECID" not in rec
    assert "MUNI_NAME" not in rec


def test_parse_zoning_skips_missing_key():
    features = [{"attributes": {"ZCODE": "R1"}}]  # no ZRECID
    records = parse_zoning_features(features)
    assert len(records) == 0


def test_parse_zoning_empty_string_to_none():
    features = [{"attributes": {"ZRECID": 1, "ZCODE": ""}}]
    records = parse_zoning_features(features)
    assert records[0]["zcode"] is None
```

- [ ] **Step 4: Run tests**

Run: `cd pipelines && source .venv/bin/activate && python3 -m pytest tests/test_zoning_parser.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add pipelines/countyiq/lib/parsers/zoning.py pipelines/tests/fixtures/zoning_sample.json pipelines/tests/test_zoning_parser.py
git commit -m "feat(parser): add zoning parser with tests"
```

---

### Task 4: Roads Parser + Tests

**Files:**
- Create: `pipelines/countyiq/lib/parsers/roads.py`
- Create: `pipelines/tests/fixtures/roads_sample.json`
- Create: `pipelines/tests/test_roads_parser.py`

- [ ] **Step 1: Save test fixture**

```bash
cd pipelines && curl -s "https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/Roads/FeatureServer/0/query?where=1%3D1&outFields=*&resultRecordCount=2&outSR=4326&f=json" | python3 -m json.tool > tests/fixtures/roads_sample.json
```

- [ ] **Step 2: Write parser**

```python
"""Parser for ArcGIS Roads FeatureServer response.

Maps ArcGIS field names to staging.roads column names.
"""


FIELD_MAP = {
    "RCL_NGUID": "rcl_nguid",
    "StreetName": "street_name",
    "St_PreDir": "st_pre_dir",
    "St_PreTyp": "st_pre_typ",
    "St_PosTyp": "st_pos_typ",
    "St_PosDir": "st_pos_dir",
    "RoadClass": "road_class",
    "SpeedLimit": "speed_limit",
    "OneWay": "one_way",
    "RTE_NUM": "rte_num",
    "FromAddr_L": "from_addr_l",
    "ToAddr_L": "to_addr_l",
    "FromAddr_R": "from_addr_r",
    "ToAddr_R": "to_addr_r",
    "IncMuni_L": "inc_muni_l",
    "IncMuni_R": "inc_muni_r",
    "PostCode_L": "post_code_l",
    "PostCode_R": "post_code_r",
}

# Fields that should stay as integers, not stringified
INT_FIELDS = {"speed_limit", "from_addr_l", "to_addr_l", "from_addr_r", "to_addr_r"}


def parse_roads_features(raw_features: list[dict]) -> list[dict]:
    """Parse ArcGIS Roads features into staging.roads records.

    Args:
        raw_features: ArcGIS feature dicts with 'attributes' key.

    Returns:
        List of flat dicts with staging.roads column names.
    """
    records = []
    for feat in raw_features:
        attrs = feat.get("attributes", {})
        rcl_nguid = attrs.get("RCL_NGUID")
        if not rcl_nguid:
            continue

        record = {}
        for src, dest in FIELD_MAP.items():
            val = attrs.get(src)
            if val is None or val == "":
                record[dest] = None
            elif dest in INT_FIELDS:
                record[dest] = val  # keep as int
            else:
                record[dest] = str(val)

        records.append(record)

    return records
```

- [ ] **Step 3: Write test**

```python
"""Tests for roads parser."""

import json
import pathlib

from countyiq.lib.parsers.roads import parse_roads_features

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "roads_sample.json"


def test_parse_roads_returns_records():
    raw = json.loads(FIXTURE.read_text())
    records = parse_roads_features(raw["features"])
    assert len(records) > 0


def test_parse_roads_field_mapping():
    raw = json.loads(FIXTURE.read_text())
    records = parse_roads_features(raw["features"])
    rec = records[0]
    assert "rcl_nguid" in rec
    assert "street_name" in rec
    assert "road_class" in rec
    assert "speed_limit" in rec
    assert "inc_muni_l" in rec
    # Raw ArcGIS names absent
    assert "RCL_NGUID" not in rec
    assert "StreetName" not in rec


def test_parse_roads_skips_missing_key():
    features = [{"attributes": {"StreetName": "MAIN"}}]  # no RCL_NGUID
    records = parse_roads_features(features)
    assert len(records) == 0


def test_parse_roads_preserves_int_fields():
    features = [{"attributes": {"RCL_NGUID": "abc-123", "SpeedLimit": 35, "FromAddr_L": 100}}]
    records = parse_roads_features(features)
    assert records[0]["speed_limit"] == 35
    assert records[0]["from_addr_l"] == 100
```

- [ ] **Step 4: Run tests**

Run: `cd pipelines && source .venv/bin/activate && python3 -m pytest tests/test_roads_parser.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add pipelines/countyiq/lib/parsers/roads.py pipelines/tests/fixtures/roads_sample.json pipelines/tests/test_roads_parser.py
git commit -m "feat(parser): add roads parser with tests"
```

---

### Task 5: Structures Parser + Tests

**Files:**
- Create: `pipelines/countyiq/lib/parsers/structures.py`
- Create: `pipelines/tests/fixtures/structures_sample.json`
- Create: `pipelines/tests/test_structures_parser.py`

- [ ] **Step 1: Save test fixture**

```bash
cd pipelines && curl -s "https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/BLDG_Footprint/FeatureServer/0/query?where=1%3D1&outFields=*&resultRecordCount=2&outSR=4326&f=json" | python3 -m json.tool > tests/fixtures/structures_sample.json
```

- [ ] **Step 2: Write parser**

```python
"""Parser for ArcGIS BLDG_Footprint FeatureServer response.

Maps ArcGIS field names to staging.structures column names.
"""


def parse_structures_features(raw_features: list[dict]) -> list[dict]:
    """Parse ArcGIS Building Footprint features into staging.structures records.

    Args:
        raw_features: ArcGIS feature dicts with 'attributes' key.

    Returns:
        List of flat dicts with staging.structures column names.
    """
    records = []
    for feat in raw_features:
        attrs = feat.get("attributes", {})
        index_id = attrs.get("INDEX_")
        if not index_id:
            continue

        record = {
            "index_id": str(index_id),
            "building_type": str(attrs["BUILDING_TYPE"]) if attrs.get("BUILDING_TYPE") else None,
        }
        records.append(record)

    return records
```

- [ ] **Step 3: Write test**

```python
"""Tests for structures parser."""

import json
import pathlib

from countyiq.lib.parsers.structures import parse_structures_features

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "structures_sample.json"


def test_parse_structures_returns_records():
    raw = json.loads(FIXTURE.read_text())
    records = parse_structures_features(raw["features"])
    assert len(records) > 0


def test_parse_structures_field_mapping():
    raw = json.loads(FIXTURE.read_text())
    records = parse_structures_features(raw["features"])
    rec = records[0]
    assert "index_id" in rec
    assert "building_type" in rec
    assert "INDEX_" not in rec


def test_parse_structures_skips_missing_key():
    features = [{"attributes": {"BUILDING_TYPE": "Main Living Quarters"}}]
    records = parse_structures_features(features)
    assert len(records) == 0


def test_parse_structures_null_building_type():
    features = [{"attributes": {"INDEX_": "123", "BUILDING_TYPE": None}}]
    records = parse_structures_features(features)
    assert records[0]["building_type"] is None
```

- [ ] **Step 4: Run tests**

Run: `cd pipelines && source .venv/bin/activate && python3 -m pytest tests/test_structures_parser.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add pipelines/countyiq/lib/parsers/structures.py pipelines/tests/fixtures/structures_sample.json pipelines/tests/test_structures_parser.py
git commit -m "feat(parser): add structures parser with tests"
```

---

### Task 6: Zoning Asset + Checks

**Files:**
- Create: `pipelines/countyiq/assets/arcgis/zoning.py`

The asset follows the FEMA pattern: custom `_geom_scd2_upsert()` that handles geometry atomically with attribute data via `execute_batch`.

- [ ] **Step 1: Write the asset file**

```python
"""Zoning districts from ArcGIS REST API → staging.zoning.

Records: ~1,694 polygons
Schedule: Weekly (Sunday 02:00)
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

from countyiq.lib.arcgis_client import query_all_features
from countyiq.lib.county_config import get_county_config
from countyiq.lib.parsers.zoning import parse_zoning_features
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

KEY_COLUMNS = ["zrecid"]
VALUE_COLUMNS = [
    "muni_name", "district", "zcode", "zname", "ztype",
    "gen_zcode", "gen_zname", "changetype", "prj_num",
    "muni_ord", "adpt_date", "prev_zcode", "prev_zname",
]

EXPECTED_FIELDS = {
    "ZRECID", "MUNI_NAME", "DISTRICT", "ZCODE", "ZNAME", "ZTYPE",
    "GEN_ZCODE", "GEN_ZNAME", "CHANGETYPE", "PRJ_NUM", "MUNI_ORD",
    "ADPT_DATE", "PREV_ZCODE", "PREV_ZNAME",
}


@asset(
    group_name="gis_layers",
    description="York County zoning districts from ArcGIS REST API → staging.zoning",
    kinds={"postgres", "arcgis"},
)
def zoning_arcgis(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Fetch zoning polygons, archive to S3, SCD2 upsert with geometry."""

    county = get_county_config()
    context.log.info(f"Querying ArcGIS zoning for {county.name}: {county.arcgis_zoning_url}")

    raw_features = query_all_features(
        url=county.arcgis_zoning_url,
        where="1=1",
        out_fields="*",
        out_sr=4326,
        batch_size=2000,
    )
    context.log.info(f"Fetched {len(raw_features)} raw features")

    s3.archive(f"{county.s3_prefix}/arcgis/zoning", raw_features)

    records = parse_zoning_features(raw_features)
    context.log.info(f"Parsed {len(records)} zoning records")

    if not records:
        context.log.warning("No records parsed — skipping upsert")
        return MaterializeResult(metadata={"record_count": MetadataValue.int(0)})

    if len(records) < county.arcgis_zoning_min_records:
        raise RuntimeError(
            f"Only {len(records)} zoning records (expected >= {county.arcgis_zoning_min_records}). "
            f"Possible truncated response — aborting."
        )

    cur = database.cursor()
    try:
        stats = _geom_scd2_upsert(cur, records, raw_features)
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


def _geom_scd2_upsert(cursor, records: list[dict], raw_features: list[dict]) -> dict:
    """SCD2 upsert with PostGIS geometry for staging.zoning."""
    conn = cursor.connection
    was_autocommit = conn.autocommit
    if was_autocommit:
        conn.autocommit = False

    try:
        all_cols = KEY_COLUMNS + VALUE_COLUMNS
        fqn = "staging.zoning"

        cursor.execute("DROP TABLE IF EXISTS _tmp_zoning")
        cursor.execute(f"CREATE TEMP TABLE _tmp_zoning (LIKE {fqn} INCLUDING DEFAULTS)")

        # Build geometry lookup by zrecid
        geom_lookup = {}
        for feat in raw_features:
            attrs = feat.get("attributes", {})
            zrecid = attrs.get("ZRECID")
            geom = feat.get("geometry")
            if zrecid is not None and geom:
                geojson = _arcgis_polygon_to_geojson(geom)
                if geojson:
                    geom_lookup[zrecid] = json.dumps(geojson)

        insert_sql = f"""
            INSERT INTO _tmp_zoning ({', '.join(all_cols)}, geom)
            VALUES ({', '.join(['%s'] * len(all_cols))},
                    CASE WHEN %s IS NOT NULL
                         THEN ST_SetSRID(ST_Multi(ST_GeomFromGeoJSON(%s)), 4326)
                         ELSE NULL END)
        """
        rows = []
        for rec in records:
            row = [rec.get(c) for c in all_cols]
            geom_json = geom_lookup.get(rec["zrecid"])
            row.extend([geom_json, geom_json])
            rows.append(row)
        execute_batch(cursor, insert_sql, rows, page_size=500)

        # Expire changed/deleted
        key_join = "c.zrecid = t.zrecid"
        value_diff = " OR ".join(f"c.{v}::text IS DISTINCT FROM t.{v}::text" for v in VALUE_COLUMNS)
        cursor.execute(f"""
            UPDATE {fqn} c SET valid_to = NOW()
            WHERE c.valid_to IS NULL
            AND (
                EXISTS (SELECT 1 FROM _tmp_zoning t WHERE {key_join} AND ({value_diff}))
                OR NOT EXISTS (SELECT 1 FROM _tmp_zoning t WHERE {key_join})
            )
        """)
        expired = cursor.rowcount

        # Insert new/changed
        col_list = ', '.join(all_cols)
        cursor.execute(f"""
            INSERT INTO {fqn} ({col_list}, geom, valid_from)
            SELECT {', '.join(f't.{c}' for c in all_cols)}, t.geom, NOW()
            FROM _tmp_zoning t
            WHERE NOT EXISTS (
                SELECT 1 FROM {fqn} c WHERE c.valid_to IS NULL AND {key_join}
            )
        """)
        inserted = cursor.rowcount

        cursor.execute("DROP TABLE IF EXISTS _tmp_zoning")
        conn.commit()

        if was_autocommit:
            conn.autocommit = True

        return {"inserted": inserted, "expired": expired, "unchanged": len(records) - inserted}
    except Exception:
        conn.rollback()
        if was_autocommit:
            conn.autocommit = True
        raise


def _arcgis_polygon_to_geojson(geom: dict) -> dict | None:
    """Convert ArcGIS polygon geometry to GeoJSON MultiPolygon."""
    rings = geom.get("rings")
    if not rings:
        return None
    # Treat each ring set as a polygon; ArcGIS clockwise = exterior
    polygons = []
    current_polygon = []
    for ring in rings:
        if not current_polygon:
            current_polygon.append(ring)
        elif _is_clockwise(ring):
            polygons.append(current_polygon)
            current_polygon = [ring]
        else:
            current_polygon.append(ring)
    if current_polygon:
        polygons.append(current_polygon)
    return {"type": "MultiPolygon", "coordinates": polygons}


def _is_clockwise(ring: list[list[float]]) -> bool:
    """Shoelace formula to determine ring orientation."""
    total = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[i + 1][0], ring[i + 1][1]
        total += (x2 - x1) * (y2 + y1)
    return total > 0


@asset_check(asset=zoning_arcgis)
def zoning_record_count_nonzero(database: DatabaseResource) -> AssetCheckResult:
    """Verify staging.zoning has at least one current record."""
    result = database.execute("SELECT COUNT(*) FROM staging.zoning WHERE valid_to IS NULL")
    count = result[0][0] if result else 0
    return AssetCheckResult(
        passed=count > 0,
        severity=AssetCheckSeverity.ERROR,
        metadata={"current_record_count": MetadataValue.int(count)},
    )


@asset_check(asset=zoning_arcgis)
def zoning_schema_drift(database: DatabaseResource) -> AssetCheckResult:
    """Verify ArcGIS Zoning layer still has expected fields."""
    county = get_county_config()
    try:
        resp = requests.get(f"{county.arcgis_zoning_url}?f=json", timeout=30)
        resp.raise_for_status()
        actual_fields = {f["name"] for f in resp.json().get("fields", [])}
        missing = EXPECTED_FIELDS - actual_fields
        return AssetCheckResult(
            passed=len(missing) == 0,
            severity=AssetCheckSeverity.WARN,
            metadata={
                "missing_fields": MetadataValue.text(str(missing) if missing else "none"),
            },
        )
    except requests.exceptions.RequestException as e:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.WARN,
            metadata={"error": MetadataValue.text(f"Network error: {e}")},
        )
```

- [ ] **Step 2: Verify import**

Run: `cd pipelines && source .venv/bin/activate && python3 -c "from countyiq.assets.arcgis.zoning import zoning_arcgis; print(zoning_arcgis)"`
Expected: No import errors

- [ ] **Step 3: Commit**

```bash
git add pipelines/countyiq/assets/arcgis/zoning.py
git commit -m "feat(asset): add zoning ArcGIS asset with SCD2 geometry upsert and checks"
```

---

### Task 7: Roads Asset + Checks

**Files:**
- Create: `pipelines/countyiq/assets/arcgis/roads.py`

Same pattern as zoning but with MULTILINESTRING geometry (polylines, not polygons).

- [ ] **Step 1: Write the asset file**

```python
"""Road centerlines from ArcGIS REST API → staging.roads.

Records: ~33,748 polylines
Schedule: Weekly (Sunday 02:00)
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

from countyiq.lib.arcgis_client import query_all_features
from countyiq.lib.county_config import get_county_config
from countyiq.lib.parsers.roads import parse_roads_features
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

KEY_COLUMNS = ["rcl_nguid"]
VALUE_COLUMNS = [
    "street_name", "st_pre_dir", "st_pre_typ", "st_pos_typ", "st_pos_dir",
    "road_class", "speed_limit", "one_way", "rte_num",
    "from_addr_l", "to_addr_l", "from_addr_r", "to_addr_r",
    "inc_muni_l", "inc_muni_r", "post_code_l", "post_code_r",
]

EXPECTED_FIELDS = {
    "RCL_NGUID", "StreetName", "St_PreDir", "St_PreTyp", "St_PosTyp",
    "St_PosDir", "RoadClass", "SpeedLimit", "OneWay", "RTE_NUM",
    "FromAddr_L", "ToAddr_L", "FromAddr_R", "ToAddr_R",
    "IncMuni_L", "IncMuni_R", "PostCode_L", "PostCode_R",
}


@asset(
    group_name="gis_layers",
    description="York County road centerlines from ArcGIS REST API → staging.roads",
    kinds={"postgres", "arcgis"},
)
def roads_arcgis(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Fetch road centerlines, archive to S3, SCD2 upsert with geometry."""

    county = get_county_config()
    context.log.info(f"Querying ArcGIS roads for {county.name}: {county.arcgis_roads_url}")

    raw_features = query_all_features(
        url=county.arcgis_roads_url,
        where="1=1",
        out_fields="*",
        out_sr=4326,
        batch_size=2000,
    )
    context.log.info(f"Fetched {len(raw_features)} raw features")

    s3.archive(f"{county.s3_prefix}/arcgis/roads", raw_features)

    records = parse_roads_features(raw_features)
    context.log.info(f"Parsed {len(records)} road records")

    if not records:
        context.log.warning("No records parsed — skipping upsert")
        return MaterializeResult(metadata={"record_count": MetadataValue.int(0)})

    if len(records) < county.arcgis_roads_min_records:
        raise RuntimeError(
            f"Only {len(records)} road records (expected >= {county.arcgis_roads_min_records}). "
            f"Possible truncated response — aborting."
        )

    cur = database.cursor()
    try:
        stats = _geom_scd2_upsert(cur, records, raw_features)
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


def _geom_scd2_upsert(cursor, records: list[dict], raw_features: list[dict]) -> dict:
    """SCD2 upsert with PostGIS geometry for staging.roads (MULTILINESTRING)."""
    conn = cursor.connection
    was_autocommit = conn.autocommit
    if was_autocommit:
        conn.autocommit = False

    try:
        all_cols = KEY_COLUMNS + VALUE_COLUMNS
        fqn = "staging.roads"

        cursor.execute("DROP TABLE IF EXISTS _tmp_roads")
        cursor.execute(f"CREATE TEMP TABLE _tmp_roads (LIKE {fqn} INCLUDING DEFAULTS)")

        # Build geometry lookup by rcl_nguid
        geom_lookup = {}
        for feat in raw_features:
            attrs = feat.get("attributes", {})
            nguid = attrs.get("RCL_NGUID")
            geom = feat.get("geometry")
            if nguid and geom:
                geojson = _arcgis_polyline_to_geojson(geom)
                if geojson:
                    geom_lookup[nguid] = json.dumps(geojson)

        insert_sql = f"""
            INSERT INTO _tmp_roads ({', '.join(all_cols)}, geom)
            VALUES ({', '.join(['%s'] * len(all_cols))},
                    CASE WHEN %s IS NOT NULL
                         THEN ST_SetSRID(ST_Multi(ST_GeomFromGeoJSON(%s)), 4326)
                         ELSE NULL END)
        """
        rows = []
        for rec in records:
            row = [rec.get(c) for c in all_cols]
            geom_json = geom_lookup.get(rec["rcl_nguid"])
            row.extend([geom_json, geom_json])
            rows.append(row)
        execute_batch(cursor, insert_sql, rows, page_size=500)

        # Expire changed/deleted
        key_join = "c.rcl_nguid = t.rcl_nguid"
        value_diff = " OR ".join(f"c.{v}::text IS DISTINCT FROM t.{v}::text" for v in VALUE_COLUMNS)
        cursor.execute(f"""
            UPDATE {fqn} c SET valid_to = NOW()
            WHERE c.valid_to IS NULL
            AND (
                EXISTS (SELECT 1 FROM _tmp_roads t WHERE {key_join} AND ({value_diff}))
                OR NOT EXISTS (SELECT 1 FROM _tmp_roads t WHERE {key_join})
            )
        """)
        expired = cursor.rowcount

        # Insert new/changed
        col_list = ', '.join(all_cols)
        cursor.execute(f"""
            INSERT INTO {fqn} ({col_list}, geom, valid_from)
            SELECT {', '.join(f't.{c}' for c in all_cols)}, t.geom, NOW()
            FROM _tmp_roads t
            WHERE NOT EXISTS (
                SELECT 1 FROM {fqn} c WHERE c.valid_to IS NULL AND {key_join}
            )
        """)
        inserted = cursor.rowcount

        cursor.execute("DROP TABLE IF EXISTS _tmp_roads")
        conn.commit()

        if was_autocommit:
            conn.autocommit = True

        return {"inserted": inserted, "expired": expired, "unchanged": len(records) - inserted}
    except Exception:
        conn.rollback()
        if was_autocommit:
            conn.autocommit = True
        raise


def _arcgis_polyline_to_geojson(geom: dict) -> dict | None:
    """Convert ArcGIS polyline geometry to GeoJSON MultiLineString."""
    paths = geom.get("paths")
    if not paths:
        return None
    return {"type": "MultiLineString", "coordinates": paths}


@asset_check(asset=roads_arcgis)
def roads_record_count_nonzero(database: DatabaseResource) -> AssetCheckResult:
    """Verify staging.roads has at least one current record."""
    result = database.execute("SELECT COUNT(*) FROM staging.roads WHERE valid_to IS NULL")
    count = result[0][0] if result else 0
    return AssetCheckResult(
        passed=count > 0,
        severity=AssetCheckSeverity.ERROR,
        metadata={"current_record_count": MetadataValue.int(count)},
    )


@asset_check(asset=roads_arcgis)
def roads_schema_drift(database: DatabaseResource) -> AssetCheckResult:
    """Verify ArcGIS Roads layer still has expected fields."""
    county = get_county_config()
    try:
        resp = requests.get(f"{county.arcgis_roads_url}?f=json", timeout=30)
        resp.raise_for_status()
        actual_fields = {f["name"] for f in resp.json().get("fields", [])}
        missing = EXPECTED_FIELDS - actual_fields
        return AssetCheckResult(
            passed=len(missing) == 0,
            severity=AssetCheckSeverity.WARN,
            metadata={
                "missing_fields": MetadataValue.text(str(missing) if missing else "none"),
            },
        )
    except requests.exceptions.RequestException as e:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.WARN,
            metadata={"error": MetadataValue.text(f"Network error: {e}")},
        )
```

- [ ] **Step 2: Verify import**

Run: `cd pipelines && source .venv/bin/activate && python3 -c "from countyiq.assets.arcgis.roads import roads_arcgis; print(roads_arcgis)"`
Expected: No import errors

- [ ] **Step 3: Commit**

```bash
git add pipelines/countyiq/assets/arcgis/roads.py
git commit -m "feat(asset): add roads ArcGIS asset with SCD2 geometry upsert and checks"
```

---

### Task 8: Structures Asset + Checks

**Files:**
- Create: `pipelines/countyiq/assets/arcgis/structures.py`

213K records — uses `execute_batch` with page_size=500 for performance.

- [ ] **Step 1: Write the asset file**

```python
"""Building footprints from ArcGIS REST API → staging.structures.

Records: ~213,041 polygons
Schedule: Weekly (Sunday 02:00)
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

from countyiq.lib.arcgis_client import query_all_features
from countyiq.lib.county_config import get_county_config
from countyiq.lib.parsers.structures import parse_structures_features
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

KEY_COLUMNS = ["index_id"]
VALUE_COLUMNS = ["building_type"]

EXPECTED_FIELDS = {"INDEX_", "BUILDING_TYPE"}


@asset(
    group_name="gis_layers",
    description="York County building footprints from ArcGIS REST API → staging.structures",
    kinds={"postgres", "arcgis"},
)
def structures_arcgis(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Fetch building footprints, archive to S3, SCD2 upsert with geometry."""

    county = get_county_config()
    context.log.info(f"Querying ArcGIS structures for {county.name}: {county.arcgis_structures_url}")

    raw_features = query_all_features(
        url=county.arcgis_structures_url,
        where="1=1",
        out_fields="*",
        out_sr=4326,
        batch_size=2000,
    )
    context.log.info(f"Fetched {len(raw_features)} raw features")

    s3.archive(f"{county.s3_prefix}/arcgis/structures", raw_features)

    records = parse_structures_features(raw_features)
    context.log.info(f"Parsed {len(records)} structure records")

    if not records:
        context.log.warning("No records parsed — skipping upsert")
        return MaterializeResult(metadata={"record_count": MetadataValue.int(0)})

    if len(records) < county.arcgis_structures_min_records:
        raise RuntimeError(
            f"Only {len(records)} structure records (expected >= {county.arcgis_structures_min_records}). "
            f"Possible truncated response — aborting."
        )

    cur = database.cursor()
    try:
        stats = _geom_scd2_upsert(cur, records, raw_features)
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


def _geom_scd2_upsert(cursor, records: list[dict], raw_features: list[dict]) -> dict:
    """SCD2 upsert with PostGIS geometry for staging.structures."""
    conn = cursor.connection
    was_autocommit = conn.autocommit
    if was_autocommit:
        conn.autocommit = False

    try:
        all_cols = KEY_COLUMNS + VALUE_COLUMNS
        fqn = "staging.structures"

        cursor.execute("DROP TABLE IF EXISTS _tmp_structures")
        cursor.execute(f"CREATE TEMP TABLE _tmp_structures (LIKE {fqn} INCLUDING DEFAULTS)")

        # Build geometry lookup by index_id
        geom_lookup = {}
        for feat in raw_features:
            attrs = feat.get("attributes", {})
            idx = attrs.get("INDEX_")
            geom = feat.get("geometry")
            if idx and geom:
                geojson = _arcgis_polygon_to_geojson(geom)
                if geojson:
                    geom_lookup[str(idx)] = json.dumps(geojson)

        insert_sql = f"""
            INSERT INTO _tmp_structures ({', '.join(all_cols)}, geom)
            VALUES ({', '.join(['%s'] * len(all_cols))},
                    CASE WHEN %s IS NOT NULL
                         THEN ST_SetSRID(ST_Multi(ST_GeomFromGeoJSON(%s)), 4326)
                         ELSE NULL END)
        """
        rows = []
        for rec in records:
            row = [rec.get(c) for c in all_cols]
            geom_json = geom_lookup.get(rec["index_id"])
            row.extend([geom_json, geom_json])
            rows.append(row)
        execute_batch(cursor, insert_sql, rows, page_size=500)

        # Expire changed/deleted
        key_join = "c.index_id = t.index_id"
        value_diff = "c.building_type::text IS DISTINCT FROM t.building_type::text"
        cursor.execute(f"""
            UPDATE {fqn} c SET valid_to = NOW()
            WHERE c.valid_to IS NULL
            AND (
                EXISTS (SELECT 1 FROM _tmp_structures t WHERE {key_join} AND ({value_diff}))
                OR NOT EXISTS (SELECT 1 FROM _tmp_structures t WHERE {key_join})
            )
        """)
        expired = cursor.rowcount

        # Insert new/changed
        col_list = ', '.join(all_cols)
        cursor.execute(f"""
            INSERT INTO {fqn} ({col_list}, geom, valid_from)
            SELECT {', '.join(f't.{c}' for c in all_cols)}, t.geom, NOW()
            FROM _tmp_structures t
            WHERE NOT EXISTS (
                SELECT 1 FROM {fqn} c WHERE c.valid_to IS NULL AND {key_join}
            )
        """)
        inserted = cursor.rowcount

        cursor.execute("DROP TABLE IF EXISTS _tmp_structures")
        conn.commit()

        if was_autocommit:
            conn.autocommit = True

        return {"inserted": inserted, "expired": expired, "unchanged": len(records) - inserted}
    except Exception:
        conn.rollback()
        if was_autocommit:
            conn.autocommit = True
        raise


def _arcgis_polygon_to_geojson(geom: dict) -> dict | None:
    """Convert ArcGIS polygon geometry to GeoJSON MultiPolygon."""
    rings = geom.get("rings")
    if not rings:
        return None
    polygons = []
    current_polygon = []
    for ring in rings:
        if not current_polygon:
            current_polygon.append(ring)
        elif _is_clockwise(ring):
            polygons.append(current_polygon)
            current_polygon = [ring]
        else:
            current_polygon.append(ring)
    if current_polygon:
        polygons.append(current_polygon)
    return {"type": "MultiPolygon", "coordinates": polygons}


def _is_clockwise(ring: list[list[float]]) -> bool:
    """Shoelace formula to determine ring orientation."""
    total = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[i + 1][0], ring[i + 1][1]
        total += (x2 - x1) * (y2 + y1)
    return total > 0


@asset_check(asset=structures_arcgis)
def structures_record_count_nonzero(database: DatabaseResource) -> AssetCheckResult:
    """Verify staging.structures has at least one current record."""
    result = database.execute("SELECT COUNT(*) FROM staging.structures WHERE valid_to IS NULL")
    count = result[0][0] if result else 0
    return AssetCheckResult(
        passed=count > 0,
        severity=AssetCheckSeverity.ERROR,
        metadata={"current_record_count": MetadataValue.int(count)},
    )


@asset_check(asset=structures_arcgis)
def structures_schema_drift(database: DatabaseResource) -> AssetCheckResult:
    """Verify ArcGIS BLDG_Footprint layer still has expected fields."""
    county = get_county_config()
    try:
        resp = requests.get(f"{county.arcgis_structures_url}?f=json", timeout=30)
        resp.raise_for_status()
        actual_fields = {f["name"] for f in resp.json().get("fields", [])}
        missing = EXPECTED_FIELDS - actual_fields
        return AssetCheckResult(
            passed=len(missing) == 0,
            severity=AssetCheckSeverity.WARN,
            metadata={
                "missing_fields": MetadataValue.text(str(missing) if missing else "none"),
            },
        )
    except requests.exceptions.RequestException as e:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.WARN,
            metadata={"error": MetadataValue.text(f"Network error: {e}")},
        )
```

- [ ] **Step 2: Verify import**

Run: `cd pipelines && source .venv/bin/activate && python3 -c "from countyiq.assets.arcgis.structures import structures_arcgis; print(structures_arcgis)"`
Expected: No import errors

- [ ] **Step 3: Commit**

```bash
git add pipelines/countyiq/assets/arcgis/structures.py
git commit -m "feat(asset): add structures ArcGIS asset with SCD2 geometry upsert and checks"
```

---

### Task 9: Job + Schedule Configuration

**Files:**
- Modify: `pipelines/countyiq/jobs/__init__.py`
- Modify: `pipelines/countyiq/schedules/__init__.py`
- Modify: `pipelines/countyiq/definitions.py`

**Conflict warning:** The other agent may be modifying these files. Check `git diff` before editing. If there are unstaged changes, coordinate with the other agent or wait for their commit.

- [ ] **Step 1: Add gis_layers_refresh job**

In `pipelines/countyiq/jobs/__init__.py`, add:

```python
gis_layers_refresh = define_asset_job(
    name="gis_layers_refresh",
    selection=AssetSelection.groups("gis_layers"),
    description="Refresh GIS Portal layers (zoning, roads, structures)",
)
```

- [ ] **Step 2: Add schedule**

In `pipelines/countyiq/schedules/__init__.py`, add import of `gis_layers_refresh` and the schedule:

```python
from countyiq.jobs import arcgis_refresh, scraper_refresh, bulk_refresh, fema_refresh, gis_layers_refresh

# Add to all_schedules list:
    ScheduleDefinition(
        job=gis_layers_refresh,
        cron_schedule="0 2 * * 0",  # Sunday 02:00
        name="weekly_gis_layers",
    ),
```

- [ ] **Step 3: Register job in definitions.py**

In `pipelines/countyiq/definitions.py`, add `gis_layers_refresh` to imports and jobs list:

```python
from countyiq.jobs import arcgis_refresh, scraper_refresh, bulk_refresh, enrichment_refresh, fema_refresh, gis_layers_refresh

    jobs=[arcgis_refresh, scraper_refresh, bulk_refresh, enrichment_refresh, fema_refresh, gis_layers_refresh],
```

- [ ] **Step 4: Verify definitions load**

Run: `cd pipelines && source .venv/bin/activate && python3 -c "from countyiq.definitions import defs; print(len(list(defs.get_all_job_defs())),'jobs'); print([j.name for j in defs.get_all_job_defs()])"`
Expected: 6 jobs, includes `gis_layers_refresh`

- [ ] **Step 5: Commit**

```bash
git add pipelines/countyiq/jobs/__init__.py pipelines/countyiq/schedules/__init__.py pipelines/countyiq/definitions.py
git commit -m "feat(schedule): add weekly Sunday 2 AM schedule for GIS layers"
```

---

### Task 10: Local Integration Test

**Pre-req:** Docker Postgres running, migrations applied (Task 2).

- [ ] **Step 1: Run all parser tests**

Run: `cd pipelines && source .venv/bin/activate && python3 -m pytest tests/test_zoning_parser.py tests/test_roads_parser.py tests/test_structures_parser.py -v`
Expected: 12 passed

- [ ] **Step 2: Verify Dagster can load all definitions**

Run: `cd pipelines && source .venv/bin/activate && python3 -c "from countyiq.definitions import defs; assets = list(defs.get_asset_graph().all_asset_keys); print(f'{len(assets)} assets loaded'); print([str(a) for a in assets])"`
Expected: Lists `zoning_arcgis`, `roads_arcgis`, `structures_arcgis` among assets

- [ ] **Step 3: Test zoning asset against live API + Docker Postgres**

Run: `cd pipelines && source .venv/bin/activate && DATABASE_HOST=localhost DATABASE_PORT=5433 DATABASE_NAME=countyiq DATABASE_USER=dagster_admin DATABASE_PASSWORD=localtest AWS_DEFAULT_REGION=us-east-1 dagster asset materialize -m countyiq.definitions --select zoning_arcgis`

Verify: `PGPASSWORD=localtest psql -h localhost -p 5433 -U dagster_admin -d countyiq -c "SELECT COUNT(*) FROM staging.zoning WHERE valid_to IS NULL;"`
Expected: ~1,694 rows

- [ ] **Step 4: Test roads asset**

Run: `cd pipelines && source .venv/bin/activate && DATABASE_HOST=localhost DATABASE_PORT=5433 DATABASE_NAME=countyiq DATABASE_USER=dagster_admin DATABASE_PASSWORD=localtest AWS_DEFAULT_REGION=us-east-1 dagster asset materialize -m countyiq.definitions --select roads_arcgis`

Verify: `PGPASSWORD=localtest psql -h localhost -p 5433 -U dagster_admin -d countyiq -c "SELECT COUNT(*) FROM staging.roads WHERE valid_to IS NULL;"`
Expected: ~33,748 rows

- [ ] **Step 5: Test structures asset**

Run: `cd pipelines && source .venv/bin/activate && DATABASE_HOST=localhost DATABASE_PORT=5433 DATABASE_NAME=countyiq DATABASE_USER=dagster_admin DATABASE_PASSWORD=localtest AWS_DEFAULT_REGION=us-east-1 dagster asset materialize -m countyiq.definitions --select structures_arcgis`

Verify: `PGPASSWORD=localtest psql -h localhost -p 5433 -U dagster_admin -d countyiq -c "SELECT COUNT(*) FROM staging.structures WHERE valid_to IS NULL;"`
Expected: ~213,041 rows

- [ ] **Step 6: Verify geometry is populated**

```sql
PGPASSWORD=localtest psql -h localhost -p 5433 -U dagster_admin -d countyiq -c "
SELECT 'zoning' as layer, COUNT(*) as total, COUNT(geom) as with_geom FROM staging.zoning WHERE valid_to IS NULL
UNION ALL SELECT 'roads', COUNT(*), COUNT(geom) FROM staging.roads WHERE valid_to IS NULL
UNION ALL SELECT 'structures', COUNT(*), COUNT(geom) FROM staging.structures WHERE valid_to IS NULL;"
```
Expected: with_geom should be close to total for each layer

- [ ] **Step 7: Verify idempotency (re-run should show 0 inserted)**

Run zoning again and check stats show 0 inserted, 0 expired.
