"""Unified search — pg_trgm fuzzy match + LLM-powered natural language fallback."""

from fastapi import APIRouter, Query

from api.lib.database import get_cursor
from api.lib.llm_search import parse_query_with_llm, ALLOWED_TABLES

router = APIRouter(tags=["search"])


@router.get("")
def search(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(default=20, le=100),
) -> dict:
    """Search across all sources. Uses pg_trgm for name/address matching,
    falls back to LLM intent parsing for natural language queries."""
    search_term = q.strip()

    # Step 1: Try pg_trgm fuzzy matching
    trgm_results = _trgm_search(search_term, limit)

    # Step 2: If pg_trgm found good results (score > 0.3), return them
    if trgm_results and trgm_results[0].get("score", 0) > 0.3:
        return {"mode": "fuzzy", "results": trgm_results}

    # Step 3: Try LLM intent parsing for natural language queries
    llm_intent = parse_query_with_llm(search_term)

    if llm_intent and llm_intent.get("intent") == "redirect":
        return {
            "mode": "redirect",
            "redirect_path": llm_intent.get("redirect_path", "/"),
            "description": llm_intent.get("description", ""),
            "results": [],
        }

    if llm_intent and llm_intent.get("intent") == "query":
        llm_results = _execute_llm_query(llm_intent, limit)
        if llm_results is not None:
            return {
                "mode": "smart",
                "description": llm_intent.get("description", ""),
                "results": llm_results,
            }

    # Step 4: Return whatever pg_trgm found (even if low quality)
    return {"mode": "fuzzy", "results": trgm_results}


def _trgm_search(search_term: str, limit: int) -> list[dict]:
    """Standard pg_trgm fuzzy matching across all sources."""
    with get_cursor() as cur:
        # Parcel owners
        cur.execute("""
            SELECT DISTINCT ON (owner_full)
                'parcel' AS result_type,
                owner_full AS title,
                pidn || ' · ' || COALESCE(propadr, '') || ' · ' || COALESCE(municipality, '') AS subtitle,
                NULL::float AS lat, NULL::float AS lng,
                similarity(owner_full, %(q)s) AS score,
                pidn
            FROM staging.parcels
            WHERE valid_to IS NULL AND owner_full %% %(q)s
            ORDER BY owner_full, similarity(owner_full, %(q)s) DESC
            LIMIT %(limit)s
        """, {"q": search_term, "limit": limit})
        parcel_owners = cur.fetchall()

        # Address points
        cur.execute("""
            SELECT
                'address' AS result_type,
                CONCAT_WS(' ', add_number, street_name, st_pos_typ) AS title,
                inc_muni AS subtitle,
                lat, long AS lng,
                similarity(CONCAT_WS(' ', add_number, street_name, st_pos_typ), %(q)s) AS score
            FROM staging.address_points
            WHERE valid_to IS NULL
              AND CONCAT_WS(' ', add_number, street_name, st_pos_typ) %% %(q)s
            ORDER BY score DESC
            LIMIT %(limit)s
        """, {"q": search_term, "limit": limit})
        addresses = cur.fetchall()

        # Tax claim owners
        cur.execute("""
            SELECT
                'tax_claim' AS result_type,
                owner_name AS title,
                tax_district_name || ' · ' || COUNT(DISTINCT pidn) || ' parcels · $' ||
                    TRIM(TO_CHAR(SUM(CASE WHEN total > 0 THEN total ELSE 0 END), 'FM999,999,999')) AS subtitle,
                NULL::float AS lat, NULL::float AS lng,
                similarity(owner_name, %(q)s) AS score
            FROM staging.tax_claims
            WHERE valid_to IS NULL AND owner_name %% %(q)s
            GROUP BY owner_name, tax_district_name
            ORDER BY score DESC
            LIMIT %(limit)s
        """, {"q": search_term, "limit": limit})
        tax_owners = cur.fetchall()

        # PLCB licensees
        cur.execute("""
            SELECT DISTINCT ON (COALESCE(premises_name, licensee))
                'license' AS result_type,
                COALESCE(premises_name, licensee) AS title,
                license_type || ' · ' || municipality AS subtitle,
                NULL::float AS lat, NULL::float AS lng,
                similarity(COALESCE(premises_name, licensee), %(q)s) AS score
            FROM staging.plcb_licenses
            WHERE valid_to IS NULL AND UPPER(status) = 'ACTIVE'
              AND (premises_name %% %(q)s OR licensee %% %(q)s)
            ORDER BY COALESCE(premises_name, licensee), score DESC
            LIMIT %(limit)s
        """, {"q": search_term, "limit": limit})
        licenses = cur.fetchall()

    all_results = [dict(r) for r in parcel_owners + addresses + tax_owners + licenses]
    all_results.sort(key=lambda r: r["score"], reverse=True)
    return all_results[:limit]


def _execute_llm_query(intent: dict, limit: int) -> list[dict] | None:
    """Execute a structured query from LLM intent parsing."""
    table_key = intent.get("table", "")
    fqn = ALLOWED_TABLES.get(table_key)
    if not fqn:
        return None

    sql_where = intent.get("sql_where", "valid_to IS NULL")
    sql_order = intent.get("sql_order", "")
    sql_limit = min(intent.get("sql_limit", limit), limit)

    # Safety: ensure valid_to IS NULL is always present
    if "valid_to IS NULL" not in sql_where:
        sql_where = f"valid_to IS NULL AND ({sql_where})"

    query = f"SELECT * FROM {fqn} WHERE {sql_where}"
    if sql_order:
        query += f" ORDER BY {sql_order}"
    query += f" LIMIT {sql_limit}"

    try:
        with get_cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
        return [_clean_row(dict(r)) for r in rows]
    except Exception:
        return None


def _clean_row(row: dict) -> dict:
    """Clean a database row for JSON serialization."""
    # Remove geometry and SCD columns
    for key in ("geom", "valid_from", "valid_to"):
        row.pop(key, None)
    # Convert Decimal to float
    for key, val in row.items():
        if hasattr(val, "as_tuple"):  # Decimal
            row[key] = float(val)
    return row
