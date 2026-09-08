"""Followed activity filters the full result set before ranking and pagination."""

import psycopg2
from psycopg2.extras import Json

from api.tests.conftest import DB_ENV, TEST_MUNICIPALITY, TEST_PIDN


def test_empty_watches_do_not_fall_back_to_county_activity(client):
    response = client.get("/api/feed", params={"watched_only": True})
    assert response.status_code == 200, response.text
    assert response.json()["events"] == []
    assert response.json()["has_more"] is False


def test_following_matches_any_subject_before_pagination_and_keeps_explicit_history(
    client,
):
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT source_evidence FROM public.intelligence_events WHERE event_key=%s",
            ("parcel:test-transfer",),
        )
        original = cur.fetchone()[0]
        changed = [
            {**item, "details": {**item["details"], "discovery_eligible": False}}
            for item in original
        ]
        cur.execute(
            "UPDATE public.intelligence_events SET related_pidns=ARRAY['followed-only'], source_evidence=%s WHERE event_key=%s",
            (Json(changed), "parcel:test-transfer"),
        )
    try:
        parcel = client.get(
            "/api/feed",
            params={"watched_only": True, "boost_pidns": "followed-only", "limit": 1},
        )
        assert parcel.status_code == 200, parcel.text
        assert [event["event_key"] for event in parcel.json()["events"]] == [
            "parcel:test-transfer"
        ]
        assert parcel.json()["has_more"] is False
        combined = {
            "watched_only": True,
            "boost_pidns": "followed-only",
            "boost_project_keys": "project:test-main-street",
            "limit": 1,
        }
        first = client.get("/api/feed", params=combined).json()
        second = client.get("/api/feed", params={**combined, "offset": 1}).json()
        assert first["has_more"] is True
        assert {event["event_key"] for event in first["events"] + second["events"]} == {
            "parcel:test-transfer",
            "development:test-project",
        }
        municipality = client.get(
            "/api/feed",
            params={"watched_only": True, "boost_municipalities": TEST_MUNICIPALITY},
        ).json()
        assert len(municipality["events"]) == 2
    finally:
        with psycopg2.connect(DB_ENV["DATABASE_URL"]) as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE public.intelligence_events SET related_pidns=%s, source_evidence=%s WHERE event_key=%s",
                ([TEST_PIDN], Json(original), "parcel:test-transfer"),
            )
