"""Real PostGIS coverage and source-policy regressions for intake screening."""

import psycopg2
import pytest

from api.tests.conftest import DB_ENV, TEST_PIDN
from api.tests.test_parcel_spatial_facts import PARCEL_FULL, PARCEL_RIGHT


@pytest.fixture(autouse=True)
def restore_flood_test_records(client):
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE TEMP TABLE flood_backup AS TABLE staging.flood_zones")
            cur.execute(
                "CREATE TEMP TABLE refresh_backup AS TABLE meta.asset_refresh_status"
            )
        try:
            yield
        finally:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM staging.flood_zones")
                cur.execute(
                    "INSERT INTO staging.flood_zones SELECT * FROM flood_backup"
                )
                cur.execute("DELETE FROM meta.asset_refresh_status")
                cur.execute(
                    "INSERT INTO meta.asset_refresh_status SELECT * FROM refresh_backup"
                )
                cur.execute(
                    "UPDATE staging.parcels SET geom = ST_GeomFromText(%s, 4326) WHERE pidn = %s",
                    (PARCEL_FULL, TEST_PIDN),
                )


def set_mapping(zone="X", sfha="F", geometry=PARCEL_FULL, copies=1):
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM staging.flood_zones")
        for index in range(copies):
            cur.execute(
                """INSERT INTO staging.flood_zones
                (fld_ar_id, fld_zone, sfha_tf, geom, source_url)
                VALUES (%s, %s, %s, ST_GeomFromText(%s, 4326), %s)""",
                (
                    f"flood-test-{index}",
                    zone,
                    sfha,
                    geometry,
                    "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28",
                ),
            )


@pytest.mark.parametrize(
    ("zone", "sfha", "geometry", "expected"),
    [
        ("X", "F", PARCEL_FULL, "no_overlap"),
        ("X", "F", PARCEL_RIGHT, "unknown"),
        ("D", "F", PARCEL_FULL, "unknown"),
        ("UNCLASSIFIED", "", PARCEL_FULL, "unknown"),
        ("AE", "T", PARCEL_RIGHT, "overlap"),
    ],
)
def test_coverage_is_required_for_a_supported_negative(
    client, zone, sfha, geometry, expected
):
    set_mapping(zone, sfha, geometry)
    response = client.get(f"/api/parcels/{TEST_PIDN}")
    assert response.status_code == 200
    flood = response.json()["flood_zone"]
    assert flood["status"] == expected
    assert flood["evidence"]["effective_at"] is None
    assert flood["in_flood_zone"] == (expected == "overlap")
    if expected == "unknown":
        assert flood["overlap_pct"] is None


def test_duplicate_polygons_do_not_inflate_overlap(client):
    set_mapping("AE", "T", PARCEL_RIGHT, copies=2)
    flood = client.get(f"/api/parcels/{TEST_PIDN}/summary").json()["flood_zone"]
    assert flood["status"] == "overlap"
    assert flood["overlap_pct"] == pytest.approx(50, abs=0.1)


def test_empty_coverage_and_missing_parcel_geometry_are_unknown(client):
    set_mapping(copies=0)
    flood = client.get(f"/api/parcels/{TEST_PIDN}").json()["flood_zone"]
    assert flood["status"] == "unknown"
    assert flood["mapped_coverage_pct"] is None
    set_mapping()
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE staging.parcels SET geom = NULL WHERE pidn = %s", (TEST_PIDN,)
        )
    flood = client.get(f"/api/parcels/{TEST_PIDN}").json()["flood_zone"]
    assert flood["status"] == "unknown"
    assert flood["mapped_coverage_pct"] is None


def test_failed_latest_refresh_qualifies_loaded_mapping(client):
    set_mapping()
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO meta.asset_refresh_status
            (asset_key, job_name, run_id, status, finished_at, last_success_at, failure_reason)
            VALUES ('fema_flood_zones', 'fema_refresh', 'test', 'failure', NOW(), NOW(), 'step_failed')"""
        )
    flood = client.get(f"/api/parcels/{TEST_PIDN}").json()["flood_zone"]
    assert flood["status"] == "no_overlap"
    assert flood["freshness"]["status"] == "stale"


def test_boundary_contact_is_not_positive_overlap(client):
    adjacent = "MULTIPOLYGON(((-76.795 39.901, -76.795 39.905, -76.791 39.905, -76.791 39.901, -76.795 39.901)))"
    set_mapping("AE", "T", adjacent)
    flood = client.get(f"/api/parcels/{TEST_PIDN}").json()["flood_zone"]
    assert flood["status"] == "unknown"
    assert flood["in_flood_zone"] is False
    assert flood["mapped_coverage_pct"] is None


def test_rounding_cannot_erase_a_coverage_gap(client):
    tiny_gap = PARCEL_FULL.replace("-76.7950", "-76.79500001")
    set_mapping("X", "F", tiny_gap)
    flood = client.get(f"/api/parcels/{TEST_PIDN}").json()["flood_zone"]
    assert flood["mapped_coverage_pct"] == 100.0
    assert flood["status"] == "unknown"


@pytest.mark.parametrize(
    "condition",
    [
        "rights_status = 'paused'",
        "derived_product_allowed = FALSE",
        "review_due_on = CURRENT_DATE - 1",
    ],
)
def test_source_withdrawal_blocks_all_parcel_flood_surfaces(client, condition):
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT rights_status, derived_product_allowed, review_due_on FROM meta.source_rights WHERE source_key = 'fema_nfhl'"
            )
            original = cur.fetchone()
            cur.execute(
                f"UPDATE meta.source_rights SET {condition} WHERE source_key = 'fema_nfhl'"
            )
        conn.commit()
        try:
            for suffix in ("", "/summary", "/intake"):
                assert (
                    client.get(f"/api/parcels/{TEST_PIDN}{suffix}").status_code == 503
                )
        finally:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE meta.source_rights SET rights_status=%s, derived_product_allowed=%s, review_due_on=%s WHERE source_key = 'fema_nfhl'",
                    original,
                )
