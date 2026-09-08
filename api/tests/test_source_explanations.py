"""Accepted explanations retract with their source, not on the next batch run."""

# Shared fixtures are requested by pytest by name.
# ruff: noqa: F811

from copy import deepcopy

from psycopg2.extras import Json

from api.tests.conftest import TEST_PIDN
from api.tests.test_municipal_evidence import writer
from api.tests.test_municipal_evidence_workflow import (
    add_source,  # noqa: F401
    project_current_sources,
    watch_property,
)
from api.tests.test_watchspaces import watch_client  # noqa: F401


def append_explanation(
    cur,
    source,
    *,
    headline="Agenda proposes final-plan approval",
    disposition="accepted",
    event_tags=None,
    source_language="en",
    english_text=None,
):
    municipal = source["kind"] == "municipal"
    source_id = source["sources"][0]["id"]
    explanation = {
        "presentation_language": "en",
        "source_presentations": [
            {
                "source_id": item["id"],
                "language": source_language,
                "english_text": english_text,
            }
            for item in source["sources"]
            if "text" in item
        ],
        "headline": headline,
        "summary": f"The source proposes consideration of the final plan. [Evidence:source:{source_id}]",
        "next_step": None,
        "citations": [source_id],
        "record": {
            "event_type": "upcoming_decision",
            "event_tags": event_tags or ["upcoming_decision"],
            "record_status": "proposed",
            "matter_category": "development",
            "decision_scope": None,
            "dates": [],
        }
        if municipal
        else None,
    }
    cur.execute(
        """
        INSERT INTO meta.intelligence_inference_history (
            subject_key, pass_number, output_kind, decision_key, source_hash,
            input_hash, requested_model, prompt_version, output_hash,
            decision_fingerprint, payload, disposition
        ) VALUES (%s, 3, 'record_explanation', 'record_explanation', 'test',
            'test', 'test-model', 'test', 'test', 'test', %s, %s)
        RETURNING inference_id
        """,
        (
            source["subject_key"],
            Json({"version": 1, "source": source, "explanation": explanation}),
            disposition,
        ),
    )
    return cur.fetchone()[0]


def municipal_bundle(cur, proceeding_id):
    cur.execute(
        "SELECT explanation_source FROM public.current_municipal_intelligence WHERE proceeding_id=%s",
        (proceeding_id,),
    )
    return cur.fetchone()[0]


def test_spanish_original_is_retained_but_property_feed_and_sources_use_english(
    client, add_source
):
    original = "Audiencia pública para 1 Main Street. Fecha propuesta: 8 de septiembre de 2026.\n"
    translated = "Public hearing for 1 Main Street. Proposed date: September 8, 2026."
    proceeding_id, _, _ = add_source(original)
    project_current_sources()
    with writer() as cur:
        source = municipal_bundle(cur, proceeding_id)
        append_explanation(
            cur,
            source,
            headline="Agenda proposes a public hearing",
            event_tags=["hearing"],
            source_language="es",
            english_text=translated,
        )
    project_current_sources()
    card = next(
        item
        for item in client.get(f"/api/parcels/{TEST_PIDN}/evidence").json()["cards"]
        if item["event_key"] == source["subject_key"]
    )
    assert card["title"] == "Agenda proposes a public hearing"
    assert card["passages"][0]["text"] == translated
    receipt = card["explanation"]["citation_evidence"][0]
    assert receipt["excerpt"] == translated
    assert receipt["details"]["translated"] is True
    feed = client.get("/api/feed", params={"pidn": TEST_PIDN}).json()
    event = next(
        item for item in feed["events"] if item["event_key"] == source["subject_key"]
    )
    assert event["sources"][0]["excerpt"] == translated
    with writer() as cur:
        assert municipal_bundle(cur, proceeding_id)["sources"][0]["text"] == original


def test_summary_reaches_property_feed_and_watch_with_resolvable_citations(
    watch_client, add_source
):
    watch_property(watch_client)
    proceeding_id, _, _ = add_source()
    project_current_sources()
    with writer() as cur:
        source = municipal_bundle(cur, proceeding_id)
        inference_id = append_explanation(cur, source)
    project_current_sources()
    response = watch_client.get(f"/api/parcels/{TEST_PIDN}")
    assert response.status_code == 200, response.text
    card = next(
        card
        for card in response.json()["municipal_evidence"]["cards"]
        if card["event_key"] == source["subject_key"]
    )
    assert card["explanation"]["record"]["record_status"] == "proposed"
    receipt = card["explanation"]["citation_evidence"][0]
    assert receipt["citation_key"] == "evidence:source:P1"
    assert "Consider approval" in receipt["excerpt"]
    assert receipt["details"]["passages"] == [
        {"text": source["sources"][0]["text"], "page": 1}
    ]
    feed = watch_client.get("/api/feed", params={"pidns": TEST_PIDN}).json()["events"]
    event = next(event for event in feed if event["event_key"] == source["subject_key"])
    assert event["event_type"] == "upcoming_decision"
    assert event["sources"][0]["citation_key"] == "evidence:source:P1"
    assert event["sources"][0]["details"]["explanation_inference_id"] == inference_id
    assert event["sources"][0]["details"]["passages"] == receipt["details"]["passages"]
    notices = watch_client.get("/api/watchspaces/notifications").json()["notifications"]
    assert any(item["event"]["event_key"] == source["subject_key"] for item in notices)

    # A new accepted explanation must hide the old event immediately, until
    # the deterministic producer projects the new accepted wording.
    with writer() as cur:
        append_explanation(cur, source, headline="Revised explanation")
    current = watch_client.get("/api/feed", params={"pidns": TEST_PIDN}).json()[
        "events"
    ]
    assert source["subject_key"] not in {event["event_key"] for event in current}
    notices = watch_client.get("/api/watchspaces/notifications").json()["notifications"]
    assert source["subject_key"] not in {item["event"]["event_key"] for item in notices}
    project_current_sources()
    current = watch_client.get("/api/feed", params={"pidns": TEST_PIDN}).json()[
        "events"
    ]
    assert (
        next(event for event in current if event["event_key"] == source["subject_key"])[
            "title"
        ]
        == "Revised explanation"
    )


