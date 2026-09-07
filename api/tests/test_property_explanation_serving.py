"""Property explanation serving stays current without running a producer."""

from copy import deepcopy

from psycopg2.extras import Json

from api.tests.conftest import TEST_PIDN
from api.tests.test_municipal_evidence import writer


def append_explanation(
    cur,
    source,
    *,
    headline="Agenda proposes final-plan approval",
    disposition="accepted",
    event_tags=None,
):
    municipal = source["kind"] == "municipal"
    source_id = source["sources"][0]["id"]
    explanation = {
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


def test_property_explanation_requires_current_raw_facts_and_source_rights(client):
    with writer() as cur:
        cur.execute(
            "SELECT public.property_explanation_source(%s,'york_open_data',250,500)",
            (TEST_PIDN,),
        )
        source = cur.fetchone()[0]
        assert any(item["id"] == "parcel" for item in source["sources"])
        append_explanation(cur, source, headline="Current property explanation")
    assert (
        client.get(f"/api/parcels/{TEST_PIDN}").json()["source_explanation"]["headline"]
        == "Current property explanation"
    )
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
    client,
):
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
