"""A source mention reaches the correct property/watch and retracts when stale."""

# Fixtures imported from the watch API suite are injected by pytest by name.
# ruff: noqa: F811

import hashlib
import os
import subprocess
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from api.tests.conftest import (
    DB_ENV,
    PIPELINES_DIR,
    SECOND_PIDN,
    TEST_MUNICIPALITY,
    TEST_PIDN,
)
from api.tests.test_municipal_evidence import append_read, writer
from api.tests.test_watchspaces import create, watch_client  # noqa: F401


def project_current_sources():
    """Exercise the pipeline producers in their own project environment."""
    script = """
from countyiq.assets.enrichment.municipal_evidence_linking import refresh_evidence_links
from countyiq.assets.enrichment.intelligence_events import _INSERT_SQL, _insert_tuple
from countyiq.assets.enrichment.development_signals import _SIGNALS
from countyiq.assets.enrichment.development_momentum import build_rebuild_sql
from countyiq.lib.intelligence_events import build_municipal_evidence_event
from countyiq.resources.database import make_database_resource

database = make_database_resource()
database.setup_for_execution(None)
try:
    refresh_evidence_links(database)
    with database.dict_cursor() as cur:
        cur.execute('SELECT * FROM public.current_municipal_intelligence')
        events = [build_municipal_evidence_event(dict(row)) for row in cur.fetchall()]
    with database.transaction() as cur:
        cur.execute("DELETE FROM public.intelligence_events WHERE source_kind='municipal_evidence'")
        for event in events:
            cur.execute(_INSERT_SQL, _insert_tuple(event))
        cur.execute("DELETE FROM public.development_signals WHERE signal_key='municipal_record'")
        cur.execute(dict(_SIGNALS)['municipal_record'])
        cur.execute('DELETE FROM public.development_momentum')
        cur.execute(build_rebuild_sql())
        cur.execute('SELECT public.refresh_watch_notifications()')
finally:
    database.teardown_after_execution(None)
"""
    subprocess.run(
        [str(PIPELINES_DIR / ".venv/bin/python"), "-c", script],
        cwd=PIPELINES_DIR,
        env={**os.environ, **DB_ENV, "PYTHONPATH": str(PIPELINES_DIR)},
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def add_source(client):
    ids = []

    def add(
        text="Consider approval of the final plan at 1 Main Street.\nStormwater revisions are complete.\n",
        *,
        reference_quote=None,
        reference_role="subject_property",
        subject_end=None,
        reference_overrides=None,
        selection_contract="subject-passages-v1",
    ):
        digest = hashlib.sha256(text.encode()).hexdigest()
        subject_end = len(text) if subject_end is None else subject_end

        def span(start, end, **extra):
            return {
                "start": start,
                "end": end,
                "text": text[start:end],
                "source_text_sha256": digest,
                **extra,
            }

        if reference_quote is None:
            reference_quote = next(
                (
                    quote
                    for quote in (
                        TEST_PIDN,
                        "1east Main Street",
                        "1 Main\nStreet",
                        "1 Main Street",
                        "2 Main Street",
                        "1 Maine Street",
                    )
                    if quote in text
                ),
                None,
            )
        references = []
        if reference_quote is not None:
            start = text.index(reference_quote)
            reference = span(
                start,
                start + len(reference_quote),
                role=reference_role,
                context=span(0, len(text)),
            )
            reference.update(reference_overrides or {})
            references.append(reference)
        subject = span(0, subject_end)
        meeting = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()
        url = f"https://example.com/workflow-{uuid4().hex}.pdf"
        snapshot = {
            "content_hash": digest,
            "raw_text_sha256": digest,
            "body_name": "Hanover Borough Council",
            "meeting_date": meeting,
            "proceeding_type": "council",
            "document_url": url,
        }
        payload = {
            "record_snapshot": snapshot,
            "source_text_sha256": digest,
            "document_kind": "agenda",
            "pages": [{"page": 1, "start": 0, "end": len(text)}],
            "cards": [
                {
                    "id": "source-selection",
                    "title": "Final plan",
                    "subject": subject,
                    "passages": [span(0, len(text))],
                    "selection_contract": selection_contract,
                    "subject_passages": [subject],
                    "context_passages": [],
                    "references": references,
                }
            ],
        }
        with writer() as cur:
            cur.execute(
                """
                INSERT INTO staging.public_proceedings (
                    body_name, meeting_date, proceeding_type, raw_text, source_url,
                    document_url, content_hash, metadata_quality
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, '{"status":"ready"}')
                RETURNING id
                """,
                (snapshot["body_name"], meeting, "council", text, url, url, digest),
            )
            source_id = cur.fetchone()[0]
            inference_id = append_read(cur, source_id, payload)
        ids.append(source_id)
        return source_id, inference_id, payload

    yield add
    with writer() as cur:
        cur.execute(
            "UPDATE staging.public_proceedings SET valid_to=NOW() WHERE id=ANY(%s)",
            (ids,),
        )
        cur.execute(
            "DELETE FROM public.intelligence_events WHERE source_kind='municipal_evidence'"
        )
        cur.execute(
            "DELETE FROM public.development_signals WHERE signal_key='municipal_record'"
        )


def watch_property(client):
    _, headers = create(client)
    response = client.put(
        "/api/watchspaces/current",
        headers=headers,
        json={
            "version": 0,
            "items": [
                {
                    "kind": "parcel",
                    "subject_key": TEST_PIDN,
                    "label": "Watched property",
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    client.headers.update(headers)
    return headers


def explain_current_sources():
    """Give watch-policy fixtures an accepted explanation before alerting."""
    from api.tests.test_source_explanations import append_explanation

    with writer() as cur:
        cur.execute(
            "SELECT explanation_source FROM public.current_municipal_intelligence"
        )
        sources = [row[0] for row in cur.fetchall()]
        for source in sources:
            append_explanation(cur, source)
    project_current_sources()


def test_source_to_property_signal_feed_owner_and_private_watch(
    watch_client, add_source
):
    headers = watch_property(watch_client)
    _, other_headers = create(watch_client)
    project_current_sources()
    baseline = watch_client.get(f"/api/parcels/{TEST_PIDN}").json()[
        "development_momentum"
    ] or {
        "score": 0,
        "opportunity_score": 0,
        "site_readiness_score": 50,
        "has_active_plan": False,
    }
    add_source()
    project_current_sources()

    response = watch_client.get(f"/api/parcels/{TEST_PIDN}")
    assert response.status_code == 200, response.text
    momentum = response.json()["development_momentum"]
    for key in (
        "score",
        "opportunity_score",
        "site_readiness_score",
        "has_active_plan",
    ):
        assert momentum[key] == baseline[key]
    cards = response.json()["municipal_evidence"]["cards"]
    assert "municipal_record" in response.json()["development_momentum"]["signals"]
    finding = next(
        item
        for item in response.json()["record_brief"]["findings"]
        if item["signal_key"] == "municipal_record"
    )
    assert "municipal record" in finding["text"]
    assert len(cards) == 1
    assert cards[0]["matched_properties"] == [
        {"pidn": TEST_PIDN, "address": "1 Main St", "match_method": "address"}
    ]
    assert cards[0]["proceeding_type"] == "agenda"
    assert cards[0]["passages"] == []
    event_key = cards[0]["event_key"]
    feed = watch_client.get(
        "/api/feed", params={"pidns": TEST_PIDN, "view": "research"}
    ).json()
    event = next(item for item in feed["events"] if item["event_key"] == event_key)
    assert event["event_type"] == "municipal_record"
    assert event["event_tags"] == ["municipal_record"]
    assert event["what_happened"] == "An English account is being prepared."
    assert event["related_entities"] == ["Alpha Holdings LLC"]
    notices = watch_client.get("/api/watchspaces/notifications", headers=headers).json()
    assert not any(
        item["event"]["event_key"] == event_key for item in notices["notifications"]
    )
    assert (
        watch_client.get(
            "/api/watchspaces/notifications", headers=other_headers
        ).json()["notifications"]
        == []
    )
    with writer() as cur:
        cur.execute(
            "SELECT signal_weight, evidence FROM public.development_signals WHERE pidn=%s AND signal_key='municipal_record'",
            (TEST_PIDN,),
        )
        weight, evidence = cur.fetchone()
        assert weight == 0
        assert evidence["document_kind"] == "agenda"
        assert evidence["event_key"] == event_key


@pytest.mark.parametrize(
    "change",
    [
        "source",
        "metadata",
        "permission",
        "global_permission",
        "address",
        "ambiguous_address",
        "target_unit",
        "owner",
    ],
)
def test_current_property_and_watch_views_retract_without_waiting_for_rebuild(
    watch_client, add_source, change
):
    headers = watch_property(watch_client)
    source_id, _, _ = add_source()
    project_current_sources()
    cards = watch_client.get(f"/api/parcels/{TEST_PIDN}/evidence").json()["cards"]
    event_key = cards[0]["event_key"]
    with writer() as cur:
        cur.execute(
            "SELECT pidn, propadr, owner_full FROM staging.parcels WHERE pidn=ANY(%s) AND valid_to IS NULL",
            ([TEST_PIDN, SECOND_PIDN],),
        )
        parcels = cur.fetchall()
        if change == "source":
            cur.execute(
                "UPDATE staging.public_proceedings SET raw_text='Replacement source' WHERE id=%s",
                (source_id,),
            )
        elif change == "metadata":
            cur.execute(
                """UPDATE staging.public_proceedings
                   SET metadata_quality='{"status":"review_required"}' WHERE id=%s""",
                (source_id,),
            )
        elif change == "permission":
            cur.execute(
                "UPDATE meta.municipality_source_rights SET derived_product_allowed=FALSE WHERE body_name='Hanover Borough Council'"
            )
        elif change == "global_permission":
            cur.execute(
                "UPDATE meta.source_rights SET derived_product_allowed=FALSE WHERE source_key='public_proceedings'"
            )
        elif change == "address":
            cur.execute(
                "UPDATE staging.parcels SET propadr='99 Different Road' WHERE pidn=%s AND valid_to IS NULL",
                (TEST_PIDN,),
            )
        elif change == "ambiguous_address":
            cur.execute(
                "UPDATE staging.parcels SET propadr='1 Main Street' WHERE pidn=%s AND valid_to IS NULL",
                (SECOND_PIDN,),
            )
        elif change == "target_unit":
            cur.execute(
                "UPDATE staging.parcels SET propadr='1 Main Street Suite 4' WHERE pidn=%s AND valid_to IS NULL",
                (TEST_PIDN,),
            )
        else:
            cur.execute(
                "UPDATE staging.parcels SET owner_full='New Owner LLC' WHERE pidn=%s AND valid_to IS NULL",
                (TEST_PIDN,),
            )
    try:
        if change != "owner":
            response = watch_client.get(f"/api/parcels/{TEST_PIDN}/evidence")
            if change == "global_permission":
                assert response.status_code == 404
            else:
                assert response.json()["cards"] == []
            report_response = watch_client.get(f"/api/parcels/{TEST_PIDN}")
            if change == "global_permission":
                assert report_response.status_code == 503
            else:
                assert (
                    "municipal_record"
                    not in report_response.json()["development_momentum"]["signals"]
                )
        feed_response = watch_client.get("/api/feed", params={"pidn": TEST_PIDN})
        if change == "global_permission":
            assert feed_response.status_code == 503
        else:
            assert all(
                item["event_key"] != event_key
                for item in feed_response.json()["events"]
            )
        notices = watch_client.get(
            "/api/watchspaces/notifications", headers=headers
        ).json()["notifications"]
        assert all(item["event"]["event_key"] != event_key for item in notices)
    finally:
        with writer() as cur:
            for pidn, address, owner in parcels:
                cur.execute(
                    "UPDATE staging.parcels SET propadr=%s,owner_full=%s WHERE pidn=%s AND valid_to IS NULL",
                    (address, owner, pidn),
                )
            if change == "permission":
                cur.execute(
                    "UPDATE meta.municipality_source_rights SET derived_product_allowed=TRUE WHERE body_name='Hanover Borough Council'"
                )
            if change == "global_permission":
                cur.execute(
                    "UPDATE meta.source_rights SET derived_product_allowed=TRUE WHERE source_key='public_proceedings'"
                )


def test_identical_reread_and_projection_keep_one_notification(
    watch_client, add_source
):
    headers = watch_property(watch_client)
    source_id, _, payload = add_source()
    project_current_sources()
    explain_current_sources()
    before = watch_client.get("/api/watchspaces/notifications", headers=headers).json()[
        "notifications"
    ]
    with writer() as cur:
        append_read(cur, source_id, payload)
    project_current_sources()
    after = watch_client.get("/api/watchspaces/notifications", headers=headers).json()[
        "notifications"
    ]
    assert len(before) == 1
    assert [(item["id"], item["event"]["event_key"]) for item in after] == [
        (item["id"], item["event"]["event_key"]) for item in before
    ]


@pytest.mark.parametrize(
    "text",
    [
        "Proposed project near Main Street.\n",
        "Project at 1-2 Main Street.\n",
        "Project at 1-\n2 Main Street.\n",
        "Project at 1 and 2 Main Street.\n",
        "Project at 1 Main Street Suite 4.\n",
        "Project at 1 Main Street\nSuite 4.\n",
    ],
)
def test_ambiguous_references_remain_municipality_only(client, add_source, text):
    add_source(text)
    project_current_sources()
    assert client.get(f"/api/parcels/{TEST_PIDN}/evidence").json()["cards"] == []
    municipal = client.get(f"/api/municipalities/{TEST_MUNICIPALITY}/evidence").json()
    assert any(
        not card["passages"] and not card["matched_properties"]
        for card in municipal["cards"]
    )


@pytest.mark.parametrize(
    ("role", "expected_link"),
    [
        ("subject_property", True),
        ("speaker_address", False),
        ("meeting_venue", False),
        ("representative_address", False),
        ("neighboring_property", False),
        ("uncertain", False),
    ],
)
def test_only_subject_property_references_link_a_municipal_card(
    client, add_source, role, expected_link
):
    add_source(reference_role=role)
    project_current_sources()
    cards = client.get(f"/api/parcels/{TEST_PIDN}/evidence").json()["cards"]

    if expected_link:
        assert cards[0]["matched_properties"] == [
            {"pidn": TEST_PIDN, "address": "1 Main St", "match_method": "address"}
        ]
    else:
        assert cards == []


def test_legacy_cards_remain_visible_without_rebuildable_property_links(
    client, add_source
):
    add_source(selection_contract=None)
    project_current_sources()

    assert client.get(f"/api/parcels/{TEST_PIDN}/evidence").json()["cards"] == []
    municipal = client.get(f"/api/municipalities/{TEST_MUNICIPALITY}/evidence").json()
    assert any(
        card["title"] == "Municipal record awaiting an English account"
        for card in municipal["cards"]
    )


@pytest.mark.parametrize(
    "reference_overrides",
    [
        {"source_text_sha256": "0" * 64},
        {"text": "9 Main Street"},
        {"start": 10**30},
        {"end": -1},
        {"start": "0"},
        {"context": None},
    ],
)
def test_forged_reference_provenance_does_not_link_a_property(
    client, add_source, reference_overrides
):
    add_source(reference_overrides=reference_overrides)
    project_current_sources()

    assert client.get(f"/api/parcels/{TEST_PIDN}/evidence").json()["cards"] == []


def test_subject_property_reference_outside_substantive_passage_does_not_link(
    client, add_source
):
    text = "Final plan discussion.\nThe project site is 1 Main Street.\n"
    add_source(text, subject_end=text.index("The project site"))
    project_current_sources()

    assert client.get(f"/api/parcels/{TEST_PIDN}/evidence").json()["cards"] == []


def test_empty_review_is_counted_but_changed_source_requires_reading_again(
    client, add_source
):
    baseline = client.get(f"/api/municipalities/{TEST_MUNICIPALITY}/evidence").json()[
        "coverage"
    ]
    source_id, _, payload = add_source(
        "Routine meeting with no useful project matter.\n"
    )
    payload["cards"] = []
    with writer() as cur:
        append_read(cur, source_id, payload)
    reviewed = client.get(f"/api/municipalities/{TEST_MUNICIPALITY}/evidence").json()[
        "coverage"
    ]
    assert reviewed["total_documents"] == baseline["total_documents"] + 1
    assert reviewed["reviewed_documents"] == baseline["reviewed_documents"] + 1
    assert reviewed["documents_with_passages"] == baseline["documents_with_passages"]
    with writer() as cur:
        cur.execute(
            "UPDATE staging.public_proceedings SET raw_text='Changed' WHERE id=%s",
            (source_id,),
        )
    changed = client.get(f"/api/municipalities/{TEST_MUNICIPALITY}/evidence").json()[
        "coverage"
    ]
    assert changed["reviewed_documents"] == baseline["reviewed_documents"]
    assert changed["awaiting_read_documents"] == baseline["awaiting_read_documents"] + 1


@pytest.mark.parametrize(
    ("text", "address", "method"),
    [
        (f"Final plan for parcel {TEST_PIDN}.\n", "1 Main St", "pidn"),
        ("Request a hearing at 1east Main Street.\n", "1 E Main St", "address"),
        ("Request a hearing at 1 Main\nStreet.\n", "1 Main St", "address"),
        (
            "Final plan at 1 Main Street.\nPlan dated 1-30-2024, revised 8-12-2025.\n",
            "1 Main St",
            "address",
        ),
        ("Final plan at 1 Main Street Lot 2.\n", "1 Main St", None),
        ("Final plan at 1 Main Street Floor 2.\n", "1 Main St", None),
        ("Final plan at 1 Maine Street.\n", "1 Main St", None),
    ],
)
def test_literal_reference_matching_preserves_units_and_rejects_fuzzy_names(
    client, add_source, text, address, method
):
    with writer() as cur:
        cur.execute(
            "UPDATE staging.parcels SET propadr=%s WHERE pidn=%s AND valid_to IS NULL",
            (address, TEST_PIDN),
        )
    try:
        add_source(text)
        project_current_sources()
        cards = client.get(f"/api/parcels/{TEST_PIDN}/evidence").json()["cards"]
        if method is None:
            assert cards == []
        else:
            assert cards[0]["matched_properties"] == [
                {"pidn": TEST_PIDN, "address": address, "match_method": method}
            ]
            assert cards[0]["passages"] == []
    finally:
        with writer() as cur:
            cur.execute(
                "UPDATE staging.parcels SET propadr='1 Main St' WHERE pidn=%s AND valid_to IS NULL",
                (TEST_PIDN,),
            )


@pytest.mark.parametrize(
    ("quote", "address", "method"),
    [
        ("1 Main St.", "1 Main St", "address"),
        ("12345 Oak Road", "12345 Oak Rd", "address"),
        ("00-000-00-0000.01-\n00000", "1 Main St", "pidn"),
    ],
)
def test_declared_reference_keeps_punctuation_and_wrapped_identifier_matches(
    client, add_source, quote, address, method
):
    with writer() as cur:
        cur.execute(
            "UPDATE staging.parcels SET propadr=%s WHERE pidn=%s AND valid_to IS NULL",
            (address, TEST_PIDN),
        )
    try:
        add_source(f"Final subdivision plan for {quote}.\n", reference_quote=quote)
        project_current_sources()
        cards = client.get(f"/api/parcels/{TEST_PIDN}/evidence").json()["cards"]
        assert cards[0]["matched_properties"] == [
            {"pidn": TEST_PIDN, "address": address, "match_method": method}
        ]
    finally:
        with writer() as cur:
            cur.execute(
                "UPDATE staging.parcels SET propadr='1 Main St' WHERE pidn=%s AND valid_to IS NULL",
                (TEST_PIDN,),
            )


def test_municipal_property_mention_reaches_an_existing_owner_watch(
    watch_client, add_source
):
    _, headers = create(watch_client)
    with writer() as cur:
        cur.execute(
            "SELECT owner_id FROM public.owners WHERE canonical_name='Alpha Holdings LLC'"
        )
        owner_id = cur.fetchone()[0]
    response = watch_client.put(
        "/api/watchspaces/current",
        headers=headers,
        json={
            "version": 0,
            "items": [
                {
                    "kind": "entity",
                    "subject_key": str(owner_id),
                    "label": "Alpha Holdings LLC",
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    add_source()
    project_current_sources()
    explain_current_sources()
    notices = watch_client.get(
        "/api/watchspaces/notifications", headers=headers
    ).json()["notifications"]
    assert len(notices) == 1
    assert notices[0]["event"]["related_pidns"] == [TEST_PIDN]
    assert notices[0]["event"]["related_entities"] == ["Alpha Holdings LLC"]


@pytest.mark.parametrize("kind", ["parcel", "entity"])
def test_obsolete_watch_match_stays_hidden_after_event_projection_rebuild(
    watch_client, add_source, kind
):
    _, headers = create(watch_client)
    with writer() as cur:
        cur.execute(
            "SELECT owner_id FROM public.owners WHERE canonical_name='Alpha Holdings LLC'"
        )
        owner_id = cur.fetchone()[0]
    subject = TEST_PIDN if kind == "parcel" else str(owner_id)
    response = watch_client.put(
        "/api/watchspaces/current",
        headers=headers,
        json={
            "version": 0,
            "items": [
                {"kind": kind, "subject_key": subject, "label": "Original watch"}
            ],
        },
    )
    assert response.status_code == 200, response.text
    add_source()
    project_current_sources()
    explain_current_sources()
    before = watch_client.get("/api/watchspaces/notifications", headers=headers).json()[
        "notifications"
    ]
    assert len(before) == 1
    with writer() as cur:
        if kind == "parcel":
            cur.execute(
                "UPDATE staging.parcels SET propadr='99 Different Road' WHERE pidn=%s AND valid_to IS NULL",
                (TEST_PIDN,),
            )
        else:
            cur.execute(
                "UPDATE staging.parcels SET owner_full='New Owner LLC' WHERE pidn=%s AND valid_to IS NULL",
                (TEST_PIDN,),
            )
    try:
        project_current_sources()
        assert (
            watch_client.get("/api/watchspaces/notifications", headers=headers).json()[
                "notifications"
            ]
            == []
        )
        # Hiding a stale match preserves its notification history/read state.
        with writer() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM public.watch_notifications WHERE notification_id=%s",
                (before[0]["id"],),
            )
            assert cur.fetchone()[0] == 1
    finally:
        with writer() as cur:
            cur.execute(
                "UPDATE staging.parcels SET propadr='1 Main St',owner_full='Alpha Holdings LLC' WHERE pidn=%s AND valid_to IS NULL",
                (TEST_PIDN,),
            )
