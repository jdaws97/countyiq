"""Real-role integration: private workspace ownership, concurrency and inbox scope."""

import time
from uuid import uuid4
from types import SimpleNamespace
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
import psycopg2
import pytest
from api.tests.conftest import DB_ENV, TEST_PIDN


KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
ISSUER = "https://countyiq-test.cloudflareaccess.com"


def admin():
    return psycopg2.connect(DB_ENV["DATABASE_URL"])


@pytest.fixture
def watch_client(client, monkeypatch):
    from api.routes import watchspaces

    monkeypatch.setenv("COUNTYIQ_WATCH_SYNC_ENABLED", "true")
    from api.lib import auth

    monkeypatch.setattr(auth.verification_limiter, "allow", lambda ip: True)
    monkeypatch.setenv("COUNTYIQ_AUTH_PROVIDER", "cloudflare_access")
    monkeypatch.setenv("COUNTYIQ_ACCESS_ISSUER", ISSUER)
    monkeypatch.setenv("COUNTYIQ_ACCESS_AUD", "test-audience")
    monkeypatch.setattr(
        auth,
        "signing_keys",
        lambda issuer: SimpleNamespace(
            get_signing_key_from_jwt=lambda value: SimpleNamespace(key=KEY.public_key())
        ),
    )

    monkeypatch.setattr(watchspaces.request_limiter, "allow", lambda ip: True)
    return client


def create(client, subject=None, email="tester@example.test"):
    subject = subject or str(uuid4())
    token = jwt.encode(
        {
            "iss": ISSUER,
            "aud": ["test-audience"],
            "sub": subject,
            "email": email,
            "type": "app",
            "iat": int(time.time()) - 1,
            "exp": int(time.time()) + 300,
        },
        KEY,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )
    headers = {"Cf-Access-Jwt-Assertion": token, "X-CountyIQ-Workspace": "1"}
    response = client.post("/api/session", headers=headers)
    assert response.status_code == 200, response.text
    headers["X-CountyIQ-User"] = response.json()["user"]["id"]
    return subject, headers


def test_workspace_isolation_and_version_conflicts(watch_client):
    c = watch_client
    token, a = create(c)
    _, b = create(c)
    item = {"kind": "parcel", "subject_key": TEST_PIDN, "label": "My parcel"}
    assert c.get("/api/watchspaces/current").status_code == 401
    assert (
        c.put(
            "/api/watchspaces/current", headers=a, json={"version": 0, "items": [item]}
        ).status_code
        == 200
    )
    assert c.get("/api/watchspaces/current", headers=b).json()["items"] == []
    assert (
        c.put(
            "/api/watchspaces/current", headers=a, json={"version": 0, "items": []}
        ).status_code
        == 409
    )
    assert c.get("/api/watchspaces/current", headers=a).json()["items"] == [item]
    with admin() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT token_hash FROM public.watchspaces WHERE owner_user_id=(SELECT user_id FROM public.app_identities WHERE subject=%s)",
            (token,),
        )
        assert cur.fetchone()[0] is None
    assert c.delete("/api/watchspaces/current", headers=a).status_code == 204
    assert c.get("/api/watchspaces/current", headers=a).json()["items"] == []
    assert c.get("/api/watchspaces/current", headers=b).status_code == 200


def test_refresh_excludes_existing_events_and_is_idempotent(watch_client):
    c = watch_client
    token, auth = create(c)
    c.put(
        "/api/watchspaces/current",
        headers=auth,
        json={
            "version": 0,
            "items": [
                {"kind": "parcel", "subject_key": TEST_PIDN, "label": "My parcel"}
            ],
        },
    )
    with admin() as conn, conn.cursor() as cur:
        cur.execute("SELECT public.refresh_watch_notifications()")
        assert (
            c.get("/api/watchspaces/notifications", headers=auth).json()[
                "notifications"
            ]
            == []
        )
        cur.execute(
            "UPDATE public.watch_items SET added_at=NOW()-INTERVAL '1 day' WHERE workspace_id=(SELECT workspace_id FROM public.watchspaces WHERE owner_user_id=(SELECT user_id FROM public.app_identities WHERE subject=%s))",
            (token,),
        )
        cur.execute("SELECT public.refresh_watch_notifications()")
        conn.commit()
    inbox = c.get("/api/watchspaces/notifications", headers=auth)
    assert inbox.status_code == 200, inbox.text
    assert len(inbox.json()["notifications"]) == 2
    with admin() as conn, conn.cursor() as cur:
        # A rebuild may update extraction timestamps; the same source event stays one notification.
        cur.execute(
            "UPDATE public.intelligence_events SET detected_at=detected_at+INTERVAL '1 second'"
        )
        cur.execute("SELECT public.refresh_watch_notifications()")
        assert cur.fetchone()[0] == 0
    assert (
        len(
            c.get("/api/watchspaces/notifications", headers=auth).json()[
                "notifications"
            ]
        )
        == 2
    )


