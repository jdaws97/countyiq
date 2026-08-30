"""LLM-powered natural-language intent parsing via OpenRouter."""

import json
import logging
import os

import requests

from api.lib.settings import county_metadata

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Search uses a cheap, dedicated model pool. It intentionally does not inherit
# the more expensive intelligence-pipeline model default.
DEFAULT_MODELS = [
    "qwen/qwen3.5-flash-02-23",
    "mistralai/mistral-small-2603",
    "qwen/qwen3.5-9b",
]

ALLOWED_REDIRECT_PATHS = frozenset(
    {
        "/",
        "/map",
        "/feed",
        "/radar",
        "/licenses",
        "/watch",
    }
)

_COUNTY = county_metadata()
SYSTEM_PROMPT = f"You interpret search requests for CountyIQ, a real-estate intelligence product for {_COUNTY['county_name']}, {_COUNTY['state']}. Return exactly one JSON object. Never produce SQL, code, markdown, or commentary.\n\n" + """The application compiles your JSON through a strict allowlist. Use only this grammar.

INTENTS

1. Row query:
{"intent":"query","table":"parcels","description":"What the result represents and any data limitation","filters":[{"field":"acres","op":"gte","value":2}],"signals":["vacant"],"location":{"type":"municipality","value":"Spring Garden"},"sort":[{"field":"acres","direction":"desc"}],"limit":20}

2. Numeric aggregate (tax claims are aggregate-only):
{"intent":"aggregate","table":"tax_claims","description":"Total delinquent taxes in Dover Township","aggregate":{"operation":"sum","field":"total"},"filters":[{"field":"total","op":"gt","value":0}],"location":{"type":"municipality","value":"Dover Township"},"label":"Total Delinquent","format":"currency"}

3. Exact person, company, address, or parcel lookup:
{"intent":"lookup","search_term":"DAWS JAROD","description":"Looking up property owner Jarod Daws"}

4. Existing product page:
{"intent":"redirect","redirect_path":"/radar","description":"Development radar"}
Allowed redirect_path values: /, /map, /feed, /radar, /licenses, /watch.

TABLES AND FIELDS
- parcels: pidn, owner_full, propadr, class, acres, aprtotal, aprland, aprbldg, price, saledt, school_dis
  class codes: R residential, C commercial, I industrial, F farm, A agricultural, E exempt, U utility.
  owner_full is stored LAST FIRST MIDDLE. propadr has street address but usually no municipality or ZIP.
- tax_claims (aggregate intent only): pidn, tax_district_name, tax_year, authority_name, total
- plcb_licenses: premises_name, premises_address, license_type, status, municipality
  This is the only restaurant/bar/brewery source and covers only licensed establishments; say so in descriptions.
- penndot_projects: project_name, description, status, cost, start_date, end_date
- penndot_roads: road_name, road_class, speed_limit
- municipalities: name, muni_type
- zipcodes: zipcode, po_name

FILTERS
- Each filter is {"field":"one listed field","op":"operator","value":value}.
- Text operators: eq, neq, contains, starts_with, in.
- Numeric/integer/date operators: eq, neq, gt, gte, lt, lte, in.
- Dates must be YYYY-MM-DD.
- Do not invent fields. Omit filters rather than guessing values.

PARCEL SIGNALS
- vacant: no intersecting building footprint plus conservative assessment/sale guards. Footprints may be stale, so describe results as likely vacant.
- tax_delinquent: parcel has a current tax claim with a positive balance.
- flood_zone: parcel intersects a FEMA Special Flood Hazard Area.
- recent_sale: sale within recent_sale_years, an integer from 1 to 10; default 1.
Signals are valid only with table=parcels.

LOCATION
- {"type":"zipcode","value":"17404"}
- {"type":"municipality","value":"York City"}
Location is supported for parcels and plcb_licenses; municipality is also supported for tax_claims.

SORT AND AGGREGATES
- sort is a list of up to three {"field":"one table field","direction":"asc|desc"} objects.
- aggregate.operation: count, count_distinct, sum, avg, min, max.
- count has no field. count_distinct requires a field. sum/avg/min/max require a numeric field.
- format: number, currency, or percent.

EXAMPLES
- most expensive property -> {"intent":"query","table":"parcels","description":"Highest assessed parcels","sort":[{"field":"aprtotal","direction":"desc"}],"limit":5}
- breweries in 17404 -> {"intent":"query","table":"plcb_licenses","description":"Active brewery licenses in 17404; this covers licensed establishments only","filters":[{"field":"status","op":"eq","value":"Active"},{"field":"license_type","op":"contains","value":"Brewery"}],"location":{"type":"zipcode","value":"17404"},"sort":[{"field":"premises_name","direction":"asc"}],"limit":20}
- vacant delinquent parcels over 2 acres in Spring Garden -> {"intent":"query","table":"parcels","description":"Likely vacant, tax-delinquent parcels over two acres in Spring Garden; footprint data may be stale","filters":[{"field":"acres","op":"gte","value":2}],"signals":["vacant","tax_delinquent"],"location":{"type":"municipality","value":"Spring Garden"},"sort":[{"field":"acres","direction":"desc"}],"limit":20}
- parcels in flood zone in 17401 -> {"intent":"query","table":"parcels","description":"Parcels intersecting FEMA Special Flood Hazard Areas in 17401","signals":["flood_zone"],"location":{"type":"zipcode","value":"17401"},"sort":[{"field":"aprtotal","direction":"desc"}],"limit":20}
- recent sales over 500000 -> {"intent":"query","table":"parcels","description":"Property sales over $500,000 in the last year","filters":[{"field":"price","op":"gt","value":500000}],"signals":["recent_sale"],"recent_sale_years":1,"sort":[{"field":"saledt","direction":"desc"}],"limit":20}
- average property value -> {"intent":"aggregate","table":"parcels","description":"Average assessed parcel value","aggregate":{"operation":"avg","field":"aprtotal"},"label":"Average Assessed Value","format":"currency"}
- how many parcels are delinquent -> {"intent":"aggregate","table":"tax_claims","description":"Number of parcels with a positive current delinquent balance","aggregate":{"operation":"count_distinct","field":"pidn"},"filters":[{"field":"total","op":"gt","value":0}],"label":"Delinquent Parcels","format":"number"}

Be honest about source limitations. Return only the JSON object."""


