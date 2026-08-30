"""Lookup-first search with optional constrained LLM intent parsing."""

import logging

from fastapi import APIRouter, HTTPException, Query, Request
from psycopg2 import Error as PsycopgError

from api.lib.database import get_cursor
from api.lib.llm_search import ALLOWED_REDIRECT_PATHS, parse_query_with_llm
from api.lib.rate_limit import client_ip, llm_search_daily_budget, llm_search_limiter
from api.lib.search_plan import InvalidSearchPlan, compile_aggregate, compile_query
from api.lib.source_policy import require_source_use
from api.lib.settings import llm_search_enabled, open_data_source_key

router = APIRouter(tags=["search"])
logger = logging.getLogger(__name__)

_SOURCE_BY_SEARCH_TABLE = {
    "parcels": open_data_source_key(),
    "tax_claims": "tax_claims",
    "plcb_licenses": "plcb_licenses",
    "penndot_projects": "penndot_open_data",
    "penndot_roads": "penndot_open_data",
    "municipalities": open_data_source_key(),
    "zipcodes": open_data_source_key(),
}


def _require_search_source(cur, table: str) -> None:
    source_key = _SOURCE_BY_SEARCH_TABLE.get(table)
    if source_key:
        require_source_use(cur, source_key, "derived_product", conceal=False)

