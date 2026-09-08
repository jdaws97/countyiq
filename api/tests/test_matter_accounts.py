"""A case account retains its sources and retracts when its evidence scope changes."""

# Shared fixtures are requested by pytest by name.
# ruff: noqa: F811

import json
import os
import subprocess
from pathlib import Path

import pytest

from api.tests.conftest import DB_ENV, PIPELINES_DIR, SECOND_PIDN, TEST_PIDN
from api.tests.test_municipal_evidence import append_read, writer
from api.tests.test_municipal_evidence_workflow import (  # noqa: F401
    add_source,
    project_current_sources,
)
from api.tests.test_watchspaces import watch_client  # noqa: F401


def publish_test_account(*, split_latest=False):
    """Use the real validator, persistence boundary and deterministic producer."""
    result = subprocess.run(
        [
            str(PIPELINES_DIR / ".venv/bin/python"),
            str(Path(__file__).parent / "helpers/publish_matter_account.py"),
            TEST_PIDN,
            str(split_latest).lower(),
        ],
        cwd=PIPELINES_DIR,
        env={**os.environ, **DB_ENV, "PYTHONPATH": str(PIPELINES_DIR)},
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def add_case(add_source):
    agenda, _, _ = add_source(
        "Store requests use and parking variances at 1 Main Street."
    )
    minutes, _, payload = add_source(
        "The Board approved the store use and parking variances at 1 Main Street."
    )
    payload["document_kind"] = "minutes"
    with writer() as cur:
        append_read(cur, minutes, payload)
    project_current_sources()
    return agenda, minutes


def test_case_account_replaces_agendas_and_retains_individual_source_history(
    client, add_source
):
    add_case(add_source)
    keys = publish_test_account()
    response = client.get(
        "/api/feed", params={"project_keys": ",".join(keys), "limit": 1}
    )
    assert response.status_code == 200, response.text
    event = next(
        item for item in response.json()["events"] if item["event_key"] in keys
    )
    assert event["matter"]["outcome"] == "approved"
    assert event["why_it_matters"]
    assert len(event["matter"]["history"]) == 2
    assert len({source["document_url"] for source in event["sources"]}) == 2
    assert all(
        source["details"]["passages"][0]["page"] == 1 for source in event["sources"]
    )
    assert {entry["document_kind"] for entry in event["matter"]["history"]} == {
        "agenda",
        "minutes",
    }
    assert not client.get(
        "/api/feed", params={"pidns": TEST_PIDN, "view": "research"}
    ).json()["events"]


def test_new_source_retracts_old_case_until_complete_scope_is_reexplained(
    client, add_source
):
    add_case(add_source)
    keys = publish_test_account()
    assert any(
        item["event_key"] in keys for item in client.get("/api/feed").json()["events"]
    )
    add_source("A separate subdivision application concerns 1 Main Street.")
    project_current_sources()
    assert not any(
        item["event_key"] in keys for item in client.get("/api/feed").json()["events"]
    )
    refreshed = publish_test_account(split_latest=True)
    assert keys[0] in refreshed
    first = client.get(
        "/api/feed", params={"project_keys": ",".join(refreshed), "limit": 1}
    ).json()
    second = client.get(
        "/api/feed",
        params={"project_keys": ",".join(refreshed), "limit": 1, "offset": 1},
    ).json()
    assert first["has_more"]
    assert {first["events"][0]["event_key"], second["events"][0]["event_key"]} == set(
        refreshed
    )
    assert sorted(
        len(item["matter"]["history"])
        for item in [first["events"][0], second["events"][0]]
    ) == [1, 2]


def test_changed_source_withdraws_case_without_waiting_for_a_projection_rebuild(
    client, add_source
):
    agenda, _ = add_case(add_source)
    keys = publish_test_account()
    with writer() as cur:
        cur.execute(
            "UPDATE staging.public_proceedings SET raw_text=raw_text || ' amended' WHERE id=%s",
            (agenda,),
        )
    assert not any(
        item["event_key"] in keys for item in client.get("/api/feed").json()["events"]
    )


@pytest.mark.parametrize(
    "change", ["address", "ambiguous_address", "owner", "global_rights"]
)
def test_matter_accounts_recheck_live_connections_and_global_rights(
    client, add_source, change
):
    add_case(add_source)
    keys = publish_test_account()
    with writer() as cur:
        cur.execute(
            "SELECT pidn, propadr, owner_full FROM staging.parcels "
            "WHERE pidn = ANY(%s) AND valid_to IS NULL",
            ([TEST_PIDN, SECOND_PIDN],),
        )
        original_parcels = cur.fetchall()
        if change == "address":
            cur.execute(
                "UPDATE staging.parcels SET propadr = '99 Different Road' "
                "WHERE pidn = %s AND valid_to IS NULL",
                (TEST_PIDN,),
            )
        elif change == "ambiguous_address":
            cur.execute(
                "UPDATE staging.parcels SET propadr = '1 Main Street' "
                "WHERE pidn = %s AND valid_to IS NULL",
                (SECOND_PIDN,),
            )
        elif change == "owner":
            cur.execute(
                "UPDATE staging.parcels SET owner_full = 'New Owner LLC' "
                "WHERE pidn = %s AND valid_to IS NULL",
                (TEST_PIDN,),
            )
        else:
            cur.execute(
                "UPDATE meta.source_rights SET derived_product_allowed = FALSE "
                "WHERE source_key = 'public_proceedings'"
            )
    try:
        with writer() as cur:
            cur.execute(
                "SELECT related_pidns, related_entities "
                "FROM public.current_municipal_matter_accounts WHERE event_key = ANY(%s)",
                (keys,),
            )
            current = cur.fetchall()
        if change == "owner":
            assert current == [([TEST_PIDN], ["New Owner LLC"])]
        else:
            assert current == []
        response = client.get("/api/feed", params={"project_keys": ",".join(keys)})
        if change == "global_rights":
            assert response.status_code == 503
        else:
            assert response.status_code == 200, response.text
            assert response.json()["events"] == []
    finally:
        with writer() as cur:
            for pidn, address, owner in original_parcels:
                cur.execute(
                    "UPDATE staging.parcels SET propadr = %s, owner_full = %s "
                    "WHERE pidn = %s AND valid_to IS NULL",
                    (address, owner, pidn),
                )
            if change == "global_rights":
                cur.execute(
                    "UPDATE meta.source_rights SET derived_product_allowed = TRUE "
                    "WHERE source_key = 'public_proceedings'"
                )


def test_raw_agenda_is_a_research_lead_until_its_substance_is_explained(
    client, add_source
):
    add_source("Variance request at 1 Main Street, Section 101.")
    project_current_sources()
    assert not any(
        item["event_type"] == "municipal_record"
        for item in client.get("/api/feed").json()["events"]
    )
    research = client.get("/api/feed", params={"pidns": TEST_PIDN, "view": "research"})
    assert research.status_code == 200, research.text
    assert any(
        item["event_type"] == "municipal_record" for item in research.json()["events"]
    )


@pytest.mark.parametrize(
    "title", ["CUH 2026-8", "CUH2026-8", "CUH-2026-8", "CUH.2026.8"]
)
def test_case_reference_spacing_preserves_literal_retrieval_identity(client, title):
    with writer() as cur:
        cur.execute("SELECT public.municipal_case_reference(%s)", (title,))
        assert cur.fetchone()[0] == "cuh2026-8"


def test_case_notification_retracts_immediately_when_source_rights_expire(
    watch_client, add_source
):
    from api.tests.test_municipal_evidence_workflow import watch_property

    client = watch_client
    headers = watch_property(client)
    add_case(add_source)
    keys = publish_test_account()
    with writer() as cur:
        cur.execute("SELECT public.refresh_watch_notifications()")
    notices = client.get("/api/watchspaces/notifications", headers=headers).json()[
        "notifications"
    ]
    assert any(item["event"]["event_key"] in keys for item in notices)
    with writer() as cur:
        cur.execute(
            "UPDATE meta.municipality_source_rights SET review_due_on=CURRENT_DATE-1 WHERE body_name='Hanover Borough Council'"
        )
    try:
        assert not client.get(
            "/api/feed", params={"project_keys": ",".join(keys)}
        ).json()["events"]
        assert not client.get("/api/watchspaces/notifications", headers=headers).json()[
            "notifications"
        ]
    finally:
        with writer() as cur:
            cur.execute(
                "UPDATE meta.municipality_source_rights SET review_due_on=CURRENT_DATE+365 WHERE body_name='Hanover Borough Council'"
            )
