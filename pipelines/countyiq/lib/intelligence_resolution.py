"""Human review workflow for quarantined intelligence contradictions.

The product API remains read-only. Operators use this module through the
pipeline CLI with a writer credential. A resolution appends a human-origin
inference, updates or retracts the serving projection, records the resolution,
and repairs pass status in one transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from countyiq.lib.intelligence_integrity import canonical_json, content_hash

ResolutionDecision = Literal["accept_prior", "accept_challenger", "discard_both"]
_RESOLUTIONS = {"accept_prior", "accept_challenger", "discard_both"}


class ContradictionResolutionError(RuntimeError):
    """Raised when a contradiction cannot be safely resolved."""


@dataclass(frozen=True)
class ResolutionResult:
    contradiction_id: int
    resolution_id: int
    resolved_inference_id: int
    resolution: ResolutionDecision
    output_kind: str
    subject_key: str


def list_unresolved_contradictions(database, *, limit: int = 50) -> list[dict]:
    """Return a bounded oldest-first operator queue without source payloads."""

    limit = min(max(int(limit), 1), 500)
    rows = database.execute(
        """
        SELECT
            c.contradiction_id, c.pass_number, c.output_kind, c.subject_key,
            c.decision_key, c.source_hash, c.prior_inference_id,
            c.challenger_inference_id, c.reason, c.detected_at,
            prior.requested_model AS prior_model,
            challenger.requested_model AS challenger_model
        FROM meta.intelligence_contradictions c
        JOIN meta.intelligence_inference_history prior
          ON prior.inference_id = c.prior_inference_id
        JOIN meta.intelligence_inference_history challenger
          ON challenger.inference_id = c.challenger_inference_id
        LEFT JOIN meta.intelligence_contradiction_resolutions resolution
          USING (contradiction_id)
        WHERE resolution.contradiction_id IS NULL
        ORDER BY c.detected_at, c.contradiction_id
        LIMIT %s
        """,
        (limit,),
    ) or []
    keys = (
        "contradiction_id", "pass_number", "output_kind", "subject_key",
        "decision_key", "source_hash", "prior_inference_id",
        "challenger_inference_id", "reason", "detected_at", "prior_model",
        "challenger_model",
    )
    return [
        dict(row) if isinstance(row, dict) else dict(zip(keys, row, strict=True))
        for row in rows
    ]


def get_contradiction(database, contradiction_id: int) -> dict | None:
    """Return the complete immutable evidence needed for human review."""

    rows = database.execute(
        """
        SELECT
            row_to_json(c) AS contradiction,
            row_to_json(prior) AS prior,
            row_to_json(challenger) AS challenger,
            row_to_json(res) AS resolution
        FROM meta.intelligence_contradictions c
        JOIN meta.intelligence_inference_history prior
          ON prior.inference_id = c.prior_inference_id
        JOIN meta.intelligence_inference_history challenger
          ON challenger.inference_id = c.challenger_inference_id
        -- Alias must not be "resolution": with USING, that bare name resolves
        -- to the TEXT column of the same name and row_to_json(text) fails.
        LEFT JOIN meta.intelligence_contradiction_resolutions res
          USING (contradiction_id)
        WHERE c.contradiction_id = %s
        """,
        (contradiction_id,),
    ) or []
    if not rows:
        return None
    row = rows[0]
    if isinstance(row, dict):
        return dict(row)
    return dict(zip(("contradiction", "prior", "challenger", "resolution"), row, strict=True))


def resolve_contradiction(
    database,
    *,
    contradiction_id: int,
    resolution: ResolutionDecision,
    resolved_by: str,
    rationale: str,
    expected_source_hash: str,
    decision_origin: str = "human_resolution",
) -> ResolutionResult:
    """Resolve one contradiction and its serving projection atomically.

    ``decision_origin`` is ``human_resolution`` for the CLI and
    ``auto_resolution`` for the rule/judge policy in
    :mod:`countyiq.lib.intelligence_autoresolve`; both are recorded on the
    resolved inference so the ledger shows who decided.
    """

    if resolution not in _RESOLUTIONS:
        raise ValueError(f"unsupported resolution: {resolution}")
    if decision_origin not in {"human_resolution", "auto_resolution"}:
        raise ValueError(f"unsupported decision origin: {decision_origin}")
    if not resolved_by.strip():
        raise ValueError("resolved_by is required")
    if len(rationale.strip()) < 12:
        raise ValueError("rationale must contain at least 12 characters")
    if not expected_source_hash.strip():
        raise ValueError("expected_source_hash is required")

    with database.transaction(dict_rows=True) as cur:
        cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        cur.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"intelligence-contradiction:{contradiction_id}",),
        )
        cur.execute(
            """
            SELECT
                row_to_json(c) AS contradiction,
                row_to_json(prior) AS prior,
                row_to_json(challenger) AS challenger,
                row_to_json(existing_resolution) AS existing_resolution
            FROM meta.intelligence_contradictions c
            JOIN meta.intelligence_inference_history prior
              ON prior.inference_id = c.prior_inference_id
            JOIN meta.intelligence_inference_history challenger
              ON challenger.inference_id = c.challenger_inference_id
            LEFT JOIN meta.intelligence_contradiction_resolutions existing_resolution
              USING (contradiction_id)
            WHERE c.contradiction_id = %s
            FOR UPDATE OF c
            """,
            (contradiction_id,),
        )
        detail = cur.fetchone()
        if detail is None:
            raise ContradictionResolutionError(
                f"contradiction {contradiction_id} does not exist"
            )

        contradiction = detail["contradiction"]
        prior = detail["prior"]
        challenger = detail["challenger"]
        if detail["existing_resolution"] is not None:
            raise ContradictionResolutionError(
                f"contradiction {contradiction_id} is already resolved"
            )
        if contradiction["source_hash"] != expected_source_hash:
            raise ContradictionResolutionError(
                "source-hash confirmation failed; inspect the contradiction again"
            )

        cur.execute(
            """
            SELECT inference_id
            FROM meta.intelligence_inference_history
            WHERE pass_number = %s
              AND output_kind = %s
              AND subject_key = %s
              AND decision_key = %s
              AND disposition = 'accepted'
            ORDER BY inference_id DESC
            LIMIT 1
            """,
            (
                contradiction["pass_number"], contradiction["output_kind"],
                contradiction["subject_key"], contradiction["decision_key"],
            ),
        )
        latest = cur.fetchone()
        if latest is None or latest["inference_id"] != contradiction["prior_inference_id"]:
            raise ContradictionResolutionError(
                "the prior inference is no longer current; review the newer version"
            )

        current_source_hash = _current_source_hash(cur, contradiction, prior, challenger)
        if current_source_hash != contradiction["source_hash"]:
            raise ContradictionResolutionError(
                "current source evidence no longer matches this contradiction; rerun the pass"
            )

        selected = challenger if resolution == "accept_challenger" else prior
        if resolution == "discard_both":
            payload = {
                "resolution": "discard_both",
                "discarded_inference_ids": [
                    contradiction["prior_inference_id"],
                    contradiction["challenger_inference_id"],
                ],
            }
            decision_fingerprint = content_hash({"resolution": "discard_both"})
            citations: list[str] = []
            evidence_refs: list[str] = []
        else:
            payload = selected["payload"]
            decision_fingerprint = selected["decision_fingerprint"]
            citations = selected["citations"] or []
            evidence_refs = selected["evidence_refs"] or []

        cur.execute(
            """
            INSERT INTO meta.intelligence_inference_history (
                subject_key, pass_number, output_kind, decision_key,
                source_hash, input_hash, requested_model, served_model, provider,
                prompt_version, output_hash, decision_fingerprint, payload,
                citations, evidence_refs, disposition, supersedes_inference_id,
                decision_origin, resolution_source_inference_id
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s::jsonb, %s::jsonb, %s::jsonb, 'accepted', %s,
                %s, %s
            )
            RETURNING inference_id
            """,
            (
                contradiction["subject_key"], contradiction["pass_number"],
                contradiction["output_kind"], contradiction["decision_key"],
                contradiction["source_hash"], challenger["input_hash"],
                selected["requested_model"], selected["served_model"],
                selected["provider"], selected["prompt_version"],
                content_hash(payload), decision_fingerprint, canonical_json(payload),
                canonical_json(citations), canonical_json(evidence_refs),
                contradiction["prior_inference_id"], decision_origin,
                selected["inference_id"],
            ),
        )
        resolved_inference_id = cur.fetchone()["inference_id"]

        _apply_projection(
            cur,
            contradiction=contradiction,
            prior=prior,
            challenger=challenger,
            resolution=resolution,
            resolved_inference_id=resolved_inference_id,
            resolved_by=resolved_by.strip(),
        )

        cur.execute(
            """
            INSERT INTO meta.intelligence_contradiction_resolutions (
                contradiction_id, resolution, resolved_by, rationale,
                resolved_inference_id
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING resolution_id
            """,
            (
                contradiction_id, resolution, resolved_by.strip(), rationale.strip(),
                resolved_inference_id,
            ),
        )
        resolution_id = cur.fetchone()["resolution_id"]

        if contradiction["pass_number"] > 0:
            cur.execute(
                """
                INSERT INTO meta.intelligence_passes
                    (pidn, pass_number, status, last_run_at, input_hash, error_message)
                VALUES (%s, %s, 'complete', NOW(), %s, NULL)
                ON CONFLICT (pidn, pass_number)
                DO UPDATE SET
                    status = 'complete', last_run_at = NOW(),
                    input_hash = EXCLUDED.input_hash, error_message = NULL
                """,
                (
                    contradiction["subject_key"], contradiction["pass_number"],
                    challenger["input_hash"],
                ),
            )

    return ResolutionResult(
        contradiction_id=contradiction_id,
        resolution_id=resolution_id,
        resolved_inference_id=resolved_inference_id,
        resolution=resolution,
        output_kind=contradiction["output_kind"],
        subject_key=contradiction["subject_key"],
    )


def _candidate_names(prior: dict, challenger: dict) -> list[str]:
    refs = list(prior.get("evidence_refs") or []) + list(
        challenger.get("evidence_refs") or []
    )
    return sorted({ref.split(":", 1)[1] for ref in refs if ref.startswith("candidate:")})


def _current_source_hash(cur, contradiction: dict, prior: dict, challenger: dict) -> str:
    kind = contradiction["output_kind"]
    subject_key = contradiction["subject_key"]
    if kind == "proceeding_extraction":
        from countyiq.assets.enrichment.proceeding_extraction import (
            _MAX_RAW_TEXT_CHARS,
            _MIN_RAW_TEXT_CHARS,
        )

        proceeding_id = int(subject_key.split(":", 1)[1])
        cur.execute(
            """
            SELECT id, body_name, meeting_date, proceeding_type, document_url,
                   raw_text, content_hash
            FROM staging.public_proceedings
            WHERE id = %s AND valid_to IS NULL
            """,
            (proceeding_id,),
        )
        row = cur.fetchone()
        if row is None:
            return ""
        raw_text = row["raw_text"] or ""
        if len(raw_text.strip()) >= _MIN_RAW_TEXT_CHARS:
            verification_text = raw_text[:_MAX_RAW_TEXT_CHARS]
            source_version = content_hash({
                "document_content_hash": row["content_hash"],
                "raw_text_hash": content_hash(verification_text),
            })
        else:
            source_version = row["content_hash"]
        if not source_version:
            return ""
        return content_hash({
            "proceeding_id": row["id"], "body_name": row["body_name"],
            "meeting_date": row["meeting_date"],
            "proceeding_type": row["proceeding_type"],
            "document_url": row["document_url"], "source_version": source_version,
        })

    if kind == "entity_verification":
        from countyiq.lib.intelligence_common import compute_input_hash
        from countyiq.lib.pass1_entity_verification import gather_cluster_records

        names = _candidate_names(prior, challenger)
        return compute_input_hash(gather_cluster_records(cur, names)) if names else ""

    if kind == "signal_validation":
        from countyiq.lib.intelligence_common import compute_input_hash
        from countyiq.lib.pass2_batched_validation import gather_parcel_batch_context

        return compute_input_hash(gather_parcel_batch_context(cur, subject_key))

    if kind == "parcel_brief":
        from countyiq.lib.intelligence_common import compute_input_hash
        from countyiq.lib.pass3_brief_generation import gather_brief_context

        return compute_input_hash(gather_brief_context(cur, subject_key))

    if kind == "owner_brief":
        from countyiq.lib.pass3_owner_briefs import (
            OWNER_PORTFOLIO_QUERY,
            PORTFOLIO_EVIDENCE_QUERY,
        )

        cur.execute(
            """
            SELECT owner_id
            FROM public.owner_briefs
            WHERE active_inference_id = %s
            """,
            (contradiction["prior_inference_id"],),
        )
        projection = cur.fetchone()
        if projection is None:
            return ""
        cur.execute(OWNER_PORTFOLIO_QUERY, {"owner_id": projection["owner_id"]})
        owner = cur.fetchone()
        if owner is None:
            return ""
        owner = dict(owner)
        cur.execute(PORTFOLIO_EVIDENCE_QUERY, {"pidns": owner["pidns"] or []})
        evidence_rows = [dict(row) for row in cur.fetchall()]
        return content_hash({
            "owner": owner,
            "evidence": [
                {
                    key: row.get(key)
                    for key in (
                        "pidn", "signal_key", "validation_status",
                        "adjusted_significance", "validation_reasoning",
                        "evidence_data", "confidence", "municipality",
                    )
                }
                for row in evidence_rows
            ],
        })

    raise ContradictionResolutionError(f"unsupported output kind: {kind}")


def _apply_projection(
    cur,
    *,
    contradiction: dict,
    prior: dict,
    challenger: dict,
    resolution: ResolutionDecision,
    resolved_inference_id: int,
    resolved_by: str,
) -> None:
    table_by_kind = {
        "proceeding_extraction": "staging.proceeding_extractions",
        "entity_verification": "public.entity_graph",
        "signal_validation": "public.evidence",
        "parcel_brief": "public.parcel_briefs",
        "owner_brief": "public.owner_briefs",
    }
    kind = contradiction["output_kind"]
    table = table_by_kind[kind]
    prior_id = contradiction["prior_inference_id"]

    if resolution == "accept_prior":
        cur.execute(
            f"UPDATE {table} SET active_inference_id = %s WHERE active_inference_id = %s",
            (resolved_inference_id, prior_id),
        )
        return
    if resolution == "discard_both":
        cur.execute(f"DELETE FROM {table} WHERE active_inference_id = %s", (prior_id,))
        return

    payload = challenger["payload"]
    if kind == "proceeding_extraction":
        _project_proceeding(cur, contradiction, challenger, payload, resolved_inference_id)
    elif kind == "entity_verification":
        _project_entities(cur, prior, challenger, payload, resolved_inference_id)
    elif kind == "signal_validation":
        _project_signals(cur, contradiction, challenger, payload, resolved_inference_id)
    elif kind == "parcel_brief":
        _project_parcel_brief(
            cur, contradiction, challenger, payload, resolved_inference_id, resolved_by
        )
    elif kind == "owner_brief":
        _project_owner_brief(
            cur, contradiction, challenger, payload, resolved_inference_id, resolved_by
        )


def _project_proceeding(cur, contradiction, challenger, payload, inference_id: int) -> None:
    from countyiq.lib.intelligence_events import normalize_development_tags

    proceeding_id = int(contradiction["subject_key"].split(":", 1)[1])
    model_used = Path(challenger["requested_model"].split("|", 1)[0]).name
    cur.execute(
        "DELETE FROM staging.proceeding_extractions WHERE proceeding_id = %s",
        (proceeding_id,),
    )
    extractions = payload.get("extractions", [])
    for extraction in extractions:
        conditions = extraction.get("conditions") or []
        event_tags = normalize_development_tags(
            extraction_type=extraction.get("extraction_type"),
            decision=extraction.get("decision"),
            conditions=conditions,
            proposed_tags=extraction.get("event_tags") or [],
            what_happens_next=extraction.get("what_happens_next"),
            upcoming_date=extraction.get("upcoming_date"),
        )
        related_entities = list(dict.fromkeys(
            value.strip()
            for value in [
                extraction.get("applicant_name"),
                *(extraction.get("related_entities") or []),
            ]
            if isinstance(value, str) and value.strip()
        ))
        confidence = {"high": 0.9, "medium": 0.6, "low": 0.3}.get(
            extraction.get("confidence", "low"), 0.3
        )
        cur.execute(
            """
            INSERT INTO staging.proceeding_extractions (
                proceeding_id, extraction_type, applicant_name, parcel_reference,
                current_zoning, proposed_zoning, decision, conditions,
                supporting_text, extraction_confidence, model_used, page_number,
                event_tags, project_name, related_entities, what_happened,
                why_it_matters, what_happens_next, upcoming_date,
                interpretation_generated_at, active_inference_id
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, NULL,
                %s, %s, %s, %s, %s, %s, %s, NOW(), %s
            )
            """,
            (
                proceeding_id, extraction.get("extraction_type"),
                extraction.get("applicant_name"), extraction.get("parcel_reference"),
                extraction.get("current_zoning"), extraction.get("proposed_zoning"),
                extraction.get("decision"), canonical_json(conditions) if conditions else None,
                extraction.get("supporting_text"), confidence, model_used, event_tags,
                extraction.get("project_name"), related_entities,
                extraction.get("what_happened"), extraction.get("why_it_matters"),
                extraction.get("what_happens_next"), extraction.get("upcoming_date"),
                inference_id,
            ),
        )
    if not extractions:
        cur.execute(
            """
            INSERT INTO staging.proceeding_extractions
                (proceeding_id, extraction_type, extraction_confidence,
                 model_used, page_number, active_inference_id)
            VALUES (%s, '_no_extractions', 0.0, %s, 0, %s)
            """,
            (proceeding_id, model_used, inference_id),
        )
    cur.execute(
        """
        INSERT INTO staging.proceeding_extractions
            (proceeding_id, extraction_type, extraction_confidence,
             model_used, page_number, active_inference_id)
        VALUES (%s, '_complete', 1.0, %s, 0, %s)
        """,
        (proceeding_id, model_used, inference_id),
    )


def _project_entities(cur, prior, challenger, payload, inference_id: int) -> None:
    from countyiq.assets.enrichment.entity_verification import (
        _candidate_names as entity_candidate_names,
    )
    from countyiq.assets.enrichment.entity_verification import (
        _merge_linked_sources,
        _merge_relationships,
    )

    names = _candidate_names(prior, challenger)
    cur.execute(
        """
        DELETE FROM public.entity_graph
        WHERE canonical_name = ANY(%s)
           OR COALESCE(linked_names, ARRAY[]::text[]) && %s::text[]
        """,
        (names, names),
    )
    for entity in payload.get("entities", []):
        linked_records = entity.get("linked_records", {})
        cur.execute(
            """
            INSERT INTO public.entity_graph (
                canonical_name, entity_type, linked_names, linked_sources,
                relationships, verification_status, verification_reasoning,
                verified_at, active_inference_id
            ) VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, NOW(), %s)
            """,
            (
                entity.get("canonical_name", ""), entity.get("entity_type", "unknown"),
                entity_candidate_names(entity) or None,
                canonical_json(_merge_linked_sources({}, linked_records)),
                canonical_json(_merge_relationships([], entity.get("relationships", []))),
                "verified" if entity.get("confidence", 0) >= 0.7 else "tentative",
                entity.get("reasoning", ""), inference_id,
            ),
        )


def _project_signals(cur, contradiction, challenger, payload, inference_id: int) -> None:
    from countyiq.assets.enrichment.signal_validation_batched import (
        UPSERT_EVIDENCE_QUERY,
    )

    pidn = contradiction["subject_key"]
    validations = payload.get("validations", [])
    keys = [item["signal_key"] for item in validations]
    cur.execute("DELETE FROM public.evidence WHERE pidn = %s", (pidn,))
    for validation in validations:
        signal_key = validation["signal_key"]
        cur.execute(
            """
            SELECT evidence
            FROM public.development_signals
            WHERE pidn = %s AND signal_key = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (pidn, signal_key),
        )
        source = cur.fetchone()
        if source is None:
            raise ContradictionResolutionError(
                f"current development signal is missing: {pidn}/{signal_key}"
            )
        cur.execute(
            UPSERT_EVIDENCE_QUERY,
            {
                "pidn": pidn, "signal_key": signal_key,
                "claim": (
                    f"{signal_key} classified {validation['validation_status']} with "
                    f"{validation['adjusted_significance']} significance"
                ),
                "evidence_data": canonical_json(source["evidence"] or {}),
                "source_url": None, "internal_url": f"/property/{pidn}",
                "validation_status": validation["validation_status"],
                "adjusted_significance": validation["adjusted_significance"],
                "validation_reasoning": validation["reasoning"],
                "cross_references": canonical_json(validation.get("cross_references", [])),
                "validated_at": datetime.now(UTC).isoformat(),
                "model_version": challenger["requested_model"].split("|", 1)[0],
                "prompt_version": challenger["prompt_version"],
                "n_trials": validation.get("n_trials"),
                "trial_agreement": validation.get("trial_agreement"),
                "confidence": validation.get("confidence"),
                "active_inference_id": inference_id,
            },
        )
    if len(keys) != len(set(keys)):
        raise ContradictionResolutionError("challenger contains duplicate signal keys")


