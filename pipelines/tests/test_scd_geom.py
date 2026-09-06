"""Tests for scd2_upsert_geom — geometry SCD2 helper.

Mirrors test_scd_expire_missing.py but exercises the geometry column,
the data-loss guard, the scope_column path (FEMA-style multi-county
scoping), and the multi-geometry kinds.
"""

import json

import psycopg2
import pytest

from countyiq.lib.geometry import (
    _is_clockwise,
    paths_to_multilinestring_geojson,
    point_to_geojson,
    rings_to_multipolygon_geojson,
)
from countyiq.lib.scd import scd2_upsert_geom


@pytest.fixture
def db_conn():
    """Connect to local Docker Postgres test database (PostGIS enabled)."""
    conn = psycopg2.connect(
        host="localhost",
        port=5433,
        dbname="countyiq_test",
        user="dagster_admin",
        password="localtest",
    )
    yield conn
    conn.close()


@pytest.fixture
def polygon_table(db_conn):
    cur = db_conn.cursor()
    cur.execute("DROP TABLE IF EXISTS staging._test_geom_poly")
    cur.execute(
        """
        CREATE TABLE staging._test_geom_poly (
            id TEXT NOT NULL,
            name TEXT,
            geom geometry(MultiPolygon, 4326),
            valid_from TIMESTAMPTZ DEFAULT NOW() NOT NULL,
            valid_to TIMESTAMPTZ,
            PRIMARY KEY (id, valid_from)
        )
        """
    )
    db_conn.commit()
    yield "staging._test_geom_poly"
    cur.execute("DROP TABLE IF EXISTS staging._test_geom_poly")
    db_conn.commit()
    cur.close()


@pytest.fixture
def line_table(db_conn):
    cur = db_conn.cursor()
    cur.execute("DROP TABLE IF EXISTS staging._test_geom_line")
    cur.execute(
        """
        CREATE TABLE staging._test_geom_line (
            id TEXT NOT NULL,
            name TEXT,
            geom geometry(MultiLineString, 4326),
            valid_from TIMESTAMPTZ DEFAULT NOW() NOT NULL,
            valid_to TIMESTAMPTZ,
            PRIMARY KEY (id, valid_from)
        )
        """
    )
    db_conn.commit()
    yield "staging._test_geom_line"
    cur.execute("DROP TABLE IF EXISTS staging._test_geom_line")
    db_conn.commit()
    cur.close()


@pytest.fixture
def point_table(db_conn):
    cur = db_conn.cursor()
    cur.execute("DROP TABLE IF EXISTS staging._test_geom_point")
    cur.execute(
        """
        CREATE TABLE staging._test_geom_point (
            id TEXT NOT NULL,
            name TEXT,
            geom geometry(Point, 4326),
            valid_from TIMESTAMPTZ DEFAULT NOW() NOT NULL,
            valid_to TIMESTAMPTZ,
            PRIMARY KEY (id, valid_from)
        )
        """
    )
    db_conn.commit()
    yield "staging._test_geom_point"
    cur.execute("DROP TABLE IF EXISTS staging._test_geom_point")
    db_conn.commit()
    cur.close()


@pytest.fixture
def scoped_table(db_conn):
    cur = db_conn.cursor()
    cur.execute("DROP TABLE IF EXISTS staging._test_geom_scoped")
    cur.execute(
        """
        CREATE TABLE staging._test_geom_scoped (
            scope TEXT NOT NULL,
            id TEXT NOT NULL,
            name TEXT,
            geom geometry(MultiPolygon, 4326),
            valid_from TIMESTAMPTZ DEFAULT NOW() NOT NULL,
            valid_to TIMESTAMPTZ,
            PRIMARY KEY (scope, id, valid_from)
        )
        """
    )
    db_conn.commit()
    yield "staging._test_geom_scoped"
    cur.execute("DROP TABLE IF EXISTS staging._test_geom_scoped")
    db_conn.commit()
    cur.close()


# Tiny CW square ring used in multiple tests
SQUARE = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]


def test_is_clockwise_recognises_cw_and_ccw():
    assert _is_clockwise(SQUARE) is False  # default GeoJSON-style winding
    # Reverse the square — should flip orientation
    assert _is_clockwise(list(reversed(SQUARE))) is True


def test_rings_to_multipolygon_handles_empty():
    assert rings_to_multipolygon_geojson([]) is None
    assert rings_to_multipolygon_geojson(None) is None


