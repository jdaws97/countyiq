"""Real-Postgres checks for direct municipal matter-source freshness reads."""

from __future__ import annotations

import hashlib
import os
from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

import psycopg2
import pytest
from countyiq.lib.municipal_matters import current_matter_source
from psycopg2.extras import Json


def _connect():
    return psycopg2.connect(
        host=os.environ.get("DATABASE_HOST", "localhost"),
        port=int(os.environ.get("DATABASE_PORT", "5433")),
        dbname="countyiq_test",
        user=os.environ.get("DATABASE_USER", "dagster_admin"),
        password=os.environ.get("DATABASE_PASSWORD", "localtest"),
    )


def _insert_evidence(cursor, *, proceeding_id, suffix, payload):
    cursor.execute(
        """
        INSERT INTO meta.intelligence_inference_history (
            subject_key, pass_number, output_kind, decision_key, source_hash,
            input_hash, requested_model, prompt_version, output_hash,
            decision_fingerprint, payload, disposition
        )
        VALUES (%s, 0, 'municipal_evidence', 'document', %s, %s,
                'test/model', 'test-prompt', %s, %s, %s, 'accepted')
        RETURNING inference_id
        """,
        (
            f"proceeding:{proceeding_id}",
            f"source-{suffix}",
            f"input-{suffix}",
            f"output-{suffix}",
            f"decision-{suffix}",
            Json(payload),
        ),
    )
    return cursor.fetchone()[0]


@pytest.fixture
def seeded_selection_source():
    """Seed one current source whose only safe scope is the selection itself."""
    suffix = uuid4().hex
    body_name = f"MATTER FRESHNESS BODY {suffix}"
    source_key = f"matter-freshness-{suffix}"
    raw_text = "The board received a proposal for review and requested a vote."
    document_url = f"https://example.test/{suffix}.pdf"
    meeting_date = datetime.now(UTC).date()
    card_id = hashlib.sha256(suffix.encode()).hexdigest()
    snapshot = {
        "content_hash": f"content-{suffix}",
        "raw_text_sha256": hashlib.sha256(raw_text.encode()).hexdigest(),
        "body_name": body_name,
        "meeting_date": str(meeting_date),
        "proceeding_type": "planning",
        "document_url": document_url,
    }
    payload = {
        "record_snapshot": snapshot,
        "source_text_sha256": hashlib.sha256(raw_text.encode()).hexdigest(),
        "cards": [
            {
                "id": card_id,
                "title": "Proposal for board review",
                "passages": [
                    {"text": raw_text[:41], "start": 0, "end": 41},
                    {"text": raw_text[42:], "start": 42, "end": len(raw_text)},
                ],
            }
        ],
    }
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE meta.source_rights SET rights_status = 'conditional', "
                "derived_product_allowed = true, review_due_on = CURRENT_DATE + 1 "
                "WHERE source_key = 'public_proceedings'"
            )
            cursor.execute(
                """
                INSERT INTO meta.municipality_source_rights (
                    source_key, municipality_name, body_name, proceeding_type,
                    rights_status, acquisition_allowed, raw_retention_allowed,
                    derived_product_allowed, person_level_display_allowed,
                    raw_export_allowed, allowed_methods, terms_review_status,
                    reviewed_on, review_due_on, evidence
                )
                VALUES (%s, %s, %s, 'planning', 'conditional', true, true,
                        true, false, false, ARRAY['official_document_direct'],
                        'reviewed', CURRENT_DATE, CURRENT_DATE + 1, '{}'::jsonb)
                """,
                (source_key, f"Matter Freshness {suffix}", body_name),
            )
            cursor.execute(
                """
                INSERT INTO staging.public_proceedings (
                    body_name, meeting_date, proceeding_type, raw_text, source_url,
                    document_url, content_hash, metadata_quality
                )
                VALUES (%s, %s, 'planning', %s, %s, %s, %s,
                        '{"status": "ready"}'::jsonb)
                RETURNING id
                """,
                (
                    body_name,
                    meeting_date,
                    raw_text,
                    f"https://example.test/{suffix}",
                    document_url,
                    snapshot["content_hash"],
                ),
            )
            proceeding_id = cursor.fetchone()[0]
            inference_id = _insert_evidence(
                cursor,
                proceeding_id=proceeding_id,
                suffix=suffix,
                payload=payload,
            )
            cursor.execute(
                """
                SELECT source
                FROM public.current_municipal_matter_sources
                WHERE source->>'candidate_scope' LIKE 'selection:%%'
                  AND jsonb_array_length(source->'records') = 1
                  AND source->'records'->0->>'key' LIKE %s
                """,
                (f"municipal:{proceeding_id}:%",),
            )
            canonical = cursor.fetchone()[0]
            yield {
                "canonical": canonical,
                "connection": connection,
                "cursor": cursor,
                "payload": payload,
                "proceeding_id": proceeding_id,
                "inference_id": inference_id,
                "source_key": source_key,
            }
    finally:
        connection.rollback()
        connection.close()