def _project_parcel_brief(
    cur, contradiction, challenger, payload, inference_id: int, resolved_by: str
) -> None:
    from countyiq.assets.enrichment.brief_generation import UPSERT_BRIEF_QUERY

    pidn = contradiction["subject_key"]
    cur.execute("SELECT COUNT(*) AS count FROM public.evidence WHERE pidn = %s", (pidn,))
    signal_count = cur.fetchone()["count"]
    cur.execute(
        UPSERT_BRIEF_QUERY,
        {
            "pidn": pidn, "brief_text": payload["brief"],
            "assessment": payload["assessment"],
            "assessment_reasoning": payload.get("assessment_reasoning", ""),
            "key_questions": payload.get("key_questions", []),
            "signal_count": signal_count,
            "citations": canonical_json(payload.get("citations", [])),
            "pass_metadata": canonical_json({
                "origin": "human_resolution", "resolved_by": resolved_by,
                "recommendation": payload.get("recommendation"),
                "urgency": payload.get("urgency"),
                "evidence_strength": payload.get("evidence_strength"),
                "top_signal_key": payload.get("top_signal_key"),
                "top_risk": payload.get("top_risk"),
            }),
            "generated_at": datetime.now(UTC).isoformat(),
            "model_version": challenger["requested_model"].split("|", 1)[0],
            "prompt_version": challenger["prompt_version"], "n_trials": 1,
            "trial_agreement": None, "confidence": payload.get("confidence"),
            "active_inference_id": inference_id,
        },
    )


