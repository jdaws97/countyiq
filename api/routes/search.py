"""Lookup-first search with optional constrained LLM intent parsing."""

import logging
import re

from fastapi import APIRouter, HTTPException, Query, Request
from psycopg2 import Error as PsycopgError

from api.lib.database import get_cursor
from api.lib.llm_search import ALLOWED_REDIRECT_PATHS, parse_query_with_llm
from api.lib.rate_limit import client_ip, llm_search_daily_budget, llm_search_limiter
from api.lib.search_plan import InvalidSearchPlan, compile_aggregate, compile_query
from api.lib.settings import llm_search_enabled, open_data_source_key
from api.lib.source_policy import require_source_use

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
        return {
            "mode": "fuzzy",
            "results": _trgm_search_with_reversal(search_term, limit),
        }

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
        return {
            "mode": "fuzzy",
            "results": _trgm_search_with_reversal(search_term, limit),
        }

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
            # An accepted smart-search plan with no matching rows is still a
            # successful query. Falling through to fuzzy lookup here changes
            # the meaning of the request and can surface unrelated records.
            if llm_results is not None:
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
    "show",
    "find",
    "list",
    "what",
    "who",
    "where",
    "which",
    "how",
    "oldest",
    "newest",
    "most",
    "least",
    "biggest",
    "cheapest",
    "expensive",
    "vacant",
    "delinquent",
    "flood",
    "commercial",
    "residential",
    "industrial",
    "restaurants",
    "restaurant",
    "breweries",
    "brewery",
    "wineries",
    "bars",
    "properties",
    "parcels",
    "owners",
    "sales",
    "sold",
    "near",
    "recent",
    "top",
    "total",
    "average",
    "all",
    "zoning",
    "zoned",
}


