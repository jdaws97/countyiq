"""Classify consecutive staging.parcels SCD2 versions into explicit events.

Turns weekly parcel version diffs into transfer / value_change /
structure_change rows for public.parcel_events. This is the scrape-free
replacement for recorder-portal document scraping: a transfer is asserted
only from observed county-published field changes (deed reference, sale
date/price, owner), never inferred beyond them. Mortgages, liens, easements,
and title chains are out of scope by design — they cannot be derived from
parcel diffs and are not collected.

Confidence semantics (kept separate from LLM prose by design):
  confirmed — the county's own record states the fact (a new deed reference
              corroborated by owner/price movement, or an assessed-value change).
  likely    — a single uncorroborated indicator moved.
"""

from datetime import date, datetime
from typing import Any

# Fields that indicate a recorded transfer when they change.
TRANSFER_INDICATOR_FIELDS = ("deed_bk", "deed_pg", "saledt")
# Fields that corroborate a transfer.
TRANSFER_CORROBORATING_FIELDS = ("owner_full", "price", "prev_owner", "mail_addr_full")

VALUE_FIELDS = ("aprland", "aprbldg", "aprtotal")

STRUCTURE_FIELDS = (
    "yrblt",
    "res_living_area",
    "num_stories",
    "comm_struc",
    "comm_year_built",
    "comm_building_sq_ft",
)

# Every field the classifier reads — the asset's fetch query selects these
# from both versions and pre-filters to pairs where at least one differs.
TRACKED_FIELDS = tuple(
    dict.fromkeys(
        TRANSFER_INDICATOR_FIELDS
        + TRANSFER_CORROBORATING_FIELDS
        + VALUE_FIELDS
        + STRUCTURE_FIELDS
    )
)


def _norm(value: Any) -> str | None:
    """Normalize a staged value for comparison (columns arrive as text/str)."""
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _changed(old: dict, new: dict, field: str) -> bool:
    return _norm(old.get(field)) != _norm(new.get(field))


def _to_float(value: Any) -> float | None:
    text = _norm(value)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_saledt(value: Any) -> date | None:
    """Parse the county's DD-MON-YYYY sale date; None on any malformed value."""
    text = _norm(value)
    if text is None:
        return None
    try:
        return datetime.strptime(text, "%d-%b-%Y").date()
    except ValueError:
        return None


def _evidence(old: dict, new: dict, fields: tuple[str, ...]) -> dict:
    return {
        field: {"old": _norm(old.get(field)), "new": _norm(new.get(field))}
        for field in fields
        if _changed(old, new, field)
    }


def _classify_transfer(old: dict, new: dict) -> dict | None:
    indicators = [f for f in TRANSFER_INDICATOR_FIELDS if _changed(old, new, f)]
    if not indicators:
        return None

    corroborating = [f for f in TRANSFER_CORROBORATING_FIELDS if _changed(old, new, f)]
    deed_changed = "deed_bk" in indicators or "deed_pg" in indicators

    # A deed reference change backed by owner/price/prev_owner movement is the
    # county stating a recorded transfer. A lone sale-date drift (data cleanup,
    # backfilled SALEDT) stays "likely" until something else moves with it.
    if deed_changed and any(
        f in corroborating for f in ("owner_full", "price", "prev_owner")
    ):
        confidence = "confirmed"
    elif len(indicators) + len(corroborating) >= 3:
        confidence = "confirmed"
    else:
        confidence = "likely"

    return {
        "event_type": "transfer",
        "confidence": confidence,
        "event_date": _parse_saledt(new.get("saledt")),
        "evidence": {
            "changed": _evidence(
                old, new, TRANSFER_INDICATOR_FIELDS + TRANSFER_CORROBORATING_FIELDS
            ),
            "indicators": indicators,
            "corroboration": corroborating,
        },
    }


def _classify_value_change(
    old: dict, new: dict, transfer_detected: bool
) -> dict | None:
    changed = [f for f in VALUE_FIELDS if _changed(old, new, f)]
    if not changed:
        return None

    old_bldg = _to_float(old.get("aprbldg"))
    new_bldg = _to_float(new.get("aprbldg"))
    old_land = _to_float(old.get("aprland"))
    new_land = _to_float(new.get("aprland"))

    pattern = "general"
    bldg_up = old_bldg is not None and new_bldg is not None and new_bldg > old_bldg
    land_stable = (
        old_land is not None
        and new_land is not None
        and (old_land == 0 or abs(new_land - old_land) / max(old_land, 1.0) <= 0.05)
    )
    bldg_gone = (
        old_bldg is not None and old_bldg > 0 and (new_bldg is None or new_bldg == 0)
    )
    if bldg_gone:
        pattern = "demolition_like"
    elif bldg_up and land_stable and not transfer_detected:
        pattern = "renovation_like"

    return {
        "event_type": "value_change",
        "confidence": "confirmed",  # the assessed value itself changed — a fact
        "event_date": None,
        "evidence": {
            "changed": _evidence(old, new, VALUE_FIELDS),
            "pattern": pattern,
        },
    }


def _classify_structure_change(old: dict, new: dict) -> dict | None:
    changed = [f for f in STRUCTURE_FIELDS if _changed(old, new, f)]
    if not changed:
        return None
    return {
        "event_type": "structure_change",
        "confidence": "likely",
        "event_date": None,
        "evidence": {"changed": _evidence(old, new, STRUCTURE_FIELDS)},
    }


def classify_parcel_change(old: dict, new: dict) -> list[dict]:
    """Classify one consecutive version pair into zero or more events.

    Args:
        old: the expired version's tracked fields (staged values, text-ish).
        new: the replacing version's tracked fields.

    Returns:
        Event dicts with event_type, confidence, event_date, evidence —
        the caller adds pidn and version provenance.
    """
    events = []
    transfer = _classify_transfer(old, new)
    if transfer:
        events.append(transfer)
    value_change = _classify_value_change(
        old, new, transfer_detected=transfer is not None
    )
    if value_change:
        events.append(value_change)
    structure = _classify_structure_change(old, new)
    if structure:
        events.append(structure)
    return events
