"""Deterministic scoring helpers for immutable LLM regression fixtures."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any

PASS2_SCORING_VERSION = "2026-08-30.3"


def enforce_production_gate(score: dict, errors: list[str]) -> dict:
    """Make the serving validator a required part of a promotion result."""

    return {
        **score,
        "production_gate_pass": not errors,
        "production_gate_errors": errors,
        "gold_pass": bool(score.get("gold_pass")) and not errors,
    }


def _normalized(value: Any) -> str:
    """Normalize punctuation and spacing while preserving word boundaries."""
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def _match_tokens(value: Any) -> list[str]:
    """Normalize light plurals so evidence phrases can contain modifiers."""
    tokens = _normalized(value).split()
    return [
        token[:-1]
        if len(token) > 3 and token.endswith("s") and not token.endswith("ss")
        else token
        for token in tokens
    ]


def _ordered_token_match(value: Any, alternative: str, max_gap: int = 6) -> bool:
    """Match an evidence phrase as nearby ordered tokens, not brittle prose."""
    haystack = _match_tokens(value)
    needle = _match_tokens(alternative)
    if not needle:
        return False
    for start, token in enumerate(haystack):
        if token != needle[0]:
            continue
        position = start
        for expected in needle[1:]:
            stop = min(len(haystack), position + max_gap + 1)
            position = next(
                (
                    index
                    for index in range(position + 1, stop)
                    if haystack[index] == expected
                ),
                -1,
            )
            if position < 0:
                break
        else:
            return True
    return False


def _contains_any(value: Any, alternatives: list[str]) -> bool:
    haystack = _normalized(value)
    return any(
        _normalized(alternative) in haystack or _ordered_token_match(value, alternative)
        for alternative in alternatives
    )


def _forbidden_assertions(value: Any, claims: list[str]) -> list[str]:
    """Return prohibited claims unless their sentence explicitly disclaims them."""
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    segments = [part for part in re.split(r"[.!?;\n]+", text) if part.strip()]
    found = []
    negations = {
        "no",
        "not",
        "without",
        "absent",
        "lack",
        "lacking",
        "unproven",
        "unsupported",
        "unverified",
        "unclear",
        "unknown",
        "cannot",
        "speculative",
        "insufficient",
        "rather than",
        "does not",
        "do not",
        "did not",
        "no evidence",
        "no indication",
        "no support",
        "not establish",
        "not confirm",
        "not demonstrate",
    }

    def has_negation(segment: str) -> bool:
        normalized = f" {_normalized(segment).replace('not only', '')} "
        return any(f" {_normalized(marker)} " in normalized for marker in negations)

    def is_explicitly_conditional(segment: str, claim: str) -> bool:
        normalized = f" {_normalized(segment)} "
        needle = _normalized(claim)
        return f" any {needle} " in normalized

    for claim in claims:
        asserted_segments = [
            segment
            for segment in segments
            if _contains_any(segment, [claim])
            and not has_negation(segment)
            and not is_explicitly_conditional(segment, claim)
        ]
        if asserted_segments:
            found.append(claim)
    return found


def _record_matches(extraction: dict, expected: dict) -> bool:
    if extraction.get("extraction_type") not in expected["accepted_types"]:
        return False
    haystack = _normalized(extraction)
    return all(
        any(_normalized(alternative) in haystack for alternative in alternatives)
        for alternatives in expected["anchors"]
    )


def _score_pass0_fields(extraction: dict, expected: dict) -> dict:
    checks: dict[str, bool] = {}
    for field_name, alternatives in expected.get("field_expectations", {}).items():
        checks[field_name] = _contains_any(extraction.get(field_name), alternatives)
    for field_name in expected.get("required_nonempty_fields", []):
        checks[f"{field_name}:nonempty"] = bool(extraction.get(field_name))
    for field_name in expected.get("expected_empty_fields", []):
        checks[f"{field_name}:empty"] = not extraction.get(field_name)
    return {"checks": checks, "pass": all(checks.values())}


def score_pass0(parsed: dict | None, fixture: dict) -> dict:
    """Match one output extraction to at most one human-reviewed gold matter.

    The anchors deliberately test identity, location, and distinguishing source
    facts without requiring exact prose. Extra or duplicate extractions remain
    visible and fail the strict gold gate.
    """
    extractions = (
        parsed.get("extractions", [])
        if isinstance(parsed, dict) and isinstance(parsed.get("extractions"), list)
        else []
    )
    expected = fixture.get("expected_records", [])
    available = set(range(len(extractions)))
    matched: list[str] = []
    missing: list[str] = []
    field_scores: dict[str, dict] = {}

    for gold in expected:
        match_index = next(
            (
                index
                for index in sorted(available)
                if isinstance(extractions[index], dict)
                and _record_matches(extractions[index], gold)
            ),
            None,
        )
        if match_index is None:
            missing.append(gold["id"])
        else:
            available.remove(match_index)
            matched.append(gold["id"])
            field_scores[gold["id"]] = _score_pass0_fields(
                extractions[match_index], gold
            )

    fields_pass = all(score["pass"] for score in field_scores.values())

    return {
        "expected_count": len(expected),
        "actual_count": len(extractions),
        "count_pass": len(extractions) == len(expected),
        "matched_records": matched,
        "missing_records": missing,
        "extra_extractions": len(available),
        "field_scores": field_scores,
        "fields_pass": fields_pass,
        "gold_pass": (
            not missing
            and not available
            and len(extractions) == len(expected)
            and fields_pass
        ),
    }


def _canonical_partition(groups: list[list[str]], universe: set[str]) -> tuple:
    """Normalize possibly overlapping groups into one deterministic partition."""
    parent = {item: item for item in universe}

    def find(item: str) -> str:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(left: str, right: str) -> None:
        lroot, rroot = find(left), find(right)
        if lroot != rroot:
            parent[rroot] = lroot

    for group in groups:
        valid = [item for item in group if item in universe]
        for item in valid[1:]:
            union(valid[0], item)

    buckets: dict[str, list[str]] = defaultdict(list)
    for item in universe:
        buckets[find(item)].append(item)
    return tuple(sorted(tuple(sorted(items)) for items in buckets.values()))


def score_pass1(parsed: dict | None, fixture: dict) -> dict:
    """Score entity resolution as a partition over immutable record IDs."""
    record_ids = {
        str(parcel["pidn"]) for parcel in fixture.get("records", {}).get("parcels", [])
    }
    normalized_ids = {
        re.sub(r"[^A-Z0-9]", "", record_id.upper()): record_id
        for record_id in record_ids
    }
    entities = parsed.get("entities", []) if isinstance(parsed, dict) else []
    output_groups: list[list[str]] = []
    returned_ids: set[str] = set()
    for entity in entities if isinstance(entities, list) else []:
        if not isinstance(entity, dict):
            continue
        linked = entity.get("linked_records") or {}
        parcels = linked.get("parcels") or [] if isinstance(linked, dict) else []
        group = []
        for pidn in parcels:
            if not isinstance(pidn, str):
                continue
            key = re.sub(r"[^A-Z0-9]", "", pidn.upper())
            if key.startswith("PIDN"):
                key = key[4:]
            group.append(normalized_ids.get(key, pidn))
        output_groups.append(group)
        returned_ids.update(group)

    fabricated = sorted(returned_ids - record_ids)
    output_partition = _canonical_partition(output_groups, record_ids)
    accepted = [
        _canonical_partition(groups, record_ids)
        for groups in fixture.get("labels", {}).get("acceptable_partitions", [])
    ]
    partition_pass = output_partition in accepted
    linked_checks = []
    for expectation in fixture.get("labels", {}).get("linked_record_expectations", []):
        anchor_keys = {
            normalized_ids.get(re.sub(r"[^A-Z0-9]", "", str(pidn).upper()), str(pidn))
            for pidn in expectation.get("entity_parcels", [])
        }
        matching_entity = None
        for entity in entities if isinstance(entities, list) else []:
            linked = entity.get("linked_records") or {}
            entity_keys = set()
            for pidn in linked.get("parcels") or []:
                key = re.sub(r"[^A-Z0-9]", "", str(pidn).upper())
                if key.startswith("PIDN"):
                    key = key[4:]
                entity_keys.add(normalized_ids.get(key, str(pidn)))
            if anchor_keys <= entity_keys:
                matching_entity = entity
                break
        checks = {}
        for field_name, required_values in expectation.get("required", {}).items():
            returned = (
                (matching_entity.get("linked_records") or {}).get(field_name) or []
                if matching_entity
                else []
            )
            normalized_returned = {_normalized(value) for value in returned}
            checks[field_name] = all(
                _normalized(value) in normalized_returned for value in required_values
            )
        linked_checks.append(
            {
                "entity_parcels": sorted(anchor_keys),
                "checks": checks,
                "pass": matching_entity is not None and all(checks.values()),
            }
        )
    linked_records_pass = all(check["pass"] for check in linked_checks)
    return {
        "record_count": len(record_ids),
        "output_partition": [list(group) for group in output_partition],
        "partition_pass": partition_pass,
        "linked_record_checks": linked_checks,
        "linked_records_pass": linked_records_pass,
        "fabricated_record_ids": fabricated,
        "gold_pass": partition_pass and linked_records_pass and not fabricated,
    }


def _validation_text(validation: dict) -> str:
    return " ".join(
        [
            str(validation.get("reasoning") or ""),
            *[str(v) for v in validation.get("key_facts") or []],
            *[str(v) for v in validation.get("cross_references") or []],
        ]
    )


def score_pass2(parsed: dict | None, fixture: dict) -> dict:
    """Score every labeled signal for calibration and evidence grounding."""
    validations = parsed.get("validations", []) if isinstance(parsed, dict) else []
    by_key = {
        item.get("signal_key"): item
        for item in validations
        if isinstance(item, dict) and item.get("signal_key")
    }
    signal_scores = {}
    for label in fixture.get("labels", {}).get("signals", []):
        key = label["signal_key"]
        value = by_key.get(key)
        if not value:
            signal_scores[key] = {"present": False, "pass": False}
            continue
        text = _validation_text(value)
        required_groups = label.get("required_fact_groups", [])
        required_matches = [_contains_any(text, group) for group in required_groups]
        required_pass = all(required_matches)
        forbidden = _forbidden_assertions(text, label.get("forbidden_claims", []))
        status_pass = value.get("validation_status") in label["accepted_statuses"]
        significance_pass = (
            value.get("adjusted_significance") in label["accepted_significance"]
        )
        decision_pass = status_pass and significance_pass and not forbidden
        signal_scores[key] = {
            "present": True,
            "status_pass": status_pass,
            "significance_pass": significance_pass,
            "decision_pass": decision_pass,
            "matched_required_fact_groups": sum(required_matches),
            "required_fact_group_count": len(required_matches),
            "required_fact_recall": (
                round(sum(required_matches) / len(required_matches), 3)
                if required_matches
                else 1.0
            ),
            "required_facts_pass": required_pass,
            "forbidden_claims_found": forbidden,
            "pass": (decision_pass and required_pass),
        }

    expected_keys = set(signal_scores)
    extra_keys = sorted(set(by_key) - expected_keys)
    gold_pass = (
        bool(signal_scores)
        and all(score["pass"] for score in signal_scores.values())
        and not extra_keys
    )
    return {
        "signal_scores": signal_scores,
        "missing_signals": sorted(
            key for key, score in signal_scores.items() if not score["present"]
        ),
        "extra_signals": extra_keys,
        "gold_pass": gold_pass,
    }


_SIGNAL_CITATION_RE = re.compile(r"\[Signal:\s*([a-z0-9_]+)\]", re.I)


def score_pass3(parsed: dict | None, fixture: dict) -> dict:
    """Score a brief's decision, evidence citations, and labeled anchors."""
    if not isinstance(parsed, dict):
        return {"gold_pass": False, "error": "output is not an object"}
    labels = fixture.get("labels", {})
    structured = {
        field: parsed.get(field) in accepted
        for field, accepted in labels.get("accepted_fields", {}).items()
    }
    brief = str(parsed.get("brief") or "")
    reasoning = str(parsed.get("assessment_reasoning") or "")
    text = f"{reasoning}\n{brief}"
    cited_in_text = set(_SIGNAL_CITATION_RE.findall(text))
    declared = {
        str(item) for item in parsed.get("citations") or [] if isinstance(item, str)
    }
    allowed = set(labels.get("allowed_citations", []))
    required = set(labels.get("required_citations", []))
    citation_pass = (
        required <= cited_in_text
        and required <= declared
        and cited_in_text <= allowed
        and declared <= allowed
    )
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", brief) if part.strip()]
    paragraph_citations_pass = bool(paragraphs) and all(
        _SIGNAL_CITATION_RE.search(paragraph) for paragraph in paragraphs
    )
    required_facts_pass = all(
        _contains_any(text, group) for group in labels.get("required_fact_groups", [])
    )
    forbidden = _forbidden_assertions(text, labels.get("forbidden_claims", []))
    top_signal_pass = parsed.get("top_signal_key") in allowed
    return {
        "structured_checks": structured,
        "citation_pass": citation_pass,
        "paragraph_citations_pass": paragraph_citations_pass,
        "required_facts_pass": required_facts_pass,
        "forbidden_claims_found": forbidden,
        "top_signal_pass": top_signal_pass,
        "gold_pass": (
            bool(structured)
            and all(structured.values())
            and citation_pass
            and paragraph_citations_pass
            and required_facts_pass
            and not forbidden
            and top_signal_pass
        ),
    }
