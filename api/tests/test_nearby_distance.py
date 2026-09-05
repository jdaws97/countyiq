"""A degree approximation must not discard in-radius east/west neighbors."""
import psycopg2
import pytest
from api.tests.conftest import DB_ENV, TEST_PIDN, OTHER_PIDN


@pytest.mark.parametrize("bearing", [90, 270])
def test_nearby_includes_east_west_parcel_at_radius_edge(client, bearing):
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pidn, ST_AsEWKB(geom) FROM staging.parcels WHERE valid_to IS NULL AND pidn=ANY(%s)", ([TEST_PIDN, OTHER_PIDN],))
            original = cur.fetchall()
            cur.execute("UPDATE staging.parcels SET geom=ST_Multi(ST_Buffer(ST_SetSRID(ST_Point(-76.7,40),4326),0.000001)) WHERE valid_to IS NULL AND pidn=%s", (OTHER_PIDN,))
            cur.execute("UPDATE staging.parcels SET geom=ST_Multi(ST_Buffer(ST_Project(ST_SetSRID(ST_Point(-76.7,40),4326)::geography,395,radians(%s))::geometry,0.000001)) WHERE valid_to IS NULL AND pidn=%s", (bearing, TEST_PIDN))
    try:
        response = client.get("/api/parcels/near", params={"pidn": OTHER_PIDN, "radius_m": 400})
        assert response.status_code == 200, response.text
        assert TEST_PIDN in [p["pidn"] for p in response.json()["parcels"]]
        response = client.get("/api/feed", params={"near_pidns": OTHER_PIDN, "near_radius_m": 400})
        assert response.status_code == 200, response.text
        assert any(TEST_PIDN in e["related_pidns"] for e in response.json()["events"])
        outside = client.get("/api/feed", params={"near_pidns": OTHER_PIDN, "near_radius_m": 380})
        assert outside.status_code == 200, outside.text
        assert not any(TEST_PIDN in e["related_pidns"] for e in outside.json()["events"])
    finally:
        with psycopg2.connect(DB_ENV["DATABASE_URL"]) as conn:
            with conn.cursor() as cur:
                for pidn, geom in original:
                    cur.execute("UPDATE staging.parcels SET geom=ST_GeomFromEWKB(%s) WHERE valid_to IS NULL AND pidn=%s", (geom, pidn))
