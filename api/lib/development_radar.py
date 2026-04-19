"""Helpers for presenting development radar signals in the API."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation

SIGNAL_PRIORITY: dict[str, int] = {
    "active_subdivision": 1,
    "ecodev_candidate": 2,
    "tax_distress": 3,
    "ownership_change": 4,
    "vacancy": 5,
    "assemblage": 6,
    "zoning_mismatch": 7,
    "penndot_project": 8,
    "cdbg_investment": 9,
    "growth_area": 10,
    "flood_zone": 99,
}

DIRECT_SIGNAL_KEYS = {
    "active_subdivision",
    "ecodev_candidate",
    "tax_distress",
    "ownership_change",
    "vacancy",
    "assemblage",
}

EXCLUDED_SIGNAL_KEYS = {"conservation_easement", "ag_security"}

from api.lib.response_types import ReasonSignalPayload as ReasonSignal

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


def signal_weight(signal: object) -> Decimal:
    signal_dict = _as_mapping(signal)
    if signal_dict is not None:
        return _as_decimal(signal_dict.get("weight"))
    return Decimal("0")


def format_signal_label(key: str, signal: object) -> str:
    ev = _evidence(signal)

    if key == "active_subdivision":
        return f"Active subdivision: {ev.get('plan_title') or 'Unknown'}"
    if key == "ecodev_candidate":
        pct = ev.get("percent_underutilized")
        return f"YCPC underutilized parcel ({pct or '?'}% underutilized)"
    if key == "tax_distress":
        return f"${_currency(ev.get('total_owed'))} owed ({ev.get('years_delinquent') or '?'} years)"
    if key == "ownership_change":
        prefix = "Investor purchase" if ev.get("buyer_is_llc") else "Sold"
        return f"{prefix} {ev.get('saledt') or '?'} for ${_currency(ev.get('price'))}"
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
    if key == "cdbg_investment":
        return f"Near CDBG housing: {ev.get('name') or ev.get('address') or 'project'}"
    if key == "growth_area":
        label = "Primary" if ev.get("ga_type") == "PGA" else "Secondary"
        return f"In {label} Growth Area"
    if key == "flood_zone":
        return f"In SFHA flood zone ({ev.get('fld_zone') or '?'})"
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
                "is_risk": key == "flood_zone",
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