def test_paths_to_multilinestring_handles_empty():
    assert paths_to_multilinestring_geojson([]) is None
    assert paths_to_multilinestring_geojson(None) is None


def test_point_to_geojson_handles_missing():
    assert point_to_geojson(None, 1.0) is None
    assert point_to_geojson(1.0, None) is None
    assert point_to_geojson(1.0, 2.0) == {"type": "Point", "coordinates": [1.0, 2.0]}


@pytest.mark.integration
def test_geom_upsert_multipolygon_inserts(db_conn, polygon_table):
    cur = db_conn.cursor()

    geojson = json.dumps(
        rings_to_multipolygon_geojson([list(reversed(SQUARE))])  # need a CW outer ring
    )
    stats = scd2_upsert_geom(
        cursor=cur,
        schema="staging",
        table="_test_geom_poly",
        records=[{"id": "A", "name": "Alpha"}],
        key_columns=["id"],
        value_columns=["name"],
        geom_lookup={"A": geojson},
        geom_kind="multipolygon",
    )
    assert stats == {"inserted": 1, "expired": 0, "unchanged": 0}

    cur.execute(
        "SELECT id, name, ST_GeometryType(geom), ST_SRID(geom) "
        "FROM staging._test_geom_poly WHERE valid_to IS NULL"
    )
    rows = cur.fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "A"
    assert rows[0][1] == "Alpha"
    assert rows[0][2] == "ST_MultiPolygon"
    assert rows[0][3] == 4326
    cur.close()


@pytest.mark.integration
def test_geom_upsert_multilinestring_inserts(db_conn, line_table):
    cur = db_conn.cursor()
    paths = [[[0.0, 0.0], [1.0, 1.0]]]
    geojson = json.dumps(paths_to_multilinestring_geojson(paths))
    stats = scd2_upsert_geom(
        cursor=cur,
        schema="staging",
        table="_test_geom_line",
        records=[{"id": "L1", "name": "Line"}],
        key_columns=["id"],
        value_columns=["name"],
        geom_lookup={"L1": geojson},
        geom_kind="multilinestring",
    )
    assert stats["inserted"] == 1
    cur.execute(
        "SELECT ST_GeometryType(geom) FROM staging._test_geom_line WHERE valid_to IS NULL"
    )
    assert cur.fetchone()[0] == "ST_MultiLineString"
    cur.close()


@pytest.mark.integration
def test_geom_upsert_point_inserts(db_conn, point_table):
    cur = db_conn.cursor()
    geojson = json.dumps(point_to_geojson(10.0, 20.0))
    stats = scd2_upsert_geom(
        cursor=cur,
        schema="staging",
        table="_test_geom_point",
        records=[{"id": "P1", "name": "Pin"}],
        key_columns=["id"],
        value_columns=["name"],
        geom_lookup={"P1": geojson},
        geom_kind="point",
    )
    assert stats["inserted"] == 1
    cur.execute(
        "SELECT ST_GeometryType(geom) FROM staging._test_geom_point WHERE valid_to IS NULL"
    )
    assert cur.fetchone()[0] == "ST_Point"
    cur.close()


@pytest.mark.integration
def test_geom_upsert_data_loss_guard_aborts(db_conn, polygon_table):
    """Refuse to expire when incoming << existing (and existing > 100)."""
    cur = db_conn.cursor()

    # Seed 200 records (above the 100-row guard threshold)
    geojson = json.dumps(rings_to_multipolygon_geojson([list(reversed(SQUARE))]))
    seed_records = [{"id": f"R{i}", "name": f"name-{i}"} for i in range(200)]
    seed_lookup = {r["id"]: geojson for r in seed_records}
    scd2_upsert_geom(
        cursor=cur,
        schema="staging",
        table="_test_geom_poly",
        records=seed_records,
        key_columns=["id"],
        value_columns=["name"],
        geom_lookup=seed_lookup,
        geom_kind="multipolygon",
    )

    # Now feed back only 50 records — well below 50% of 200
    partial = seed_records[:50]
    partial_lookup = {r["id"]: geojson for r in partial}
    with pytest.raises(RuntimeError, match="DATA LOSS GUARD"):
        scd2_upsert_geom(
            cursor=cur,
            schema="staging",
            table="_test_geom_poly",
            records=partial,
            key_columns=["id"],
            value_columns=["name"],
            geom_lookup=partial_lookup,
            geom_kind="multipolygon",
        )

    # All 200 should still be current — guard prevented mass expiration
    cur.execute("SELECT COUNT(*) FROM staging._test_geom_poly WHERE valid_to IS NULL")
    assert cur.fetchone()[0] == 200
    cur.close()


