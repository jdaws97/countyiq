"""Migrated-Postgres coverage for immutable LLM inference history."""

from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime

import psycopg2
import psycopg2.extras
import pytest

from countyiq.assets.enrichment.brief_generation import UPSERT_BRIEF_QUERY
from countyiq.assets.enrichment.entity_verification import _replace_cluster_entities
from countyiq.assets.enrichment.proceeding_extraction import (
    _write_proceeding_extractions,
)
from countyiq.assets.enrichment.signal_validation_batched import (
    UPSERT_EVIDENCE_QUERY,
)
from countyiq.lib.intelligence_integrity import content_hash, record_inference_decision
from countyiq.lib.intelligence_resolution import resolve_contradiction
from countyiq.lib.pass3_owner_briefs import UPSERT_OWNER_BRIEF


def _connect():
    return psycopg2.connect(
        host=os.environ.get("DATABASE_HOST", "localhost"),
        port=int(os.environ.get("DATABASE_PORT", "5433")),
        dbname="countyiq_test",
        user=os.environ.get("DATABASE_USER", "dagster_admin"),
        password=os.environ.get("DATABASE_PASSWORD", "localtest"),
    )


class _DatabaseAdapter:
    def __init__(self, connection) -> None:
        self.connection = connection
        self.connection.autocommit = True

    def execute(self, sql, params=None):
        """Mirror DatabaseResource.execute: autocommit, tuple rows."""
        with self.connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall() if cursor.description else None

    @contextmanager
    def dict_cursor(self):
        cursor = self.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            yield cursor
        finally:
            cursor.close()

    @contextmanager
    def transaction(self, *, dict_rows: bool = False):
        prior_autocommit = self.connection.autocommit
        self.connection.autocommit = False
        cursor_factory = psycopg2.extras.RealDictCursor if dict_rows else None
        cursor = self.connection.cursor(cursor_factory=cursor_factory)
        try:
            yield cursor
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        finally:
            cursor.close()
            self.connection.autocommit = prior_autocommit


@pytest.mark.integration
def test_intelligence_integrity_schema_and_projection_links_exist() -> None:
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT to_regclass(name)
                FROM unnest(%s::text[]) AS names(name)
                ORDER BY name
                """,
                (
                    [
                        "meta.intelligence_contradiction_resolutions",
                        "meta.intelligence_contradictions",
                        "meta.intelligence_integrity_status",
                        "meta.intelligence_inference_history",
                        "meta.intelligence_validation_rejections",
                        "meta.intelligence_validation_rejection_status",
                    ],
                ),
            )
            assert all(row[0] is not None for row in cursor.fetchall())

            cursor.execute(
                """
                SELECT table_schema, table_name
                FROM information_schema.columns
                WHERE column_name = 'active_inference_id'
                  AND (table_schema, table_name) IN (
                      ('staging', 'proceeding_extractions'),
                      ('public', 'entity_graph'),
                      ('public', 'evidence'),
                      ('public', 'parcel_briefs'),
                      ('public', 'owner_briefs')
                  )
                """
            )
            assert len(cursor.fetchall()) == 5

            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'meta'
                  AND (
                    (table_name = 'intelligence_inference_history'
                     AND column_name IN (
                        'decision_origin', 'resolution_source_inference_id'
                     ))
                    OR
                    (table_name = 'intelligence_contradiction_resolutions'
                     AND column_name = 'resolved_inference_id')
                  )
                """
            )
            assert {row[0] for row in cursor.fetchall()} == {
                "decision_origin",
                "resolution_source_inference_id",
                "resolved_inference_id",
            }
    finally:
        connection.close()


