"""Parse York County Delinquent Tax Claim Listing PDF text.

The PDF is a report-style layout (not tabular HTML). pdfplumber's
extract_text() returns clean text that this module parses line-by-line
using a state machine.

Two entry points:
  - tax_claim_id_to_pidn() — convert parcel ID to (pidn, unit_suffix)
  - parse_tax_claims_text() — parse full extracted text into records
"""

import re
from datetime import date, datetime


def tax_claim_id_to_pidn(parcel_id: str) -> tuple[str, str]:
    """Convert tax claim parcel ID to (pidn, unit_suffix).

    Format: DD-BBB-MM-PPPP.SS-UUUUU
    PIDN:   DD + BBB + MM + PPPP + SS  (13 chars)

    Examples:
        '01-001-01-0002.00-00000' → ('0100101000200', '00000')
        '20-000-NC-0073.A0-00000' → ('20000NC0073A0', '00000')
        '01-001-01-0023.00-C0001' → ('0100101002300', 'C0001')
    """
    m = re.match(r"(\d{2})-(\d{3})-(\w{2})-(\d{4})\.(\w{2})-(\w{5})", parcel_id)
    if not m:
        return ("", "")
    district, block, map_code, parcel, sub, unit = m.groups()
    pidn = district + block + map_code + parcel + sub
    return (pidn, unit)


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_REPORT_DATE = re.compile(r"AS OF BUSINESS DATE\s+(\d{2}/\d{2}/\d{4})")
_DISTRICT = re.compile(r"TAX DIST CODE/NAME\s*:\s*(\d+)\s*/\s*(.+)")

# Parcel ID + first data row on same line
_PARCEL_LINE = re.compile(
    r"^(\d{2}-\d{3}-\w{2}-\d{4}\.\w{2}-\w{5})\s+"
    r"(\d{4})\s+"
    r"(COUNTY|SCHOOL|MUNICIPAL)\s+"
    r"([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+"
    r"([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+"
    r"([\d,.-]+)"
)

# New year for same property (year + authority + 9 numbers)
_YEAR_AUTH_LINE = re.compile(
    r"^\s*(\d{4})\s+"
    r"(COUNTY|SCHOOL|MUNICIPAL)\s+"
    r"([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+"
    r"([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+"
    r"([\d,.-]+)"
)

# Continuation authority row (no year, just authority + 9 numbers)
_AUTH_ONLY_LINE = re.compile(
    r"^\s*(COUNTY|SCHOOL|MUNICIPAL)\s+"
    r"([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+"
    r"([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+"
    r"([\d,.-]+)"
)

# Owner/address line with embedded authority data (e.g. "OWNER NAME  SCHOOL  num num ...")
_TEXT_WITH_AUTH = re.compile(
    r"^(.+?)\s+(COUNTY|SCHOOL|MUNICIPAL)\s+"
    r"([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+"
    r"([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+"
    r"([\d,.-]+)"
)

# Lines to skip (totals, headers, blanks)
_SKIP = re.compile(
    r"^\s*\*+TOTAL:|^TOTAL FOR DISTRICT|^TOTAL PARCEL|"
    r"^YORK COUNTY|^PARCEL ID|^OWNER NAME|^---+|"
    r"^\s*$|^GRAND TOTAL|^PARID CNT|^\s+PRIM\s|"
    r"^MAR\s|^[A-Z][a-z]{2}\s+\d|^07:|^\s+PAGE:"
)


def _parse_amount(text: str) -> float:
    """Parse currency: '1,508.82' → 1508.82, '-2,039.46' → -2039.46"""
    return float(text.replace(",", ""))


