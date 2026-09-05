"""Helpers for presenting development radar signals in the API."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation

from api.lib.response_types import ReasonSignalPayload as ReasonSignal

SIGNAL_PRIORITY: dict[str, int] = {
    "active_subdivision": 1,
    "municipal_action": 2,
    "economic_development_park": 3,
    "entity_assemblage": 4,
    "tax_distress": 5,
    "ownership_change": 6,
    "nearby_subdivision": 7,
    "vacancy": 8,
    "assemblage": 9,
    "zoning_mismatch": 10,
    "penndot_project": 11,
    "development_overlay": 12,
    "local_traffic_activity": 13,
    "growth_area": 14,
    "ag_security": 95,
    "conservation_easement": 96,
    "environmental_diligence": 96,
    "soil_constraint": 97,
    "zoning_constraint": 98,
    "flood_zone": 99,
}

DIRECT_SIGNAL_KEYS = {
    "active_subdivision",
    "municipal_action",
    "economic_development_park",
    "entity_assemblage",
    "tax_distress",
    "ownership_change",
    "vacancy",
    "assemblage",
}

RISK_SIGNAL_KEYS = {
    "flood_zone",
    "soil_constraint",
    "zoning_constraint",
    "environmental_diligence",
}

# Keys stripped from list-style radar responses. They are per-signal prose
# and machine refs that only the property page renders; shipping them for
# 200 rows at a time bloated the radar payload several-fold.
LIST_OMITTED_SIGNAL_FIELDS = {
    "validation_reasoning",
    "cross_references",
    "claim",
    "internal_url",
}

EXCLUDED_SIGNAL_KEYS = {"conservation_easement"}

SIGNAL_TITLES: dict[str, str] = {
    "active_subdivision": "Subdivision / land-development plan",
    "nearby_subdivision": "Nearby plan activity",
    "economic_development_park": "Business / industrial park inventory",
    "municipal_action": "Municipal proceeding",
    "zoning_mismatch": "Plan / zoning divergence",
    "ownership_change": "Recent recorded sale",
    "vacancy": "Building-footprint and value screen",
    "tax_distress": "Tax-delinquency indicator",
    "assemblage": "Neighbor ownership pattern",
    "entity_assemblage": "Same-name contiguous ownership pattern",
    "penndot_project": "Nearby PennDOT project",
    "development_overlay": "Municipal development overlay",
    "local_traffic_activity": "Nearby traffic count",
    "growth_area": "County growth-area policy",
    "soil_constraint": "Mapped soil and terrain constraint",
    "zoning_constraint": "Special-purpose zoning overlay",
    "environmental_diligence": "Nearby PA DEP screening record",
    "flood_zone": "FEMA Special Flood Hazard Area overlap",
    "conservation_easement": "Agricultural conservation easement",
    "ag_security": "Agricultural Security Area enrollment",
}

SIGNAL_INTERPRETATIONS: dict[str, str] = {
    "active_subdivision": "A recent county planning point is mapped on or immediately beside this parcel.",
    "nearby_subdivision": "A recent county planning point is nearby and is treated as neighborhood activity, not this parcel's plan.",
    "economic_development_park": "The PIDN appears in the county's official business- or industrial-park parcel inventory.",
    "municipal_action": "A governed municipal record was linked to the parcel by PIDN or normalized address.",
    "zoning_mismatch": "The zoning category and adopted future-land-use category differ at the parcel center point.",
    "ownership_change": "The county parcel record shows a non-nominal sale within the scoring window.",
    "vacancy": "No county building footprint intersects the parcel and the parcel also passes low-value filters.",
    "tax_distress": "The PIDN appears with a positive balance in the current governed tax-claim listing.",
    "assemblage": "The parcel geometry intersects several parcels held by different resolved owners (name variants merged).",
    "entity_assemblage": "The same resolved owner (name variants merged) holds touching parcels after a recent acquisition.",
    "penndot_project": "The closest non-completed PennDOT project point falls within the configured 800 m screen.",
    "development_overlay": "The parcel center point lies inside a county-published municipal development overlay.",
    "local_traffic_activity": "A qualifying traffic-count point from the last five years falls within 400 m of the parcel center.",
    "growth_area": "The parcel center point lies in a Primary or Secondary Growth Area in the county plan layer.",
    "soil_constraint": "Mapped soil units covering at least 5% of the parcel triggered on slope, drainage, or hydrologic group.",
    "zoning_constraint": "The parcel center point lies in a special-purpose municipal overlay that warrants ordinance review.",
    "environmental_diligence": "A public PA DEP facility or site record falls within the configured 500 m screening radius.",
    "flood_zone": "FEMA Special Flood Hazard Area geometry overlaps at least 1% of the parcel geometry.",
    "conservation_easement": "The county inventory associates the PIDN with a recorded agricultural conservation easement.",
    "ag_security": "The county inventory associates the PIDN with an Agricultural Security Area.",
}

SIGNAL_CAVEATS: dict[str, str] = {
    "active_subdivision": "A planning point is not a surveyed plan boundary, approval, permit, or proof that every part of the parcel is involved.",
    "nearby_subdivision": "The plan belongs to a nearby location; it does not establish activity, access, or entitlement on this parcel.",
    "economic_development_park": "Inventory membership does not by itself establish zoning, utility capacity, incentives, or development entitlement.",
    "municipal_action": "Address matches can be ambiguous, and a proceeding is not necessarily an approval; confirm the cited document and status.",
    "zoning_mismatch": "Future land use is policy guidance, not current zoning or an entitlement. Center-point matching can miss split-zoned parcels.",
    "ownership_change": "An organization-looking owner name is a text pattern, not a verified investor classification or evidence of development intent.",
    "vacancy": "Missing footprints can reflect source lag or mapping omissions; this signal does not prove the land is vacant or buildable.",
    "tax_distress": "Exact claims and balances are suppressed under source policy. Confirm current status and payoff directly with the Tax Claim Bureau.",
    "assemblage": "This is a parcel-topology pattern. It can indicate either opportunity or fragmented ownership and does not prove assemblage activity.",
    "entity_assemblage": "Owner resolution merges recorded name variants but can still combine or split legal entities; it does not prove coordinated acquisition intent.",
    "penndot_project": "A mapped project point and published status do not establish parcel impact, access changes, funding, or completion timing.",
    "development_overlay": "An overlay is a planning or regulatory context layer, not automatic development permission.",
    "local_traffic_activity": "The displayed value is the source's reported volume for a dated count and is not assumed to be current AADT.",
    "growth_area": "Growth-area policy does not override zoning, sewer capacity, environmental constraints, or site approvals.",
    "soil_constraint": "County soil mapping is a screening layer, not a site investigation. Confirm grading, foundations, drainage, and on-lot wastewater with qualified professionals.",
    "zoning_constraint": "Overlay boundaries and requirements must be confirmed against the current municipal ordinance and official zoning map.",
    "environmental_diligence": "Proximity to a DEP record is not a contamination finding or regulatory determination; inspect the record and perform appropriate due diligence.",
    "flood_zone": "This is not an official flood determination. Floodplain limits, structures, elevation, and insurance requirements require parcel-specific confirmation.",
    "conservation_easement": "County inventory matching is a strong exclusion screen, but the recorded deed and any permitted building area control.",
    "ag_security": "Pennsylvania states ASA enrollment does not itself prevent sale, subdivision, or development; it is not a conservation easement.",
}

TAX_SIGNAL_PRIVATE_FIELDS = {"total_owed", "years_delinquent", "oldest_year"}

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
) -> dict[str, object] | None:
    """Return public-safe signal JSON.

    Owner identity is public record and passes through unchanged. Exact
    tax-claim facts are the one restricted surface: the property-level boolean
    stays visible, balances and claim history do not.
    """

    if signals is None:
        return None

    public_signals = {str(key): value for key, value in signals.items()}
    tax_signal = _as_mapping(public_signals.get("tax_distress"))
    if tax_signal is not None:
        cleaned_tax = dict(tax_signal)
        tax_evidence = _as_mapping(cleaned_tax.get("evidence"))
        if tax_evidence is not None:
            cleaned_tax["evidence"] = {
                key: value
                for key, value in tax_evidence.items()
                if str(key).lower() not in TAX_SIGNAL_PRIVATE_FIELDS
            }
        for field in TAX_SIGNAL_PRIVATE_FIELDS:
            cleaned_tax.pop(field, None)
        public_signals["tax_distress"] = cleaned_tax
    return public_signals


def signal_weight(signal: object) -> Decimal:
    signal_dict = _as_mapping(signal)
    if signal_dict is not None:
        return _as_decimal(signal_dict.get("weight"))
    return Decimal("0")


def _distance_m(signal: object, evidence: SignalMapping) -> object:
    signal_map = _as_mapping(signal)
    if signal_map and signal_map.get("distance_m") is not None:
        return signal_map.get("distance_m")
    return evidence.get("distance_m")


def _soil_units(evidence: SignalMapping) -> list[SignalMapping]:
    units = evidence.get("soil_units")
    if not isinstance(units, (list, tuple)):
        return []
    return [unit for raw in units if (unit := _as_mapping(raw)) is not None]


def _percent(value: object) -> str:
    number = _as_decimal(value)
    return f"{number.quantize(Decimal('0.1'))}%"


def _plain_number(value: object) -> str:
    number = _as_decimal(value)
    if number == number.to_integral_value():
        return f"{number:.0f}"
    return f"{number.normalize():f}"


def soil_constraint_reasons(evidence: SignalMapping) -> list[str]:
    """Translate the actual soil trigger fields into readable reasons."""

    units = _soil_units(evidence)
    if not units:
        units = [evidence]
    reasons: list[str] = []
    for unit in units:
        coverage = unit.get("coverage_pct")
        coverage_prefix = f"{_percent(coverage)} of parcel: " if coverage is not None else ""
        symbol = str(unit.get("map_unit_symbol") or "mapped unit")
        representative = _as_decimal(unit.get("representative_slope"))
        slope_low = unit.get("slope_low")
        slope_high = unit.get("slope_high")
        if representative >= 15:
            slope_range = (
                f"{slope_low}–{slope_high}% slope; "
                if slope_low is not None and slope_high is not None
                else ""
            )
            reasons.append(
                f"{coverage_prefix}{symbol} has {slope_range}{_plain_number(representative)}% representative slope"
            )
        drainage = str(unit.get("drainage") or "")
        if drainage in {"Poorly drained", "Somewhat poorly drained"}:
            reasons.append(f"{coverage_prefix}{symbol} is {drainage.lower()}")
        if str(unit.get("hydrologic_group") or "") == "D":
            reasons.append(f"{coverage_prefix}{symbol} is hydrologic group D (high runoff potential)")
    return reasons


def format_signal_label(key: str, signal: object) -> str:
    ev = _evidence(signal)

    if key == "active_subdivision":
        distance = _distance_m(signal, ev)
        if distance is not None and _as_decimal(distance) > Decimal("0.5"):
            return f"Plan point {float(distance):,.0f} m from parcel boundary: {ev.get('plan_title') or 'Unknown'}"
        return f"Plan point mapped on parcel: {ev.get('plan_title') or 'Unknown'}"
    if key == "nearby_subdivision":
        distance = _distance_m(signal, ev)
        where = f"{float(distance):,.0f} m away" if distance is not None else "nearby"
        return f"Plan {where}: {ev.get('plan_title') or 'Unknown'}"
    if key == "municipal_action":
        kind = str(ev.get("extraction_type") or "proceeding").replace("_", " ")
        decision = ev.get("decision")
        suffix = f" ({decision})" if decision else ""
        match_method = str(ev.get("match_method") or "record").replace("_", " ")
        return f"Municipal {kind} linked by {match_method}{suffix}"
    if key == "entity_assemblage":
        return (
            "Same recorded owner holds "
            f"{ev.get('contiguous_same_owner_parcels') or '?'} touching parcels after a recent acquisition"
        )
    if key == "economic_development_park":
        names = ev.get("park_names")
        park_types = ev.get("park_types")
        name = names[0] if isinstance(names, list) and names else None
        kind = park_types[0] if isinstance(park_types, list) and park_types else "development"
        return f"Mapped in {name or kind.title() + ' park'}"
    if key == "tax_distress":
        return "Current tax-delinquency indicator"
    if key == "ownership_change":
        organization_name = ev.get("buyer_name_looks_organizational", ev.get("buyer_is_llc"))
        prefix = "Recorded sale to organization-name buyer" if organization_name else "Recorded sale"
        sale_date = ev.get("saledt")
        dated_prefix = f"{prefix} {sale_date}" if sale_date else prefix
        return f"{dated_prefix} for ${_currency(ev.get('price'))}"
    if key == "vacancy":
        return "No mapped building footprint; low-value screen"
    if key == "assemblage":
        return (
            "Touches "
            f"{ev.get('neighbor_parcels') or '?'} parcels held by other named owners"
        )
    if key == "zoning_mismatch":
        current = ev.get("current_zname") or ev.get("current_ztype") or "?"
        future = ev.get("future_lu") or "?"
        return f"Parcel-center zoning {current} differs from planned land use {future}"
    if key == "penndot_project":
        distance = _distance_m(signal, ev)
        where = f" {float(distance):,.0f} m away" if distance is not None else " nearby"
        status = str(ev.get("status") or "Mapped").title()
        return f"{status} PennDOT project{where}: {ev.get('project_name') or 'Unnamed project'}"
    if key == "development_overlay":
        return f"Parcel center mapped in {ev.get('overlay_name') or ev.get('overlay_type') or 'development overlay'}"
    if key == "local_traffic_activity":
        volume = ev.get("volume")
        count_year = ev.get("count_year") or "recent"
        distance = _distance_m(signal, ev)
        where = f", {float(distance):,.0f} m away" if distance is not None else ""
        return f"Reported volume {_currency(volume)} at {count_year} traffic count{where}"
    if key == "growth_area":
        label = "Primary" if ev.get("ga_type") == "PGA" else "Secondary"
        return f"Parcel center lies in {label} Growth Area"
    if key == "flood_zone":
        overlap = ev.get("overlap_pct")
        if overlap is not None:
            return f"Special Flood Hazard Area overlaps {_percent(overlap)} of parcel"
        return f"Parcel center lies in SFHA flood zone ({ev.get('fld_zone') or '?'})"
    if key == "environmental_diligence":
        distance = _distance_m(signal, ev)
        suffix = f" {float(distance):,.0f} m away" if distance is not None else " nearby"
        site = ev.get("site_name") or ev.get("facility_type") or ev.get("source_layer") or "record"
        return f"PA DEP screening record{suffix}: {site}"
    if key == "soil_constraint":
        reasons = soil_constraint_reasons(ev)
        return f"Mapped soil constraint: {reasons[0] if reasons else 'review mapped soil units'}"
    if key == "zoning_constraint":
        name = ev.get("overlay_name") or ev.get("overlay_type") or "special-purpose overlay"
        return f"Parcel center lies in {name}"
    if key == "conservation_easement":
        return "Recorded agricultural conservation easement"
    if key == "ag_security":
        return "Agricultural Security Area enrollment — not a development prohibition"
    return key.replace("_", " ")


def _fact(label: str, value: object) -> dict[str, str] | None:
    if value in (None, "", [], {}):
        return None
    return {"label": label, "value": str(value)}


def _signal_facts(key: str, signal: object) -> list[dict[str, str]]:
    ev = _evidence(signal)
    distance = _distance_m(signal, ev)
    raw: list[dict[str, str] | None] = []
    if key in {"active_subdivision", "nearby_subdivision"}:
        raw = [
            _fact("Plan", ev.get("plan_title")),
            _fact("Received", ev.get("date_rcvd")),
            _fact("Proposed lots", ev.get("prop_lots")),
            _fact("Proposed dwelling units", ev.get("prop_du")),
            _fact("Distance", f"{float(distance):,.0f} m" if distance is not None else None),
        ]
    elif key == "municipal_action":
        raw = [
            _fact("Matter", str(ev.get("extraction_type") or "").replace("_", " ")),
            _fact("Decision", ev.get("decision")),
            _fact("Meeting", ev.get("meeting_date")),
            _fact("Matched by", str(ev.get("match_method") or "").replace("_", " ")),
        ]
    elif key == "economic_development_park":
        names = ev.get("park_names")
        types = ev.get("park_types")
        raw = [
            _fact("Park", ", ".join(map(str, names)) if isinstance(names, list) else names),
            _fact("Inventory type", ", ".join(map(str, types)) if isinstance(types, list) else types),
        ]
    elif key == "zoning_mismatch":
        raw = [
            _fact("Current zoning", ev.get("current_zname") or ev.get("current_ztype")),
            _fact("Future land use", ev.get("future_lu")),
            _fact("Spatial basis", "parcel center point"),
        ]
    elif key == "ownership_change":
        raw = [
            _fact("Sale date", ev.get("saledt")),
            _fact("Sale price", f"${_currency(ev.get('price'))}"),
            _fact("Organization-name pattern", "yes" if ev.get("buyer_name_looks_organizational", ev.get("buyer_is_llc")) else "no"),
        ]
    elif key == "vacancy":
        raw = [
            _fact("Mapped footprints", ev.get("structure_count")),
            _fact("Property class", ev.get("class")),
            _fact("Assessed total", f"${_currency(ev.get('aprtotal'))}"),
        ]
    elif key == "tax_distress":
        raw = [_fact("Public result", "Current delinquency indicator detected; exact claim details suppressed")]
    elif key == "assemblage":
        raw = [
            _fact("Intersecting neighbor parcels", ev.get("neighbor_parcels")),
            _fact("Different recorded owner names", ev.get("different_owner_neighbors")),
        ]
    elif key == "entity_assemblage":
        raw = [
            _fact("Touching same-name parcels", ev.get("contiguous_same_owner_parcels")),
            _fact("Latest acquisition", ev.get("latest_acquisition")),
            _fact("Match basis", "resolved owner identity (recorded name variants merged)"),
        ]
    elif key == "penndot_project":
        raw = [
            _fact("Project", ev.get("project_name")),
            _fact("Status", ev.get("status")),
            _fact("Type", ev.get("project_type")),
            _fact("Distance", f"{float(distance):,.0f} m" if distance is not None else None),
        ]
    elif key in {"development_overlay", "zoning_constraint"}:
        raw = [
            _fact("Overlay", ev.get("overlay_name") or ev.get("overlay_type")),
            _fact("Type", ev.get("overlay_type")),
            _fact("Spatial basis", "parcel center point"),
        ]
    elif key == "local_traffic_activity":
        raw = [
            _fact("Reported volume", _currency(ev.get("volume"))),
            _fact("Count year", ev.get("count_year")),
            _fact("Count purpose", ev.get("purpose")),
            _fact("Distance", f"{float(distance):,.0f} m" if distance is not None else None),
        ]
    elif key == "growth_area":
        raw = [
            _fact("Growth area", "Primary" if ev.get("ga_type") == "PGA" else "Secondary"),
            _fact("Status", ev.get("ga_status")),
            _fact("Spatial basis", "parcel center point"),
        ]
    elif key == "soil_constraint":
        units = _soil_units(ev)
        raw = [_fact("Trigger", reason) for reason in soil_constraint_reasons(ev)[:3]]
        if units:
            septic = sorted({str(unit.get("septic_rating")) for unit in units if unit.get("septic_rating")})
            drainage = sorted({str(unit.get("drainage")) for unit in units if unit.get("drainage")})
            raw.extend([
                _fact("Mapped drainage", ", ".join(drainage)),
                _fact("On-lot septic rating", ", ".join(septic)),
            ])
        else:
            raw.extend([
                _fact("Mapped drainage", ev.get("drainage")),
                _fact("On-lot septic rating", ev.get("septic_rating")),
            ])
    elif key == "environmental_diligence":
        raw = [
            _fact("Site / facility", ev.get("site_name") or ev.get("facility_type")),
            _fact("Status", ev.get("facility_status")),
            _fact("Source layer", ev.get("source_layer")),
            _fact("Distance", f"{float(distance):,.0f} m" if distance is not None else None),
        ]
    elif key == "flood_zone":
        zones = ev.get("flood_zones")
        zone_text = None
        if isinstance(zones, list):
            zone_text = ", ".join(
                str(zone.get("fld_zone"))
                for raw_zone in zones
                if (zone := _as_mapping(raw_zone)) and zone.get("fld_zone")
            )
        raw = [
            _fact("Parcel overlap", _percent(ev.get("overlap_pct")) if ev.get("overlap_pct") is not None else None),
            _fact("Mapped zone", zone_text or ev.get("fld_zone")),
        ]
    elif key == "conservation_easement":
        raw = [
            _fact("Easement ID", ev.get("ease_id")),
            _fact("Preserved", ev.get("preservation_date")),
            _fact("Mapped easement acres", ev.get("ease_acres")),
        ]
    elif key == "ag_security":
        raw = [
            _fact("Resolution", ev.get("resolution")),
            _fact("Resolution date", ev.get("res_date")),
            _fact("Last review", ev.get("last_review")),
            _fact("Legal effect", "ASA enrollment is not itself a development prohibition"),
        ]
    return [item for item in raw if item is not None]


def build_signal_presentation(key: str, signal: object) -> dict[str, object]:
    """Return the shared, plain-language contract used by the property page."""

    signal_map = _as_mapping(signal) or {}
    impacts = {
        "momentum": int(_as_decimal(signal_map.get("momentum_points"))),
        "opportunity": int(_as_decimal(signal_map.get("opportunity_points"))),
        "site_screening": int(_as_decimal(signal_map.get("site_screening_points"))),
    }
    return {
        "title": SIGNAL_TITLES.get(key, key.replace("_", " ").title()),
        "summary": format_signal_label(key, signal),
        "interpretation": SIGNAL_INTERPRETATIONS.get(key),
        "caveat": SIGNAL_CAVEATS.get(key),
        "facts": _signal_facts(key, signal),
        "score_impacts": impacts,
        "affects_eligibility": bool(signal_map.get("affects_eligibility", key == "conservation_easement")),
    }


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
                "is_risk": key in RISK_SIGNAL_KEYS,
            }
        )
    return reasons


def compact_signals_for_list(
    signals: SignalMapping | None,
) -> dict[str, object] | None:
    """Drop per-signal prose from list responses; the property page keeps it."""

    if signals is None:
        return None
    compact: dict[str, object] = {}
    for key, value in signals.items():
        mapping = _as_mapping(value)
        if mapping is None:
            compact[str(key)] = value
            continue
        compact[str(key)] = {
            str(field): item
            for field, item in mapping.items()
            if str(field) not in LIST_OMITTED_SIGNAL_FIELDS
        }
    return compact


def compute_headline_signal(
    signals: SignalMapping | None,
    fallback: str | None = None,
) -> str | None:
    reasons = build_reason_signals(signals, limit=1)
    if reasons:
        return reasons[0]["label"]
    return fallback
