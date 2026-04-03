"""Shared intelligence context module.

Provides reusable SQL query constants, formatter functions, and a hash helper
used across all intelligence pipeline passes (Pass 0 through Pass 4).

SQL constants use %(name)s-style parameterization for psycopg2.
Formatter functions accept psycopg2 RealDictCursor row dicts and return
clean, typed context dicts suitable for LLM prompt injection.
"""

import datetime
import hashlib
import json
from typing import Any


# =============================================================================
# SQL QUERY CONSTANTS
# =============================================================================

PARCEL_QUERY = """
    SELECT
        pidn,
        owner_full,
        propadr,
        aprtotal,
        acres,
        class,
        saledt,
        price,
        prev_owner,
        municipality,
        school_dis
    FROM staging.parcels
    WHERE pidn = %(pidn)s
      AND valid_to IS NULL
"""

TAX_CLAIMS_QUERY = """
    SELECT
        tax_year,
        authority_name,
        total,
        owner_name
    FROM staging.tax_claims
    WHERE pidn = %(pidn)s
      AND valid_to IS NULL
    ORDER BY tax_year
"""

PROCEEDINGS_FOR_PARCEL_QUERY = """
    SELECT
        pe.extraction_type,
        pe.applicant_name,
        pe.parcel_reference,
        pe.decision,
        pp.meeting_date,
        pp.body_name,
        pp.source_url,
        pe.supporting_text
    FROM staging.proceeding_extractions pe
    JOIN staging.public_proceedings pp ON pp.id = pe.proceeding_id
    WHERE pe.parcel_reference = %(pidn)s
      AND pp.valid_to IS NULL
    ORDER BY pp.meeting_date DESC
"""

PROCEEDINGS_FOR_ENTITY_QUERY = """
    SELECT
        pe.extraction_type,
        pe.applicant_name,
        pe.parcel_reference,
        pe.decision,
        pp.meeting_date,
        pp.body_name,
        pp.source_url,
        pe.supporting_text
    FROM staging.proceeding_extractions pe
    JOIN staging.public_proceedings pp ON pp.id = pe.proceeding_id
    WHERE pe.applicant_name = ANY(%(names)s)
      AND pp.valid_to IS NULL
    ORDER BY pp.meeting_date DESC
"""

NEIGHBORS_QUERY = """
    SELECT
        n.pidn,
        n.owner_full,
        n.aprtotal,
        n.acres,
        n.class,
        COALESCE(tc.total_owed, 0) AS total_owed,
        COALESCE(tc.years_delinquent, 0) AS years_delinquent
    FROM staging.parcels p
    JOIN staging.parcels n
        ON n.valid_to IS NULL
       AND n.geom IS NOT NULL
       AND p.pidn <> n.pidn
       AND ST_Touches(p.geom, n.geom)
    LEFT JOIN (
        SELECT
            pidn,
            SUM(total) AS total_owed,
            COUNT(DISTINCT tax_year) AS years_delinquent
        FROM staging.tax_claims
        WHERE valid_to IS NULL
        GROUP BY pidn
    ) tc ON tc.pidn = n.pidn
    WHERE p.pidn = %(pidn)s
      AND p.valid_to IS NULL
      AND p.geom IS NOT NULL
"""

CORPORATE_FOR_NAMES_QUERY = """
    SELECT
        entity_name,
        entity_number,
        status,
        formation_date,
        office_address,
        source_url
    FROM staging.corporate_entities
    WHERE entity_name = ANY(%(names)s)
      AND valid_to IS NULL
"""

ENTITY_GRAPH_QUERY = """
    SELECT
        entity_id,
        canonical_name,
        entity_type,
        linked_names,
        relationships,
        verification_status
    FROM public.entity_graph
    WHERE canonical_name = %(name)s
       OR %(name)s = ANY(linked_names)
    LIMIT 1
"""

PORTFOLIO_QUERY = """
    SELECT
        pidn,
        propadr,
        aprtotal,
        saledt,
        price
    FROM staging.parcels
    WHERE owner_full = ANY(%(names)s)
      AND valid_to IS NULL
    ORDER BY aprtotal DESC NULLS LAST
"""


# =============================================================================
# PRIVATE HELPERS
# =============================================================================

def _format_date(val: Any) -> str:
    """Convert a date or datetime to ISO-format string.

    Returns an empty string for None or any unrecognised value type.
    String values are returned as-is (pass-through).
    """
    if val is None:
        return ""
    if isinstance(val, (datetime.date, datetime.datetime)):
        return val.isoformat()
    # Already a string (e.g. "01-JAN-2023" from staging.parcels) — pass through
    return str(val)


def _str(val: Any) -> str:
    """Return val as a string, or '' for None."""
    if val is None:
        return ""
    return str(val)


def _num(val: Any) -> float | int:
    """Return val as a number, or 0 for None."""
    if val is None:
        return 0
    return val


# =============================================================================
# FORMATTER FUNCTIONS
# =============================================================================

