"""Ambiguous source names never select an arbitrary owner or watch."""

import psycopg2
from api.tests.conftest import DB_ENV


def test_shared_alias_hides_owner_link_and_watch_until_resolved(client):
    owner_id = client.get("/api/owners/top?limit=1").json()[0]["owner_id"]
    params = {"category": "development", "boost_entity_ids": str(owner_id)}

    def project():
        response = client.get("/api/feed", params=params)
        assert response.status_code == 200, response.text
        return next(
            e
            for e in response.json()["events"]
            if e["event_key"] == "development:test-project"
        )

    baseline = project()
    assert baseline["entity_links"][0]["owner_id"] == owner_id
    assert "Watched subject" in baseline["importance_reasons"]
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO public.owners (canonical_name, entity_type, aliases) VALUES (%s, 'business', %s) RETURNING owner_id",
                ("Different Fixture Organization", ["  ALPHA HOLDINGS LLC  "]),
            )
            competing_id = cur.fetchone()[0]
    try:
        ambiguous = project()
        assert ambiguous["entity_links"] == []
        assert "Watched subject" not in ambiguous["importance_reasons"]
        response = client.get(
            "/api/feed", params={"category": "development", "entity_ids": str(owner_id)}
        )
        assert response.status_code == 200, response.text
        assert response.json()["events"] == []
    finally:
        with psycopg2.connect(DB_ENV["DATABASE_URL"]) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM public.owners WHERE owner_id=%s", (competing_id,)
                )
    restored = project()
    assert restored["entity_links"] == baseline["entity_links"]
    assert "Watched subject" in restored["importance_reasons"]
