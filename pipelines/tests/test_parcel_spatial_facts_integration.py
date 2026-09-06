"""Real PostGIS regressions for parcel reports and deterministic signals."""

import os

import psycopg2
from psycopg2.extras import RealDictCursor
import pytest

from countyiq.assets.enrichment.development_signals import _SIGNALS


@pytest.fixture
def spatial_cursor():
    database_name = os.environ.get("DATABASE_NAME", "countyiq_test")
    if database_name != "countyiq_test":
        raise RuntimeError("Spatial fixtures may only use countyiq_test")
    connection = psycopg2.connect(
        host=os.environ.get("DATABASE_HOST", "localhost"),
        port=int(os.environ.get("DATABASE_PORT", "5433")),
        dbname=database_name,
        user=os.environ.get("DATABASE_USER", "dagster_admin"),
        password=os.environ.get("DATABASE_PASSWORD", "localtest"),
    )
    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            # All fixtures and generated signals roll back, including failures.
            cursor.execute("DELETE FROM staging.parcels")
            cursor.execute("DELETE FROM staging.soils")
            cursor.execute("DELETE FROM staging.zoning")
            cursor.execute("DELETE FROM staging.future_landuse")
            cursor.execute("DELETE FROM public.development_signals")
            cursor.execute("""
                INSERT INTO staging.parcels (pidn, geom)
                VALUES ('GEO0660000001', ST_Multi(ST_Transform(
                    ST_MakeEnvelope(500000, 4400000, 500100, 4400100, 32617), 4326)))
            """)
            yield cursor
    finally:
        connection.rollback()
        connection.close()


def _soil(
    cursor, objectid, left, width, *, slope=20, septic="Very limited", key="542898"
):
    cursor.execute(
        """
        INSERT INTO staging.soils (
            objectid, map_unit_key, map_unit_symbol, map_unit_name,
            representative_slope, septic_rating, source_url, geom
        ) VALUES (%s, %s, 'MOD', 'Mapped test soil', %s, %s,
            'https://example.com/soils/FeatureServer/0', ST_Multi(ST_Transform(
                ST_MakeEnvelope(500000 + %s, 4400000, 500000 + %s + %s, 4400100, 32617), 4326)))
    """,
        (objectid, key, slope, septic, left, left, width),
    )


@pytest.mark.integration
@pytest.mark.parametrize("second_left,expected_coverage", [(30, 25.207), (10, 23.188)])
def test_soil_fragments_union_before_rounding_and_preserve_distinct_attributes(
    spatial_cursor, second_left, expected_coverage
):
    cur = spatial_cursor
    _soil(cur, 66001, 0, 12.019)
    _soil(cur, 66002, second_left, 13.188)
    # Same name/key with conflicting screening attributes stays separate. Its
    # duplicate geometry must not increase parcel-wide mapped/septic totals.
    _soil(cur, 66003, 0, 12.019, slope=5, septic="Not limited")
    cur.execute("""
        SELECT s.* FROM staging.parcels p
        CROSS JOIN LATERAL public.parcel_soil_units(p.geom) s
        ORDER BY s.source_record_ids
    """)
    units = cur.fetchall()
    assert [u["source_record_ids"] for u in units] == [[66001, 66002], [66003]]
    assert float(units[0]["coverage_pct"]) == pytest.approx(
        expected_coverage, abs=0.001
    )
    for unit in units:
        assert float(unit["mapped_coverage_pct"]) == pytest.approx(
            expected_coverage, abs=0.001
        )
        assert float(unit["very_limited_coverage_pct"]) == pytest.approx(
            expected_coverage, abs=0.001
        )
    cur.execute(dict(_SIGNALS)["soil_constraint"], {})
    cur.execute("SELECT source_id, evidence FROM public.development_signals")
    signal = cur.fetchone()
    assert signal["source_id"] == "66001,66002,66003"
    assert signal["evidence"]["source_record_ids"] == [66001, 66002, 66003]
    assert signal["evidence"]["soil_units"][0]["source_record_ids"] == [66001, 66002]
    assert signal["evidence"]["soil_units"][0]["coverage_pct"] == round(
        expected_coverage, 1
    )


@pytest.mark.integration
@pytest.mark.parametrize("second_left,should_trigger", [(4, True), (1, False)])
def test_soil_screen_threshold_uses_combined_area_without_overlap_inflation(
    spatial_cursor, second_left, should_trigger
):
    cur = spatial_cursor
    _soil(cur, 66001, 0, 3)
    _soil(cur, 66002, second_left, 3)
    cur.execute(dict(_SIGNALS)["soil_constraint"], {})
    assert cur.rowcount == int(should_trigger)


