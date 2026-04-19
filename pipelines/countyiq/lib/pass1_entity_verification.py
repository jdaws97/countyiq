"""Pass 1 — Entity Verification.

Provides the LLM prompt template, formatting helpers, SQL constants, and
parsing functions for cross-referencing owner identities across all data
sources and producing a relationship graph.

Two stages:
  A) SQL pre-filter — finds candidate entity clusters via pg_trgm similarity
     and shared office addresses.
  B) LLM reasoning — verifies each cluster, grouping records to the same
     entity, identifying relationship structures, and flagging rejected
     matches.
"""

from __future__ import annotations

import hashlib


# =============================================================================
# SQL CONSTANTS
# =============================================================================

# Reads from the pre-computed materialized view instead of running
# the expensive trgm self-join live. The view is refreshed by the
# refresh_entity_candidate_pairs Dagster asset on a weekly schedule.
CANDIDATE_CLUSTERS_QUERY = """
    SELECT name_a, name_b, municipality, sim
    FROM public.entity_candidate_pairs

    UNION

    SELECT DISTINCT
        c1.entity_name AS name_a,
        c2.entity_name AS name_b,
        '' AS municipality,
        0.0 AS sim
    FROM staging.corporate_entities c1
    JOIN staging.corporate_entities c2
        ON c1.office_address = c2.office_address
       AND c1.entity_name < c2.entity_name
    WHERE c1.valid_to IS NULL
      AND c2.valid_to IS NULL
      AND c1.office_address IS NOT NULL
      AND c1.office_address != ''
"""

# Standalone refresh query — used by the Dagster asset that maintains the matview.
REFRESH_CANDIDATE_PAIRS = "REFRESH MATERIALIZED VIEW public.entity_candidate_pairs"


def stable_cluster_key(cluster_names: list[str]) -> str:
    """Return a deterministic tracking key for a candidate entity cluster."""
    canonical_names = sorted({name.strip() for name in cluster_names if name and name.strip()})
    digest = hashlib.sha256("\x1f".join(canonical_names).encode("utf-8")).hexdigest()[:20]
    return f"entity_cluster:{digest}"

CLUSTER_RECORDS_QUERY_PARCELS = """
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
        municipality
    FROM staging.parcels
    WHERE owner_full = ANY(%(names)s)
      AND valid_to IS NULL
"""

CLUSTER_RECORDS_QUERY_TAX = """
    SELECT
        pidn,
        owner_name,
        tax_year,
        authority_name,
        total
    FROM staging.tax_claims
    WHERE owner_name = ANY(%(names)s)
      AND valid_to IS NULL
    ORDER BY tax_year
"""

CLUSTER_RECORDS_QUERY_PLCB = """
    SELECT
        license_number,
        license_type,
        licensee,
        premises_name,
        premises_owner,
        premises_address,
        municipality,
        status
    FROM staging.plcb_licenses
    WHERE (licensee = ANY(%(names)s) OR premises_owner = ANY(%(names)s))
      AND valid_to IS NULL
"""

CLUSTER_RECORDS_QUERY_CORPORATE = """
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

CLUSTER_RECORDS_QUERY_PROCEEDINGS = """
    SELECT
        pe.extraction_type,
        pe.applicant_name,
        pe.parcel_reference,
        pe.decision,
        pp.meeting_date,
        pp.body_name
    FROM staging.proceeding_extractions pe
    JOIN staging.public_proceedings pp ON pp.id = pe.proceeding_id
    WHERE pe.applicant_name = ANY(%(names)s)
      AND pp.valid_to IS NULL
    ORDER BY pp.meeting_date DESC
"""


# =============================================================================
# LLM TEMPLATE
# =============================================================================

ENTITY_VERIFICATION_TEMPLATE = """You are a county intelligence analyst verifying entity identities across public records from York County, PA.

Below are records from multiple data sources that may belong to the same person or related entities. Your job is to determine which records belong to the same real-world entity and identify relationships between entities.

{sections}

TASKS:
1. GROUP records that belong to the same real-world entity (person or organization). Consider name variations, abbreviations, and common patterns (e.g., "SMITH JOHN A" and "J A SMITH HOLDINGS LLC" may be related).
2. IDENTIFY relationship structures — e.g., an individual who controls an LLC, or multiple LLCs sharing an office address with the same registered agent.
3. FLAG any matches you REJECT — cases where similar names are clearly different entities.
4. PORTFOLIO SUMMARY — for each confirmed entity, summarize the property portfolio (count of parcels, total assessed value, any tax delinquencies).