@pytest.mark.integration
def test_geom_upsert_scope_column_isolates_counties(db_conn, scoped_table):
    """scope_column='scope' must keep county A's records out of county B's expire."""
    cur = db_conn.cursor()
    geojson = json.dumps(rings_to_multipolygon_geojson([list(reversed(SQUARE))]))

    # Seed county A with two records
    scd2_upsert_geom(
        cursor=cur,
        schema="staging",
        table="_test_geom_scoped",
        records=[
            {"scope": "A", "id": "1", "name": "A1"},
            {"scope": "A", "id": "2", "name": "A2"},
        ],
        key_columns=["scope", "id"],
        value_columns=["name"],
        geom_lookup={"1": geojson, "2": geojson},
        geom_kind="multipolygon",
        geom_key="id",
        scope_column="scope",
        scope_value="A",
    )

    # Seed county B with one record
    scd2_upsert_geom(
        cursor=cur,
        schema="staging",
        table="_test_geom_scoped",
        records=[{"scope": "B", "id": "9", "name": "B9"}],
        key_columns=["scope", "id"],
        value_columns=["name"],
        geom_lookup={"9": geojson},
        geom_kind="multipolygon",
        geom_key="id",
        scope_column="scope",
        scope_value="B",
    )

    # Reload county A with fewer records — but scope must isolate from county B.
    # County A has 2 existing rows so the data-loss guard's 100-row threshold
    # does not apply; we expect "1" to be expired (missing) and B's row
    # to be untouched.
    scd2_upsert_geom(
        cursor=cur,
        schema="staging",
        table="_test_geom_scoped",
        records=[{"scope": "A", "id": "2", "name": "A2"}],
        key_columns=["scope", "id"],
        value_columns=["name"],
        geom_lookup={"2": geojson},
        geom_kind="multipolygon",
        geom_key="id",
        scope_column="scope",
        scope_value="A",
    )

    cur.execute(
        "SELECT scope, id FROM staging._test_geom_scoped "
        "WHERE valid_to IS NULL ORDER BY scope, id"
    )
    rows = cur.fetchall()
    assert rows == [("A", "2"), ("B", "9")]
    cur.close()


@pytest.mark.integration
def test_geom_upsert_change_detection_expires_then_inserts(db_conn, polygon_table):
    cur = db_conn.cursor()
    geojson = json.dumps(rings_to_multipolygon_geojson([list(reversed(SQUARE))]))

    scd2_upsert_geom(
        cursor=cur,
        schema="staging",
        table="_test_geom_poly",
        records=[{"id": "X", "name": "first"}],
        key_columns=["id"],
        value_columns=["name"],
        geom_lookup={"X": geojson},
        geom_kind="multipolygon",
    )
    stats = scd2_upsert_geom(
        cursor=cur,
        schema="staging",
        table="_test_geom_poly",
        records=[{"id": "X", "name": "second"}],
        key_columns=["id"],
        value_columns=["name"],
        geom_lookup={"X": geojson},
        geom_kind="multipolygon",
    )
    # Same row, different value: 1 expired, 1 inserted
    assert stats["expired"] == 1
    assert stats["inserted"] == 1
    cur.execute("SELECT COUNT(*) FROM staging._test_geom_poly WHERE valid_to IS NULL")
    assert cur.fetchone()[0] == 1
    cur.execute("SELECT name FROM staging._test_geom_poly WHERE valid_to IS NULL")
    assert cur.fetchone()[0] == "second"
    cur.close()


@pytest.mark.integration
def test_geom_upsert_handles_missing_geometry(db_conn, polygon_table):
    cur = db_conn.cursor()
    # Record "Z" has no geometry in the lookup
    stats = scd2_upsert_geom(
        cursor=cur,
        schema="staging",
        table="_test_geom_poly",
        records=[{"id": "Z", "name": "no-geom"}],
        key_columns=["id"],
        value_columns=["name"],
        geom_lookup={},
        geom_kind="multipolygon",
    )
    assert stats["inserted"] == 1
    cur.execute(
        "SELECT geom FROM staging._test_geom_poly WHERE valid_to IS NULL AND id='Z'"
    )
    assert cur.fetchone()[0] is None
    cur.close()