@pytest.mark.integration
def test_validation_rejection_ledger_is_append_only() -> None:
    connection = _connect()
    subject = f"rejection-test:{uuid.uuid4()}"
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO meta.intelligence_validation_rejections (
                    subject_key, pass_number, output_kind, source_hash, input_hash,
                    requested_model, prompt_version, validation_errors
                )
                VALUES (%s, 2, 'signal_validation', 'source', 'input',
                        'test/model', 'test-prompt', '["missing evidence"]'::jsonb)
                RETURNING rejection_id
                """,
                (subject,),
            )
            rejection_id = cursor.fetchone()[0]
        connection.commit()

        with (
            pytest.raises(psycopg2.Error, match="append-only"),
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                UPDATE meta.intelligence_validation_rejections
                SET prompt_version = 'rewritten'
                WHERE rejection_id = %s
                """,
                (rejection_id,),
            )
        connection.rollback()

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT rejection_count, rejections_last_24h
                FROM meta.intelligence_validation_rejection_status
                """
            )
            total, recent = cursor.fetchone()
            assert total >= 1
            assert recent >= 1
    finally:
        connection.close()


@pytest.mark.integration
@pytest.mark.parametrize(
    "table_name",
    ["intelligence_auto_resolutions", "intelligence_audit_reviews"],
)
def test_auto_resolution_audit_ledgers_reject_truncate(table_name: str) -> None:
    connection = _connect()
    try:
        with (
            pytest.raises(psycopg2.Error, match="append-only"),
            connection.cursor() as cursor,
        ):
            cursor.execute(f"TRUNCATE meta.{table_name}")
        connection.rollback()
    finally:
        connection.close()


@pytest.mark.integration
def test_same_evidence_semantic_flip_is_quarantined_and_history_is_append_only() -> (
    None
):
    connection = _connect()
    database = _DatabaseAdapter(connection)
    subject = f"integrity-test:{uuid.uuid4()}"
    common = {
        "subject_key": subject,
        "pass_number": 2,
        "output_kind": "signal_validation",
        "decision_key": "signal_batch",
        "source_hash": "source-a",
        "input_hash": "input-a",
        "requested_model": "test/model",
        "prompt_version": "test-prompt",
        "evidence_refs": ["signal:vacancy"],
    }
    confirmed = [
        {
            "signal_key": "vacancy",
            "validation_status": "confirmed",
            "adjusted_significance": "high",
        }
    ]
    irrelevant = [
        {
            "signal_key": "vacancy",
            "validation_status": "irrelevant",
            "adjusted_significance": "none",
        }
    ]
    try:
        first = record_inference_decision(
            database,
            **common,
            payload={"validations": confirmed},
            semantic_decision=confirmed,
        )
        assert first.accepted

        repeat = record_inference_decision(
            database,
            **common,
            payload={"validations": confirmed, "wording": "changed"},
            semantic_decision=confirmed,
        )
        assert repeat.accepted

        challenger = record_inference_decision(
            database,
            **common,
            payload={"validations": irrelevant},
            semantic_decision=irrelevant,
        )
        assert not challenger.accepted
        assert challenger.contradiction_id is not None

        changed_source = record_inference_decision(
            database,
            **{**common, "source_hash": "source-b", "input_hash": "input-b"},
            payload={"validations": irrelevant},
            semantic_decision=irrelevant,
        )
        assert changed_source.accepted

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT disposition
                FROM meta.intelligence_inference_history
                WHERE subject_key = %s
                ORDER BY inference_id
                """,
                (subject,),
            )
            assert [row[0] for row in cursor.fetchall()] == [
                "accepted",
                "accepted",
                "quarantined",
                "accepted",
            ]

        with (
            pytest.raises(psycopg2.errors.RaiseException, match="append-only"),
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                UPDATE meta.intelligence_inference_history
                SET payload = '{}'::jsonb
                WHERE inference_id = %s
                """,
                (first.inference_id,),
            )

        with (
            pytest.raises(psycopg2.errors.RaiseException, match="append-only"),
            connection.cursor() as cursor,
        ):
            cursor.execute("TRUNCATE meta.intelligence_contradiction_resolutions")
    finally:
        connection.close()


@pytest.mark.integration
def test_entity_projection_replacement_removes_stale_cluster_membership() -> None:
    connection = _connect()
    database = _DatabaseAdapter(connection)
    suffix = uuid.uuid4().hex
    name_a = f"INTEGRITY A {suffix}"
    name_b = f"INTEGRITY B {suffix}"
    stale = f"STALE {suffix}"
    try:
        gate = record_inference_decision(
            database,
            subject_key=f"entity-cluster:{suffix}",
            pass_number=1,
            output_kind="entity_verification",
            decision_key="partition",
            source_hash="source",
            input_hash="input",
            requested_model="test/model",
            prompt_version="test-prompt",
            payload={"entities": []},
            semantic_decision={"entities": []},
        )
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO public.entity_graph
                    (canonical_name, linked_names, linked_sources, relationships)
                VALUES (%s, %s, '{}'::jsonb, '[]'::jsonb)
                """,
                (name_a, [name_a, name_b, stale]),
            )

        inserted = _replace_cluster_entities(
            database,
            [
                {
                    "canonical_name": name_a,
                    "member_names": [name_a],
                    "entity_type": "llc",
                    "confidence": 0.9,
                    "reasoning": "test",
                    "linked_records": {
                        "parcels": [],
                        "tax_claims": [],
                        "plcb_licenses": [],
                        "corporate_entities": [],
                        "proceedings": [],
                    },
                    "relationships": [],
                }
            ],
            [name_a, name_b],
            inference_id=gate.inference_id,
        )
        assert inserted == 1

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT linked_names, active_inference_id
                FROM public.entity_graph
                WHERE canonical_name = %s
                """,
                (name_a,),
            )
            rows = cursor.fetchall()
            assert rows == [([name_a], gate.inference_id)]
            cursor.execute(
                "DELETE FROM public.entity_graph WHERE canonical_name = %s",
                (name_a,),
            )
    finally:
        connection.close()


@pytest.mark.integration
def test_proceeding_projection_points_to_immutable_inference() -> None:
    connection = _connect()
    database = _DatabaseAdapter(connection)
    suffix = uuid.uuid4().hex
    proceeding_id = None
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO staging.public_proceedings
                    (body_name, meeting_date, proceeding_type, raw_text,
                     source_url, document_url, content_hash)
                VALUES (%s, CURRENT_DATE, 'planning', %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    f"INTEGRITY BODY {suffix}",
                    "The board approved Acme.",
                    f"https://example.test/{suffix}",
                    f"https://example.test/{suffix}.pdf",
                    suffix,
                ),
            )
            proceeding_id = cursor.fetchone()[0]

        gate = record_inference_decision(
            database,
            subject_key=f"proceeding:{proceeding_id}",
            pass_number=0,
            output_kind="proceeding_extraction",
            decision_key="document",
            source_hash="source",
            input_hash="input",
            requested_model="test/model",
            prompt_version="test-prompt",
            payload={"extractions": []},
            semantic_decision=[],
        )
        _, inserted = _write_proceeding_extractions(
            database,
            proceeding_id=proceeding_id,
            extractions=[
                {
                    "extraction_type": "rezoning_application",
                    "applicant_name": "Acme",
                    "parcel_reference": "P1",
                    "decision": "approved",
                    "conditions": [],
                    "supporting_text": "The board approved Acme.",
                    "confidence": "high",
                    "event_tags": ["approval"],
                    "related_entities": [],
                }
            ],
            model_used="test-model",
            inference_id=gate.inference_id,
        )
        assert inserted == 1

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT active_inference_id
                FROM staging.proceeding_extractions
                WHERE proceeding_id = %s
                """,
                (proceeding_id,),
            )
            assert cursor.fetchall() == [(gate.inference_id,)]
            cursor.execute(
                "DELETE FROM staging.proceeding_extractions WHERE proceeding_id = %s",
                (proceeding_id,),
            )
            cursor.execute(
                "DELETE FROM staging.public_proceedings WHERE id = %s",
                (proceeding_id,),
            )
    finally:
        connection.close()


