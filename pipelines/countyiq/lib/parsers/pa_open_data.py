"""Parse PA Open Data Portal (SODA API) JSON responses.

Each SODA dataset returns a flat JSON array. Records are stored generically
in staging.pa_open_data as (dataset_id, record_id, data JSONB) with SCD2.
"""


# Fields expected in the "Registered Businesses" dataset (xvd7-5r2c).
# Used by schema drift check — not exhaustive, just the fields we rely on.
EXPECTED_BUSINESS_FIELDS = {
    "business_name",
    "filing_number",
    "shortcountyname",
    "typeofbusinessregistration",
}


def parse_soda_records(
    records: list[dict],
    dataset_id: str,
    record_id_field: str = ":id",
) -> list[dict]:
    """Convert raw SODA JSON records into staging.pa_open_data rows.

    Args:
        records: Raw JSON list from SODA API response.
        dataset_id: The Socrata dataset identifier (e.g. "xvd7-5r2c").
        record_id_field: Field name to use as record_id. SODA provides ":id"
            by default; some datasets may use a domain-specific key.

    Returns:
        List of dicts with keys: dataset_id, record_id, data.
        Records missing a record_id are skipped.
    """
    parsed = []
    for rec in records:
        rid = rec.get(record_id_field)
        if rid is None:
            continue
        parsed.append({
            "dataset_id": dataset_id,
            "record_id": str(rid),
            "data": rec,
        })
    return parsed
