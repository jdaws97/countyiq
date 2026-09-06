"""Scoped decisions remain in history without becoming discovery leads."""

import copy
import psycopg2
from psycopg2.extras import Json
from api.tests.conftest import DB_ENV


def test_scoped_decision_discovery_and_explicit_history(client):
    from api.routes import feed

    key = "development:test-project"
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT source_evidence,event_type FROM public.intelligence_events WHERE event_key=%s",
                (key,),
            )
            sources, previous_type = cur.fetchone()
            changed = copy.deepcopy(sources)
            for source in changed:
                source.setdefault("details", {}).update(
                    discovery_eligible=False,
                    matter_category="public_works",
                    decision_scope="bond",
                )
            cur.execute(
                "UPDATE public.intelligence_events SET source_evidence=%s,event_type='scoped_decision' WHERE event_key=%s",
                (Json(changed), key),
            )
    try:
        default = feed.fetch_feed(category="development", since_days=None)
        assert key not in {e["event_key"] for e in default["events"]}
        history = feed.fetch_feed(event_keys=[key], since_days=None)
        assert [e["event_key"] for e in history["events"]] == [key]
        assert history["events"][0]["event_type"] == "scoped_decision"
        explicit = feed.fetch_feed(matter_category="public_works", since_days=None)
        assert key in {e["event_key"] for e in explicit["events"]}
    finally:
        with psycopg2.connect(DB_ENV["DATABASE_URL"]) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE public.intelligence_events SET source_evidence=%s,event_type=%s WHERE event_key=%s",
                    (Json(sources), previous_type, key),
                )