@router.get("")
def search(
    request: Request,
    q: str = Query(..., min_length=2, max_length=160, description="Search query"),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    """Smart search - fast path for name/address lookups, LLM for natural language."""
    search_term = q.strip()

    # Fast path: if it looks like a name (2-3 short words, no special keywords),
    # skip the LLM entirely and go straight to pg_trgm
    if _is_name_lookup(search_term):
        trgm_results = _trgm_search_with_reversal(search_term, limit)
        return {"mode": "fuzzy", "results": trgm_results}

    # A pipeline provider key must not silently turn a public endpoint into a
    # metered LLM surface. Natural-language intent parsing is an explicit,
    # separately budgeted product choice.
    if not llm_search_enabled():
        return {"mode": "fuzzy", "results": _trgm_search_with_reversal(search_term, limit)}

    # LLM path costs real money on a public endpoint: throttle per client,
    # and degrade to the free fuzzy path once the global daily budget is spent.
    if not llm_search_limiter.allow(client_ip(request)):
        raise HTTPException(
            status_code=429,
            detail="Search rate limit exceeded; try again shortly.",
            headers={"Retry-After": "30"},
        )
    if not llm_search_daily_budget.spend():
        logger.warning("Daily LLM search budget exhausted; serving fuzzy fallback")
        return {"mode": "fuzzy", "results": _trgm_search_with_reversal(search_term, limit)}

    # Otherwise, use LLM for intent classification
    llm_intent = parse_query_with_llm(search_term)

    if llm_intent:
        intent = llm_intent.get("intent")
        description = llm_intent.get("description", "")

        if intent == "redirect":
            redirect_path = llm_intent.get("redirect_path")
            if redirect_path in ALLOWED_REDIRECT_PATHS:
                return {
                    "mode": "redirect",
                    "redirect_path": redirect_path,
                    "description": description,
                    "results": [],
                }

        if intent == "aggregate":
            agg_result = _execute_llm_aggregate(llm_intent)
            if agg_result is not None:
                return {
                    "mode": "aggregate",
                    "description": description,
                    "label": llm_intent.get("label", "Result"),
                    "value": agg_result,
                    "format": llm_intent.get("format", "number"),
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
            if not isinstance(cleaned, str) or not 1 <= len(cleaned.strip()) <= 160:
                cleaned = search_term
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

    # Single word - could be a name or a keyword
    if len(words) == 1:
        return words[0] not in NL_WORDS

    # 5+ words is almost certainly natural language
    if len(words) >= 5:
        return False

    # Contains a zip code (5 digits)
    if any(w.isdigit() and len(w) == 5 for w in words):
        return False

    # Any NL keyword present -> not a name
    for w in words:
        if w in NL_WORDS:
            return False

    # "X in Y" pattern -> natural language
    if "in" in words[1:]:
        return False

    # 2-3 words with no keywords -> probably a name
    return True


def _trgm_search_with_reversal(search_term: str, limit: int) -> list[dict]:
    """Run pg_trgm search with automatic name reversal (FIRST LAST -> LAST FIRST)."""
    results = _trgm_search(search_term, limit)

    # Also try reversed name order
    parts = search_term.strip().split()
    if len(parts) >= 2:
        reversed_name = parts[-1] + " " + " ".join(parts[:-1])
        reversed_results = _trgm_search(reversed_name, limit)

        # Merge, deduplicate by title, keep highest score
        seen: dict[str, dict] = {}
        for result in results + reversed_results:
            key = result.get("title", "")
            if key not in seen or (result.get("score") or 0) > (seen[key].get("score") or 0):
                seen[key] = result
        results = sorted(seen.values(), key=lambda item: item.get("score", 0), reverse=True)[:limit]

    return results


def _trgm_search(search_term: str, limit: int) -> list[dict]:
    """Standard pg_trgm fuzzy matching across all sources."""
    with get_cursor() as cur:
        require_source_use(cur, open_data_source_key(), "derived_product", conceal=False)
        require_source_use(cur, "plcb_licenses", "derived_product", conceal=False)
        pidn_results: list = []
        stripped = search_term.replace("-", "").replace(".", "").replace(" ", "")
        if len(stripped) >= 10 and stripped[:2].isdigit():
            cur.execute(
                """
                SELECT 'parcel' AS result_type,
                       COALESCE(propadr, pidn) AS title,
                       pidn || ' · ' || COALESCE(municipality, '') AS subtitle,
                       NULL::float AS lat, NULL::float AS lng,
                       1.0 AS score, pidn
                FROM staging.parcels
                WHERE valid_to IS NULL AND pidn = %(q)s
                LIMIT 1
                """,
                {"q": stripped},
            )
            pidn_results = cur.fetchall()

        address_parcel_results: list = []
        if any(char.isdigit() for char in search_term) and not pidn_results:
            cur.execute(
                """
                SELECT 'parcel' AS result_type,
                       COALESCE(propadr, pidn) AS title,
                       pidn || ' · ' || COALESCE(municipality, '') AS subtitle,
                       NULL::float AS lat, NULL::float AS lng,
                       similarity(propadr, %(q)s) AS score, pidn
                FROM staging.parcels
                WHERE valid_to IS NULL AND propadr %% %(q)s
                ORDER BY similarity(propadr, %(q)s) DESC
                LIMIT %(limit)s
                """,
                {"q": search_term.upper(), "limit": limit},
            )
            address_parcel_results = cur.fetchall()

        parcel_results = [dict(row) for row in pidn_results + address_parcel_results]

        addresses = _fetch_results(
            cur,
            query="""
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
            """,
            params={"q": search_term, "limit": limit},
        )

        licenses = _fetch_results(
            cur,
            query="""
                SELECT DISTINCT ON (premises_name)
                    'license' AS result_type,
                    premises_name AS title,
                    license_type || ' · ' || municipality AS subtitle,
                    NULL::float AS lat, NULL::float AS lng,
                    similarity(premises_name, %(q)s) AS score
                FROM staging.plcb_licenses
                WHERE valid_to IS NULL AND UPPER(status) = 'ACTIVE'
                  AND premises_name %% %(q)s
                ORDER BY premises_name, score DESC
                LIMIT %(limit)s
            """,
            params={"q": search_term, "limit": limit},
        )

    all_results = [dict(row) for row in parcel_results + addresses + licenses]
    all_results.sort(key=lambda row: row["score"], reverse=True)
    return all_results[:limit]


def _fetch_results(cur, query: str, params: dict) -> list:
    """Execute one fuzzy-search branch against the migrated schema."""
    cur.execute(query, params)
    return cur.fetchall()


def _execute_llm_aggregate(intent: dict) -> str | None:
    """Compile and execute a typed aggregate plan."""
    try:
        compiled = compile_aggregate(intent)
    except InvalidSearchPlan as exc:
        logger.warning("LLM aggregate plan rejected: %s", exc)
        return None
    fmt = intent.get("format", "number")
    if fmt not in {"currency", "number", "percent"}:
        fmt = "number"

    try:
        with get_cursor() as cur:
            _require_search_source(cur, compiled.table)
            cur.execute("SET LOCAL statement_timeout = '5s'")
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute(compiled.query, compiled.params)
            row = cur.fetchone()
            if not row or row["result"] is None:
                return "0"
            try:
                val = float(row["result"])
            except (TypeError, ValueError) as exc:
                logger.warning(
                    "LLM aggregate returned non-numeric result for %s: %s",
                    compiled.table,
                    exc,
                )
                return None
            if fmt == "currency":
                if val >= 1e9:
                    return f"${val / 1e9:.1f}B"
                if val >= 1e6:
                    return f"${val / 1e6:.1f}M"
                return f"${val:,.0f}"
            if fmt == "percent":
                return f"{val:.1f}%"
            return f"{val:,.0f}"
    except PsycopgError as exc:
        logger.warning("LLM aggregate query failed for %s: %s", compiled.table, exc)
        return None


def _execute_llm_query(intent: dict, limit: int) -> list[dict] | None:
    """Compile and execute a typed row query from LLM intent parsing.

    Safety measures:
    - The LLM cannot supply SQL, identifiers, expressions, or joins
    - Tables, fields, operators, signals, locations, and sorts are allowlisted
    - Model/user values are query parameters
    - Query wrapped in read-only transaction
    - Statement timeout of 5 seconds prevents expensive scans
    - Errors logged, never expose SQL details to client
    """
    try:
        compiled = compile_query(intent, max_limit=limit)
    except InvalidSearchPlan as exc:
        logger.warning("LLM query plan rejected: %s", exc)
        return None

    try:
        with get_cursor() as cur:
            _require_search_source(cur, compiled.table)
            cur.execute("SET LOCAL statement_timeout = '5s'")
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute(compiled.query, compiled.params)
            rows = cur.fetchall()
        return [_clean_row(dict(row)) for row in rows]
    except PsycopgError as exc:
        logger.warning("LLM query failed for %s: %s", compiled.table, exc)
        return None


SCHOOL_DISTRICTS = {
    "002": "Central York", "004": "Dallastown", "006": "Dover",
    "008": "Eastern York", "010": "Hanover", "012": "Northeastern",
    "014": "Northern York", "016": "Red Lion", "018": "South Eastern",
    "020": "South Western", "022": "Southern York", "024": "Spring Grove",
    "026": "West Shore", "028": "West York", "030": "York Suburban",
    "17F": "York City", "17G": "York City", "17L": "York City", "17N": "York City",
}

CLASS_NAMES = {
    "R": "Residential", "C": "Commercial", "I": "Industrial",
    "F": "Farm", "E": "Exempt", "A": "Agricultural", "U": "Utility",
}

FRIENDLY_NAMES = {
    "pidn": "Parcel ID",
    "owner_full": None,  # used as title, hide from details
    "owner_name": None,
    "propadr": None,  # used as subtitle
    "property_address": None,
    "premises_name": None,
    "premises_address": None,
    "licensee": None,
    "aprtotal": "Assessed Value",
    "aprland": "Land Value",
    "aprbldg": "Building Value",
    "saledt": "Sale Date",
    "price": "Sale Price",
    "prev_price": "Previous Price",
    "acres": "Acres",
    "class": "Class",
    "school_dis": "School District",
    "municipality": "Municipality",
    "tax_district_name": "Tax District",
    "tax_year": "Tax Year",
    "authority_name": "Authority",
    "total": "Amount Owed",
    "tax_owed": "Tax Owed",
    "penalty_owed": "Penalty",
    "interest_owed": "Interest",
    "fees_owed": "Fees",
    "license_type": "License Type",
    "status": "Status",
    "parcel_id_raw": "Parcel ID (Raw)",
    "unit_suffix": None,
    "tax_district_code": None,
    "report_date": None,
    "dataset_id": None,
    "record_id": None,
}


PARCEL_KEY_FIELDS = ["pidn", "propadr", "class", "acres", "aprtotal", "school_dis"]
TAX_KEY_FIELDS = ["pidn", "owner_name", "property_address", "tax_district_name", "tax_year", "authority_name", "total"]
LICENSE_KEY_FIELDS = ["premises_name", "premises_address", "license_type", "status", "municipality"]

# Friendly names for key fields that are normally hidden (used as title/subtitle in fuzzy mode)
_KEY_FIELD_NAMES = {
    "owner_full": "Owner",
    "propadr": "Address",
    "owner_name": "Owner",
    "property_address": "Address",
    "premises_name": "Premises",
    "premises_address": "Address",
    "licensee": "Licensee",
}


def _clean_row(row: dict) -> dict:
    """Clean a database row for JSON serialization with friendly names."""
    for key in ("geom", "valid_from", "valid_to"):
        row.pop(key, None)

    # Determine which key fields to always show based on table
    always_show = set()
    if "pidn" in row and "tax_year" not in row and "license_type" not in row:
        always_show = set(PARCEL_KEY_FIELDS)
    elif "tax_year" in row:
        always_show = set(TAX_KEY_FIELDS)
    elif "license_type" in row:
        always_show = set(LICENSE_KEY_FIELDS)

    cleaned = {}
    for key, val in row.items():
        # Skip hidden fields unless they're key fields for this result type
        if FRIENDLY_NAMES.get(key) is None and key in FRIENDLY_NAMES:
            if key not in always_show:
                continue

        if hasattr(val, "as_tuple"):
            val = float(val)

        if key == "school_dis" and val:
            val = SCHOOL_DISTRICTS.get(str(val), str(val))

        if key == "class" and val:
            val = CLASS_NAMES.get(str(val), str(val))

        if key in ("aprtotal", "price", "prev_price", "aprland", "aprbldg", "total", "tax_owed", "penalty_owed", "interest_owed", "fees_owed") and val:
            val = f"${float(val):,.0f}"

        if key in always_show and key in _KEY_FIELD_NAMES:
            friendly = _KEY_FIELD_NAMES[key]
        else:
            friendly = FRIENDLY_NAMES.get(key, key.replace("_", " ").title())

        # Always show key fields (use "--" for missing), skip other empty fields
        if val is not None and str(val).strip():
            cleaned[friendly] = val
        elif key in always_show:
            cleaned[friendly] = "--"

    if "pidn" in row:
        cleaned["_link"] = f"/property/{row['pidn']}"
    elif "Parcel ID" in cleaned:
        cleaned["_link"] = f"/property/{cleaned['Parcel ID']}"

    return cleaned