@pytest.mark.integration
def test_soil_missing_unit_identity_is_not_grouped_by_label(spatial_cursor):
    cur = spatial_cursor
    _soil(cur, 66001, 0, 3, key=None)
    _soil(cur, 66002, 4, 3, key=None)
    cur.execute("""
        SELECT s.source_record_ids FROM staging.parcels p
        CROSS JOIN LATERAL public.parcel_soil_units(p.geom) s
        ORDER BY s.source_record_ids
    """)
    assert [u["source_record_ids"] for u in cur.fetchall()] == [[66001], [66002]]
    cur.execute(dict(_SIGNALS)["soil_constraint"], {})
    assert cur.rowcount == 0


def _zoning(cursor, record_id, adopted, kind, name, general_name=None):
    cursor.execute(
        """
        INSERT INTO staging.zoning (zrecid, adpt_date, ztype, zname, gen_zname, geom)
        SELECT %s, %s::timestamptz, %s, %s, %s, geom FROM staging.parcels
    """,
        (record_id, adopted, kind, name, general_name or name),
    )


def _future(cursor, name, general):
    cursor.execute(
        """
        INSERT INTO staging.future_landuse (globalid, future_lu, general_lu, geom)
        SELECT 'GEO066-FUTURE', %s, %s, geom FROM staging.parcels
    """,
        (name, general),
    )


@pytest.mark.integration
@pytest.mark.parametrize("adoption", ["2026-05-12", None])
def test_newest_zoning_is_selected_before_filtering_for_divergence(
    spatial_cursor, adoption
):
    cur = spatial_cursor
    # With a dated rezoning it wins over undated mapping. With no dates, the
    # higher record ID is the stable tie-breaker for both report and signal.
    _zoning(cur, 66001, None, "C", "Commercial Office")
    _zoning(cur, 66002, adoption, "R", "Residential Low Density")
    _future(cur, "Neighborhood housing", "Low Density Residential")
    cur.execute("""
        SELECT z.zrecid FROM staging.parcels p
        CROSS JOIN LATERAL public.parcel_center_zoning(p.geom) z
    """)
    assert cur.fetchone()["zrecid"] == 66002
    cur.execute(dict(_SIGNALS)["zoning_mismatch"], {})
    assert cur.rowcount == 0  # The older commercial district cannot survive.
    cur.execute(
        "UPDATE staging.future_landuse SET general_lu = 'Industrial', future_lu = 'Employment' "
    )
    cur.execute(dict(_SIGNALS)["zoning_mismatch"], {})
    cur.execute("SELECT evidence FROM public.development_signals")
    evidence = cur.fetchone()["evidence"]
    assert evidence["current_zoning_id"] == 66002
    assert evidence["current_zname"] == "Residential Low Density"


@pytest.mark.integration
@pytest.mark.parametrize(
    "kind,name,general_name,future,expected",
    [
        (
            "M",
            "Mixed Residential Commercial",
            "Mixed Use",
            "Mixed Use - Residential and Commerical",
            False,
        ),
        ("M", "Mixed Residential Commercial", "Mixed Use", "Agriculture", True),
        (
            "C",
            "Commercial Office",
            "Highway Commercial",
            "Mixed Use - Commerical and Industrial",
            False,
        ),
        ("C", "Rural Residential", "Low Density Residential", "Agriculture", False),
        ("A", "Commercial", "Low Density Residential", "Industrial", False),
        ("A", "Farming", "Resource Protection", "Industrial", True),
        ("R", "Residential Low Density", "Low Density Residential", "Industrial", True),
    ],
)
def test_zoning_screen_respects_county_labels_and_abstains_on_conflicting_codes(
    spatial_cursor, kind, name, general_name, future, expected
):
    cur = spatial_cursor
    _zoning(cur, 66001, None, kind, name, general_name)
    _future(cur, "Future test designation", future)
    cur.execute(dict(_SIGNALS)["zoning_mismatch"], {})
    assert cur.rowcount == int(expected)
    if expected:
        cur.execute("SELECT evidence FROM public.development_signals")
        assert cur.fetchone()["evidence"]["general_lu"] == future


@pytest.mark.integration
def test_future_land_use_selection_precedes_comparison(spatial_cursor):
    cur = spatial_cursor
    _zoning(cur, 66001, None, "R", "Residential Low Density")
    _future(cur, "Employment", "Industrial")
    cur.execute("""
        INSERT INTO staging.future_landuse (globalid, future_lu, general_lu, adopt_date, geom)
        SELECT 'GEO066-NEW', 'Neighborhood housing', 'Low Density Residential', '2026-01-01', geom
        FROM staging.parcels
    """)
    cur.execute(dict(_SIGNALS)["zoning_mismatch"], {})
    assert cur.rowcount == 0