def _is_name_lookup(query: str) -> bool:
    """Fast check: is this a person/business name vs a natural language query?

    Name lookups: "Avery Coleman", "KEYSTONE REALTY", "123 Main St"
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

    # 2-3 words without an "X in Y" pattern -> probably a name
    return "in" not in words[1:]


_STREET_SUFFIX_ALIASES = {
    "avenue": "ave",
    "ave": "avenue",
    "boulevard": "blvd",
    "blvd": "boulevard",
    "circle": "cir",
    "cir": "circle",
    "court": "ct",
    "ct": "court",
    "drive": "dr",
    "dr": "drive",
    "highway": "hwy",
    "hwy": "highway",
    "lane": "ln",
    "ln": "lane",
    "parkway": "pkwy",
    "pkwy": "parkway",
    "place": "pl",
    "pl": "place",
    "road": "rd",
    "rd": "road",
    "route": "rte",
    "rte": "route",
    "street": "st",
    "st": "street",
    "terrace": "ter",
    "ter": "terrace",
    "trail": "trl",
    "trl": "trail",
    "turnpike": "tpke",
    "tpke": "turnpike",
    "way": "wy",
    "wy": "way",
}

_BUSINESS_SUFFIXES = {
    "association",
    "company",
    "corp",
    "corporation",
    "inc",
    "incorporated",
    "llc",
    "llp",
    "lp",
    "partners",
    "partnership",
    "trust",
}


def _lookup_variants(search_term: str) -> list[str]:
    """Return a small, ordered set of useful name/address query variants."""
    normalized = " ".join(search_term.strip().split())
    variants: list[str] = []

    def add(value: str) -> None:
        value = " ".join(value.split()).strip()
        if value and value.casefold() not in {item.casefold() for item in variants}:
            variants.append(value)

    add(normalized)
    punctuation_normalized = re.sub(r"[,;]+", " ", normalized)
    add(punctuation_normalized)

    tokens = punctuation_normalized.split()
    clean_tokens = [token.strip(".()") for token in tokens]
    lowered = [token.casefold() for token in clean_tokens]

    # Parcel addresses normally omit the county/state/ZIP suffix users paste
    # from another site. Keep a variant ending at the recognized street type.
    if clean_tokens and any(char.isdigit() for char in clean_tokens[0]):
        for index, token in enumerate(lowered):
            if token in _STREET_SUFFIX_ALIASES:
                add(" ".join(clean_tokens[: index + 1]))
                break

    # County owner data commonly stores people LAST FIRST MIDDLE. Search both
    # orders, but do not turn a company suffix into the first token.
    elif 2 <= len(clean_tokens) <= 4 and lowered[-1] not in _BUSINESS_SUFFIXES:
        add(" ".join([clean_tokens[-1], *clean_tokens[:-1]]))

    # Street/ST and similar variants make pasted and county-normalized
    # addresses converge before trigram ranking.
    for value in tuple(variants):
        value_tokens = value.split()
        for index, token in enumerate(value_tokens):
            replacement = _STREET_SUFFIX_ALIASES.get(token.casefold().rstrip("."))
            if replacement:
                replaced = value_tokens.copy()
                replaced[index] = replacement
                add(" ".join(replaced))

    return variants[:6]


def _pidn_candidate(search_term: str) -> str | None:
    """Normalize a numeric or alphanumeric PIDN pasted with separators."""
    if not re.fullmatch(r"[A-Za-z0-9.\-\s]+", search_term):
        return None
    tokens = [token.casefold().rstrip(".") for token in search_term.split()]
    if any(token in _STREET_SUFFIX_ALIASES for token in tokens):
        return None
    compact = re.sub(r"[^A-Za-z0-9]", "", search_term).upper()
    if not any(char.isdigit() for char in compact):
        return None
    minimum_length = 10 if any(char.isalpha() for char in compact) else 6
    return compact if minimum_length <= len(compact) <= 16 else None


def _trgm_search_with_reversal(search_term: str, limit: int) -> list[dict]:
    """Run one ranked lookup across PIDNs, parcel owners/addresses, and places."""
    variants = _lookup_variants(search_term)
    branch_limit = min(max(limit, 20), 100)

    with get_cursor() as cur:
        cur.execute("SET LOCAL statement_timeout = '5s'")
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute("SET LOCAL pg_trgm.similarity_threshold = 0.22")
        cur.execute("SET LOCAL pg_trgm.strict_word_similarity_threshold = 0.45")
        require_source_use(
            cur, open_data_source_key(), "derived_product", conceal=False
        )
        include_licenses = True
        try:
            require_source_use(cur, "plcb_licenses", "derived_product", conceal=False)
        except HTTPException as exc:
            include_licenses = False
            logger.info(
                "License search unavailable; continuing with parcels: %s", exc.detail
            )

        all_results: list[dict] = []
        for variant in variants:
            all_results.extend(
                _trgm_search(
                    cur, variant, branch_limit, include_licenses=include_licenses
                )
            )

    return _deduplicate_and_rank(all_results, limit)


def _trgm_search(
    cur,
    search_term: str,
    limit: int,
    *,
    include_licenses: bool,
) -> list[dict]:
    """Run index-backed fuzzy branches for one normalized query variant."""
    pidn_results: list = []
    pidn_candidate = _pidn_candidate(search_term)
    if pidn_candidate:
        cur.execute(
            """
            SELECT 'parcel' AS result_type,
                   COALESCE(propadr, pidn) AS title,
                   CONCAT_WS(' · ', pidn, municipality, 'Parcel ID match') AS subtitle,
                   NULL::float AS lat, NULL::float AS lng,
                   CASE
                       WHEN pidn = %(q)s THEN 1.0::float
                       ELSE 0.96::float
                   END AS score,
                   pidn, 'parcel_id' AS match_kind
            FROM staging.parcels
            WHERE valid_to IS NULL
              AND (
                pidn = %(q)s
                OR (%(is_prefix)s AND pidn LIKE %(q)s || '%%')
              )
            ORDER BY score DESC, pidn
            LIMIT %(limit)s
            """,
            {
                "q": pidn_candidate,
                "is_prefix": len(pidn_candidate) < 13,
                "limit": limit,
            },
        )
        pidn_results = cur.fetchall()
        if pidn_results:
            return [dict(row) for row in pidn_results]

    owner_parcels = _fetch_results(
        cur,
        query="""
            SELECT 'parcel' AS result_type,
                   COALESCE(propadr, pidn) AS title,
                   CONCAT_WS(' · ', pidn, municipality, 'Owner match') AS subtitle,
                   NULL::float AS lat, NULL::float AS lng,
                   GREATEST(
                       similarity(owner_full, %(q)s),
                       strict_word_similarity(%(q)s, owner_full)
                   ) AS score,
                   pidn, 'owner' AS match_kind
            FROM staging.parcels
            WHERE valid_to IS NULL
              AND %(allow_owner)s
              AND owner_full IS NOT NULL
              AND (owner_full %% %(q)s OR %(q)s <<%% owner_full)
              AND GREATEST(
                  similarity(owner_full, %(q)s),
                  strict_word_similarity(%(q)s, owner_full)
              ) >= 0.55
            ORDER BY score DESC, pidn
            LIMIT %(limit)s
        """,
        params={
            "q": search_term,
            "allow_owner": not any(char.isdigit() for char in search_term),
            "limit": limit,
        },
    )

    address_parcels: list = []
    addresses: list = []
    if any(char.isdigit() for char in search_term):
        address_parcels = _fetch_results(
            cur,
            query="""
                SELECT 'parcel' AS result_type,
                       COALESCE(propadr, pidn) AS title,
                       CONCAT_WS(' · ', pidn, municipality, 'Parcel address') AS subtitle,
                       NULL::float AS lat, NULL::float AS lng,
                       GREATEST(
                           similarity(propadr, %(q)s),
                           strict_word_similarity(%(q)s, propadr)
                       ) AS score,
                       pidn, 'address' AS match_kind
                FROM staging.parcels
                WHERE valid_to IS NULL
                  AND propadr IS NOT NULL
                  AND (propadr %% %(q)s OR %(q)s <<%% propadr)
                  AND GREATEST(
                      similarity(propadr, %(q)s),
                      strict_word_similarity(%(q)s, propadr)
                  ) >= 0.40
                ORDER BY score DESC, pidn
                LIMIT %(limit)s
            """,
            params={"q": search_term, "limit": limit},
        )

        addresses = _fetch_results(
            cur,
            query="""
                SELECT 'address' AS result_type,
                       address_text AS title,
                       CONCAT_WS(' · ', inc_muni, 'Mapped address') AS subtitle,
                       lat, long AS lng,
                       GREATEST(
                           similarity(address_text, %(q)s),
                           strict_word_similarity(%(q)s, address_text)
                       ) AS score,
                       'mapped_address' AS match_kind
                FROM (
                    SELECT
                        COALESCE(add_number::text, '') || ' ' ||
                        COALESCE(street_name, '') || ' ' ||
                        COALESCE(st_pos_typ, '') AS address_text,
                        inc_muni, lat, long
                    FROM staging.address_points
                    WHERE valid_to IS NULL
                ) points
                WHERE (address_text %% %(q)s OR %(q)s <<%% address_text)
                  AND GREATEST(
                      similarity(address_text, %(q)s),
                      strict_word_similarity(%(q)s, address_text)
                  ) >= 0.40
                ORDER BY score DESC, title
                LIMIT %(limit)s
            """,
            params={"q": search_term, "limit": limit},
        )

    licenses: list = []
    if include_licenses:
        licenses = _fetch_results(
            cur,
            query="""
                SELECT *
                FROM (
                    SELECT DISTINCT ON (premises_name)
                           'license' AS result_type,
                           premises_name AS title,
                           CONCAT_WS(' · ', license_type, municipality, 'Licensed premises') AS subtitle,
                           NULL::float AS lat, NULL::float AS lng,
                           GREATEST(
                               similarity(premises_name, %(q)s),
                               strict_word_similarity(%(q)s, premises_name)
                           ) AS score,
                           'license' AS match_kind
                    FROM staging.plcb_licenses
                    WHERE valid_to IS NULL
                      AND UPPER(status) = 'ACTIVE'
                      AND premises_name IS NOT NULL
                      AND (premises_name %% %(q)s OR %(q)s <<%% premises_name)
                      AND GREATEST(
                          similarity(premises_name, %(q)s),
                          strict_word_similarity(%(q)s, premises_name)
                      ) >= 0.45
                    ORDER BY premises_name, score DESC
                ) matches
                ORDER BY score DESC, title
                LIMIT %(limit)s
            """,
            params={"q": search_term, "limit": limit},
        )

    return [
        dict(row) for row in [*owner_parcels, *address_parcels, *addresses, *licenses]
    ]


_MATCH_PRIORITY = {
    "parcel_id": 5,
    "address": 4,
    "owner": 3,
    "mapped_address": 2,
    "license": 1,
}

_RESULT_TYPE_BONUS = {
    "parcel": 0.12,
}


def _deduplicate_and_rank(results: list[dict], limit: int) -> list[dict]:
    """Keep the strongest result per parcel/place and apply stable tie-breaks."""
    best: dict[tuple, dict] = {}
    for result in results:
        if result.get("pidn"):
            key = ("parcel", result["pidn"])
        elif result.get("result_type") == "address":
            key = (
                "address",
                str(result.get("title") or "").casefold(),
                str(result.get("subtitle") or "").casefold(),
            )
        else:
            key = (
                result.get("result_type"),
                result.get("title"),
                result.get("subtitle"),
            )

        current = best.get(key)
        result_rank = (
            float(result.get("score") or 0),
            _MATCH_PRIORITY.get(str(result.get("match_kind")), 0),
        )
        current_rank = (
            (
                float(current.get("score") or 0),
                _MATCH_PRIORITY.get(str(current.get("match_kind")), 0),
            )
            if current
            else (-1.0, -1)
        )
        if result_rank > current_rank:
            best[key] = result

    return sorted(
        best.values(),
        key=lambda item: (
            -(
                float(item.get("score") or 0)
                + _RESULT_TYPE_BONUS.get(str(item.get("result_type")), 0)
            ),
            -_MATCH_PRIORITY.get(str(item.get("match_kind")), 0),
            str(item.get("title") or ""),
            str(item.get("pidn") or ""),
        ),
    )[:limit]


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
    "002": "Central York",
    "004": "Dallastown",
    "006": "Dover",
    "008": "Eastern York",
    "010": "Hanover",
    "012": "Northeastern",
    "014": "Northern York",
    "016": "Red Lion",
    "018": "South Eastern",
    "020": "South Western",
    "022": "Southern York",
    "024": "Spring Grove",
    "026": "West York",
    "028": "York City",
    "030": "York Suburban",
    "17F": "West Shore",
    "17G": "West Shore",
    "17L": "West Shore",
    "17N": "West Shore",
}

CLASS_NAMES = {
    "R": "Residential",
    "C": "Commercial",
    "I": "Industrial",
    "F": "Farm",
    "E": "Exempt",
    "A": "Agricultural",
    "U": "Utility",
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
TAX_KEY_FIELDS = [
    "pidn",
    "owner_name",
    "property_address",
    "tax_district_name",
    "tax_year",
    "authority_name",
    "total",
]
LICENSE_KEY_FIELDS = [
    "premises_name",
    "premises_address",
    "license_type",
    "status",
    "municipality",
]

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
        if (
            FRIENDLY_NAMES.get(key) is None
            and key in FRIENDLY_NAMES
            and key not in always_show
        ):
            continue

        if hasattr(val, "as_tuple"):
            val = float(val)

        if key == "school_dis" and val:
            val = SCHOOL_DISTRICTS.get(str(val), str(val))

        if key == "class" and val:
            val = CLASS_NAMES.get(str(val), str(val))

        if (
            key
            in (
                "aprtotal",
                "price",
                "prev_price",
                "aprland",
                "aprbldg",
                "total",
                "tax_owed",
                "penalty_owed",
                "interest_owed",
                "fees_owed",
            )
            and val
        ):
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
