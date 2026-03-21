"""Parse PLCB liquor license CSV and filter to a specific county."""

import csv
from io import StringIO

EXPECTED_HEADERS = {
    "LID",
    "License Number",
    "License Type",
    "Status",
    "Licensee",
    "Premises",
    "Premises Address",
    "Premises Mailing Address",
    "Premises Owner",
    "Premises Manager",
    "County",
    "Municipality",
    "Last Issue Date",
    "Expiration Date",
}

# CSV header → staging column name
COLUMN_MAP = {
    "LID": "lid",
    "License Number": "license_number",
    "License Type": "license_type",
    "Status": "status",
    "Licensee": "licensee",
    "Premises": "premises_name",
    "Premises Address": "premises_address",
    "Premises Mailing Address": "premises_mailing_address",
    "Premises Owner": "premises_owner",
    "Premises Manager": "premises_manager",
    "Municipality": "municipality",
    "Last Issue Date": "last_issue_date",
    "Expiration Date": "expiration_date",
}


def parse_plcb_csv(csv_text: str, county_filter: str = "York County") -> list[dict]:
    """Parse PLCB CSV text and return records for a specific county.

    Args:
        csv_text: Raw CSV string (full statewide file).
        county_filter: Value to match in the "County" CSV column.

    Returns:
        List of dicts with staging column names, filtered to county_filter.
    """
    reader = csv.DictReader(StringIO(csv_text.lstrip("\ufeff")))
    by_lid: dict[str, dict] = {}

    for row in reader:
        if row.get("County", "").strip() != county_filter:
            continue

        record = {}
        for csv_col, db_col in COLUMN_MAP.items():
            val = row.get(csv_col, "").strip()
            record[db_col] = val if val else None

        # Deduplicate by LID — PLCB CSV has multiple rows per LID
        # (e.g. Special Occasion Permits with different date ranges).
        # Keep the last occurrence (most recent in file order).
        lid = record.get("lid")
        if lid:
            by_lid[lid] = record

    return list(by_lid.values())
