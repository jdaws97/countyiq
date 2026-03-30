"""LLM-powered natural language search via OpenRouter."""

import json
import os

import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openrouter/auto"  # auto-selects best free model

SYSTEM_PROMPT = """You are a search query parser for CountyIQ, a civic intelligence platform for York County, PA.

Given a user's natural language query, return a JSON object describing what they want.

Available data tables and their key columns:

1. staging.parcels — 176,059 property parcels
   Columns: pidn, owner_full, propadr, municipality, class (R/C/I), acres, aprtotal (assessed value), saledt (sale date), price (sale price), school_dis

2. staging.tax_claims — 36,831 delinquent tax records
   Columns: pidn, owner_name, property_address, tax_district_name, tax_year, authority_name (COUNTY/SCHOOL/MUNICIPAL), total (amount owed), report_date

3. staging.plcb_licenses — 1,346 liquor licenses
   Columns: licensee, premises_name, premises_address, license_type, status, municipality

4. staging.municipalities — 72 municipalities
   Columns: name, muni_type

5. staging.flood_zones — 4,000 FEMA flood zones
   Columns: fld_zone, sfha_tf

Return ONLY valid JSON with this structure:
{
  "intent": "query" | "lookup" | "redirect",
  "table": "parcels" | "tax_claims" | "plcb_licenses" | "municipalities",
  "description": "human-readable description of what we're finding",
  "sql_where": "SQL WHERE clause (use column names from above)",
  "sql_order": "SQL ORDER BY clause",
  "sql_limit": number (default 20),
  "redirect_path": "/path" (only if intent is "redirect")
}

Examples:
- "oldest tax delinquent parcel" → {"intent":"query","table":"tax_claims","description":"Oldest tax delinquent parcel in York County","sql_where":"valid_to IS NULL AND total > 0","sql_order":"tax_year ASC, total DESC","sql_limit":1}
- "most expensive property" → {"intent":"query","table":"parcels","description":"Most expensive property by assessed value","sql_where":"valid_to IS NULL AND aprtotal IS NOT NULL","sql_order":"aprtotal::numeric DESC","sql_limit":1}
- "breweries in york" → {"intent":"query","table":"plcb_licenses","description":"Breweries in York","sql_where":"valid_to IS NULL AND license_type ILIKE '%brewery%' AND UPPER(status) = 'ACTIVE'","sql_order":"licensee","sql_limit":20}
- "top delinquent owners" → {"intent":"redirect","redirect_path":"/delinquent","description":"Top delinquent property owners"}
- "who owns 123 main st" → {"intent":"query","table":"parcels","description":"Owner of 123 Main St","sql_where":"valid_to IS NULL AND UPPER(propadr) LIKE '%123 MAIN%'","sql_order":"propadr","sql_limit":5}
- "properties in flood zone" → {"intent":"query","table":"parcels","description":"Properties in FEMA flood zones","sql_where":"valid_to IS NULL AND pidn IN (SELECT p.pidn FROM staging.parcels p JOIN staging.flood_zones f ON ST_Intersects(p.geom, f.geom) WHERE f.valid_to IS NULL AND f.sfha_tf = 'T')","sql_order":"aprtotal::numeric DESC","sql_limit":20}
- "vacant land in 17404 that's delinquent" → {"intent":"query","table":"parcels","description":"Vacant tax-delinquent parcels in 17404 zip code","sql_where":"valid_to IS NULL AND pidn IN (SELECT ap.pidn FROM staging.address_points ap WHERE ap.post_code = '17404' AND ap.valid_to IS NULL) AND NOT EXISTS (SELECT 1 FROM staging.structures s WHERE s.valid_to IS NULL AND ST_Intersects(s.geom, staging.parcels.geom)) AND pidn IN (SELECT tc.pidn FROM staging.tax_claims tc WHERE tc.valid_to IS NULL AND tc.total > 0)","sql_order":"aprtotal::numeric DESC","sql_limit":20}

Spatial capabilities:
- staging.address_points has: post_code (zip code), lat, long, inc_muni
- staging.structures has geometry — use NOT EXISTS with ST_Intersects to find vacant parcels (no building footprint)
- staging.flood_zones has geometry — use ST_Intersects to check flood risk
- staging.roads has geometry — use ST_DWithin(p.geom, r.geom, distance_in_degrees) for proximity. 1 mile ≈ 0.0145 degrees.
- staging.penndot_roads has geometry for state highways

You can compose complex queries joining multiple tables. Always use subqueries with pidn to filter parcels.

Data limitations to be aware of (reflect these in your description):
- We only know about restaurants/bars/breweries that have liquor licenses (PLCB data). Not all restaurants have liquor licenses.
- Business type/industry classification is NOT available — PA Open Data only has registration type (LLC, Corp), not what the business does.
- Zip codes come from staging.address_points (post_code column), not from parcels directly.

IMPORTANT: Only use columns that exist. Always include valid_to IS NULL for SCD2 filtering. Return ONLY the JSON object, no markdown."""


def parse_query_with_llm(query: str) -> dict | None:
    """Send a natural language query to OpenRouter and get structured intent."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return None

    try:
        resp = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": query},
                ],
                "max_tokens": 500,
                "temperature": 0,
            },
            timeout=10,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]

        # Strip markdown code fences if present
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]
        content = content.strip()

        return json.loads(content)
    except Exception:
        return None


# Allowed tables for safety (prevent SQL injection via table name)
ALLOWED_TABLES = {
    "parcels": "staging.parcels",
    "tax_claims": "staging.tax_claims",
    "plcb_licenses": "staging.plcb_licenses",
    "municipalities": "staging.municipalities",
}

# Column whitelist per table (prevent SQL injection via column references)
ALLOWED_COLUMNS = {
    "parcels": {"pidn", "owner_full", "propadr", "municipality", "class", "acres",
                "aprtotal", "saledt", "price", "school_dis", "valid_to", "prev_owner"},
    "tax_claims": {"pidn", "owner_name", "property_address", "tax_district_name",
                   "tax_year", "authority_name", "total", "report_date", "valid_to"},
    "plcb_licenses": {"licensee", "premises_name", "premises_address", "license_type",
                      "status", "municipality", "valid_to"},
    "municipalities": {"name", "muni_type", "valid_to"},
}
