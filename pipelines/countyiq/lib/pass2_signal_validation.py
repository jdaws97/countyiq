"""Shared validation questions and output contract for batched Pass 2."""

from __future__ import annotations

import re

VALID_STATUSES = {"confirmed", "upgraded", "downgraded", "stale", "irrelevant"}
VALID_SIGNIFICANCE = {"high", "medium", "low", "none"}
NON_SERVING_VALIDATION_STATUSES = {"stale", "irrelevant"}
SERVING_VALIDATION_STATUSES = VALID_STATUSES - NON_SERVING_VALIDATION_STATUSES


SIGNAL_QUESTIONS: dict[str, list[str]] = {
    "municipal_action": [
        "Does the linked proceeding actually concern this parcel, or was the address match ambiguous?",
        "What is the procedural state (application, hearing, approval, denial, continuance) and how recent is it?",
        "Do the proposed use or zoning and any conditions change what can be built here?",
    ],
    "entity_assemblage": [
        "Is the same owner genuinely accumulating contiguous parcels, or is this a long-held family or farm holding?",
        "Do the acquisition dates and prices suggest a development site being assembled?",
        "Does the entity's portfolio or corporate record indicate a developer or investor?",
    ],
    "active_subdivision": [
        "Is the plan date within the last 3 years, or is this data stale?",
        "Is the scale significant — how many lots/units and total acreage?",
        "Is the distance (signal's distance_m) close enough to be relevant to this parcel?",
        "Does the plan type (subdivision vs land development) match the parcel's context?",
    ],
    "tax_distress": [
        "Is this chronic multi-year delinquency or a one-time shortfall?",
        "How does the total owed compare to the parcel's assessed value — is it material?",
        "Has the delinquency reached the judicial/sheriff sale threshold?",
    ],
    "ownership_change": [
        "Was this a market-rate arm's-length transaction, or a nominal/interfamily transfer?",
        "How does price compare with assessment? Do not infer distress, foreclosure, or a flip from that ratio alone.",
        "Does cited context show buyer development activity? An organizational-looking name alone does not establish developer identity or intent.",
    ],
    "zoning_mismatch": [
        "Is this a meaningful mismatch between current zoning and future land use, or a data artifact?",
        "How recent and authoritative is the future land use designation?",
        "Is this part of a corridor-wide pattern or an isolated anomaly?",
    ],
    "vacancy": [
        "Is this genuinely vacant land, or a data gap (missing structure footprint)?",
        "Is the assessed value consistent with vacant status?",
        "How long has the parcel appeared vacant — recent demolition or long-term?",
    ],
    "assemblage": [
        "Do cited records establish common ownership or active consolidation, or only fragmented neighboring ownership? Do not speculate about hidden shared ownership.",
        "Which neighbors have recorded tax claims or positive balances? A missing or zero amount does not negate a recorded claim.",
        "Preserve the supplied adjacent acreage and owner count. Large acreage alone does not establish an assemblage opportunity.",
    ],
    "economic_development_park": [
        "Is the parcel actually within the mapped business or industrial park boundary?",
        "Is the park identity and type useful evidence of development context?",
        "Do parcel fundamentals support the apparent park-based opportunity?",
    ],
    "penndot_project": [
        "Is the PennDOT project still active and funded, or completed/cancelled?",
        "Is the proximity close enough to meaningfully affect this parcel's access or value?",
    ],
    "growth_area": [
        "Is this a Primary Growth Area (PGA) or Secondary Growth Area (SGA)?",
        "Growth area status is a tiebreaker only — does this add meaningful differentiation?",
    ],
    "flood_zone": [
        "Is the flood zone overlap partial (edge of parcel) or does it cover the full parcel?",
        "Should this discount the opportunity score, or effectively eliminate the parcel?",
    ],
    "conservation_easement": [
        "Is the conservation restriction still active and enforceable?",
        "Should this be a hard exclusion from development consideration?",
    ],
    "ag_security": [
        "Is the agricultural security area enrollment still active?",
        "Should this be a hard exclusion from development consideration?",
    ],
}


def parse_signal_validation_output(output: object) -> dict:
    """Validate and normalize LLM signal validation output.

    Clamps validation_status to VALID_STATUSES (default: "confirmed").
    Clamps adjusted_significance to VALID_SIGNIFICANCE (default: "medium").
    Returns an error key if reasoning is missing.

    Args:
        output: Parsed JSON dict from LLM response.

    Returns:
        Normalized dict with signal_key, validation_status,
        adjusted_significance, reasoning, key_facts, cross_references.
        Or dict with 'error' key if the output is invalid.
    """
    if not isinstance(output, dict):
        return {"error": "Output is not a dict"}

    signal_key = output.get("signal_key")
    if not signal_key:
        return {"error": "Missing 'signal_key' in output"}

    reasoning = output.get("reasoning")
    if not reasoning:
        return {"error": "Missing or empty 'reasoning' in output"}

    # Clamp validation_status
    status = output.get("validation_status", "confirmed")
    if status not in VALID_STATUSES:
        status = "confirmed"

    # Clamp adjusted_significance
    significance = output.get("adjusted_significance", "medium")
    if significance not in VALID_SIGNIFICANCE:
        significance = "medium"

    if status in NON_SERVING_VALIDATION_STATUSES and significance != "none":
        return {
            "error": (
                f"validation_status '{status}' requires adjusted_significance 'none'"
            )
        }

    # Normalize key_facts
    key_facts = output.get("key_facts", [])
    if not isinstance(key_facts, list):
        key_facts = []

    # Normalize cross_references
    cross_references = output.get("cross_references", [])
    if not isinstance(cross_references, list):
        cross_references = []
    # The prose wrapper is formatting, not a different evidence identity. Strip
    # only this exact wrapper; unknown/malformed IDs still reach the source gate.
    cross_references = [
        re.sub(r"^Evidence:\s*((?:signal|context):[a-z_]+)$", r"\1", ref)
        if isinstance(ref, str) else ref
        for ref in cross_references
    ]

    return {
        "signal_key": signal_key,
        "validation_status": status,
        "adjusted_significance": significance,
        "reasoning": reasoning,
        "key_facts": key_facts,
        "cross_references": cross_references,
    }
