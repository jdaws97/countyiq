"""Regression coverage for the shared parcel zoning and soil SQL functions."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg2
import pytest

from api.tests.conftest import DB_ENV, TEST_MUNICIPALITY, TEST_PIDN
from api.routes import parcels


SOIL_IDS = (991001, 991002, 991003)
ZONING_IDS = (992001, 992002, 992003)
SOIL_LAYER_URL = "https://soils.example.test/arcgis/rest/services/Soils/FeatureServer/0"
PARCEL_LEFT_LOWER = (
    "MULTIPOLYGON(((-76.7990 39.9010, -76.7990 39.9030, "
    "-76.7970 39.9030, -76.7970 39.9010, -76.7990 39.9010)))"
)
PARCEL_LEFT_UPPER = (
    "MULTIPOLYGON(((-76.7990 39.9030, -76.7990 39.9050, "
    "-76.7970 39.9050, -76.7970 39.9030, -76.7990 39.9030)))"
)
PARCEL_RIGHT = (
    "MULTIPOLYGON(((-76.7970 39.9010, -76.7970 39.9050, "
    "-76.7950 39.9050, -76.7950 39.9010, -76.7970 39.9010)))"
)
PARCEL_FULL = (
    "MULTIPOLYGON(((-76.7990 39.9010, -76.7990 39.9050, "
    "-76.7950 39.9050, -76.7950 39.9010, -76.7990 39.9010)))"
)


@pytest.fixture
def spatial_fact_rows() -> Iterator[None]:
    """Remove only this module's untruncated soil and zoning fixture rows."""

    try:
        yield
    finally:
        with psycopg2.connect(DB_ENV["DATABASE_URL"]) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM staging.soils WHERE objectid = ANY(%s)",
                    (list(SOIL_IDS),),
                )
                cur.execute(
                    "DELETE FROM staging.zoning WHERE zrecid = ANY(%s)",
                    (list(ZONING_IDS),),
                )


def _insert_soils() -> None:
    rows = (
        (SOIL_IDS[0], PARCEL_LEFT_LOWER, "Well drained", "Very limited"),
        (SOIL_IDS[1], PARCEL_LEFT_UPPER, "Well drained", "Very limited"),
        (SOIL_IDS[2], PARCEL_RIGHT, "Poorly drained", "Somewhat limited"),
    )
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            for objectid, geom, drainage, septic_rating in rows:
                cur.execute(
                    """
                    INSERT INTO staging.soils (
                        objectid, map_unit_symbol, map_unit_name, map_unit_key,
                        drainage, capability_class, permeability, septic_rating,
                        slope_low, slope_high, representative_slope, hydric_rating,
                        hydrologic_group, relative_value, source_url, geom
                    ) VALUES (
                        %s, 'Mu', 'Mapped unit', 'same-map-unit',
                        %s, 3, 1.5, %s, 2, 8, 5, 'No', 'B', 'Moderate', %s,
                        ST_GeomFromText(%s, 4326)
                    )
                    """,
                    (objectid, drainage, septic_rating, SOIL_LAYER_URL, geom),
                )


def test_parcel_soils_group_fragments_and_preserve_source_receipt(
    client, spatial_fact_rows
):
    _insert_soils()

    response = client.get(f"/api/parcels/{TEST_PIDN}")

    assert response.status_code == 200
    payload = response.json()
    soil_profile = payload["soil_profile"]
    assert soil_profile["mapped_coverage_pct"] == pytest.approx(100.0, abs=0.1)
    assert soil_profile["source_record_ids"] == list(SOIL_IDS)
    assert len(soil_profile["units"]) == 2

    by_drainage = {unit["drainage"]: unit for unit in soil_profile["units"]}
    grouped = by_drainage["Well drained"]
    assert grouped["map_unit_key"] == "same-map-unit"
    assert grouped["source_record_ids"] == list(SOIL_IDS[:2])
    assert grouped["coverage_pct"] == pytest.approx(50.0, abs=0.1)
    assert by_drainage["Poorly drained"]["source_record_ids"] == [SOIL_IDS[2]]
    assert by_drainage["Poorly drained"]["coverage_pct"] == pytest.approx(50.0, abs=0.1)

    for source_id in SOIL_IDS[:2]:
        assert str(source_id) in soil_profile["source_url"]
    receipt = next(
        item
        for item in payload["evidence"]
        if item["source_kind"] == "official_soil_layer"
    )
    assert receipt["source_record_id"] == ",".join(str(value) for value in SOIL_IDS)
    assert all(str(source_id) in receipt["url"] for source_id in SOIL_IDS)
    receipt_units = {unit["drainage"]: unit for unit in receipt["details"]["map_units"]}
    assert receipt_units["Well drained"]["source_record_ids"] == list(SOIL_IDS[:2])
    assert receipt_units["Well drained"]["map_unit_key"] == "same-map-unit"


def test_map_summary_preserves_displayed_facts_without_soil_query(
    client, spatial_fact_rows, monkeypatch
):
    _insert_soils()
    report_response = client.get(f"/api/parcels/{TEST_PIDN}")
    assert report_response.status_code == 200
    report = report_response.json()
    assert report["soil_profile"]["units"]
    original_get_cursor = parcels.get_cursor

    class SummaryCursor:
        def __init__(self, cursor):
            self.cursor = cursor

        def execute(self, query, params=None):
            assert "parcel_soil_units" not in query, "Map selection calculated soils"
            return self.cursor.execute(query, params)

        def __getattr__(self, name):
            return getattr(self.cursor, name)

    @contextmanager
    def summary_cursor(**kwargs):
        with original_get_cursor(**kwargs) as cursor:
            yield SummaryCursor(cursor)

    monkeypatch.setattr(parcels, "get_cursor", summary_cursor)
    response = client.get(f"/api/parcels/{TEST_PIDN}/summary")
    assert response.status_code == 200
    assert response.json() == {
        key: report[key]
        for key in (
            "parcel",
            "tax_delinquency",
            "flood_zone",
            "structures",
            "development_momentum",
            "source_explanation",
        )
    }
    assert client.get("/api/parcels/nonexistent/summary").status_code == 404


def test_parcel_zoning_prefers_newest_adoption_then_highest_record_id(
    client, spatial_fact_rows
):
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            for zrecid, code, adopted in (
                (ZONING_IDS[0], "OLD", "2024-01-01"),
                (ZONING_IDS[1], "LOW", "2025-01-01"),
                (ZONING_IDS[2], "HIGH", "2025-01-01"),
            ):
                cur.execute(
                    """
                    INSERT INTO staging.zoning (
                        zrecid, muni_name, zcode, zname, ztype, gen_zcode, gen_zname,
                        adpt_date, source_url, geom
                    ) VALUES (
                        %s, %s, %s, %s, 'C', 'C', 'Commercial', %s, %s,
                        ST_GeomFromText(%s, 4326)
                    )
                    """,
                    (
                        zrecid,
                        TEST_MUNICIPALITY,
                        code,
                        f"{code} district",
                        adopted,
                        "https://zoning.example.test/FeatureServer/0",
                        PARCEL_FULL,
                    ),
                )

    response = client.get(f"/api/parcels/{TEST_PIDN}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["zoning"]["code"] == "HIGH"
    receipt = next(
        item
        for item in payload["evidence"]
        if item["source_kind"] == "official_zoning_layer"
    )
    assert receipt["source_record_id"] == str(ZONING_IDS[2])
    assert receipt["details"]["code"] == "HIGH"
