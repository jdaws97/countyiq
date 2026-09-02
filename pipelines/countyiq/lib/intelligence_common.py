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
from decimal import Decimal

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
    ORDER BY tax_year, authority_name, total
"""

PROCEEDINGS_FOR_PARCEL_QUERY = """
    SELECT
        pe.id AS extraction_id,
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
    WHERE pp.valid_to IS NULL
      AND LEFT(pe.extraction_type, 1) <> '_'
      AND (
          -- Match by canonical PIDN even when the minutes contain punctuation.
          REGEXP_REPLACE(pe.parcel_reference, '[^0-9]', '', 'g') = %(pidn)s
          -- Address matches are valid only inside the proceeding municipality.
          OR EXISTS (
              SELECT 1
              FROM staging.parcels parcel
              WHERE parcel.pidn = %(pidn)s
                AND parcel.valid_to IS NULL
                AND parcel.propadr IS NOT NULL
                AND public.normalize_street_address(parcel.propadr)
                    = public.normalize_street_address(pe.parcel_reference)
                AND EXISTS (
                    SELECT 1
                    FROM meta.municipality_source_rights msr
                    WHERE msr.body_name = pp.body_name
                      AND msr.municipality_name = parcel.municipality
                      AND msr.derived_product_allowed = TRUE
                )
          )
      )
    ORDER BY pp.meeting_date DESC, pe.id
"""

PROCEEDINGS_FOR_ENTITY_QUERY = """
    SELECT
        pe.id AS extraction_id,
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
    ORDER BY pp.meeting_date DESC, pe.id
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
    ORDER BY n.pidn
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
    ORDER BY entity_name, entity_number
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
    ORDER BY
        (canonical_name = %(name)s) DESC,  -- prefer exact canonical match
        entity_id
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
    ORDER BY aprtotal DESC NULLS LAST, pidn
