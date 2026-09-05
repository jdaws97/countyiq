"""Pure builders for the unified product-facing intelligence event ledger.

Facts remain source-backed.  LLM interpretation is accepted only from the
Pass 0 extraction row where it was generated and cached; deterministic parcel
and tax events use conservative, explicitly non-predictive explanations.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable

from countyiq.lib.county_config import get_county_config

DEVELOPMENT_EVENT_TAGS = {
    "application",
    "hearing",
    "revision",
    "continuance",
    "approval",
    "denial",
    "condition",
    "upcoming_decision",
    "policy_action",
    "recommendation", "withdrawn", "removed", "scoped_decision",
}

_PRIMARY_DEVELOPMENT_TYPE_ORDER = (
    "approval",
    "denial",
    "continuance",
    "revision",
    "application",
    "hearing",
    "condition",
    "upcoming_decision",
)

_APPLICATION_EXTRACTION_TYPES = {
    "rezoning_application",
    "variance_request",
    "special_exception",
    "conditional_use",
    "subdivision_review",
    "subdivision_plan",
    "development_proposal",
}

_MUNICIPAL_BODY_SUFFIXES = (
    " board of supervisors",
    " board of commissioners",
    " council",
    " planning commission",
    " zoning hearing board",
    " zoning board",
    " zhb",
)

_FIELD_LABELS = {
    "owner_full": "owner",
    "prev_owner": "previous owner",
    "price": "sale price",
    "saledt": "sale date",
    "deed_bk": "deed book",
    "deed_pg": "deed page",
    "aprland": "assessed land value",
    "aprbldg": "assessed building value",
    "aprtotal": "total assessed value",
    "yrblt": "year built",
    "res_living_area": "living area",
    "num_stories": "story count",
    "comm_struc": "commercial structure type",
    "comm_year_built": "commercial year built",
    "comm_building_sq_ft": "commercial building area",
}


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _dedupe(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _clean_text(value)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def normalize_development_tags(
    *,
    extraction_type: str | None,
    decision: str | None,
    conditions: Iterable[Any] | None,
    proposed_tags: Iterable[Any] | None,
    what_happens_next: str | None,
    upcoming_date: str | None,
    record_status: str | None = None,
    decision_scope: str | None = None,
) -> list[str]:
    """Combine model tags with deterministic tags implied by source fields."""
    tags: list[str] = []
    if record_status in {"withdrawn", "removed"}:
        return [record_status]

    def add(tag: str) -> None:
        if tag in DEVELOPMENT_EVENT_TAGS and tag not in tags:
            tags.append(tag)

    for tag in proposed_tags or []:
        add(str(tag).strip().lower())

    extraction_type_normalized = (extraction_type or "").strip().lower()
    if extraction_type_normalized in _APPLICATION_EXTRACTION_TYPES and record_status in {None, "scheduled"}:
        add("application")
    if extraction_type_normalized == "ordinance_action":
        # A municipality-wide decision, filterable on its own in the feed.
        add("policy_action")
    # Legacy fixtures retain their old classification. New contracts distinguish
    # a document about a hearing from evidence that a hearing occurred.
    if record_status is None:
        add("hearing")
    elif record_status == "scheduled":
        tags = [tag for tag in tags if tag not in {"hearing", "approval", "denial", "continuance"}]
    if record_status in {"scheduled", "recommendation"}:
        decision = None
    if decision_scope in {"bond", "contract", "naming", "procedural"}:
        tags = [tag for tag in tags if tag not in {"approval", "denial", "continuance"}]
        add("scoped_decision")
        decision = None

    decision_normalized = (decision or "").strip().lower()
    if decision_normalized in {"approved", "approval", "granted"}:
        tags = [tag for tag in tags if tag != "denial"]
        add("approval")
    elif decision_normalized in {"denied", "denial", "rejected"}:
        tags = [tag for tag in tags if tag != "approval"]
        add("denial")
    elif decision_normalized in {"continued", "tabled", "postponed", "deferred"}:
        tags = [tag for tag in tags if tag not in {"approval", "denial"}]
        add("continuance")

    if list(conditions or []):
        add("condition")
    if (record_status is None and _clean_text(what_happens_next)) or _clean_text(upcoming_date):
        add("upcoming_decision")

    return tags


def primary_development_event_type(tags: Iterable[str]) -> str:
    tag_set = set(tags)
    for event_type in _PRIMARY_DEVELOPMENT_TYPE_ORDER:
        if event_type in tag_set:
            return event_type
    return "hearing"


def make_project_key(
    *,
    applicant_name: str | None,
    project_name: str | None,
    parcel_reference: str | None,
    body_name: str | None,
) -> str:
    """Create a stable, non-PII-exposing key for local project watchlists."""
    # Board changes are a normal part of one project's lifecycle. Use the
    # municipality, not the exact board, so Planning Commission and ZHB events
    # can land on the same watched project without colliding across towns.
    parts = [
        project_name,
        applicant_name,
        parcel_reference,
        municipality_from_body_name(body_name),
    ]
    normalized = "|".join(
        re.sub(r"[^a-z0-9]+", " ", (part or "").casefold()).strip()
        for part in parts
    )
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]
    return f"project:{digest}"


def municipality_from_body_name(body_name: str | None) -> str | None:
    """Derive the municipality label from a configured public-body name."""
    cleaned = _clean_text(body_name)
    if not cleaned:
        return None
    lowered = cleaned.casefold()
    for suffix in _MUNICIPAL_BODY_SUFFIXES:
        if lowered.endswith(suffix):
            return cleaned[: -len(suffix)].strip() or cleaned
    return cleaned


def _changed_value(evidence: dict[str, Any], field: str, side: str) -> str | None:
    changed = evidence.get("changed")
    if not isinstance(changed, dict):
        return None
    field_change = changed.get(field)
    if not isinstance(field_change, dict):
        return None
    return _clean_text(field_change.get(side))


def _format_change_list(evidence: dict[str, Any]) -> str:
    changed = evidence.get("changed")
    if not isinstance(changed, dict):
        return "County parcel attributes changed."
    descriptions: list[str] = []
    for field, values in changed.items():
        if not isinstance(values, dict):
            continue
        label = _FIELD_LABELS.get(field, str(field).replace("_", " "))
        old = _clean_text(values.get("old")) or "not reported"
        new = _clean_text(values.get("new")) or "not reported"
        descriptions.append(f"{label} changed from {old} to {new}")
    if not descriptions:
        return "County parcel attributes changed."
    return "; ".join(descriptions) + "."


def build_parcel_event(row: dict[str, Any]) -> dict[str, Any]:
    event_type = str(row["event_type"])
    evidence = _json_object(row.get("evidence"))
    pidn = str(row["pidn"])
    location = _clean_text(row.get("propadr")) or pidn

    if event_type == "transfer":
        old_owner = _changed_value(evidence, "owner_full", "old")
        new_owner = _changed_value(evidence, "owner_full", "new")
        if old_owner and new_owner:
            what_happened = f"The county parcel record changed ownership from {old_owner} to {new_owner}."
        else:
            what_happened = _format_change_list(evidence)
        title = f"Ownership activity at {location}"
        why = (
            "An ownership or deed change can precede financing, redevelopment, or portfolio repositioning, "
            "but this record alone does not establish development intent."
        )
        next_step = "Monitor later deed, planning, zoning, and permit activity for corroboration."
    elif event_type == "value_change":
        what_happened = _format_change_list(evidence)
        title = f"Assessed value changed at {location}"
        why = (
            "A material assessment change may reflect improvements, demolition, reassessment, or a county data correction."
        )
        next_step = "Compare the change with structure records and municipal proceedings before drawing a conclusion."
    else:
        what_happened = _format_change_list(evidence)
        title = f"Recorded structure details changed at {location}"
        why = (
            "A structure-record change can be an early indicator of construction or demolition, but may also be a data correction."
        )
        next_step = "Check later parcel refreshes and related municipal documents for confirmation."

    entity_candidates = [row.get("owner_full")]
    for field in ("owner_full", "prev_owner"):
        entity_candidates.extend(
            [_changed_value(evidence, field, "old"), _changed_value(evidence, field, "new")]
        )

    return {
        "event_key": f"parcel:{row['id']}",
        "source_kind": "parcel_event",
        "source_record_id": str(row["id"]),
        "category": "parcel",
        "event_type": event_type,
        "event_tags": [event_type],
        "title": title,
        "what_happened": what_happened,
        "why_it_matters": why,
        "what_happens_next": next_step,
        "event_date": row.get("event_date"),
        "detected_at": row["detected_at"],
        "confidence": 0.95 if row.get("confidence") == "confirmed" else 0.65,
        "municipality": row.get("municipality"),
        "project_key": None,
        "project_name": None,
        "related_entities": _dedupe(entity_candidates),
        "related_pidns": [pidn],
        "source_evidence": [
            {
                "label": f"{get_county_config().name} parcel record",
                "url": row.get("source_url"),
                "document_url": None,
                "excerpt": None,
                "details": evidence,
            }
        ],
        "interpretation_kind": "deterministic",
        "interpretation_model": None,
        "interpretation_generated_at": None,
    }


def build_delinquency_event(row: dict[str, Any]) -> dict[str, Any]:
    pidn = str(row["pidn"])
    location = _clean_text(row.get("propadr")) or pidn
    old_total = float(row.get("old_total") or 0)
    new_total = float(row.get("new_total") or 0)
    change_kind = str(row.get("change_kind") or "changed")

    if change_kind == "new":
        title = f"New delinquency reported at {location}"
        what_happened = f"The county tax-claim listing added delinquent claims totaling ${new_total:,.2f}."
    elif change_kind == "resolved":
        title = f"Delinquency removed at {location}"
        what_happened = f"Claims totaling ${old_total:,.2f} no longer appear in the current county listing."
    elif change_kind == "increased":
        title = f"Delinquency increased at {location}"
        what_happened = f"Affected delinquent claims increased from ${old_total:,.2f} to ${new_total:,.2f}."
    else:
        title = f"Delinquency decreased at {location}"
        what_happened = f"Affected delinquent claims decreased from ${old_total:,.2f} to ${new_total:,.2f}."

    why = (
        "A delinquency change can indicate financial pressure or resolution of an obligation, "
        "but it does not establish willingness to sell or the status of other liens."
    )
    next_step = "Confirm the latest balance with the Tax Claim Bureau and monitor later county listings."

    evidence = {
        "change_kind": change_kind,
        "old_affected_total": old_total,
        "new_affected_total": new_total,
        "affected_claims": int(row.get("affected_claims") or 0),
        "tax_years": list(row.get("tax_years") or []),
    }
    transition_identity = f"{pidn}:{row['detected_at'].isoformat()}:{change_kind}"
    return {
        "event_key": f"delinquency:{transition_identity}",
        "source_kind": "delinquency_event",
        "source_record_id": transition_identity,
        "category": "parcel",
        "event_type": "delinquency_change",
        "event_tags": ["delinquency_change"],
        "title": title,
        "what_happened": what_happened,
        "why_it_matters": why,
        "what_happens_next": next_step,
        "event_date": row.get("event_date"),
        "detected_at": row["detected_at"],
        # This is a deterministic source transition, not a probabilistic model
        # judgment. Showing a synthetic 95% overstates what the number means.
        "confidence": None,
        "municipality": row.get("municipality"),
        "project_key": None,
        "project_name": None,
        "related_entities": _dedupe([row.get("owner_full")]),
        "related_pidns": [pidn],
        "source_evidence": [
            {
                "label": f"{get_county_config().name} delinquent tax-claim listing",
                "url": row.get("source_url"),
                "document_url": row.get("source_url"),
                "excerpt": None,
                "details": evidence,
            }
        ],
        "interpretation_kind": "deterministic",
        "interpretation_model": None,
        "interpretation_generated_at": None,
    }


def build_development_event(row: dict[str, Any]) -> dict[str, Any]:
    from countyiq.lib.proceeding_contract import source_project_key
    details = _json_object(row.get("extraction_details"))
    conditions = row.get("conditions") or []
    if isinstance(conditions, str):
        try:
            conditions = json.loads(conditions)
        except json.JSONDecodeError:
            conditions = [conditions]
    if not isinstance(conditions, list):
        conditions = []

    tags = normalize_development_tags(
        extraction_type=row.get("extraction_type"),
        decision=row.get("decision"),
        conditions=conditions,
        proposed_tags=row.get("event_tags") or [],
        what_happens_next=row.get("what_happens_next"),
        upcoming_date=row.get("upcoming_date"),
        record_status=details.get("record_status"),
        decision_scope=details.get("decision_scope"),
    )
    event_type = primary_development_event_type(tags)
    if details.get("record_status") == "scheduled":
        event_type = "application" if "application" in tags else "upcoming_decision"
    elif details.get("record_status") == "recommendation":
        event_type = "recommendation"
    elif details.get("record_status") == "update" and (not tags or details.get("contract_version") == 3):
        event_type = "update"
    if details.get("contract_version") == 3:
        if details.get("record_status") in {"withdrawn", "removed"}:
            event_type = details["record_status"]
        elif details.get("decision_scope"):
            event_type = "scoped_decision"
            if "scoped_decision" not in tags:
                tags.append("scoped_decision")
    applicant = _clean_text(row.get("applicant_name"))
    project_name = _clean_text(row.get("project_name"))
    parcel_reference = _clean_text(row.get("parcel_reference"))
    body_name = _clean_text(row.get("body_name"))
    is_policy_action = str(row.get("extraction_type") or "").strip().lower() == "ordinance_action"
    subject = (
        project_name or applicant or parcel_reference or body_name
        or ("Municipal policy action" if is_policy_action else "Municipal development matter")
    )

    fallback_what = f"{subject} appeared in a {str(row.get('extraction_type') or 'development').replace('_', ' ')} record."
    decision = _clean_text(row.get("decision"))
    if decision:
        fallback_what = f"{subject} was recorded with a decision of {decision}."
    if conditions:
        fallback_what += f" The record includes {len(conditions)} condition{'s' if len(conditions) != 1 else ''}."

    why_by_type = {
        "approval": "An approval advances the matter procedurally, subject to any stated conditions and later permitting requirements.",
        "denial": "A denial may stop the current application or lead to an appeal or revised submission.",
        "continuance": "A continuance leaves the matter unresolved and creates another opportunity for the proposal to change.",
        "revision": "A revision indicates the proposal is still active and that its scope or conditions may be changing.",
        "application": "A newly observed application is an early public signal of potential development activity.",
        "hearing": "A public hearing places the matter into a formal municipal review process.",
        "condition": "Conditions can materially affect project timing, cost, design, or ultimate feasibility.",
        "upcoming_decision": "A stated next action identifies a near-term point when the project's status may change.",
    }
    next_by_type = {
        "approval": "Monitor recorded plans, permits, satisfaction of conditions, and construction activity.",
        "denial": "Monitor for an appeal, amended application, or later resubmission.",
        "continuance": "Monitor the next agenda and meeting minutes for a revised plan or decision.",
        "revision": "Compare the next submission or hearing record with the current proposal.",
        "application": "Monitor scheduling, staff review, and the first formal decision.",
        "hearing": "Monitor the meeting record for a decision, conditions, or continuance.",
        "condition": "Monitor whether each stated condition is satisfied or revised.",
        "upcoming_decision": "Monitor the stated next meeting or procedural milestone.",
    }

    model_interpretation = any(
        _clean_text(row.get(field))
        for field in ("what_happened", "why_it_matters", "what_happens_next")
    )
    related_entities = _dedupe(
        [applicant, *(row.get("related_entities") or []), *(row.get("matched_owners") or [])]
    )
    related_pidns = _dedupe(row.get("related_pidns") or [])
    has_project_identity = any((applicant, project_name, parcel_reference))
    project_key = (
        make_project_key(
            applicant_name=applicant,
            project_name=project_name,
            parcel_reference=parcel_reference,
            body_name=body_name,
        )
        if has_project_identity
        else None
    )
    if details.get("contract_version") in {2, 3}:
        project_key = row["resolved_project_key"] if "resolved_project_key" in row else source_project_key(row)
    supporting_text = _clean_text(row.get("supporting_text"))
    source_details = {
        "extraction_type": row.get("extraction_type"),
        "decision": row.get("decision"),
        "conditions": conditions,
        "current_zoning": row.get("current_zoning"),
        "proposed_zoning": row.get("proposed_zoning"),
        "parcel_reference": parcel_reference,
        "upcoming_date": row.get("upcoming_date"),
        **details,
        "meeting_date": str(row.get("meeting_date")) if row.get("meeting_date") else None,
        "location_status": "supported_parcels" if related_pidns else "location_not_resolved",
        "project_identity_status": "source_identified" if project_key else "needs_review",
    }
    stable_identity = "|".join(
        str(row.get(key) or "")
        for key in ("proceeding_id", "extraction_type", "applicant_name", "parcel_reference", "supporting_text")
    )
    if details.get("contract_version") == 3:
        stable_identity += "|" + json.dumps({
            "application_ids": details.get("application_ids"), "scope": details.get("decision_scope"),
            "what_happened": row.get("what_happened"), "project_reference": details.get("project_reference"),
        }, sort_keys=True)
    digest = hashlib.sha256(stable_identity.encode("utf-8")).hexdigest()[:20]
    heading = event_type.replace("_", " ").title()
    if details.get("contract_version") == 3 and details.get("decision_scope"):
        heading = details["decision_scope"].replace("_", " ").title() + ": " + str(details.get("decision_outcome") or "decision").capitalize()

    return {
        "event_key": f"development:{digest}",
        "source_kind": "proceeding_extraction",
        "source_record_id": str(row["id"]),
        "category": "development",
        "event_type": event_type,
        "event_tags": tags,
        "title": f"{heading}: {subject}",
        "what_happened": _clean_text(row.get("what_happened")) or fallback_what,
        "why_it_matters": _clean_text(row.get("why_it_matters")) or (
            "Verify the source scope and authority; this record alone does not establish construction permission."
            if details.get("contract_version") == 3 else
            "A municipality-wide ordinance or plan action changes what can be built across "
            "the affected districts, not just on one parcel."
            if is_policy_action
            else why_by_type.get(event_type, "The source records an update; verify its scope before relying on it.")
        ),
        "what_happens_next": _clean_text(row.get("what_happens_next")) or next_by_type.get(event_type, "Check later source records for the next action."),
        "event_date": (
            details.get("event_date") if details.get("contract_version") in {2, 3}
            else row.get("meeting_date")
        ),
        "detected_at": row.get("extracted_at") or row.get("proceeding_valid_from"),
        "confidence": row.get("extraction_confidence"),
        "municipality": municipality_from_body_name(body_name),
        "project_key": project_key,
        "project_name": project_name or applicant or parcel_reference,
        "related_entities": related_entities,
        "related_pidns": related_pidns,
        "source_evidence": [
            {
                "label": body_name or "Municipal proceeding",
                "url": row.get("source_url"),
                "document_url": row.get("document_url"),
                "excerpt": quote,
                "details": {**(source_details if index == 0 else {}),
                    "supports": (details.get("evidence_spans") or [{}])[index].get("fields", [])},
            }
            for index, quote in enumerate(
                [span["quote"] for span in details.get("evidence_spans") or []] or [supporting_text]
            )
        ],
        "interpretation_kind": "llm" if model_interpretation else "deterministic",
        "interpretation_model": row.get("model_used") if model_interpretation else None,
        "interpretation_generated_at": (
            row.get("interpretation_generated_at") or row.get("extracted_at")
            if model_interpretation
            else None
        ),
    }