def test_acknowledgement_only_marks_explicit_ids_in_own_workspace(watch_client):
    c = watch_client
    token_a, a = create(c)
    token_b, b = create(c)
    with admin() as conn, conn.cursor() as cur:
        ids = []
        for token in [token_a, token_a, token_b]:
            cur.execute(
                """INSERT INTO public.watch_notifications(workspace_id,event_key,event_detected_at)
                SELECT workspace_id,%s,NOW() FROM public.watchspaces WHERE owner_user_id=(SELECT user_id FROM public.app_identities WHERE subject=%s) RETURNING notification_id""",
                ("ack-test-" + str(len(ids)), token),
            )
            ids.append(cur.fetchone()[0])
    assert (
        c.post(
            "/api/watchspaces/notifications/read",
            headers=a,
            json={"notification_ids": [ids[1], ids[2]]},
        ).status_code
        == 200
    )
    with admin() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT notification_id,read_at IS NOT NULL FROM public.watch_notifications WHERE notification_id=ANY(%s) ORDER BY notification_id",
            (ids,),
        )
        assert cur.fetchall() == [(ids[0], False), (ids[1], True), (ids[2], False)]
    assert (
        c.post(
            "/api/watchspaces/notifications/read",
            headers=b,
            json={"notification_ids": []},
        ).status_code
        == 422
    )


def test_identity_subject_controls_ownership_and_email_does_not_merge_accounts(
    watch_client,
):
    c = watch_client
    subject, a = create(c)
    _, b = create(c)  # same email, different external subject
    _, a_again = create(c, subject=subject, email="changed@example.test")
    assert (
        c.get("/api/session", headers=a).json()["workspace_id"]
        == c.get("/api/session", headers=a_again).json()["workspace_id"]
    )
    assert (
        c.get("/api/session", headers=a).json()["workspace_id"]
        != c.get("/api/session", headers=b).json()["workspace_id"]
    )


def test_saved_investigations_and_searches_are_private(watch_client):
    c = watch_client
    _, a = create(c)
    _, b = create(c)
    state = {
        "version": 0,
        "items": [],
        "saved_searches": [
            {
                "id": "radar-one",
                "kind": "radar",
                "name": "Commercial",
                "path": "/radar?min_score=40",
                "createdAt": "2026-09-04T12:00:00Z",
            }
        ],
        "comparison": [TEST_PIDN],
        "recent_investigations": [
            {
                "path": "/property/" + TEST_PIDN,
                "label": "Main Street",
                "visitedAt": "2026-09-04T12:00:00Z",
            }
        ],
    }
    assert c.put("/api/watchspaces/current", headers=a, json=state).status_code == 200
    assert (
        c.get("/api/watchspaces/current", headers=a).json()["saved_searches"][0]["name"]
        == "Commercial"
    )
    assert c.get("/api/watchspaces/current", headers=b).json()["saved_searches"] == []
    state["version"] = 1
    state["saved_searches"][0]["path"] = "https://evil.example"
    assert c.put("/api/watchspaces/current", headers=a, json=state).status_code == 422


def test_anonymous_codes_and_cross_origin_writes_are_rejected(watch_client):
    c = watch_client
    assert c.post("/api/watchspaces").status_code == 401
    assert (
        c.get(
            "/api/watchspaces/current", headers={"Authorization": "Bearer " + "a" * 43}
        ).status_code
        == 401
    )
    _, headers = create(c)
    headers["Origin"] = "https://evil.example"
    assert (
        c.put(
            "/api/watchspaces/current",
            headers=headers,
            json={"version": 0, "items": []},
        ).status_code
        == 403
    )


def test_switched_login_cannot_upload_previous_users_local_cache(watch_client):
    c = watch_client
    _, a = create(c)
    _, b = create(c)
    b["X-CountyIQ-User"] = a["X-CountyIQ-User"]
    assert (
        c.put(
            "/api/watchspaces/current", headers=b, json={"version": 0, "items": []}
        ).status_code
        == 401
    )


def test_persisted_inbox_event_disappears_when_municipality_is_paused(watch_client):
    _, headers = create(watch_client)
    with admin() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT workspace_id FROM public.workspace_members WHERE user_id=%s",
                (headers["X-CountyIQ-User"],),
            )
            workspace_id = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO public.watch_notifications(workspace_id,event_key,event_detected_at) SELECT %s,event_key,detected_at FROM public.intelligence_events WHERE event_key='development:test-project'",
                (workspace_id,),
            )
            cursor.execute(
                "SELECT rights_status FROM meta.municipality_source_rights WHERE source_key='hanover_borough_council'"
            )
            previous = cursor.fetchone()[0]
    before = watch_client.get("/api/watchspaces/notifications", headers=headers)
    assert before.status_code == 200, before.text
    assert any(
        item["event"]["event_key"] == "development:test-project"
        for item in before.json()["notifications"]
    )
    try:
        with admin() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE meta.municipality_source_rights SET rights_status='paused' WHERE source_key='hanover_borough_council'"
                )
        after = watch_client.get("/api/watchspaces/notifications", headers=headers)
        assert after.status_code == 200, after.text
        assert after.json()["notifications"] == []
    finally:
        with admin() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE meta.municipality_source_rights SET rights_status=%s WHERE source_key='hanover_borough_council'",
                    (previous,),
                )
                cursor.execute(
                    "DELETE FROM public.watch_notifications WHERE workspace_id=%s",
                    (workspace_id,),
                )