"""


# =============================================================================
# PRIVATE HELPERS
# =============================================================================

def _format_date(val: object) -> str:
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


def _str(val: object) -> str:
    """Return val as a string, or '' for None."""
    if val is None:
        return ""
    return str(val)


def _num(val: object) -> float | int:
    """Return val as a number, or 0 for None."""
    if val is None:
        return 0
    if isinstance(val, bool):
        return int(val)
    if isinstance(val, (int, float)):
        return val
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, str):
        try:
            parsed = float(val)
        except ValueError:
            return 0
        return int(parsed) if parsed.is_integer() else parsed
    return 0


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


def _normalize_relationships(raw) -> dict:
    """Normalize relationships from the entity_graph JSONB column.

    Pass 1 stores relationships as a **list of objects**:
        [{"related_entity": "...", "relationship_type": "...", "evidence": "..."}]

    But downstream consumers (Pass 2, Pass 3) iterate with .items() expecting
    a **dict** keyed by relationship_type:
        {"controls": ["Entity A"], "officer_of": ["Entity B", "Entity C"]}

    This function bridges the gap so both shapes work.
    """
    if not raw:
        return {}
    # Already a dict (legacy data or test fixtures) — pass through
    if isinstance(raw, dict):
        return raw
    # List of objects (production Pass 1 output) — group by relationship_type
    if isinstance(raw, list):
        grouped: dict[str, list[str]] = {}
        for item in raw:
            if isinstance(item, dict):
                rel_type = item.get("relationship_type", "unknown")
                related = item.get("related_entity", "")
                if related:
                    grouped.setdefault(rel_type, []).append(related)
        return grouped
    return {}


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
        "relationships": _normalize_relationships(row.get("relationships")),
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


def fetch_prior_pass_hashes(database, pass_number: int) -> dict[str, str]:
    """Fetch all completed input hashes for a pass in one query.

    Replaces the per-item ``SELECT input_hash`` the pass loops used to run —
    on a full weekly run that was thousands of extra round trips. Keys are
    whatever the pass stores in ``pidn`` (PIDN, cluster key, narrative key).

    Args:
        database: DatabaseResource (anything with an ``execute`` method).
        pass_number: The pass whose 'complete' hashes to load.

    Returns:
        Dict mapping key -> input_hash for rows with status='complete'.
    """
    rows = database.execute(
        """
        SELECT pidn, input_hash
        FROM meta.intelligence_passes
        WHERE pass_number = %(pass_number)s
          AND status = 'complete'
        """,
        {"pass_number": pass_number},
    ) or []
    hashes: dict[str, str] = {}
    for row in rows:
        if isinstance(row, dict):
            key, value = row.get("pidn"), row.get("input_hash")
        else:
            key, value = row[0], row[1]
        if key is not None:
            hashes[key] = value
    return hashes


def fetch_reusable_pass_hashes(
    database,
    *,
    pass_number: int,
) -> dict[str, str]:
    """Return hashes whose latest accepted output is completely projected.

    A bare completion-status row is not enough: a projection may have been
    retracted by a migration or cleanup. Conversely, a worker may have
    committed the projection and crashed before updating the status row. The
    live projection is therefore the primary completion proof.

    Pass 1 may legitimately accept an all-abstain partition with no projection;
    that case also requires the matching completion-status write.
    """

    if pass_number == 1:
        output_kind = "entity_verification"
        projection_table = "public.entity_graph"
        projection_clause = """
            (
                jsonb_array_length(
                    COALESCE(latest.payload->'entities', '[]'::jsonb)
                ) > 0
                AND COALESCE(projected.projection_count, 0) =
                    jsonb_array_length(
                        COALESCE(latest.payload->'entities', '[]'::jsonb)
                    )
            )
            OR (
                jsonb_array_length(
                    COALESCE(latest.payload->'entities', '[]'::jsonb)
                ) = 0
                AND EXISTS (
                    SELECT 1
                    FROM meta.intelligence_passes completed
                    WHERE completed.pidn = latest.subject_key
                      AND completed.pass_number = %(pass_number)s
                      AND completed.status = 'complete'
                      AND completed.input_hash = latest.input_hash
                )
            )
        """
    elif pass_number == 2:
        output_kind = "signal_validation"
        projection_table = "public.evidence"
        projection_clause = """
            jsonb_array_length(
                COALESCE(latest.payload->'validations', '[]'::jsonb)
            ) > 0
            AND COALESCE(projected.projection_count, 0) =
                jsonb_array_length(
                    COALESCE(latest.payload->'validations', '[]'::jsonb)
                )
        """
    else:
        raise ValueError(
            "reusable projection hashes are defined only for Passes 1 and 2"
        )

    rows = database.execute(
        f"""
        WITH latest AS (
            SELECT DISTINCT ON (subject_key)
                subject_key, input_hash, inference_id, payload
            FROM meta.intelligence_inference_history
            WHERE pass_number = %(pass_number)s
              AND output_kind = %(output_kind)s
              AND disposition = 'accepted'
            ORDER BY subject_key, inference_id DESC
        ),
        projected AS (
            SELECT active_inference_id, COUNT(*) AS projection_count
            FROM {projection_table}
            WHERE active_inference_id IS NOT NULL
            GROUP BY active_inference_id
        )
        SELECT latest.subject_key AS pidn, latest.input_hash
        FROM latest
        LEFT JOIN projected
          ON projected.active_inference_id = latest.inference_id
        WHERE {projection_clause}
        """,
        {"pass_number": pass_number, "output_kind": output_kind},
    ) or []
    hashes: dict[str, str] = {}
    for row in rows:
        if isinstance(row, dict):
            key, value = row.get("pidn"), row.get("input_hash")
        else:
            key, value = row[0], row[1]
        if key is not None:
            hashes[str(key)] = value
    return hashes


def fetch_prior_pass_attempts(database, pass_number: int) -> dict[str, object]:
    """Fetch last-attempt timestamps used to rotate capped work fairly."""
    rows = database.execute(
        """
        SELECT pidn, last_run_at
        FROM meta.intelligence_passes
        WHERE pass_number = %(pass_number)s
        """,
        {"pass_number": pass_number},
    ) or []
    attempts: dict[str, object] = {}
    for row in rows:
        if isinstance(row, dict):
            key, value = row.get("pidn"), row.get("last_run_at")
        else:
            key, value = row[0], row[1]
        if key is not None and value is not None:
            attempts[str(key)] = value
    return attempts


def pass_attempt_priority(
    subject_key: str,
    prior_attempts: dict[str, object],
) -> tuple[int, str, str]:
    """Sort never-attempted work first, then least-recently attempted work."""
    last_attempt = prior_attempts.get(subject_key)
    if last_attempt is None:
        return (0, "", subject_key)
    serialized = (
        last_attempt.isoformat()
        if hasattr(last_attempt, "isoformat")
        else str(last_attempt)
    )
    return (1, serialized, subject_key)
