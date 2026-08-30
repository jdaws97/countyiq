"""Helpers for presenting development radar signals in the API."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation

from api.lib.response_types import ReasonSignalPayload as ReasonSignal

SIGNAL_PRIORITY: dict[str, int] = {
    "active_subdivision": 1,
    "economic_development_park": 2,
    "tax_distress": 3,
    "ownership_change": 4,
    "vacancy": 5,
    "assemblage": 6,
    "zoning_mismatch": 7,
    "penndot_project": 8,
    "development_overlay": 9,
    "local_traffic_activity": 10,
    "growth_area": 11,
    "environmental_diligence": 96,
    "soil_constraint": 97,
    "zoning_constraint": 98,
    "flood_zone": 99,
}

DIRECT_SIGNAL_KEYS = {
    "active_subdivision",
    "economic_development_park",
    "tax_distress",
    "ownership_change",
    "vacancy",
    "assemblage",
}

EXCLUDED_SIGNAL_KEYS = {"conservation_easement", "ag_security"}

# Signal JSON is assembled from deterministic source evidence plus optional
# LLM validation text. These keys can carry natural-person identity or prose
# that repeats it, so they are removed when the governing source does not
# permit person-level display. Place/business/project names remain available.
PERSON_SIGNAL_FIELDS = {
    "aliases",
    "applicant_name",
    "buyer_name",
    "canonical_name",
    "claim",
    "claimant_name",
    "cross_references",
    "curr_owner",
    "current_owner",
    "grantor",
    "linked_names",
    "mail_addr_full",
    "mail_address",
    "own_name1",
    "own_name2",
    "owner_full",
    "owner_name",
    "prev_owner",
    "related_entities",
    "seller_name",
    "supporting_text",
    "validation_reasoning",
}

SignalMapping = Mapping[str, object]


def _as_mapping(value: object) -> SignalMapping | None:
    if isinstance(value, Mapping):
        return value
    return None


def _as_decimal(value: object) -> Decimal:
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _currency(value: object) -> str:
    if value in (None, ""):
        return "?"
    amount = _as_decimal(value)
    if amount == amount.to_integral_value():
        return f"{int(amount):,}"
    return f"{amount:,.2f}"


def _evidence(signal: object) -> SignalMapping:
    signal_dict = _as_mapping(signal)
    if signal_dict is None:
        return {}

    evidence = _as_mapping(signal_dict.get("evidence"))
    if evidence is not None:
        return evidence
    return signal_dict


def signal_priority(key: str) -> int:
    return SIGNAL_PRIORITY.get(key, 50)


def sanitize_signals_for_public(
    signals: SignalMapping | None,
    *,
    allow_people: bool,
) -> dict[str, object] | None:
    """Return public-safe signal JSON under the current person-use policy."""

    if signals is None:
        return None
    if allow_people:
        return dict(signals)

    def sanitize(value: object) -> object:
        mapping = _as_mapping(value)
        if mapping is not None:
            return {
                str(key): sanitize(item)
                for key, item in mapping.items()
                if str(key).lower() not in PERSON_SIGNAL_FIELDS
            }
        if isinstance(value, (list, tuple)):
            return [sanitize(item) for item in value]
        return value

    return {
        str(key): sanitize(value)
        for key, value in signals.items()
    }


def signal_weight(signal: object) -> Decimal:
    signal_dict = _as_mapping(signal)
    if signal_dict is not None:
        return _as_decimal(signal_dict.get("weight"))
    return Decimal("0")


def format_signal_label(key: str, signal: object) -> str:
    ev = _evidence(signal)

    if key == "active_subdivision":
        return f"Active subdivision: {ev.get('plan_title') or 'Unknown'}"
    if key == "economic_development_park":
        names = ev.get("park_names")
        park_types = ev.get("park_types")
        name = names[0] if isinstance(names, list) and names else None
        kind = park_types[0] if isinstance(park_types, list) and park_types else "development"
        return f"In {name or kind.title() + ' park'}"
    if key == "tax_distress":
        return f"${_currency(ev.get('total_owed'))} owed ({ev.get('years_delinquent') or '?'} years)"
    if key == "ownership_change":
        prefix = "Investor purchase" if ev.get("buyer_is_llc") else "Sold"
        sale_date = ev.get("saledt")
        dated_prefix = f"{prefix} {sale_date}" if sale_date else prefix
        return f"{dated_prefix} for ${_currency(ev.get('price'))}"
    if key == "vacancy":
        return "Likely vacant / lightly improved parcel"
    if key == "assemblage":
        return (
            "Assemblage edge: "
            f"{ev.get('different_owner_neighbors') or '?'} differently owned neighbors"
        )
    if key == "zoning_mismatch":
        current = ev.get("current_zname") or ev.get("current_ztype") or "?"
        future = ev.get("future_lu") or "?"
        return f"Zoned {current} -> planned {future}"
    if key == "penndot_project":
        return f"Near {ev.get('project_name') or 'PennDOT project'}"
    if key == "development_overlay":
        return f"In development overlay: {ev.get('overlay_name') or ev.get('overlay_type') or '?'}"
    if key == "local_traffic_activity":
        volume = ev.get("volume")
        count_year = ev.get("count_year") or "recent"
        return f"{_currency(volume)} vehicles ({count_year} count)"
    if key == "growth_area":
        label = "Primary" if ev.get("ga_type") == "PGA" else "Secondary"
        return f"In {label} Growth Area"
    if key == "flood_zone":
        return f"In SFHA flood zone ({ev.get('fld_zone') or '?'})"
    if key == "environmental_diligence":
        distance = _as_mapping(signal).get("distance_m") if _as_mapping(signal) else None
        suffix = f" ({float(distance):,.0f} m away)" if distance is not None else ""
        return f"PA DEP diligence record nearby{suffix}"
    if key == "soil_constraint":
        detail = ev.get("drainage") or ev.get("map_unit_name") or "adverse soil profile"
        return f"Soil constraint: {detail}"
    if key == "zoning_constraint":
        return f"Zoning overlay constraint: {ev.get('overlay_type') or '?'}"
    return key.replace("_", " ")


def ranked_signals(signals: SignalMapping | None) -> list[tuple[str, object]]:
    if signals is None:
        return []

    entries = [
        (key, signal)
        for key, signal in signals.items()
        if key not in EXCLUDED_SIGNAL_KEYS
    ]
    return sorted(
        entries,
        key=lambda item: (
            signal_priority(item[0]),
            -signal_weight(item[1]),
            item[0],
        ),
    )


def build_reason_signals(signals: SignalMapping | None, limit: int = 3) -> list[ReasonSignal]:
    reasons: list[ReasonSignal] = []
    for key, signal in ranked_signals(signals)[:limit]:
        reasons.append(
            {
                "key": key,
                "label": format_signal_label(key, signal),
                "weight": float(signal_weight(signal)),
                "is_direct": key in DIRECT_SIGNAL_KEYS,
                "is_risk": key in {
                    "flood_zone", "soil_constraint", "zoning_constraint",
                    "environmental_diligence",
                },
            }
        )
    return reasons


def compute_headline_signal(
    signals: SignalMapping | None,
    fallback: str | None = None,
) -> str | None:
    reasons = build_reason_signals(signals, limit=1)
    if reasons:
        return reasons[0]["label"]
    return fallback