@pytest.mark.integration
def test_direct_selection_source_equals_canonical_current_bundle(
    seeded_selection_source,
):
    """The optimized query returns the same two-passage source as the view."""
    fixture = seeded_selection_source

    assert len(fixture["canonical"]["sources"]) == 2
    assert (
        current_matter_source(fixture["cursor"], fixture["canonical"])
        == fixture["canonical"]
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    "mutation", ["raw_text", "rights_revocation", "global_rights_revocation"]
)
def test_direct_selection_source_is_unavailable_when_its_live_basis_changes(
    seeded_selection_source, mutation
):
    """A source disappears when document identity or its serving rights change."""
    fixture = seeded_selection_source
    cursor = fixture["cursor"]
    cursor.execute("SAVEPOINT live_basis_change")
    if mutation == "raw_text":
        cursor.execute(
            "UPDATE staging.public_proceedings SET raw_text = raw_text || ' changed' "
            "WHERE id = %s",
            (fixture["proceeding_id"],),
        )
    elif mutation == "rights_revocation":
        cursor.execute(
            "UPDATE meta.municipality_source_rights SET rights_status = 'paused' "
            "WHERE source_key = %s",
            (fixture["source_key"],),
        )
    else:
        cursor.execute(
            "UPDATE meta.source_rights SET derived_product_allowed = false "
            "WHERE source_key = 'public_proceedings'"
        )

    assert current_matter_source(cursor, fixture["canonical"]) is None
    cursor.execute("ROLLBACK TO SAVEPOINT live_basis_change")


@pytest.mark.integration
@pytest.mark.parametrize(
    "current_title",
    ["17-2026-Z-TEST", "123 Main Street"],
    ids=["case", "address"],
)
def test_selection_source_cannot_survive_promotion_to_case_or_address_scope(
    seeded_selection_source, current_title
):
    """A stale selection cannot bypass a newly discovered broader scope."""
    fixture = seeded_selection_source
    cursor = fixture["cursor"]
    replacement = deepcopy(fixture["payload"])
    replacement["cards"][0]["title"] = current_title
    _insert_evidence(
        cursor,
        proceeding_id=fixture["proceeding_id"],
        suffix=f"replacement-{uuid4().hex}",
        payload=replacement,
    )

    assert current_matter_source(cursor, fixture["canonical"]) is None


@pytest.mark.integration
def test_new_property_link_requires_the_current_property_bundle(
    seeded_selection_source,
):
    fixture = seeded_selection_source
    cursor = fixture["cursor"]
    canonical = fixture["canonical"]
    pidn = "99" + f"{uuid4().int % 100_000_000_000:011d}"
    cursor.execute(
        "INSERT INTO staging.parcels (pidn, propadr, municipality) VALUES (%s, %s, %s)",
        (pidn, "123 Main Street", canonical["municipality"]),
    )
    cursor.execute(
        "INSERT INTO public.municipal_evidence_links "
        "(inference_id, card_id, pidn, match_method, municipality) "
        "VALUES (%s, %s, %s, 'pidn', %s)",
        (
            fixture["inference_id"],
            fixture["payload"]["cards"][0]["id"],
            pidn,
            canonical["municipality"],
        ),
    )
    assert current_matter_source(cursor, canonical) is None

    cursor.execute(
        "SELECT source FROM public.current_municipal_matter_sources "
        "WHERE source->>'candidate_scope' = %s",
        ("property:" + pidn,),
    )
    property_source = cursor.fetchone()[0]
    assert property_source["records"][0]["related_pidns"] == [pidn]
    assert current_matter_source(cursor, property_source) == property_source