def format_parcel_context(row: dict) -> dict:
    """Format a staging.parcels row dict into a clean context dict.

    Args:
        row: psycopg2 RealDictCursor row from PARCEL_QUERY.

    Returns:
        Dict with keys: pidn, owner, address, assessed_value, acres,
        property_class, sale_date, sale_price, previous_owner,
        municipality, school_district, source_url.
        None numeric values → 0. None string values → "".
    """
    return {
        "pidn": _str(row.get("pidn")),
        "owner": _str(row.get("owner_full")),
        "address": _str(row.get("propadr")),
        "assessed_value": _num(row.get("aprtotal")),
        "acres": _num(row.get("acres")),
        "property_class": _str(row.get("class")),
        "sale_date": _format_date(row.get("saledt")),
        "sale_price": _num(row.get("price")),
        "previous_owner": _str(row.get("prev_owner")),
        "municipality": _str(row.get("municipality")),
        "school_district": _str(row.get("school_dis")),
        "source_url": _str(row.get("source_url")),
    }


def format_tax_claims_context(rows: list[dict]) -> list[dict]:
    """Format a list of staging.tax_claims rows into clean context dicts.

    Args:
        rows: List of psycopg2 RealDictCursor rows from TAX_CLAIMS_QUERY.

    Returns:
        List of dicts with keys: year, authority, amount, owner.
    """
    return [
        {
            "year": row.get("tax_year"),
            "authority": _str(row.get("authority_name")),
            "amount": _num(row.get("total")),
            "owner": _str(row.get("owner_name")),
        }
        for row in rows
    ]


def format_entity_context(row: dict | None) -> dict:
    """Format a public.entity_graph row dict into a clean context dict.

    Args:
        row: psycopg2 RealDictCursor row from ENTITY_GRAPH_QUERY, or None.

    Returns:
        {"found": False} if row is None.
        Otherwise dict with keys: found, entity_id, canonical_name,
        entity_type, linked_names, relationships, verification_status.
    """
    if row is None:
        return {"found": False}
    return {
        "found": True,
        "entity_id": row.get("entity_id"),
        "canonical_name": _str(row.get("canonical_name")),
        "entity_type": _str(row.get("entity_type")),
        "linked_names": row.get("linked_names") or [],
        "relationships": row.get("relationships") or {},
        "verification_status": _str(row.get("verification_status")),
    }


def format_portfolio_context(rows: list[dict]) -> list[dict]:
    """Format a list of staging.parcels rows (portfolio) into context dicts.

    Args:
        rows: List of psycopg2 RealDictCursor rows from PORTFOLIO_QUERY.

    Returns:
        List of dicts with keys: pidn, address, assessed_value,
        sale_date, sale_price.
    """
    return [
        {
            "pidn": _str(row.get("pidn")),
            "address": _str(row.get("propadr")),
            "assessed_value": _num(row.get("aprtotal")),
            "sale_date": _format_date(row.get("saledt")),
            "sale_price": _num(row.get("price")),
        }
        for row in rows
    ]


def format_proceedings_context(rows: list[dict]) -> list[dict]:
    """Format proceeding extraction rows into clean context dicts.

    Args:
        rows: List of psycopg2 RealDictCursor rows from
              PROCEEDINGS_FOR_PARCEL_QUERY or PROCEEDINGS_FOR_ENTITY_QUERY.

    Returns:
        List of dicts with keys: type, applicant, parcel, decision,
        meeting_date, body, source_url, supporting_text.
    """
    return [
        {
            "type": _str(row.get("extraction_type")),
            "applicant": _str(row.get("applicant_name")),
            "parcel": _str(row.get("parcel_reference")),
            "decision": _str(row.get("decision")),
            "meeting_date": _format_date(row.get("meeting_date")),
            "body": _str(row.get("body_name")),
            "source_url": _str(row.get("source_url")),
            "supporting_text": _str(row.get("supporting_text")),
        }
        for row in rows
    ]


def format_neighbors_context(rows: list[dict]) -> list[dict]:
    """Format adjacent parcel rows into clean context dicts.

    Args:
        rows: List of psycopg2 RealDictCursor rows from NEIGHBORS_QUERY.

    Returns:
        List of dicts with keys: pidn, owner, assessed_value, acres,
        property_class, total_owed, years_delinquent.
    """
    return [
        {
            "pidn": _str(row.get("pidn")),
            "owner": _str(row.get("owner_full")),
            "assessed_value": _num(row.get("aprtotal")),
            "acres": _num(row.get("acres")),
            "property_class": _str(row.get("class")),
            "total_owed": _num(row.get("total_owed")),
            "years_delinquent": _num(row.get("years_delinquent")),
        }
        for row in rows
    ]


def format_corporate_context(rows: list[dict]) -> list[dict]:
    """Format staging.corporate_entities rows into clean context dicts.

    Args:
        rows: List of psycopg2 RealDictCursor rows from CORPORATE_FOR_NAMES_QUERY.

    Returns:
        List of dicts with keys: entity_name, entity_number, status,
        formation_date, office_address, source_url.
    """
    return [
        {
            "entity_name": _str(row.get("entity_name")),
            "entity_number": _str(row.get("entity_number")),
            "status": _str(row.get("status")),
            "formation_date": _format_date(row.get("formation_date")),
            "office_address": _str(row.get("office_address")),
            "source_url": _str(row.get("source_url")),
        }
        for row in rows
    ]


# =============================================================================
# HASHING
# =============================================================================

def compute_input_hash(data: dict) -> str:
    """Compute a stable SHA-256 hex digest of a dict.

    Serializes the dict to JSON with sorted keys and default=str so that
    date/datetime values are included without raising TypeError. The same
    input always produces the same 64-character lowercase hex string.

    Args:
        data: Arbitrary dict (must be JSON-serializable with default=str).

    Returns:
        64-character lowercase hex string (SHA-256 digest).
    """
    serialized = json.dumps(data, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()