def test_source_change_retracts_summary_and_quarantine_does_not_replace_it(
    client, add_source
):
    proceeding_id, _, _ = add_source()
    project_current_sources()
    with writer() as cur:
        source = municipal_bundle(cur, proceeding_id)
        append_explanation(cur, source)
        append_explanation(
            cur, source, headline="Quarantined claim", disposition="quarantined"
        )
    report = client.get(f"/api/parcels/{TEST_PIDN}").json()
    assert (
        report["municipal_evidence"]["cards"][0]["explanation"]["headline"]
        == "Agenda proposes final-plan approval"
    )
    with writer() as cur:
        cur.execute(
            "UPDATE staging.public_proceedings SET raw_text=raw_text || ' amended' WHERE id=%s",
            (proceeding_id,),
        )
    report = client.get(f"/api/parcels/{TEST_PIDN}").json()
    assert source["subject_key"] not in {
        card["event_key"] for card in report["municipal_evidence"]["cards"]
    }


def test_hearing_filter_preserves_secondary_action_on_a_combined_record(
    client, add_source
):
    proceeding_id, _, _ = add_source(
        text="Rezoning hearing for 1 Main Street at 6:00 pm. Consider the proposed rezoning ordinance."
    )
    project_current_sources()
    with writer() as cur:
        source = municipal_bundle(cur, proceeding_id)
        append_explanation(cur, source, event_tags=["upcoming_decision", "hearing"])
    project_current_sources()
    response = client.get(
        "/api/feed", params={"pidns": TEST_PIDN, "event_type": "hearing"}
    )
    assert response.status_code == 200, response.text
    event = next(
        item
        for item in response.json()["events"]
        if item["event_key"] == source["subject_key"]
    )
    assert event["event_type"] == "upcoming_decision"
    assert "hearing" in event["event_tags"]


def test_property_explanation_requires_current_raw_facts_and_source_rights(
    client, add_source
):
    add_source()
    project_current_sources()
    with writer() as cur:
        cur.execute(
            "SELECT public.property_explanation_source(%s,'york_open_data',250,500)",
            (TEST_PIDN,),
        )
        source = cur.fetchone()[0]
        assert any(item["id"] == "M1" for item in source["sources"])
        append_explanation(cur, source, headline="Current property explanation")
    explanation = client.get(f"/api/parcels/{TEST_PIDN}").json()["source_explanation"]
    assert explanation["headline"] == "Current property explanation"
    municipal_receipt = next(
        item
        for item in explanation["citation_evidence"]
        if item["source_record_id"] == "M1"
    )
    municipal_source = next(item for item in source["sources"] if item["id"] == "M1")
    assert municipal_receipt["details"]["passages"] == [
        {"text": municipal_source["text"], "page": 1}
    ]
    assert all(item["internal_url"] for item in explanation["citation_evidence"])
    with writer() as cur:
        cur.execute(
            "UPDATE staging.parcels SET acres=acres+1 WHERE pidn=%s AND valid_to IS NULL RETURNING acres-1",
            (TEST_PIDN,),
        )
        previous_acres = cur.fetchone()[0]
    try:
        assert (
            client.get(f"/api/parcels/{TEST_PIDN}").json()["source_explanation"] is None
        )
    finally:
        with writer() as cur:
            cur.execute(
                "UPDATE staging.parcels SET acres=%s WHERE pidn=%s AND valid_to IS NULL",
                (previous_acres, TEST_PIDN),
            )
    with writer() as cur:
        cur.execute(
            "UPDATE meta.source_rights SET derived_product_allowed=FALSE WHERE source_key='york_open_data'"
        )
    try:
        response = client.get(f"/api/parcels/{TEST_PIDN}")
        assert response.status_code == 503
        assert "source_explanation" not in response.json()
    finally:
        with writer() as cur:
            cur.execute(
                "UPDATE meta.source_rights SET derived_product_allowed=TRUE WHERE source_key='york_open_data'"
            )


def test_changed_property_bundle_cannot_be_served_by_matching_only_the_parcel_id(
    client, add_source
):
    add_source()
    project_current_sources()
    with writer() as cur:
        cur.execute(
            "SELECT public.property_explanation_source(%s,'york_open_data',250,500)",
            (TEST_PIDN,),
        )
        wrong_source = deepcopy(cur.fetchone()[0])
        wrong_source["sources"] = []
        # The test targets the live bundle comparison with an invalid retained
        # proposal; the producer's schema gate normally rejects it earlier.
        wrong_source["sources"].append(
            {"id": "fictional", "label": "fictional", "text": "wrong evidence"}
        )
        append_explanation(cur, wrong_source)
    assert client.get(f"/api/parcels/{TEST_PIDN}").json()["source_explanation"] is None
