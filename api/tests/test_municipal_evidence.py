"""Evidence serving follows live source permission and immutable review history."""

import hashlib
from contextlib import closing, contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

import psycopg2
import pytest
from psycopg2.extras import Json

from api.tests.conftest import DB_ENV, TEST_MUNICIPALITY


@contextmanager
def writer():
    with (
        closing(psycopg2.connect(DB_ENV["DATABASE_URL"])) as connection,
        connection,
        connection.cursor() as cur,
    ):
        yield cur


def append_read(
    cur, proceeding_id, payload, disposition="accepted", *, created_at=None
):
    cur.execute(
        """
        INSERT INTO meta.intelligence_inference_history (
            subject_key, pass_number, output_kind, decision_key, source_hash,
            input_hash, requested_model, prompt_version, output_hash,
            decision_fingerprint, payload, disposition, created_at
        ) VALUES (%s, 0, 'municipal_evidence', 'source_selection', 'test',
                  'test', 'test', 'test', 'test', 'test', %s, %s, COALESCE(%s, NOW()))
        RETURNING inference_id
        """,
        (f"proceeding:{proceeding_id}", Json(payload), disposition, created_at),
    )
    return cur.fetchone()[0]


@pytest.fixture
def source_read(client):
    text = "Example Plan\nMotion to approve, revise, table or deny.\n"
    digest = hashlib.sha256(text.encode()).hexdigest()
    url = f"https://example.com/evidence-{uuid4().hex}.pdf"
    snapshot = {
        "content_hash": "source-pdf-hash",
        "raw_text_sha256": digest,
        "body_name": "Hanover Borough Council",
        "meeting_date": "2026-04-11",
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
                "id": "example",
                "title": "Example Plan",
                "passages": [{"start": 0, "end": len(text), "text": text}],
            }
        ],
    }
    with writer() as cur:
        cur.execute(
            """
            INSERT INTO staging.public_proceedings (
                body_name, meeting_date, proceeding_type, raw_text,
                source_url, document_url, content_hash, metadata_quality
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, '{"status":"ready"}')
            RETURNING id
            """,
            (
                snapshot["body_name"],
                snapshot["meeting_date"],
                snapshot["proceeding_type"],
                text,
                url,
                url,
                snapshot["content_hash"],
            ),
        )
        proceeding_id = cur.fetchone()[0]
        inference_id = append_read(cur, proceeding_id, payload)
    yield proceeding_id, inference_id, payload
    with writer() as cur:
        cur.execute(
            "UPDATE staging.public_proceedings SET valid_to=NOW() WHERE id=%s",
            (proceeding_id,),
        )


def cards(client):
    response = client.get(f"/api/municipalities/{TEST_MUNICIPALITY}/evidence")
    assert response.status_code == 200, response.text
    return response.json()["cards"]


def test_each_card_retains_its_first_accepted_observation(source_read):
    proceeding_id, _, payload = source_read
    first_seen = datetime(2026, 4, 12, 9, 15, 1, 123456, tzinfo=UTC)
    second_seen = datetime(2026, 4, 14, 10, 30, 2, 654321, tzinfo=UTC)
    expanded = deepcopy(payload)
    new_card = deepcopy(expanded["cards"][0])
    new_card["id"] = "later-selection"
    expanded["cards"].append(new_card)
    with writer() as cur:
        append_read(cur, proceeding_id, payload, created_at=first_seen)
        append_read(cur, proceeding_id, expanded, created_at=second_seen)
        append_read(cur, proceeding_id, expanded)
        cur.execute(
            "SELECT card->>'id', observed_at FROM public.current_municipal_evidence "
            "WHERE proceeding_id = %s",
            (proceeding_id,),
        )
        assert dict(cur.fetchall()) == {
            "example": first_seen,
            "later-selection": second_seen,
        }


def test_pending_english_presentation_withholds_raw_agenda_wording(client, source_read):
    _, inference_id, _ = source_read
    card = next(
        card for card in cards(client) if card["id"] == f"{inference_id}:example"
    )
    assert card["proceeding_type"] == "agenda"
    assert card["passages"] == []
    assert card["title"] == "Municipal record awaiting an English account"
    assert "decision" not in card
    assert "pidn" not in card


@pytest.mark.parametrize(
    "assignment",
    [
        "raw_text='Changed text'",
        "content_hash='changed-pdf'",
        "meeting_date='2026-04-12'",
        "document_url='https://example.com/replacement.pdf'",
        'metadata_quality=\'{"status":"quarantined"}\'::jsonb',
        "valid_to=NOW()",
    ],
)
def test_changed_or_quarantined_source_cannot_serve_old_selections(
    client, source_read, assignment
):
    proceeding_id, inference_id, _ = source_read
    with writer() as cur:
        cur.execute(
            f"UPDATE staging.public_proceedings SET {assignment} WHERE id=%s",
            (proceeding_id,),
        )
    assert f"{inference_id}:example" not in {card["id"] for card in cards(client)}


def test_live_municipal_permission_revocation_hides_retained_evidence(
    client, source_read
):
    _, inference_id, _ = source_read
    with writer() as cur:
        cur.execute(
            "UPDATE meta.municipality_source_rights SET derived_product_allowed=FALSE "
            "WHERE source_key='hanover_borough_council'"
        )
    try:
        assert f"{inference_id}:example" not in {card["id"] for card in cards(client)}
    finally:
        with writer() as cur:
            cur.execute(
                "UPDATE meta.municipality_source_rights SET derived_product_allowed=TRUE "
                "WHERE source_key='hanover_borough_council'"
            )


def test_quarantine_keeps_prior_and_discard_resolution_retracts_it(client, source_read):
    proceeding_id, inference_id, payload = source_read
    with writer() as cur:
        append_read(cur, proceeding_id, payload, "quarantined")
    assert f"{inference_id}:example" in {card["id"] for card in cards(client)}
    with writer() as cur:
        append_read(cur, proceeding_id, {"resolution": "discard_both"})
    assert f"{inference_id}:example" not in {card["id"] for card in cards(client)}
