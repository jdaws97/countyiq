"""Site evidence revisions and private inquiry persistence across accounts."""

from uuid import uuid4

from api.tests.conftest import TEST_PIDN
from api.tests.test_flood_screening import (  # noqa: F401
    restore_flood_test_records,
    set_mapping,
)
from api.tests.test_watchspaces import create, watch_client  # noqa: F401


def inquiry():
    return {
        "id": str(uuid4()),
        "pidn": TEST_PIDN,
        "label": "Client site",
        "proposed_use": "A small workshop",
        "note": "Ask about sewer capacity",
        "questions": "Who can confirm the access permit?",
        "status": "researching",
        "reviewed_revision": None,
        "updated_at": "2026-10-03T12:00:00Z",
    }


def test_inquiries_are_private_preserved_for_older_clients_and_versioned(watch_client):  # noqa: F811
    client = watch_client
    _, owner = create(client)
    _, other = create(client)
    item = inquiry()
    saved = client.put(
        "/api/watchspaces/current",
        headers=owner,
        json={"version": 0, "items": [], "site_inquiries": [item]},
    )
    assert saved.status_code == 200
    assert (
        client.get("/api/watchspaces/current", headers=other).json()["site_inquiries"]
        == []
    )
    older = client.put(
        "/api/watchspaces/current", headers=owner, json={"version": 1, "items": []}
    )
    assert older.status_code == 200
    assert older.json()["site_inquiries"][0]["note"] == item["note"]
    conflict = client.put(
        "/api/watchspaces/current",
        headers=owner,
        json={"version": 1, "items": [], "site_inquiries": []},
    )
    assert conflict.status_code == 409
    invalid = client.put(
        "/api/watchspaces/current",
        headers=owner,
        json={"version": 2, "items": [], "site_inquiries": [item, item]},
    )
    assert invalid.status_code == 422
    assert client.delete("/api/watchspaces/current", headers=owner).status_code == 204
    assert (
        client.get("/api/watchspaces/current", headers=owner).json()["site_inquiries"]
        == []
    )


def test_packet_revision_is_stable_and_changes_with_mapping(client):
    route = f"/api/parcels/{TEST_PIDN}/intake"
    first = client.get(route)
    assert first.status_code == 200
    assert first.json()["revision"] == client.get(route).json()["revision"]
    assert len(first.json()["sources"]) == 4
    set_mapping("D", "F")
    changed = client.get(route).json()
    assert changed["revision"] != first.json()["revision"]
    assert changed["report"]["flood_zone"]["status"] == "unknown"
    assert "buildability" in changed["scope_note"]