OUTPUT FORMAT:
{{
  "entities": [
    {{
      "canonical_name": "the primary/official name for this entity",
      "entity_type": "individual|llc|corporation|partnership|trust|unknown",
      "confidence": 0.0 to 1.0,
      "reasoning": "brief explanation of why these records are grouped together",
      "linked_records": {{
        "parcels": ["list of PIDNs"],
        "tax_claims": ["list of PIDNs with tax claims"],
        "plcb_licenses": ["list of license numbers"],
        "corporate_entities": ["list of entity names"],
        "proceedings": ["list of applicant names from proceedings"]
      }},
      "relationships": [
        {{
          "related_entity": "name of related entity",
          "relationship_type": "controls|officer_of|registered_agent_for|subsidiary_of|shares_address_with|same_person",
          "evidence": "brief evidence for this relationship"
        }}
      ],
      "portfolio_summary": {{
        "parcel_count": 0,
        "total_assessed_value": 0,
        "tax_delinquent_parcels": 0,
        "total_tax_owed": 0
      }}
    }}
  ],
  "rejected_matches": [
    {{
      "name_a": "first name",
      "name_b": "second name",
      "reason": "why these are NOT the same entity"
    }}
  ]
}}

Return ONLY valid JSON. Do not include commentary outside the JSON object."""


# =============================================================================
# PRIVATE FORMATTING HELPERS
# =============================================================================

def _safe_str(val: object) -> str:
    """Return val as a string, or '' for None."""
    if val is None:
        return ""
    return str(val)


def _format_parcel_records(parcels: list[dict]) -> str:
    """Format parcel records for the LLM prompt.

    Each record: - PIDN X | Owner: Y | Address | Sold DATE for $PRICE | Previous owner: Z
    """
    if not parcels:
        return ""
    lines = []
    for p in parcels:
        pidn = _safe_str(p.get("pidn"))
        owner = _safe_str(p.get("owner_full"))
        addr = _safe_str(p.get("propadr"))
        sale_dt = _safe_str(p.get("saledt"))
        price = p.get("price") or 0
        prev = _safe_str(p.get("prev_owner"))
        line = f"- PIDN {pidn} | Owner: {owner} | {addr}"
        if sale_dt:
            line += f" | Sold {sale_dt} for ${price:,.0f}"
        if prev:
            line += f" | Previous owner: {prev}"
        lines.append(line)
    return "\n".join(lines)


def _format_tax_claims(claims: list[dict]) -> str:
    """Format tax claim records for the LLM prompt.

    Each record: - PIDN X | Owner: Y | AUTHORITY tax YEAR: $AMOUNT
    """
    if not claims:
        return ""
    lines = []
    for c in claims:
        pidn = _safe_str(c.get("pidn"))
        owner = _safe_str(c.get("owner_name"))
        authority = _safe_str(c.get("authority_name"))
        year = c.get("tax_year", "")
        total = c.get("total") or 0
        lines.append(f"- PIDN {pidn} | Owner: {owner} | {authority} tax {year}: ${total:,.2f}")
    return "\n".join(lines)


def _format_plcb(licenses: list[dict]) -> str:
    """Format PLCB license records for the LLM prompt.

    Each record: - License #X | Licensee: Y | Premises owner: Z | Address
    """
    if not licenses:
        return ""
    lines = []
    for lic in licenses:
        num = _safe_str(lic.get("license_number"))
        licensee = _safe_str(lic.get("licensee"))
        prem_owner = _safe_str(lic.get("premises_owner"))
        addr = _safe_str(lic.get("premises_address"))
        lines.append(f"- License #{num} | Licensee: {licensee} | Premises owner: {prem_owner} | {addr}")
    return "\n".join(lines)


def _format_corporate(entities: list[dict]) -> str:
    """Format corporate entity records for the LLM prompt.

    Each record: - NAME (#NUMBER) | Status: X | Formed: DATE | Office: ADDRESS
    """
    if not entities:
        return ""
    lines = []
    for e in entities:
        name = _safe_str(e.get("entity_name"))
        number = _safe_str(e.get("entity_number"))
        status = _safe_str(e.get("status"))
        formed = _safe_str(e.get("formation_date"))
        office = _safe_str(e.get("office_address"))
        lines.append(f"- {name} (#{number}) | Status: {status} | Formed: {formed} | Office: {office}")
    return "\n".join(lines)


def _format_proceedings(procs: list[dict]) -> str:
    """Format proceeding extraction records for the LLM prompt.

    Each record: - TYPE by APPLICANT | Re: PARCEL | Decision: X | BODY DATE
    """
    if not procs:
        return ""
    lines = []
    for p in procs:
        etype = _safe_str(p.get("extraction_type"))
        applicant = _safe_str(p.get("applicant_name"))
        parcel = _safe_str(p.get("parcel_reference"))
        decision = _safe_str(p.get("decision"))
        body = _safe_str(p.get("body_name"))
        date = _safe_str(p.get("meeting_date"))
        lines.append(f"- {etype} by {applicant} | Re: {parcel} | Decision: {decision} | {body} {date}")
    return "\n".join(lines)


# =============================================================================
# PUBLIC FUNCTIONS
# =============================================================================

def build_entity_cluster_prompt(records: dict) -> str:
    """Format cluster records into the entity verification template.

    Omits empty sections (e.g., if no PLCB records, that section header
    is not included in the prompt).

    Args:
        records: dict with keys parcels, tax_claims, plcb_licenses,
                 corporate_entities, proceedings. Each value is a list
                 of dicts from the corresponding SQL query.

    Returns:
        Fully formatted prompt string ready for LLM invocation.
    """
    sections = []

    # Parcel records — always included if present
    parcel_text = _format_parcel_records(records.get("parcels", []))
    if parcel_text:
        sections.append(f"PARCEL RECORDS:\n{parcel_text}")

    # Tax claims — conditional
    tax_text = _format_tax_claims(records.get("tax_claims", []))
    if tax_text:
        sections.append(f"TAX CLAIM RECORDS:\n{tax_text}")

    # PLCB licenses — conditional
    plcb_text = _format_plcb(records.get("plcb_licenses", []))
    if plcb_text:
        sections.append(f"PLCB LICENSES:\n{plcb_text}")

    # Corporate entities — conditional
    corp_text = _format_corporate(records.get("corporate_entities", []))
    if corp_text:
        sections.append(f"PA DOS CORPORATE RECORDS:\n{corp_text}")

    # Proceedings — conditional
    proc_text = _format_proceedings(records.get("proceedings", []))
    if proc_text:
        sections.append(f"PUBLIC PROCEEDINGS:\n{proc_text}")

    # Portfolio summary — added when records are truncated for large entities
    summary = records.get("portfolio_summary")
    if summary:
        summary_lines = [
            "PORTFOLIO SUMMARY (records truncated — full statistics below):",
            f"- Total parcels: {summary['total_parcels']} (showing {summary['parcels_shown']} above)",
            f"- Total assessed value: ${summary['total_assessed_value']:,.0f}",
            f"- Total tax claims: {summary['total_tax_claims']} (showing {summary['tax_claims_shown']} above)",
            f"- Total tax owed: ${summary['total_tax_owed']:,.2f}",
            f"- Owner name variants: {summary['owners']}",
            f"- Property classes: {summary['classes']}",
            f"- Municipalities: {summary['municipalities']}",
        ]
        sections.append("\n".join(summary_lines))

    combined_sections = "\n\n".join(sections) if sections else "(no records)"

    return ENTITY_VERIFICATION_TEMPLATE.format(sections=combined_sections)


def parse_entity_verification_output(output: dict) -> dict:
    """Validate and normalize LLM entity verification output.

    Clamps confidence values to 0.0-1.0.

    Args:
        output: Parsed JSON dict from LLM response.

    Returns:
        Normalized dict with 'entities' and 'rejected_matches' keys,
        or dict with 'error' key if the output is invalid.
    """
    if not isinstance(output, dict):
        return {"error": "Output is not a dict"}

    if "entities" not in output:
        return {"error": "Missing 'entities' key in output"}

    entities = output.get("entities", [])
    if not isinstance(entities, list):
        return {"error": "'entities' is not a list"}

    # Normalize entities
    normalized_entities = []
    for entity in entities:
        if not isinstance(entity, dict):
            continue

        # Clamp confidence to [0.0, 1.0]
        confidence = entity.get("confidence", 0.5)
        if isinstance(confidence, (int, float)):
            confidence = max(0.0, min(1.0, float(confidence)))
        else:
            confidence = 0.5

        normalized = {
            "canonical_name": entity.get("canonical_name", ""),
            "entity_type": entity.get("entity_type", "unknown"),
            "confidence": confidence,
            "reasoning": entity.get("reasoning", ""),
            "linked_records": entity.get("linked_records", {}),
            "relationships": entity.get("relationships", []),
            "portfolio_summary": entity.get("portfolio_summary", {}),
        }
        normalized_entities.append(normalized)

    rejected = output.get("rejected_matches", [])
    if not isinstance(rejected, list):
        rejected = []

    return {
        "entities": normalized_entities,
        "rejected_matches": rejected,
    }


# Maximum records per source to include in the LLM prompt.
# Entities with more parcels than this get a summary section instead of
# the full listing, so the prompt stays within token budgets.
_MAX_PARCELS_DETAIL = 50
_MAX_TAX_CLAIMS_DETAIL = 30


# =============================================================================
# CONTEXT GATHERING
# =============================================================================

def gather_cluster_records(cursor, names: list[str]) -> dict:
    """Gather all records for a list of candidate entity names.

    Executes SQL queries against parcels, tax_claims, plcb_licenses,
    corporate_entities, and proceeding_extractions to collect all
    records associated with the given names.

    For large entities (50+ parcels), the full parcel list is truncated
    and a portfolio_summary is added so the LLM has the aggregate picture
    without overflowing the token budget.

    Args:
        cursor: psycopg2 cursor (RealDictCursor or similar).
        names: List of entity name strings to query for.

    Returns:
        Dict with keys: parcels, tax_claims, plcb_licenses,
        corporate_entities, proceedings, portfolio_summary (if truncated).
    """
    params = {"names": names}

    cursor.execute(CLUSTER_RECORDS_QUERY_PARCELS, params)
    all_parcels = [dict(row) for row in cursor.fetchall()] if cursor.description else []

    cursor.execute(CLUSTER_RECORDS_QUERY_TAX, params)
    all_tax = [dict(row) for row in cursor.fetchall()] if cursor.description else []

    cursor.execute(CLUSTER_RECORDS_QUERY_PLCB, params)
    plcb_licenses = [dict(row) for row in cursor.fetchall()] if cursor.description else []

    cursor.execute(CLUSTER_RECORDS_QUERY_CORPORATE, params)
    corporate_entities = [dict(row) for row in cursor.fetchall()] if cursor.description else []

    cursor.execute(CLUSTER_RECORDS_QUERY_PROCEEDINGS, params)
    proceedings = [dict(row) for row in cursor.fetchall()] if cursor.description else []

    result = {
        "parcels": all_parcels[:_MAX_PARCELS_DETAIL],
        "tax_claims": all_tax[:_MAX_TAX_CLAIMS_DETAIL],
        "plcb_licenses": plcb_licenses,
        "corporate_entities": corporate_entities,
        "proceedings": proceedings,
    }

    # For large entities, add a portfolio summary so the LLM knows the
    # full scale even though the detail is truncated.
    if len(all_parcels) > _MAX_PARCELS_DETAIL or len(all_tax) > _MAX_TAX_CLAIMS_DETAIL:
        total_assessed = sum(float(p.get("aprtotal") or 0) for p in all_parcels)
        total_tax = sum(float(t.get("total") or 0) for t in all_tax)
        owner_counts = {}
        class_counts = {}
        muni_counts = {}
        for p in all_parcels:
            owner_counts[p.get("owner_full", "?")] = owner_counts.get(p.get("owner_full", "?"), 0) + 1
            class_counts[p.get("class", "?")] = class_counts.get(p.get("class", "?"), 0) + 1
            muni_counts[p.get("municipality", "?")] = muni_counts.get(p.get("municipality", "?"), 0) + 1

        result["portfolio_summary"] = {
            "total_parcels": len(all_parcels),
            "parcels_shown": len(result["parcels"]),
            "total_assessed_value": total_assessed,
            "total_tax_claims": len(all_tax),
            "tax_claims_shown": len(result["tax_claims"]),
            "total_tax_owed": total_tax,
            "owners": dict(sorted(owner_counts.items(), key=lambda x: -x[1])[:10]),
            "classes": class_counts,
            "municipalities": dict(sorted(muni_counts.items(), key=lambda x: -x[1])[:10]),
        }

    return result
