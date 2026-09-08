"""Calendar-date filtering and cache-key regressions for the intelligence feed."""

import psycopg2

from api.tests.conftest import DB_ENV

EVENT_KEY = "development:test-project"


def test_since_days_uses_event_date_and_detected_date_fallback(client):
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT event_date, detected_at FROM public.intelligence_events "
            "WHERE event_key = %s",
            (EVENT_KEY,),
        )
        original = cur.fetchone()
        cur.execute(
            "UPDATE public.intelligence_events "
            "SET event_date = CURRENT_DATE - 120, detected_at = NOW() "
            "WHERE event_key = %s",
            (EVENT_KEY,),
        )
    try:
        assert EVENT_KEY not in _event_keys(client, 90)
        assert EVENT_KEY in _event_keys(client, 365)

        with psycopg2.connect(DB_ENV["DATABASE_URL"]) as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE public.intelligence_events "
                "SET event_date = NULL, detected_at = NOW() - INTERVAL '120 days' "
                "WHERE event_key = %s",
                (EVENT_KEY,),
            )
        assert EVENT_KEY not in _event_keys(client, 91)
        with psycopg2.connect(DB_ENV["DATABASE_URL"]) as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE public.intelligence_events "
                "SET detected_at = NOW() WHERE event_key = %s",
                (EVENT_KEY,),
            )
        assert EVENT_KEY in _event_keys(client, 92)
    finally:
        with psycopg2.connect(DB_ENV["DATABASE_URL"]) as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE public.intelligence_events "
                "SET event_date = %s, detected_at = %s WHERE event_key = %s",
                (*original, EVENT_KEY),
            )


def test_priority_and_latest_return_their_own_order_from_warmed_cache(client):
    parcel_key = "parcel:test-transfer"
    event_keys = [EVENT_KEY, parcel_key]
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT event_key, event_type, event_date FROM public.intelligence_events "
            "WHERE event_key = ANY(%s::text[])",
            (event_keys,),
        )
        originals = cur.fetchall()
        cur.execute(
            "UPDATE public.intelligence_events "
            "SET event_type = 'approval', event_date = CURRENT_DATE - 7 "
            "WHERE event_key = %s",
            (EVENT_KEY,),
        )
        cur.execute(
            "UPDATE public.intelligence_events "
            "SET event_type = 'transfer', event_date = CURRENT_DATE "
            "WHERE event_key = %s",
            (parcel_key,),
        )
    try:
        params = {"event_keys": ",".join(event_keys), "since_days": 365, "limit": 10}
        for sort, expected in [
            ("priority", [EVENT_KEY, parcel_key]),
            ("latest", [parcel_key, EVENT_KEY]),
            ("priority", [EVENT_KEY, parcel_key]),
        ]:
            response = client.get("/api/feed", params={**params, "sort": sort})
            assert response.status_code == 200, response.text
            assert [
                event["event_key"] for event in response.json()["events"]
            ] == expected
    finally:
        with psycopg2.connect(DB_ENV["DATABASE_URL"]) as conn, conn.cursor() as cur:
            cur.executemany(
                "UPDATE public.intelligence_events "
                "SET event_type = %s, event_date = %s WHERE event_key = %s",
                [
                    (event_type, event_date, key)
                    for key, event_type, event_date in originals
                ],
            )


def _event_keys(client, since_days: int) -> set[str]:
    response = client.get(
        "/api/feed",
        params={"since_days": since_days, "event_keys": EVENT_KEY},
    )
    assert response.status_code == 200, response.text
    return {event["event_key"] for event in response.json()["events"]}