def _clean_llm_json(content: str) -> dict | None:
    content = (content or "").strip()
    if not content:
        return None
    if content.startswith("```"):
        content = content.split("\n", 1)[1]
    if content.endswith("```"):
        content = content.rsplit("```", 1)[0]
    content = content.strip()

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            parsed = json.loads(content[start : end + 1])
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def resolve_search_models() -> list[str]:
    """Resolve the dedicated model pool for interactive search."""
    configured = os.environ.get("COUNTYIQ_SEARCH_MODEL")
    candidates = [configured.strip()] if configured and configured.strip() else []
    candidates.extend(DEFAULT_MODELS)

    resolved: list[str] = []
    for model in candidates:
        if model and model not in resolved:
            resolved.append(model)
    return resolved


def parse_query_with_llm(query: str) -> dict | None:
    """Send a natural-language query to OpenRouter and return structured intent."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    for model in resolve_search_models():
        try:
            response = requests.post(
                OPENROUTER_URL,
                headers=headers,
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": query},
                    ],
                    "max_tokens": 500,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                },
                timeout=15,
            )
            if response.status_code in (404, 429):
                logger.info(
                    "Search model %s returned %s; trying fallback",
                    model,
                    response.status_code,
                )
                continue
            response.raise_for_status()
            choices = response.json().get("choices", [])
            if not choices:
                continue
            parsed = _clean_llm_json(
                choices[0].get("message", {}).get("content", "")
            )
            if parsed:
                return parsed
            logger.warning("Search model %s returned invalid JSON", model)
        except (
            requests.exceptions.RequestException,
            ValueError,
            KeyError,
            TypeError,
        ) as exc:
            logger.warning("Search model %s failed: %s", model, exc)

    return None