def parse_tax_claims_text(text: str) -> list[dict]:
    """Parse extracted PDF text into tax claim records.

    Returns one dict per property-year-authority combination with keys:
        pidn, parcel_id_raw, unit_suffix, tax_district_code,
        tax_district_name, owner_name, property_address, tax_year,
        authority_name, tax_owed, penalty_owed, interest_owed, fees_owed,
        tax_paid, penalty_paid, interest_paid, fees_paid, total, report_date
    """
    records: list[dict] = []
    report_date: date | None = None
    district_code = ""
    district_name = ""

    # Current property state
    current_parcel_id = ""
    current_pidn = ""
    current_unit = ""
    current_year = 0
    owner_line_pending = False
    address_line_pending = False
    current_owner = ""
    current_address = ""

    for line in text.split("\n"):
        # Extract report date (once)
        if report_date is None:
            m = _REPORT_DATE.search(line)
            if m:
                report_date = datetime.strptime(m.group(1), "%m/%d/%Y").date()
                continue

        # Skip non-data lines; reset parcel state on district totals
        if _SKIP.match(line):
            owner_line_pending = False
            address_line_pending = False
            # District totals are followed by orphan COUNTY/SCHOOL/MUNICIPAL
            # lines that look like authority rows. Clear parcel state so they
            # don't attach to the last property.
            if "TOTAL FOR DISTRICT" in line or "TOTAL PARCEL" in line or "GRAND TOTAL" in line:
                current_parcel_id = ""
            continue

        # District header
        m = _DISTRICT.match(line)
        if m:
            district_code = m.group(1).strip()
            district_name = m.group(2).strip()
            owner_line_pending = False
            address_line_pending = False
            continue

        # New property (parcel ID + first data row)
        m = _PARCEL_LINE.match(line)
        if m:
            current_parcel_id = m.group(1)
            current_pidn, current_unit = tax_claim_id_to_pidn(current_parcel_id)
            current_year = int(m.group(2))
            current_owner = ""
            current_address = ""
            owner_line_pending = True
            address_line_pending = False
            records.append(_make_record(
                m, 3, current_parcel_id, current_pidn, current_unit,
                current_year, district_code, district_name,
                "", "", report_date,
            ))
            continue

        # Owner name line — may also contain SCHOOL authority data
        if owner_line_pending:
            m_ta = _TEXT_WITH_AUTH.match(line)
            if m_ta:
                current_owner = m_ta.group(1).strip()
                owner_line_pending = False
                address_line_pending = True
                # Backfill owner on prior records for this parcel
                for r in reversed(records):
                    if r["parcel_id_raw"] != current_parcel_id:
                        break
                    r["owner_name"] = current_owner
                # Also capture the authority data from this line
                records.append(_make_record(
                    m_ta, 2, current_parcel_id, current_pidn, current_unit,
                    current_year, district_code, district_name,
                    current_owner, "", report_date,
                ))
                continue
            # Pure text owner line (no embedded authority)
            if not _AUTH_ONLY_LINE.match(line) and not _YEAR_AUTH_LINE.match(line):
                current_owner = line.strip()
                owner_line_pending = False
                address_line_pending = True
                for r in reversed(records):
                    if r["parcel_id_raw"] != current_parcel_id:
                        break
                    r["owner_name"] = current_owner
                continue

        # Address line — may also contain MUNICIPAL authority data
        if address_line_pending:
            m_ta = _TEXT_WITH_AUTH.match(line)
            if m_ta:
                current_address = m_ta.group(1).strip()
                address_line_pending = False
                # Backfill address on all records for this parcel
                for r in reversed(records):
                    if r["parcel_id_raw"] != current_parcel_id:
                        break
                    r["property_address"] = current_address
                # Capture the authority data
                records.append(_make_record(
                    m_ta, 2, current_parcel_id, current_pidn, current_unit,
                    current_year, district_code, district_name,
                    current_owner, current_address, report_date,
                ))
                continue
            # Pure text address line
            if not _AUTH_ONLY_LINE.match(line) and not _YEAR_AUTH_LINE.match(line):
                current_address = line.strip()
                address_line_pending = False
                for r in reversed(records):
                    if r["parcel_id_raw"] != current_parcel_id:
                        break
                    r["property_address"] = current_address
                continue

        # Year + authority continuation (new year for same property)
        m = _YEAR_AUTH_LINE.match(line)
        if m and current_parcel_id:
            current_year = int(m.group(1))
            records.append(_make_record(
                m, 2, current_parcel_id, current_pidn, current_unit,
                current_year, district_code, district_name,
                current_owner, current_address, report_date,
            ))
            continue

        # Authority-only continuation (same year, next authority)
        m = _AUTH_ONLY_LINE.match(line)
        if m and current_parcel_id:
            records.append(_make_record(
                m, 1, current_parcel_id, current_pidn, current_unit,
                current_year, district_code, district_name,
                current_owner, current_address, report_date,
            ))
            continue

    # Deduplicate by composite key — keep the record with the higher total
    # (a few parcels appear twice in the report due to page breaks or
    # cross-district entries; ~0.02% of records)
    seen: dict[tuple, int] = {}
    for i, r in enumerate(records):
        key = (r["pidn"], r["unit_suffix"], r["tax_year"], r["authority_name"])
        if key in seen:
            prev_idx = seen[key]
            if abs(r["total"]) > abs(records[prev_idx]["total"]):
                seen[key] = i
        else:
            seen[key] = i
    return [records[i] for i in sorted(seen.values())]


def _make_record(
    m, auth_group: int,
    parcel_id: str, pidn: str, unit: str, year: int,
    dist_code: str, dist_name: str,
    owner: str, address: str, report_date: date | None,
) -> dict:
    """Build a record dict from a regex match."""
    g = auth_group
    return {
        "pidn": pidn,
        "parcel_id_raw": parcel_id,
        "unit_suffix": unit,
        "tax_district_code": dist_code,
        "tax_district_name": dist_name,
        "owner_name": owner,
        "property_address": address,
        "tax_year": year,
        "authority_name": m.group(g),
        "tax_owed": _parse_amount(m.group(g + 1)),
        "penalty_owed": _parse_amount(m.group(g + 2)),
        "interest_owed": _parse_amount(m.group(g + 3)),
        "fees_owed": _parse_amount(m.group(g + 4)),
        "tax_paid": _parse_amount(m.group(g + 5)),
        "penalty_paid": _parse_amount(m.group(g + 6)),
        "interest_paid": _parse_amount(m.group(g + 7)),
        "fees_paid": _parse_amount(m.group(g + 8)),
        "total": _parse_amount(m.group(g + 9)),
        "report_date": report_date,
    }
