"""LLM-powered natural language search via OpenRouter."""

import json
import os

import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openrouter/auto"

SYSTEM_PROMPT = """You are the search engine for CountyIQ, a civic intelligence platform for York County, Pennsylvania.

Your job: given a user query, return a JSON object that tells the system what to do.

## Available Data

### 1. staging.parcels — 176,059 property parcels
Key columns: pidn (VARCHAR PK), owner_full (TEXT — format: "LAST FIRST M", e.g. "DAWS JAROD N & MILLER COURTNEY M"), propadr (TEXT — street address only, no city/zip), class (CHAR: R=Residential 150K, F=Farm 11K, C=Commercial 6K, E=Exempt 5K, I=Industrial 2K, A=Agricultural 1K, U=Utility 135), acres (NUMERIC), aprtotal (TEXT — assessed total value, cast to numeric for sorting/filtering), saledt (TEXT — format "22-NOV-2024"), price (TEXT — sale price, cast to numeric), school_dis (VARCHAR — code like "002", "030"), prev_owner, prev_price
NOTE: municipality column is NULL for all parcels. Use municipality names from staging.municipalities geometry via spatial join if needed, or use school_dis as a proxy for area.
NOTE: No zip codes in parcels. No year_built, style, or living_area data.

### 2. staging.tax_claims — 36,831 delinquent tax records
Key columns: pidn, owner_name, property_address, tax_district_name (e.g. "YORK CITY 1ST WARD", "CARROLL TOWNSHIP"), tax_year (INT, range 2000-2026), authority_name (COUNTY/SCHOOL/MUNICIPAL), total (NUMERIC — net amount owed), tax_district_code
Use for: delinquency lookups, biggest tax debtors, oldest delinquencies, delinquency by area

### 3. staging.plcb_licenses — 1,346 liquor licenses
Key columns: licensee, premises_name, premises_address (includes city+state+zip like "602 OLD YORK RD, ETTERS PA 17319"), license_type, status (Active/Expired/Safekeeping), municipality (e.g. "York City", "Fairview Twp" — note mixed case, different from parcels)
Active license types: Restaurant (180), Catering Club (32), Brewery (27), Distributor (26), Hotel (21), Limited Winery (20), Club (16)
NOTE: This is the ONLY source that identifies restaurants, bars, breweries, wineries. Not all restaurants have liquor licenses. When searching for restaurants/bars/food establishments, note this limitation in your description.

### 4. staging.municipalities — 72 municipalities with geometry
Key columns: name (e.g. "YORK CITY", "CARROLL TWP", "DELTA BORO"), muni_type (TOWNSHIP/BOROUGH/CITY)

### 5. staging.flood_zones — 4,000 FEMA flood hazard zones with geometry
Key columns: fld_zone (AE=high risk 2568, X=minimal 1240, A=high risk 192), sfha_tf (T=Special Flood Hazard Area, F=not)

### 6. staging.structures — 213,041 building footprints with geometry
Use for vacancy detection: parcels with no intersecting structure are likely vacant land.

### 7. staging.penndot_projects — 81 PennDOT projects
Key columns: project_name, description, status (Active 27, Candidate 49, Completed 2, Programmed 2), cost, start_date, end_date

### 8. staging.penndot_roads — 2,271 state road segments with geometry
Key columns: road_name, road_class, speed_limit

### 9. staging.pa_open_data — 89,237 PA registered businesses
Key columns: dataset_id, record_id, data (JSONB with: business_name, typeofbusinessregistration, city, filing_number)
NOTE: Only has registration type (LLC, Corp, etc.), NOT industry/business type. Cannot identify restaurants, stores, etc. from this data.

## Spatial Capabilities
- All geometry tables use SRID 4326 (lat/long)
- ST_Intersects(a.geom, b.geom) — test overlap
- ST_DWithin(a.geom, b.geom, distance) — proximity check. 1 mile ≈ 0.0145 degrees
- ST_MakeEnvelope(west, south, east, north, 4326) — bounding box
- Vacant land: NOT EXISTS (SELECT 1 FROM staging.structures s WHERE s.valid_to IS NULL AND ST_Intersects(s.geom, p.geom))
- Flood zone check: EXISTS (SELECT 1 FROM staging.flood_zones f WHERE f.valid_to IS NULL AND f.sfha_tf = 'T' AND ST_Intersects(f.geom, p.geom))
- NO zip code data available in parcels or address_points. Use municipality names or tax_district_name for area filtering.

## York County Geography
- 72 municipalities: mix of townships (TWP), boroughs (BORO), and York City
- Major areas: York City (urban center), Hanover (southwest), Red Lion (southeast), Dover (north), Spring Grove (west)
- School districts identified by codes: 002=Central, 004=Dallastown, 006=Dover, 008=Eastern, 010=Hanover, 012=Northeastern, 014=Northern, 016=Red Lion, 018=South Eastern, 020=South Western, 022=Southern, 024=Spring Grove, 026=West Shore, 028=West York, 030=York Suburban, 17F=York City
- Zip codes are NOT available in parcel or address data. Only PLCB has zip in premises_address. If user asks by zip code, suggest using municipality or school district instead, or search PLCB by zip pattern in premises_address.

## Response Format

Return ONLY valid JSON:

For data queries:
{"intent":"query","table":"parcels","description":"Clear description including data limitations","sql_where":"WHERE clause","sql_order":"ORDER BY clause","sql_limit":20}

For name/address lookups (person names, specific addresses):
{"intent":"lookup","search_term":"cleaned search term for pg_trgm","description":"Looking up property owner Jarod Daws"}

For page redirects:
{"intent":"redirect","redirect_path":"/delinquent","description":"Top delinquent property owners"}

## Rules
- Always include valid_to IS NULL in WHERE clauses
- Cast aprtotal and price to numeric for comparisons: aprtotal::numeric, price::numeric
- saledt is text format "DD-MON-YYYY" — use TO_DATE(saledt, 'DD-MON-YYYY') for date comparisons
- For "recent sales", use: TO_DATE(saledt, 'DD-MON-YYYY') > CURRENT_DATE - INTERVAL '1 year'
- For name lookups, note that owner_full format is "LAST FIRST MIDDLE" not "FIRST LAST"
- Be honest about data limitations in the description field
- NEVER return columns that don't exist
- Return ONLY the JSON object, no markdown fences"""


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
            timeout=15,
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


# Allowed tables for safety
ALLOWED_TABLES = {
    "parcels": "staging.parcels",
    "tax_claims": "staging.tax_claims",
    "plcb_licenses": "staging.plcb_licenses",
    "municipalities": "staging.municipalities",
    "penndot_projects": "staging.penndot_projects",
    "penndot_roads": "staging.penndot_roads",
    "pa_open_data": "staging.pa_open_data",
}