def _project_owner_brief(
    cur, contradiction, challenger, payload, inference_id: int, resolved_by: str
) -> None:
    from countyiq.lib.pass3_owner_briefs import UPSERT_OWNER_BRIEF

    cur.execute(
        """
        SELECT canonical_name, owner_id, n_parcels
        FROM public.owner_briefs
        WHERE active_inference_id = %s
        """,
        (contradiction["prior_inference_id"],),
    )
    current = cur.fetchone()
    if current is None:
        raise ContradictionResolutionError("current owner brief projection is missing")
    cur.execute(
        UPSERT_OWNER_BRIEF,
        {
            "canonical_name": current["canonical_name"],
            "owner_id": current["owner_id"], "brief_text": payload["brief_text"],
            "portfolio_strategy": payload["portfolio_strategy"],
            "concentration_notes": payload["concentration_notes"],
            "key_pattern": payload["key_pattern"],
            "recommendation": payload["recommendation"], "urgency": payload["urgency"],
            "top_risk": payload["top_risk"],
            "evidence_strength": payload["evidence_strength"],
            "citations": canonical_json(payload.get("citations", [])),
            "parcel_citations": canonical_json(payload.get("parcel_citations", [])),
            "n_parcels": current["n_parcels"],
            "model_version": challenger["requested_model"].split("|", 1)[0],
            "prompt_version": challenger["prompt_version"], "n_trials": 1,
            "trial_agreement": None, "confidence": payload.get("confidence"),
            "pass_metadata": canonical_json({
                "origin": "human_resolution", "resolved_by": resolved_by,
            }),
            "generated_at": datetime.now(UTC).isoformat(),
            "active_inference_id": inference_id,
        },
    )