@pytest.mark.integration
def test_human_resolution_promotes_challenger_and_projection_atomically() -> None:
    connection = _connect()
    database = _DatabaseAdapter(connection)
    suffix = uuid.uuid4().hex
    raw_text = ("The board considered Acme and denied the application. " * 6).strip()
    body_name = f"RESOLUTION BODY {suffix}"
    document_url = f"https://example.test/{suffix}.pdf"
    meeting_date = datetime(2026, 8, 31, tzinfo=UTC).date()
    content_version = f"content-{suffix}"
    proceeding_id = None
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO staging.public_proceedings
                    (body_name, meeting_date, proceeding_type, raw_text,
                     source_url, document_url, content_hash)
                VALUES (%s, %s, 'planning', %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    body_name,
                    meeting_date,
                    raw_text,
                    f"https://example.test/{suffix}",
                    document_url,
                    content_version,
                ),
            )
            proceeding_id = cursor.fetchone()[0]

        source_version = content_hash(
            {
                "document_content_hash": content_version,
                "raw_text_hash": content_hash(raw_text),
            }
        )
        source_hash = content_hash(
            {
                "proceeding_id": proceeding_id,
                "body_name": body_name,
                "meeting_date": meeting_date,
                "proceeding_type": "planning",
                "document_url": document_url,
                "source_version": source_version,
            }
        )
        prior_extraction = {
            "extraction_type": "rezoning_application",
            "applicant_name": "Acme",
            "parcel_reference": "P1",
            "project_name": "Acme Site",
            "decision": "approved",
            "conditions": [],
            "supporting_text": "The board considered Acme and denied the application.",
            "confidence": "high",
            "event_tags": ["approval"],
            "related_entities": [],
        }
        challenger_extraction = {**prior_extraction, "decision": "denied"}
        prior = record_inference_decision(
            database,
            subject_key=f"proceeding:{proceeding_id}",
            pass_number=0,
            output_kind="proceeding_extraction",
            decision_key="document",
            source_hash=source_hash,
            input_hash="prior-input",
            requested_model="test/prior",
            prompt_version="test-prompt",
            payload={"extractions": [prior_extraction]},
            semantic_decision={"decision": "approved"},
        )
        _write_proceeding_extractions(
            database,
            proceeding_id=proceeding_id,
            extractions=[prior_extraction],
            model_used="prior",
            inference_id=prior.inference_id,
        )
        challenger = record_inference_decision(
            database,
            subject_key=f"proceeding:{proceeding_id}",
            pass_number=0,
            output_kind="proceeding_extraction",
            decision_key="document",
            source_hash=source_hash,
            input_hash="challenger-input",
            requested_model="test/challenger",
            prompt_version="test-prompt",
            payload={"extractions": [challenger_extraction]},
            semantic_decision={"decision": "denied"},
        )
        assert challenger.accepted is False

        resolved = resolve_contradiction(
            database,
            contradiction_id=challenger.contradiction_id,
            resolution="accept_challenger",
            resolved_by="integration-test",
            rationale="The cited sentence explicitly says denied.",
            expected_source_hash=source_hash,
        )

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT decision, active_inference_id
                FROM staging.proceeding_extractions
                WHERE proceeding_id = %s
                  AND extraction_type = 'rezoning_application'
                """,
                (proceeding_id,),
            )
            assert cursor.fetchone() == ("denied", resolved.resolved_inference_id)
            cursor.execute(
                """
                SELECT decision_origin, resolution_source_inference_id, disposition
                FROM meta.intelligence_inference_history
                WHERE inference_id = %s
                """,
                (resolved.resolved_inference_id,),
            )
            assert cursor.fetchone() == (
                "human_resolution",
                challenger.inference_id,
                "accepted",
            )
            cursor.execute(
                """
                SELECT resolution, resolved_inference_id
                FROM meta.intelligence_contradiction_resolutions
                WHERE contradiction_id = %s
                """,
                (challenger.contradiction_id,),
            )
            assert cursor.fetchone() == (
                "accept_challenger",
                resolved.resolved_inference_id,
            )
    finally:
        if proceeding_id is not None:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM staging.proceeding_extractions WHERE proceeding_id = %s",
                    (proceeding_id,),
                )
                cursor.execute(
                    "DELETE FROM staging.public_proceedings WHERE id = %s",
                    (proceeding_id,),
                )
        connection.close()


@pytest.mark.integration
def test_evidence_and_brief_upserts_preserve_active_provenance() -> None:
    connection = _connect()
    database = _DatabaseAdapter(connection)
    suffix = uuid.uuid4().hex
    pidn = f"I{suffix[:12]}"
    canonical_name = f"INTEGRITY OWNER {suffix}"
    now = datetime.now(UTC).isoformat()
    try:
        gates = {}
        for key, pass_number, output_kind in (
            ("evidence", 2, "signal_validation"),
            ("parcel", 3, "parcel_brief"),
            ("owner", 3, "owner_brief"),
        ):
            gates[key] = record_inference_decision(
                database,
                subject_key=f"projection:{key}:{suffix}",
                pass_number=pass_number,
                output_kind=output_kind,
                decision_key="test",
                source_hash="source",
                input_hash="input",
                requested_model="test/model",
                prompt_version="test-prompt",
                payload={"kind": key},
                semantic_decision={"kind": key},
            )

        with connection.cursor() as cursor:
            cursor.execute(
                UPSERT_EVIDENCE_QUERY,
                {
                    "pidn": pidn,
                    "signal_key": "vacancy",
                    "claim": "vacancy classified confirmed with high significance",
                    "evidence_data": "{}",
                    "source_url": None,
                    "internal_url": f"/property/{pidn}",
                    "validation_status": "confirmed",
                    "adjusted_significance": "high",
                    "validation_reasoning": "Grounded [Evidence: signal:vacancy].",
                    "cross_references": '["signal:vacancy"]',
                    "validated_at": now,
                    "model_version": "test/model",
                    "prompt_version": "test-prompt",
                    "n_trials": 1,
                    "trial_agreement": None,
                    "confidence": None,
                    "active_inference_id": gates["evidence"].inference_id,
                },
            )
            cursor.execute(
                UPSERT_BRIEF_QUERY,
                {
                    "pidn": pidn,
                    "brief_text": "Grounded [Signal: vacancy].",
                    "assessment": "emerging",
                    "assessment_reasoning": "Grounded [Signal: vacancy].",
                    "key_questions": [],
                    "signal_count": 1,
                    "citations": '["vacancy"]',
                    "pass_metadata": "{}",
                    "generated_at": now,
                    "model_version": "test/model",
                    "prompt_version": "test-prompt",
                    "n_trials": 1,
                    "trial_agreement": None,
                    "confidence": None,
                    "active_inference_id": gates["parcel"].inference_id,
                },
            )
            cursor.execute(
                UPSERT_OWNER_BRIEF,
                {
                    "canonical_name": canonical_name,
                    "owner_id": None,
                    "brief_text": f"Grounded [Signal: vacancy] [Parcel: {pidn}].",
                    "portfolio_strategy": "holder",
                    "concentration_notes": f"Grounded [Parcel: {pidn}].",
                    "key_pattern": "Grounded [Signal: vacancy].",
                    "recommendation": "monitor",
                    "urgency": "long_term_12mo",
                    "top_risk": f"Grounded [Parcel: {pidn}].",
                    "evidence_strength": "weak",
                    "citations": '["vacancy"]',
                    "parcel_citations": f'["{pidn}"]',
                    "n_parcels": 3,
                    "model_version": "test/model",
                    "prompt_version": "test-prompt",
                    "n_trials": 1,
                    "trial_agreement": None,
                    "confidence": None,
                    "pass_metadata": "{}",
                    "generated_at": now,
                    "active_inference_id": gates["owner"].inference_id,
                },
            )
            cursor.execute(
                """
                SELECT
                    (SELECT active_inference_id FROM public.evidence
                     WHERE pidn = %s AND signal_key = 'vacancy'),
                    (SELECT active_inference_id FROM public.parcel_briefs
                     WHERE pidn = %s),
                    (SELECT active_inference_id FROM public.owner_briefs
                     WHERE canonical_name = %s)
                """,
                (pidn, pidn, canonical_name),
            )
            assert cursor.fetchone() == (
                gates["evidence"].inference_id,
                gates["parcel"].inference_id,
                gates["owner"].inference_id,
            )
            cursor.execute(
                "DELETE FROM public.owner_briefs WHERE canonical_name = %s",
                (canonical_name,),
            )
            cursor.execute("DELETE FROM public.parcel_briefs WHERE pidn = %s", (pidn,))
            cursor.execute("DELETE FROM public.evidence WHERE pidn = %s", (pidn,))
    finally:
        connection.close()


@pytest.mark.integration
def test_routine_same_version_flip_auto_resolves_to_incumbent(monkeypatch) -> None:
    """A watchlist->pass brief flip on identical model/prompt/evidence keeps the incumbent."""
    from countyiq.lib import intelligence_resolution
    from countyiq.lib.intelligence_autoresolve import auto_resolve_contradiction
    from countyiq.lib.intelligence_integrity import parcel_brief_semantic_decision

    monkeypatch.delenv("COUNTYIQ_JUDGE_MODEL", raising=False)
    monkeypatch.delenv("COUNTYIQ_AUTO_RESOLVE_CONTRADICTIONS", raising=False)
    connection = _connect()
    database = _DatabaseAdapter(connection)
    pidn = f"auto-{uuid.uuid4().hex[:12]}"
    source_hash = content_hash({"pidn": pidn, "evidence": "same"})
    monkeypatch.setattr(
        intelligence_resolution,
        "_current_source_hash",
        lambda cur, contradiction, prior, challenger: contradiction["source_hash"],
    )

    def brief(recommendation: str) -> dict:
        return {
            "recommendation": recommendation,
            "urgency": "none",
            "top_signal_key": "vacancy",
            "evidence_strength": "moderate",
            "assessment": "speculative",
            "brief": "Vacant parcel [Signal: vacancy].",
            "citations": ["vacancy"],
        }

    common = dict(
        subject_key=pidn,
        pass_number=3,
        output_kind="parcel_brief",
        decision_key="brief",
        source_hash=source_hash,
        input_hash="same-model-same-prompt",
        requested_model="test/model",
        prompt_version="test-prompt",
    )
    try:
        first = record_inference_decision(
            database,
            payload=brief("watchlist"),
            semantic_decision=parcel_brief_semantic_decision(brief("watchlist")),
            **common,
        )
        assert first.accepted
        second = record_inference_decision(
            database,
            payload=brief("pass"),
            semantic_decision=parcel_brief_semantic_decision(brief("pass")),
            **common,
        )
        assert not second.accepted and second.contradiction_id

        outcome = auto_resolve_contradiction(database, second.contradiction_id)
        assert outcome.outcome == "auto_resolved"
        assert outcome.resolution == "accept_prior"

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT resolved_by, resolution FROM meta.intelligence_contradiction_resolutions WHERE contradiction_id = %s",
                (second.contradiction_id,),
            )
            assert cursor.fetchone() == ("auto:rule", "accept_prior")
            cursor.execute(
                "SELECT outcome, consequential, version_upgrade FROM meta.intelligence_auto_resolutions WHERE contradiction_id = %s",
                (second.contradiction_id,),
            )
            assert cursor.fetchone() == ("auto_resolved", False, False)
            cursor.execute(
                "SELECT COUNT(*) FROM meta.intelligence_inference_history WHERE subject_key = %s AND decision_origin = 'auto_resolution'",
                (pidn,),
            )
            assert cursor.fetchone()[0] == 1
            cursor.execute(
                "SELECT COUNT(*) FROM meta.intelligence_review_queue WHERE subject_key = %s",
                (pidn,),
            )
            assert cursor.fetchone()[0] == 0

        # A pursue_now -> pass flip on a fresh parcel is consequential and must
        # wait for a person (the auto-resolved parcel above now serves the
        # incumbent "watchlist", so its next flip would be routine again).
        pidn2 = f"auto-{uuid.uuid4().hex[:12]}"
        common2 = {
            **common,
            "subject_key": pidn2,
            "source_hash": content_hash({"pidn": pidn2}),
        }
        pursue = record_inference_decision(
            database,
            payload=brief("pursue_now"),
            semantic_decision=parcel_brief_semantic_decision(brief("pursue_now")),
            **common2,
        )
        assert pursue.accepted
        third = record_inference_decision(
            database,
            payload=brief("pass"),
            semantic_decision=parcel_brief_semantic_decision(brief("pass")),
            **common2,
        )
        assert not third.accepted
        queued = auto_resolve_contradiction(database, third.contradiction_id)
        assert queued.outcome == "queued_consequential"
        assert "recommendation flipped pursue_now -> pass" in queued.rationale
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT queue_reason FROM meta.intelligence_review_queue WHERE subject_key = %s",
                (pidn2,),
            )
            assert cursor.fetchone() == ("queued_consequential",)
    finally:
        connection.close()
