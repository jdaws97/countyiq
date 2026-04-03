"""Parser for PA Department of State business entity API responses.

Parses JSON from the PA DOS business search REST API into records
matching the staging.corporate_entities schema.

Search API: POST https://file.dos.pa.gov/api/Records/businesssearch
Detail API: GET  https://file.dos.pa.gov/api/FilingDetail/business/{id}/false

NOTE: The field names used here are best-guess approximations based on
the site's UI. They will be confirmed and adjusted during Playwright
integration testing when we intercept the actual API responses.
"""

from datetime import date, datetime

BASE_URL = "https://file.dos.pa.gov/search/business"


def _parse_date(date_str: str | None) -> date | None:
    """Parse MM/DD/YYYY date string to a date object."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%m/%d/%Y").date()
    except (ValueError, TypeError):
        return None


def _build_source_url(entity_number: str) -> str:
    """Build a source URL for the entity on the PA DOS site."""
    return f"{BASE_URL}#{entity_number}"


def parse_search_results(api_response: dict) -> list[dict]:
    """Parse the PA DOS business search API JSON response.

    Args:
        api_response: The JSON response dict from the search API.
            Expected shape: {"results": [{"entityName": ..., ...}, ...]}

    Returns:
        List of dicts matching staging.corporate_entities columns.
    """
    results = api_response.get("results")
    if not results:
        return []

    records = []
    for item in results:
        entity_number = item.get("entityNumber", "")
        records.append({
            "entity_name": item.get("entityName", ""),
            "entity_number": entity_number,
            "entity_type": item.get("entityType", ""),
            "status": item.get("status", ""),
            "formation_date": _parse_date(item.get("initialFilingDate")),
            "registered_agent_name": "",
            "registered_agent_address": "",
            "office_address": item.get("address", ""),
            "officers": [],
            "source_url": _build_source_url(entity_number),
        })

    return records


def parse_filing_detail(api_response: dict, entity_name: str) -> dict:
    """Parse the PA DOS filing detail API JSON response.

    Args:
        api_response: The JSON response dict from the detail API.
        entity_name: The entity name (used as fallback if not in response).

    Returns:
        Dict matching staging.corporate_entities columns, with full
        registered-office address assembled from the detail fields.
    """
    entity_number = api_response.get("entityNumber", "")

    # Assemble registered office address from structured fields
    reg_office = api_response.get("registeredOffice") or {}
    office_parts = [
        p for p in [
            reg_office.get("addressLine1", ""),
            reg_office.get("addressLine2", ""),
            reg_office.get("city", ""),
            reg_office.get("state", ""),
            reg_office.get("zipCode", ""),
        ]
        if p
    ]
    office_address = ", ".join(office_parts) if office_parts else ""

    # Use filingType (detail view) over entityType (search view)
    entity_type = (
        api_response.get("filingType")
        or api_response.get("entityType")
        or ""
    )

    return {
        "entity_name": api_response.get("entityName", entity_name),
        "entity_number": entity_number,
        "entity_type": entity_type,
        "status": api_response.get("status", ""),
        "formation_date": _parse_date(api_response.get("initialFilingDate")),
        "registered_agent_name": "",
        "registered_agent_address": "",
        "office_address": office_address,
        "officers": [],
        "source_url": _build_source_url(entity_number),
    }
