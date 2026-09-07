"""Explicit record search retains source policy and literal search semantics."""

import psycopg2
from psycopg2.extras import Json

from api.tests.conftest import DB_ENV


def test_search_finds_public_reference_in_context_record_and_respects_policy(client):
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT source_evidence FROM public.intelligence_events WHERE event_key = %s",
                ("development:test-project",),
            )
            original = cur.fetchone()[0]
            sources = [{**item} for item in original]
            sources[0] = {
                **sources[0],
                "excerpt": "Public reference LD 2025-5-1, schedule review only.",
                "details": {**sources[0]["details"], "discovery_eligible": False},
            }
            cur.execute(
                "UPDATE public.intelligence_events SET source_evidence = %s WHERE event_key = %s",
                (Json(sources), "development:test-project"),
            )
    try:
        assert not any(
            event["event_key"] == "development:test-project"
            for event in client.get("/api/feed").json()["events"]
        )
        response = client.get("/api/feed", params={"q": "ld 2025-5-1"})
        assert response.status_code == 200, response.text
        assert [event["event_key"] for event in response.json()["events"]] == [
            "development:test-project"
        ]
        normalized = client.get("/api/feed", params={"q": "LD2025-5-1"})
        assert [event["event_key"] for event in normalized.json()["events"]] == [
            "development:test-project"
        ]
        for query in ["%", "' OR TRUE --", "not a recorded reference"]:
            result = client.get("/api/feed", params={"q": query})
            assert result.status_code == 200, result.text
            assert result.json()["events"] == []

        with psycopg2.connect(DB_ENV["DATABASE_URL"]) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE staging.public_proceedings SET metadata_quality = %s WHERE id = 1",
                    (Json({"status": "review_required"}),),
                )
        assert (
            client.get("/api/feed", params={"q": "LD 2025-5-1"}).json()["events"] == []
        )
    finally:
        with psycopg2.connect(DB_ENV["DATABASE_URL"]) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE public.intelligence_events SET source_evidence = %s WHERE event_key = %s",
                    (Json(original), "development:test-project"),
                )
                cur.execute(
                    "UPDATE staging.public_proceedings SET metadata_quality = %s WHERE id = 1",
                    (Json({"status": "ready"}),),
                )
