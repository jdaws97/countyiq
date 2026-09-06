"""Fail-closed integrity gates for model-backed intelligence outputs.

The LLM may propose an interpretation. This module decides whether that proposal
is source-grounded, internally consistent, and safe to project into serving
tables. Accepted and quarantined proposals are both written to the immutable
history ledger; only accepted proposals may update the active projection.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

_SIGNAL_MARKER = re.compile(r"\[Signal:\s*([^\]]+?)\s*\]")
_PARCEL_MARKER = re.compile(r"\[Parcel:\s*([^\]]+?)\s*\]")
_EVIDENCE_MARKER = re.compile(r"\[Evidence:\s*([^\]]+?)\s*\]")
# Sentence punctuation only terminates before whitespace/end, so decimal points
# such as 2.5 acres do not create phantom uncited fragments.
_SENTENCE = re.compile(r".+?(?:[.!?]+(?=\s|$)|$)", re.DOTALL)


@dataclass(frozen=True)
class IntegrityGateResult:
    inference_id: int
    accepted: bool
    contradiction_id: int | None = None
    reason: str | None = None


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def inference_input_hash(
    source_hash: str,
    *,
    requested_model: str,
    prompt_version: str,
) -> str:
    return content_hash(
        {
            "source_hash": source_hash,
            "requested_model": requested_model,
            "prompt_version": prompt_version,
        }
    )


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    return row[index]


def signal_validation_consequence(value: Any) -> list[dict[str, str]]:
    """Collapse Pass 2 wording/status churn to serving-impact bands.

    Brief eligibility and product priority distinguish high, medium, and
    non-actionable evidence. Status wording changes within one of those bands,
    and low/none swaps that remain excluded from briefs, do not warrant a
    human contradiction.
    """

    validations = value.get("validations", []) if isinstance(value, dict) else value
    if not isinstance(validations, list):
        return []
    consequence = []
    for item in validations:
        if not isinstance(item, dict) or not item.get("signal_key"):
            continue
        status = str(item.get("validation_status") or "")
        significance = str(item.get("adjusted_significance") or "none")
        band = (
            significance
            if status not in {"stale", "irrelevant"}
            and significance in {"high", "medium"}
            else "non_actionable"
        )
        consequence.append(
            {
                "signal_key": str(item["signal_key"]),
                "serving_band": band,
            }
        )
    return sorted(consequence, key=lambda item: item["signal_key"])


def record_inference_decision(
    database,
    *,
    subject_key: str,
    pass_number: int,
    output_kind: str,
    decision_key: str,
    source_hash: str,
    input_hash: str,
    requested_model: str,
    prompt_version: str,
    payload: Any,
    semantic_decision: Any,
    citations: Iterable[str] = (),
    evidence_refs: Iterable[str] = (),
    served_model: str | None = None,
    provider: str | None = None,
) -> IntegrityGateResult:
    """Append a proposal and quarantine semantic flips on identical evidence."""

    output_hash = content_hash(payload)
    decision_fingerprint = content_hash(semantic_decision)
    lock_key = "\x1f".join([str(pass_number), output_kind, subject_key, decision_key])

    with database.transaction() as cur:
        cur.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (lock_key,)
        )
        cur.execute(
            """
            SELECT inference_id, source_hash, decision_fingerprint, payload
            FROM meta.intelligence_inference_history
            WHERE pass_number = %s
              AND output_kind = %s
              AND subject_key = %s
              AND decision_key = %s
              AND disposition = 'accepted'
            ORDER BY inference_id DESC
            LIMIT 1
            """,
            (pass_number, output_kind, subject_key, decision_key),
        )
        latest = cur.fetchone()
        latest_id = _row_value(latest, "inference_id", 0) if latest else None
        latest_source_hash = _row_value(latest, "source_hash", 1) if latest else None
        latest_fingerprint = (
            _row_value(latest, "decision_fingerprint", 2) if latest else None
        )
        latest_payload = _row_value(latest, "payload", 3) if latest else None

        latest_consequence = (
            signal_validation_consequence(latest_payload)
            if output_kind == "signal_validation" and latest
            else []
        )
        proposed_consequence = (
            signal_validation_consequence(semantic_decision)
            if output_kind == "signal_validation"
            else []
        )
        same_serving_consequence = bool(
            latest_consequence and latest_consequence == proposed_consequence
        )

        contradicted = bool(
            latest
            and latest_source_hash == source_hash
            and latest_fingerprint != decision_fingerprint
            and not same_serving_consequence
        )
        disposition = "quarantined" if contradicted else "accepted"
        reason = (
            "semantic decision changed while the source evidence hash was unchanged"
            if contradicted
            else None
        )

        cur.execute(
            """
            INSERT INTO meta.intelligence_inference_history (
                subject_key, pass_number, output_kind, decision_key,
                source_hash, input_hash, requested_model, served_model, provider,
                prompt_version, output_hash, decision_fingerprint, payload,
                citations, evidence_refs, disposition, supersedes_inference_id
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s::jsonb, %s::jsonb, %s::jsonb, %s, %s
            )
            RETURNING inference_id
            """,
            (
                subject_key,
                pass_number,
                output_kind,
                decision_key,
                source_hash,
                input_hash,
                requested_model,
                served_model,
                provider,
                prompt_version,
                output_hash,
                decision_fingerprint,
                canonical_json(payload),
                canonical_json(sorted(set(citations))),
                canonical_json(sorted(set(evidence_refs))),
                disposition,
                latest_id,
            ),
        )
        inference_id = cur.fetchone()[0]

        contradiction_id = None
        if contradicted:
            cur.execute(
                """
                INSERT INTO meta.intelligence_contradictions (
                    pass_number, output_kind, subject_key, decision_key,
                    source_hash, prior_inference_id, challenger_inference_id,
                    prior_fingerprint, challenger_fingerprint, reason
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING contradiction_id
                """,
                (
                    pass_number,
                    output_kind,
                    subject_key,
                    decision_key,
                    source_hash,
                    latest_id,
                    inference_id,
                    latest_fingerprint,
                    decision_fingerprint,
                    reason,
                ),
            )
            contradiction_id = cur.fetchone()[0]

    return IntegrityGateResult(
        inference_id=inference_id,
        accepted=not contradicted,
        contradiction_id=contradiction_id,
        reason=reason,
    )


def record_validation_rejection(
    database,
    *,
    subject_key: str,
    pass_number: int,
    output_kind: str,
    source_hash: str | None,
    input_hash: str | None,
    requested_model: str,
    prompt_version: str,
    errors: Iterable[str],
) -> int:
    """Append one fail-closed validator rejection for operator telemetry."""

    normalized = [str(error).strip() for error in errors if str(error).strip()]
    if not normalized:
        raise ValueError("at least one validation error is required")
    rows = database.execute(
        """
        INSERT INTO meta.intelligence_validation_rejections (
            subject_key, pass_number, output_kind, source_hash, input_hash,
            requested_model, prompt_version, validation_errors
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        RETURNING rejection_id
        """,
        (
            subject_key,
            pass_number,
            output_kind,
            source_hash,
            input_hash,
            requested_model,
            prompt_version,
            canonical_json(normalized),
        ),
    )
    if not rows:
        raise RuntimeError("validation rejection was not persisted")
    return int(_row_value(rows[0], "rejection_id", 0))


def _normalized_source_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "")
    return " ".join(normalized.split())


def _compact_text(value: str) -> str:
    """Whitespace-free comparison form.

    PDF text extraction splits tokens at line breaks ("§150- 283.B"), and
    models quote the joined form; the quote is still verbatim source text.
    """
    return "".join(_normalized_source_text(value).split())


def validate_pass0_extractions(
    extractions: Any, source_text: str, *, meeting_date=None, require_contract=False
) -> list[str]:
    errors: list[str] = []
    if not isinstance(extractions, list):
        return ["extractions must be a list"]
    normalized_source = _normalized_source_text(source_text)
    if not normalized_source:
        return ["source text is unavailable; supporting quotes cannot be verified"]
    compact_source = _compact_text(source_text)

    matters: dict[tuple[str, str, str, str], str | None] = {}
    for index, extraction in enumerate(extractions):
        if not isinstance(extraction, dict):
            errors.append(f"extraction {index} is not an object")
            continue
        if require_contract and "evidence_spans" not in extraction:
            errors.append(
                f"extraction {index} is missing the current evidence contract"
            )
        if "evidence_spans" in extraction:
            from countyiq.lib.proceeding_contract import contract_errors

            errors.extend(
                f"extraction {index} {error}"
                for error in contract_errors(extraction, source_text, meeting_date)
            )
        quote = extraction.get("supporting_text")
        if not isinstance(quote, str) or not quote.strip():
            errors.append(f"extraction {index} has no supporting_text")
        elif (
            _normalized_source_text(quote) not in normalized_source
            and _compact_text(quote) not in compact_source
        ):
            errors.append(
                f"extraction {index} supporting_text is not present in source"
            )

        matter_key = tuple(
            str(extraction.get(key) or "").strip().casefold()
            for key in (
                "extraction_type",
                "applicant_name",
                "parcel_reference",
                "project_name",
            )
        )
        decision = extraction.get("decision")
        if matter_key in matters and matters[matter_key] != decision:
            errors.append(
                f"extraction {index} conflicts with another decision for the same matter"
            )
        elif matter_key in matters:
            errors.append(f"extraction {index} duplicates the same matter")
        else:
            matters[matter_key] = decision
    return errors


def pass0_semantic_decision(extractions: Iterable[dict]) -> list[dict]:
    decisions = [
        {
            key: extraction.get(key)
            for key in (
                "extraction_type",
                "applicant_name",
                "parcel_reference",
                "project_name",
                "decision",
                "record_status",
                "event_date",
                "event_date_text",
                "upcoming_date",
                "upcoming_date_iso",
                "application_ids",
                "project_reference",
                "parcel_references",
                "matter_category",
                "conditions",
                "decision_scope",
                "decision_authority",
                "decision_outcome",
                "milestones",
                "identity_status",
                "identity_conflicts",
                "relevance_scope",
                "discovery_eligible",
            )
        }
        for extraction in extractions
    ]
    return sorted(decisions, key=canonical_json)


_LINKED_RECORD_KEYS = {
    "parcels": ("parcels", "pidn"),
    "tax_claims": ("tax_claims", "pidn"),
    "plcb_licenses": ("plcb_licenses", "license_number"),
    "corporate_entities": ("corporate_entities", "entity_name"),
    "proceedings": ("proceedings", "applicant_name"),
}


def _known_entity_names(records: dict, cluster_names: Iterable[str]) -> set[str]:
    names = {str(name).strip() for name in cluster_names if str(name).strip()}
    fields = {
        "parcels": ("owner_full", "prev_owner"),
        "tax_claims": ("owner_name",),
        "plcb_licenses": ("licensee", "premises_owner"),
        "corporate_entities": ("entity_name",),
        "proceedings": ("applicant_name",),
    }
    for source, source_fields in fields.items():
        for row in records.get(source, []) or []:
            for field in source_fields:
                value = row.get(field) if isinstance(row, dict) else None
                if isinstance(value, str) and value.strip():
                    names.add(value.strip())
    return names


def validate_entity_membership(
    parsed: dict,
    records: dict,
    cluster_names: list[str],
) -> list[str]:
    """Reject fabricated identifiers and overlapping entity partitions."""

    errors: list[str] = []
    known_names = _known_entity_names(records, cluster_names)
    cluster_set = {name.strip() for name in cluster_names if name and name.strip()}
    claimed_by: dict[str, int] = {}
    accounted_for: set[str] = set()
    entity_canonicals = {
        str(entity.get("canonical_name") or "").strip()
        for entity in parsed.get("entities", [])
        if isinstance(entity, dict)
    }

    allowed_by_key: dict[str, set[str]] = {}
    for key, (source, field) in _LINKED_RECORD_KEYS.items():
        allowed_by_key[key] = {
            str(row.get(field)).strip()
            for row in records.get(source, []) or []
            if isinstance(row, dict) and row.get(field) is not None
        }
    allowed_evidence_refs = {"trial:voting"}
    allowed_evidence_refs.update(f"candidate:{name}" for name in cluster_set)
    for key, identifiers in allowed_by_key.items():
        allowed_evidence_refs.update(
            f"{key}:{identifier}" for identifier in identifiers
        )

    def validate_cited_text(text: Any, label: str) -> None:
        # Citation is enforced per field, not per sentence: models routinely
        # write one uncited lead sentence followed by a fully cited one, and
        # a per-sentence rule rejected 6/8 correct Luna partitions (2026-09-02).
        body = str(text or "")
        if not _sentences(body):
            errors.append(f"{label} has no cited reasoning")
            return
        markers = {marker.strip() for marker in _EVIDENCE_MARKER.findall(body)}
        if not markers:
            errors.append(f"uncited {label}: no [Evidence: ref] marker")
        unknown = markers - allowed_evidence_refs
        if unknown:
            errors.append(f"unknown evidence markers in {label}: {sorted(unknown)}")

    for entity_index, entity in enumerate(parsed.get("entities", [])):
        canonical = str(entity.get("canonical_name") or "").strip()
        if not canonical or canonical not in known_names:
            errors.append(
                f"entity {entity_index} canonical_name was not present in the input"
            )
        validate_cited_text(entity.get("reasoning"), f"entity {entity_index} reasoning")

        members = entity.get("member_names") or []
        if not isinstance(members, list) or not members:
            errors.append(f"entity {entity_index} has no explicit member_names")
            members = []
        for member in members:
            if not isinstance(member, str) or member not in cluster_set:
                errors.append(
                    f"entity {entity_index} member name was not in the candidate cluster: {member!r}"
                )
                continue
            if member in claimed_by:
                errors.append(
                    f"candidate name {member!r} appears in entities {claimed_by[member]} and {entity_index}"
                )
            else:
                claimed_by[member] = entity_index
                accounted_for.add(member)

        linked = entity.get("linked_records") or {}
        if not isinstance(linked, dict):
            errors.append(f"entity {entity_index} linked_records is not an object")
            continue
        unexpected = set(linked) - set(_LINKED_RECORD_KEYS)
        if unexpected:
            errors.append(
                f"entity {entity_index} has unexpected linked record groups: {sorted(unexpected)}"
            )
        for key, allowed in allowed_by_key.items():
            values = linked.get(key, []) or []
            if not isinstance(values, list):
                errors.append(
                    f"entity {entity_index} linked_records.{key} is not a list"
                )
                continue
            fabricated = {
                str(value).strip() for value in values if str(value).strip()
            } - allowed
            if fabricated:
                errors.append(
                    f"entity {entity_index} linked_records.{key} contains identifiers absent from input: {sorted(fabricated)}"
                )

        for rel in entity.get("relationships", []) or []:
            target = rel.get("related_entity") if isinstance(rel, dict) else None
            if (
                not isinstance(target, str)
                or target.strip() not in known_names | entity_canonicals
            ):
                errors.append(
                    f"entity {entity_index} relationship target was not present in the input"
                )
            if isinstance(rel, dict):
                validate_cited_text(
                    rel.get("evidence"), f"entity {entity_index} relationship evidence"
                )

    for rejected in parsed.get("rejected_matches", []) or []:
        if not isinstance(rejected, dict):
            errors.append("rejected match is not an object")
            continue
        for key in ("name_a", "name_b"):
            if rejected.get(key) not in cluster_set:
                errors.append(f"rejected match {key} was not in the candidate cluster")
            else:
                accounted_for.add(rejected[key])
        validate_cited_text(rejected.get("reason"), "rejected match reason")
    for abstention in parsed.get("abstentions", []) or []:
        for name in abstention.get("names", []) if isinstance(abstention, dict) else []:
            if name not in cluster_set:
                errors.append("abstention name was not in the candidate cluster")
            else:
                accounted_for.add(name)
        if isinstance(abstention, dict):
            validate_cited_text(abstention.get("reason"), "abstention reason")

    missing = cluster_set - accounted_for
    if missing:
        errors.append(f"candidate names were not accounted for: {sorted(missing)}")

    return errors


def entity_semantic_decision(parsed: dict) -> dict:
    return {
        "entities": sorted(
            sorted(set(entity.get("member_names") or []))
            for entity in parsed.get("entities", [])
        ),
        "rejected_matches": sorted(
            sorted([item.get("name_a", ""), item.get("name_b", "")])
            for item in parsed.get("rejected_matches", [])
            if isinstance(item, dict)
        ),
        "abstentions": sorted(
            sorted(set(item.get("names") or []))
            for item in parsed.get("abstentions", [])
            if isinstance(item, dict)
        ),
    }


def allowed_signal_refs(
    signals: Iterable[dict], context_signals: Iterable[dict] = ()
) -> set[str]:
    refs = {f"signal:{signal['signal_key']}" for signal in signals}
    refs.update(f"context:{signal['signal_key']}" for signal in context_signals)
    return refs


def validate_pass2_evidence_refs(
    validations: Iterable[dict],
    signals: Iterable[dict],
    context_signals: Iterable[dict] = (),
    cross_signal_insight: str | None = None,
) -> list[str]:
    signals = list(signals)
    context_signals = list(context_signals)
    errors: list[str] = []
    allowed = allowed_signal_refs(signals, context_signals)
    expected = {signal["signal_key"] for signal in signals}
    seen: set[str] = set()
    for validation in validations:
        key = validation.get("signal_key")
        if key not in expected:
            errors.append(f"unexpected signal validation: {key!r}")
            continue
        if key in seen:
            errors.append(f"duplicate signal validation: {key}")
        seen.add(key)
        status = validation.get("validation_status")
        significance = validation.get("adjusted_significance")
        if status in {"stale", "irrelevant"} and significance != "none":
            errors.append(
                f"{key} status {status!r} requires adjusted_significance 'none'"
            )
        refs = validation.get("cross_references") or []
        if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
            errors.append(f"{key} cross_references must be a list of strings")
            refs = []
        if len(refs) != len(set(refs)):
            errors.append(f"{key} contains duplicate evidence references")
        if f"signal:{key}" not in refs:
            errors.append(
                f"{key} is missing its required signal:{key} evidence reference"
            )
        unknown = {ref for ref in refs if ref not in allowed}
        if unknown:
            errors.append(
                f"{key} contains unknown evidence references: {sorted(unknown)}"
            )
        reasoning_text = str(validation.get("reasoning") or "")
        reasoning_markers = {
            marker.strip() for marker in _EVIDENCE_MARKER.findall(reasoning_text)
        }
        if not reasoning_markers:
            errors.append(f"uncited {key} reasoning: no [Evidence: ref] marker")
        if set(refs) - reasoning_markers:
            errors.append(f"{key} cross_references contains refs unused in reasoning")
        if reasoning_markers - allowed:
            errors.append(
                f"{key} reasoning contains unknown evidence markers: "
                f"{sorted(reasoning_markers - allowed)}"
            )
    missing = expected - seen
    if missing:
        errors.append(f"missing validations for signals: {sorted(missing)}")

    if cross_signal_insight:
        allowed_keys = {
            ref.split(":", 1)[1] for ref in allowed if ref.startswith("signal:")
        }
        markers = {
            marker.strip()
            for marker in _SIGNAL_MARKER.findall(str(cross_signal_insight))
        }
        if not markers:
            errors.append("uncited cross_signal_insight: no [Signal: key] marker")
        if markers - allowed_keys:
            errors.append(
                "cross_signal_insight contains unknown signal markers: "
                f"{sorted(markers - allowed_keys)}"
            )
    return errors


def pass2_semantic_decision(validations: Iterable[dict]) -> list[dict]:
    return sorted(
        (
            {
                "signal_key": item.get("signal_key"),
                "validation_status": item.get("validation_status"),
                "adjusted_significance": item.get("adjusted_significance"),
            }
            for item in validations
        ),
        key=lambda item: str(item["signal_key"]),
    )


def _sentences(text: str) -> list[str]:
    return [
        match.group(0).strip()
        for match in _SENTENCE.finditer(text or "")
        if match.group(0).strip()
    ]


def validate_parcel_brief_citations(
    parsed: dict, allowed_signal_keys: Iterable[str]
) -> list[str]:
    errors: list[str] = []
    allowed = set(allowed_signal_keys)
    citations = parsed.get("citations") or []
    if not citations:
        errors.append("citations must not be empty")
    if len(citations) != len(set(citations)):
        errors.append("citations must not contain duplicates")
    unknown_citations = set(citations) - allowed
    if unknown_citations:
        errors.append(f"unknown citations: {sorted(unknown_citations)}")

    cited_markers: set[str] = set()
    for field in ("assessment_reasoning", "brief", "top_risk"):
        text = parsed.get(field) or ""
        if field == "top_risk" and not text:
            continue
        if not _sentences(text):
            errors.append(f"{field} has no sentences")
            continue
        markers = {marker.strip() for marker in _SIGNAL_MARKER.findall(text)}
        if _PARCEL_MARKER.search(text):
            errors.append(
                f"{field} uses [Parcel: PIDN] markers; parcel briefs require [Signal: key] citations"
            )
        if not markers:
            errors.append(f"uncited {field}: no [Signal: key] marker")
        unknown = markers - allowed
        if unknown:
            errors.append(f"unknown signal markers in {field}: {sorted(unknown)}")
        cited_markers.update(markers)

    if set(citations) - cited_markers:
        errors.append("citation array contains keys not used in the narrative")
    if cited_markers - set(citations):
        errors.append("narrative uses signal markers missing from the citation array")
    top_signal = parsed.get("top_signal_key")
    if top_signal is not None and top_signal not in allowed:
        errors.append("top_signal_key is not an allowed validated signal")
    if top_signal is not None and top_signal not in citations:
        errors.append("top_signal_key is not included in citations")

    allowed_assessments = {
        "pursue_now": {"strong_opportunity", "emerging"},
        "watchlist": {"emerging", "speculative", "constrained"},
        "pass": {"constrained", "not_actionable"},
    }
    recommendation = parsed.get("recommendation")
    assessment = parsed.get("assessment")
    if (
        recommendation in allowed_assessments
        and assessment not in allowed_assessments[recommendation]
    ):
        errors.append(
            f"recommendation {recommendation!r} contradicts assessment {assessment!r}"
        )
    urgency = parsed.get("urgency")
    if (
        recommendation in {"investigate", "watch", "insufficient_evidence"}
        and urgency != "none"
    ):
        errors.append("investigation briefs must not invent urgency")
    if recommendation == "pass" and urgency != "none":
        errors.append("pass recommendation must have urgency 'none'")
    if recommendation == "pursue_now" and urgency == "none":
        errors.append("pursue_now recommendation cannot have urgency 'none'")
    return errors


def validate_owner_brief_citations(
    parsed: dict,
    allowed_signal_keys: Iterable[str],
    allowed_pidns: Iterable[str],
) -> list[str]:
    errors: list[str] = []
    allowed_signals = set(allowed_signal_keys)
    allowed_parcels = set(allowed_pidns)
    citations = set(parsed.get("citations") or [])
    parcel_citations = set(parsed.get("parcel_citations") or [])
    if len(parsed.get("citations") or []) != len(citations):
        errors.append("owner signal citations must not contain duplicates")
    if len(parsed.get("parcel_citations") or []) != len(parcel_citations):
        errors.append("owner parcel citations must not contain duplicates")
    if not citations or not parcel_citations:
        errors.append("owner brief requires both signal and parcel citations")
    if citations - allowed_signals:
        errors.append(
            f"unknown signal citations: {sorted(citations - allowed_signals)}"
        )
    if parcel_citations - allowed_parcels:
        errors.append(
            f"unknown parcel citations: {sorted(parcel_citations - allowed_parcels)}"
        )

    narrative_fields = (
        "brief_text",
        "concentration_notes",
        "key_pattern",
        "top_risk",
    )
    narrative = "\n".join(str(parsed.get(field) or "") for field in narrative_fields)
    signal_markers = {item.strip() for item in _SIGNAL_MARKER.findall(narrative)}
    parcel_markers = {item.strip() for item in _PARCEL_MARKER.findall(narrative)}
    for field in narrative_fields:
        text = str(parsed.get(field) or "")
        if (
            _sentences(text)
            and not _SIGNAL_MARKER.search(text)
            and not _PARCEL_MARKER.search(text)
        ):
            errors.append(
                f"uncited owner {field}: no [Signal: key] or [Parcel: PIDN] marker"
            )
    if signal_markers - allowed_signals:
        errors.append(
            f"unknown signal markers: {sorted(signal_markers - allowed_signals)}"
        )
    if parcel_markers - allowed_parcels:
        errors.append(
            f"unknown parcel markers: {sorted(parcel_markers - allowed_parcels)}"
        )
    if citations - signal_markers:
        errors.append("signal citation array contains keys not used in the narrative")
    if parcel_citations - parcel_markers:
        errors.append("parcel citation array contains PIDNs not used in the narrative")
    if signal_markers - citations:
        errors.append("owner narrative uses signal markers missing from citations")
    if parcel_markers - parcel_citations:
        errors.append(
            "owner narrative uses parcel markers missing from parcel_citations"
        )
    recommendation = parsed.get("recommendation")
    evidence_strength = parsed.get("evidence_strength")
    urgency = parsed.get("urgency")
    if (
        recommendation in {"investigate", "watch", "insufficient_evidence"}
        and urgency != "none"
    ):
        errors.append("investigation briefs must not invent urgency")
    if recommendation == "none" and urgency != "none":
        errors.append("none recommendation must have urgency 'none'")
    return errors


def parcel_brief_semantic_decision(parsed: dict) -> dict:
    return {
        key: parsed.get(key)
        for key in (
            "recommendation",
            "urgency",
            "top_signal_key",
            "evidence_strength",
            "assessment",
        )
    }


def owner_brief_semantic_decision(parsed: dict) -> dict:
    return {
        key: parsed.get(key)
        for key in (
            "portfolio_strategy",
            "recommendation",
            "urgency",
            "evidence_strength",
        )
    }


def signal_version_refs(rows: Iterable[dict], *, pidn: str | None = None) -> list[str]:
    """Bind all signal context to its parcel, key and accepted inference version.

    Called before spending on a brief. Legacy evidence must first receive a
    versioned validation; inventing a dependency after generation is unsafe.
    """
    refs = set()
    for row in rows:
        parcel = row.get("pidn") or pidn
        key = row.get("signal_key")
        version = row.get("active_inference_id")
        if (
            not isinstance(parcel, str)
            or not parcel
            or ":" in parcel
            or not isinstance(key, str)
            or not key
            or ":" in key
            or not isinstance(version, int)
            or isinstance(version, bool)
            or version <= 0
        ):
            raise ValueError(
                "Brief signal context requires a parcel, signal key and inference version"
            )
        refs.add(f"signal-version:{parcel}:{key}:{version}")
    return sorted(refs)
