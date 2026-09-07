"""Assemble investigation summaries from the source facts already being served.

This is the zero-inference path for Pass 2/3's product job. It works for every
property, including those without model validation or a generated brief, and
cannot grow stale independently of its source signals. Existing model judgments
are deliberately not inputs to the summary or its questions.
"""

from __future__ import annotations

from collections.abc import Mapping

from api.lib.development_radar import (
    SIGNAL_CAVEATS,
    SIGNAL_TITLES,
    format_signal_label,
    sanitize_signals_for_public,
)

ACTIVITY_KEYS = (
    "municipal_record",
    "municipal_action",
    "active_subdivision",
    "ownership_change",
    "entity_assemblage",
)
CONSTRAINT_KEYS = (
    "conservation_easement",
    "flood_zone",
    "soil_constraint",
    "zoning_constraint",
    "environmental_diligence",
)
CONTEXT_KEYS = (
    "tax_distress",
    "zoning_mismatch",
    "nearby_subdivision",
    "economic_development_park",
    "assemblage",
    "development_overlay",
    "growth_area",
    "penndot_project",
    "local_traffic_activity",
    "ag_security",
    "vacancy",
)

QUESTIONS = {
    "municipal_record": "What stage, conditions and next dates does this property's original municipal passage establish?",
    "municipal_action": "What action and conditions does the original municipal record actually establish for this property?",
    "active_subdivision": "Does the named plan's submitted boundary include this parcel, and what stage is documented in the plan file?",
    "ownership_change": "Does the recorded deed confirm the parties, consideration and parcel extent of this sale?",
    "entity_assemblage": "Do the deeds confirm that the touching parcels belong to the same legal owner?",
    "conservation_easement": "What uses and building areas does the recorded easement permit?",
    "flood_zone": "Where does the mapped flood hazard overlap the area being considered for development?",
    "soil_constraint": "How do the mapped soil limitations affect the proposed building area and wastewater approach?",
    "zoning_constraint": "What additional requirements does the current municipal overlay ordinance impose?",
    "environmental_diligence": "What does the cited DEP record describe, and does it establish any connection to this parcel?",
    "tax_distress": "Is the delinquency indicator still current according to the Tax Claim Bureau?",
    "zoning_mismatch": "What does the current ordinance permit, separately from the future-land-use policy?",
    "nearby_subdivision": "Where is the nearby plan's actual boundary relative to this parcel?",
    "economic_development_park": "What zoning, utilities and requirements apply to the parcel listed in the park inventory?",
    "assemblage": "Which parcels and legal owners make up the mapped neighboring ownership pattern?",
    "vacancy": "Do current site records and imagery corroborate the missing building footprints?",
}


def build_record_brief(
    signals: Mapping[str, object] | None,
    *,
    source_updated_at: str | None,
) -> dict | None:
    """Select source facts and their limitations without assigning intent.

    At least one available constraint is kept alongside activity. Unknown
    signal types cannot gain an interpretation through their field names.
    Callers supply only signals permitted by the ordinary product boundary.
    """
    public_signals = sanitize_signals_for_public(signals) or {}
    supported = {
        key: value
        for key, value in public_signals.items()
        if key in SIGNAL_TITLES and isinstance(value, Mapping)
    }
    if not supported:
        return None
    activities = [key for key in ACTIVITY_KEYS if key in supported]
    constraints = [key for key in CONSTRAINT_KEYS if key in supported]
    context = [key for key in CONTEXT_KEYS if key in supported]
    selected = list(dict.fromkeys([*activities[:2], *constraints[:2]]))
    for key in [*context, *activities[2:], *constraints[2:]]:
        if len(selected) >= 4:
            break
        selected.append(key)

    findings = []
    for key in selected:
        category = "activity" if key in ACTIVITY_KEYS else "context"
        if key in CONSTRAINT_KEYS:
            category = "constraint"
        text = format_signal_label(key, supported[key])
        if key == "municipal_record":
            evidence = supported[key].get("evidence", supported[key])
            excerpts = evidence.get("passages", [])
            source_text = " […] ".join(
                " ".join(passage["text"].split())
                for passage in excerpts
                if isinstance(passage, Mapping) and isinstance(passage.get("text"), str)
            )
            kind = str(evidence.get("document_kind") or "record").capitalize()
            meeting_date = evidence.get("meeting_date") or "date unavailable"
            if source_text:
                preview = (
                    source_text
                    if len(source_text) <= 600
                    else source_text[:600].rstrip() + "…"
                )
                text = f"{kind}, {meeting_date}: {preview}"
        findings.append(
            {
                "signal_key": key,
                "category": category,
                "title": SIGNAL_TITLES[key],
                "text": f"{text} [Signal: {key}]",
                "caveat": (
                    "A recorded sale does not establish the buyer's development plans or the property's current market value."
                    if key == "ownership_change"
                    else SIGNAL_CAVEATS.get(key)
                ),
            }
        )

    questions = [
        f"{QUESTIONS[key]} [Signal: {key}]" for key in selected if key in QUESTIONS
    ][:3]
    if activities:
        headline = "Recorded activity and what to verify"
    elif constraints:
        headline = "Mapped constraints and what to verify"
    else:
        headline = "Property context and what to verify"
    return {
        "method": "source_records",
        "version": 1,
        "headline": headline,
        "findings": findings,
        "questions": questions,
        "signal_count": len(supported),
        "source_updated_at": source_updated_at,
    }
