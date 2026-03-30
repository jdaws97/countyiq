"""LLM-first unified search across all data sources."""

from fastapi import APIRouter, Query

from api.lib.database import get_cursor
from api.lib.llm_search import parse_query_with_llm, ALLOWED_TABLES

router = APIRouter(tags=["search"])


@router.get("")
def search(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(default=20, le=100),
) -> dict:
    """Smart search — fast-path for name/address lookups, LLM for natural language."""
    search_term = q.strip()

    # Fast path: if it looks like a name (2-3 short words, no special keywords),
    # skip the LLM entirely and go straight to pg_trgm
    if _is_name_lookup(search_term):
        trgm_results = _trgm_search_with_reversal(search_term, limit)
        return {"mode": "fuzzy", "results": trgm_results}

    # Otherwise, use LLM for intent classification
    llm_intent = parse_query_with_llm(search_term)

    if llm_intent:
        intent = llm_intent.get("intent")
        description = llm_intent.get("description", "")

        if intent == "redirect":
            return {
                "mode": "redirect",
                "redirect_path": llm_intent.get("redirect_path", "/"),
                "description": description,
                "results": [],
            }

        if intent == "query":
            llm_results = _execute_llm_query(llm_intent, limit)
            if llm_results:
                return {
                    "mode": "smart",
                    "description": description,
                    "results": llm_results,
                }

        if intent == "lookup":
            cleaned = llm_intent.get("search_term", search_term)
            trgm_results = _trgm_search_with_reversal(cleaned, limit)
            return {
                "mode": "fuzzy",
                "description": description,
                "results": trgm_results,
            }

    # Step 2: Fallback to pg_trgm if LLM unavailable or failed
    trgm_results = _trgm_search_with_reversal(search_term, limit)
    return {"mode": "fuzzy", "results": trgm_results}


NL_WORDS = {
    "show", "find", "list", "what", "who", "where", "which", "how",
    "oldest", "newest", "most", "least", "biggest", "cheapest", "expensive",
    "vacant", "delinquent", "flood", "commercial", "residential", "industrial",
    "restaurants", "restaurant", "breweries", "brewery", "wineries", "bars",
    "properties", "parcels", "owners", "sales", "sold", "near", "recent",
    "top", "total", "average", "all", "zoning", "zoned",
}


def _is_name_lookup(query: str) -> bool:
    """Fast check: is this a person/business name vs a natural language query?

    Name lookups: "Brian Daws", "KEYSTONE REALTY", "123 Main St"
    NOT name lookups: "breweries in york", "vacant delinquent parcels", "oldest tax"
    """
    words = query.lower().split()

    # Single word — could be a name or a keyword
    if len(words) == 1:
        return words[0] not in NL_WORDS

    # 5+ words is almost certainly natural language
    if len(words) >= 5:
        return False

    # Contains a zip code (5 digits)
    if any(w.isdigit() and len(w) == 5 for w in words):
        return False

    # Any NL keyword present → not a name
    for w in words:
        if w in NL_WORDS:
            return False

    # "X in Y" pattern → natural language
    if "in" in words[1:]:
        return False

    # 2-3 words with no keywords → probably a name
    return True


def _trgm_search_with_reversal(search_term: str, limit: int) -> list[dict]:
    """Run pg_trgm search with automatic name reversal (FIRST LAST → LAST FIRST)."""
    results = _trgm_search(search_term, limit)

    # Also try reversed name order
    parts = search_term.strip().split()
    if len(parts) >= 2:
        reversed_name = parts[-1] + " " + " ".join(parts[:-1])
        reversed_results = _trgm_search(reversed_name, limit)

        # Merge, deduplicate by title, keep highest score
        seen: dict[str, dict] = {}
        for r in results + reversed_results:
            key = r.get("title", "")
            if key not in seen or (r.get("score") or 0) > (seen[key].get("score") or 0):
                seen[key] = r
        results = sorted(seen.values(), key=lambda x: x.get("score", 0), reverse=True)[:limit]

    return results


def _trgm_search(search_term: str, limit: int) -> list[dict]:
    """Standard pg_trgm fuzzy matching across all sources."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT result_type, title, subtitle, lat, lng, score, pidn FROM (
                SELECT DISTINCT ON (owner_full)
                    'parcel' AS result_type,
                    owner_full AS title,
                    pidn || ' · ' || COALESCE(propadr, '') AS subtitle,
                    NULL::float AS lat, NULL::float AS lng,
                    CASE
                        WHEN UPPER(owner_full) LIKE '%%' || UPPER(%(q)s) || '%%' THEN 1.0
                        WHEN UPPER(owner_full) LIKE UPPER(SPLIT_PART(%(q)s, ' ', 2)) || '%%' THEN 0.85
                        ELSE similarity(owner_full, %(q)s)
                    END AS score,
                    pidn,
                    owner_full
                FROM staging.parcels
                WHERE valid_to IS NULL AND owner_full %% %(q)s
                ORDER BY owner_full, score DESC
            ) sub
            ORDER BY score DESC
            LIMIT %(limit)s
        """, {"q": search_term, "limit": limit})
        parcel_owners = cur.fetchall()

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
    for key in ("geom", "valid_from", "valid_to"):
        row.pop(key, None)
    for key, val in row.items():
        if hasattr(val, "as_tuple"):
            row[key] = float(val)
    return row
