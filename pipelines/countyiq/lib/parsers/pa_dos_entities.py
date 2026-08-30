"""Parser for the PA registered-business SODA dataset (data.pa.gov xvd7-5r2c).

Replaces the retired Playwright scrape of file.dos.pa.gov (2026-08-05,
scrape-free source policy). The dataset publishes one row per business
officer/party; rows are grouped by filing_number into one record per entity.

The dataset is a snapshot of currently registered businesses and carries no
operating-status field, so records are labeled `present_in_current_dos_dataset`
— never "confirmed active". Names not found get an explicit
`not_found_in_current_dos_dataset` record so the weekly refresh has a negative
cache instead of re-querying every miss forever.
"""

import re
from datetime import date, datetime

STATUS_PRESENT = "present_in_current_dos_dataset"
STATUS_NOT_FOUND = "not_found_in_current_dos_dataset"

# Entity-suffix synonyms, longest phrase first. The county abbreviates
# ("KINSLEY EQUITIES II LP") where DOS spells out ("Kinsley Equities Ii
# Limited Partnership") — both sides normalize to the short form before
# comparison.
_SUFFIX_SYNONYMS = (
    ("LIMITED LIABILITY COMPANY", "LLC"),
    ("LIMITED LIABILITY PARTNERSHIP", "LLP"),
    ("LIMITED PARTNERSHIP", "LP"),
    ("INCORPORATED", "INC"),
    ("CORPORATION", "CORP"),
    ("COMPANY", "CO"),
    ("LIMITED", "LTD"),
)


def _compact(name: str | None) -> str:
    """Reduce a business name to a canonical alphanumeric form for matching.

    Handles case, punctuation, spacing, a leading "THE", and spelled-out
    entity suffixes: "York Holdings, L.L.C." and "YORK HOLDINGS LLC" both
    compact to "YORKHOLDINGSLLC"; "Kinsley Equities Ii Limited Partnership"
    and "KINSLEY EQUITIES II LP" both compact to "KINSLEYEQUITIESIILP".
    """
    if not name:
        return ""
    text = re.sub(r"[^A-Z0-9]+", " ", name.upper()).strip()
    text = re.sub(r"^THE ", "", text)
    for phrase, abbrev in _SUFFIX_SYNONYMS:
        text = re.sub(rf"\b{phrase}\b", abbrev, text)
    return text.replace(" ", "")


def _parse_iso_date(value: str | None) -> date | None:
    """Parse the dataset's ISO timestamp (e.g. '1987-03-19T00:00:00.000')."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.split("T")[0]).date()
    except ValueError:
        return None


def _officer_name(row: dict) -> str:
    parts = [row.get("first_name"), row.get("middle_name"), row.get("last_name")]
    return " ".join(p.strip() for p in parts if p and p.strip())


def _office_address(row: dict) -> str:
    parts = [
        row.get("address_line1"),
        row.get("address_line2"),
        row.get("city"),
        row.get("state"),
        row.get("zip"),
    ]
    return ", ".join(p.strip() for p in parts if p and p.strip())


def parse_soda_business_rows(rows: list[dict], search_name: str) -> dict | None:
    """Match SODA officer rows against a parcel-owner name.

    Args:
        rows: Raw dataset rows from a full-text ($q) search.
        search_name: The parcel owner string being looked up (becomes
            entity_name — the SCD2 key the pending-lookup dedupe joins on).

    Returns:
        One staging.corporate_entities record for the best-matching filing,
        or None when no row's business name compacts to the search name.
    """
    target = _compact(search_name)
    if not target:
        return None

    # Group exact compact-name matches by filing number.
    filings: dict[str, list[dict]] = {}
    for row in rows:
        if _compact(row.get("business_name")) == target and row.get("filing_number"):
            filings.setdefault(row["filing_number"], []).append(row)

    if not filings:
        return None

    # Re-registrations can produce several filings for one name — take the
    # most recently created one.
    def _creation(filing_rows: list[dict]) -> date:
        return _parse_iso_date(filing_rows[0].get("creationdate")) or date.min

    best_rows = max(filings.values(), key=_creation)
    first = best_rows[0]

    officers = []
    seen = set()
    for row in best_rows:
        name = _officer_name(row)
        party_type = (row.get("party_type") or "").strip()
        key = (party_type, name)
        if name and key not in seen:
            seen.add(key)
            officers.append({"party_type": party_type, "name": name})

    return {
        "entity_name": search_name,
        "matched_name": first.get("business_name", ""),
        "entity_number": first.get("filing_number", ""),
        "entity_type": first.get("typeofbusinessregistration", ""),
        "status": STATUS_PRESENT,
        "formation_date": _parse_iso_date(first.get("creationdate")),
        "registered_agent_name": "",
        "registered_agent_address": "",
        "office_address": _office_address(first),
        "officers": officers,
    }


def make_not_found_record(search_name: str) -> dict:
    """Negative-cache record for a name absent from the current dataset."""
    return {
        "entity_name": search_name,
        "matched_name": "",
        "entity_number": "",
        "entity_type": "",
        "status": STATUS_NOT_FOUND,
        "formation_date": None,
        "registered_agent_name": "",
        "registered_agent_address": "",
        "office_address": "",
        "officers": [],
    }
