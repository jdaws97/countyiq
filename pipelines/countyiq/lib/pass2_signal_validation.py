"""Pass 2 — Signal Validation.

Provides LLM prompt templates, formatting helpers, and parsing functions for
validating each development signal on each parcel.  Each of the 13 signal
types has its own set of base questions (always asked) and conditional
questions (included when relevant supporting data exists).

Two public entry points:
  - build_signal_validation_prompt(context) -> str
  - parse_signal_validation_output(output)  -> dict

Plus a database helper:
  - gather_signal_context(cursor, pidn, signal) -> dict
"""

from __future__ import annotations


from countyiq.lib.intelligence_common import (
    PARCEL_QUERY,
    TAX_CLAIMS_QUERY,
    PROCEEDINGS_FOR_PARCEL_QUERY,
    NEIGHBORS_QUERY,
    CORPORATE_FOR_NAMES_QUERY,
    ENTITY_GRAPH_QUERY,
    PORTFOLIO_QUERY,
    format_parcel_context,
    format_tax_claims_context,
    format_entity_context,
    format_proceedings_context,
    format_neighbors_context,
    format_corporate_context,
    format_portfolio_context,
)


# =============================================================================
# CONSTANTS
# =============================================================================

VALID_STATUSES = {"confirmed", "upgraded", "downgraded", "stale", "irrelevant"}
VALID_SIGNIFICANCE = {"high", "medium", "low", "none"}


# =============================================================================
# SIGNAL TEMPLATES — one per signal type
# =============================================================================

SIGNAL_TEMPLATES: dict[str, dict] = {
    # ── 1. active_subdivision ─────────────────────────────────────────────
    "active_subdivision": {
        "base_questions": [
            "Is the plan date within the last 3 years, or is this data stale?",
            "Is the scale significant — how many lots/units and total acreage?",
            "Is the distance (signal's distance_m) close enough to be relevant to this parcel?",
            "Does the plan type (subdivision vs land development) match the parcel's context?",
        ],
        "conditional_questions": {
            "has_proceedings": [
                "Has this plan received formal approval, conditional approval, or been denied?",
                "Are there any outstanding conditions that could delay or block development?",
            ],
            "has_corporate": [
                "Is the applicant/developer a credible entity (active LLC, track record)?",
                "How recently was the corporate entity formed relative to the plan filing?",
            ],
        },
    },
    # ── 2. tax_distress ───────────────────────────────────────────────────
    "tax_distress": {
        "base_questions": [
            "Is this chronic multi-year delinquency or a one-time shortfall?",
            "How does the total owed compare to the parcel's assessed value — is it material?",
            "Has the delinquency reached the judicial/sheriff sale threshold?",
        ],
        "conditional_questions": {
            "has_portfolio": [
                "Does the owner have delinquency across multiple parcels (systemic distress)?",
            ],
            "has_corporate": [
                "Is the delinquent owner an LLC or shell entity (potential walk-away risk)?",
            ],
            "has_deeds": [
                "Are there recent deed transfers suggesting the owner is exiting?",
            ],
        },
    },
    # ── 3. ownership_change ───────────────────────────────────────────────
    "ownership_change": {
        "base_questions": [
            "Was this a market-rate arm's-length transaction, or a nominal/interfamily transfer?",
            "Was the price distressed relative to assessed value (potential flip or foreclosure buy)?",
            "Does the buyer show other development activity in the area?",
        ],
        "conditional_questions": {
            "has_proceedings": [
                "Has the new owner filed any zoning, subdivision, or variance applications since acquisition?",
            ],
            "has_corporate": [
                "How old is the buyer entity — newly formed (speculative) or established?",
            ],
        },
    },
    # ── 4. zoning_mismatch ────────────────────────────────────────────────
    "zoning_mismatch": {
        "base_questions": [
            "Is this a meaningful mismatch between current zoning and future land use, or a data artifact?",
            "How recent and authoritative is the future land use designation?",
            "Is this part of a corridor-wide pattern or an isolated anomaly?",
        ],
        "conditional_questions": {
            "has_proceedings": [
                "Has anyone filed a rezoning or conditional use application for this parcel?",
            ],
            "has_neighbors": [
                "Do adjacent parcels share the same zoning mismatch (corridor pattern)?",
            ],
        },
    },
    # ── 5. vacancy ────────────────────────────────────────────────────────
    "vacancy": {
        "base_questions": [
            "Is this genuinely vacant land, or a data gap (missing structure footprint)?",
            "Is the assessed value consistent with vacant status?",
            "How long has the parcel appeared vacant — recent demolition or long-term?",
        ],
        "conditional_questions": {
            "has_proceedings": [
                "Are there demolition permits, environmental orders, or code violations on record?",
            ],
        },
    },
    # ── 6. assemblage ────────────────────────────────────────────────────
    "assemblage": {
        "base_questions": [
            "Could entity resolution reduce the apparent number of distinct owners (same entity, different names)?",
            "How deep is the distress among neighboring parcels (tax delinquency, vacancy)?",
            "Is the combined acreage significant enough for a development play?",
        ],
        "conditional_questions": {
            "has_neighbors": [
                "Have any adjacent parcels changed hands recently to the same or related buyer?",
            ],
            "has_corporate": [
                "Do neighboring owners share a registered office address or agent?",
            ],
        },
    },
    # ── 7. ecodev_candidate ───────────────────────────────────────────────
    "ecodev_candidate": {
        "base_questions": [
            "How current is the YCPC economic development candidacy data?",
            "What is the underutilization percentage — is it significant?",
            "Is sewer/water infrastructure available for redevelopment?",
        ],
        "conditional_questions": {},
    },
    # ── 8. penndot_project ────────────────────────────────────────────────
    "penndot_project": {
        "base_questions": [
            "Is the PennDOT project still active and funded, or completed/cancelled?",
            "Is the proximity close enough to meaningfully affect this parcel's access or value?",
        ],
        "conditional_questions": {},
    },
    # ── 9. cdbg_investment ────────────────────────────────────────────────
    "cdbg_investment": {
        "base_questions": [
            "Is the CDBG project current or historical?",
            "Is the proximity close enough to indicate neighborhood investment momentum?",
        ],
        "conditional_questions": {},
    },
    # ── 10. growth_area ───────────────────────────────────────────────────
    "growth_area": {
        "base_questions": [
            "Is this a Primary Growth Area (PGA) or Secondary Growth Area (SGA)?",
            "Growth area status is a tiebreaker only — does this add meaningful differentiation?",
        ],
        "conditional_questions": {},
    },
    # ── 11. flood_zone ────────────────────────────────────────────────────
    "flood_zone": {
        "base_questions": [
            "Is the flood zone overlap partial (edge of parcel) or does it cover the full parcel?",
            "Should this discount the opportunity score, or effectively eliminate the parcel?",
        ],
        "conditional_questions": {},
    },
    # ── 12. conservation_easement ─────────────────────────────────────────
    "conservation_easement": {
        "base_questions": [
            "Is the conservation restriction still active and enforceable?",
            "Should this be a hard exclusion from development consideration?",
        ],
        "conditional_questions": {
            "has_proceedings": [
                "Has anyone filed a request to modify or remove the conservation easement?",
            ],
        },
    },
    # ── 13. ag_security ───────────────────────────────────────────────────
    "ag_security": {
        "base_questions": [
            "Is the agricultural security area enrollment still active?",
            "Should this be a hard exclusion from development consideration?",
        ],
        "conditional_questions": {
            "has_proceedings": [
                "Has anyone filed a withdrawal request from the agricultural security area?",
            ],
        },
    },
}


# =============================================================================
# PROMPT TEMPLATE
# =============================================================================

SIGNAL_VALIDATION_PROMPT = """You are a county intelligence analyst validating a development signal for a parcel in York County, PA.

Your job is to evaluate whether the signal is meaningful, current, and correctly weighted for this specific parcel. Answer each validation question, then provide your overall assessment.

SIGNAL:
- Signal type: {signal_key}
- Signal weight: {signal_weight}
- Source: {source_table}
- Distance: {distance_m}

EVIDENCE:
{evidence_text}

PARCEL:
- PIDN: {pidn}
- Owner: {owner}
- Address: {address}
- Assessed value: ${assessed_value:,.0f}
- Acres: {acres}
- Class: {property_class}
- Last sale: {sale_date} for ${sale_price:,.0f}
- Previous owner: {previous_owner}
- Municipality: {municipality}
- School district: {school_district}

ENTITY CONTEXT:
{entity_text}

{optional_sections}

VALIDATION QUESTIONS:
{questions_text}

OUTPUT FORMAT:
Return ONLY valid JSON with this structure:
{{
  "signal_key": "{signal_key}",
  "validation_status": "confirmed|upgraded|downgraded|stale|irrelevant",
  "adjusted_significance": "high|medium|low|none",
  "reasoning": "2-4 sentence explanation of your assessment",
  "key_facts": ["fact 1", "fact 2", "..."],
  "cross_references": [
    {{"source": "source_name", "detail": "relevant detail"}}
  ]
}}

Return ONLY valid JSON. Do not include commentary outside the JSON object."""


# =============================================================================
# PRIVATE HELPERS
# =============================================================================

def _format_evidence(evidence: dict) -> str:
    """Format the signal evidence dict into readable text."""
    if not evidence:
        return "(no evidence data)"
    lines = []
    for key, val in evidence.items():
        if val is not None:
            lines.append(f"- {key}: {val}")
    return "\n".join(lines) if lines else "(no evidence data)"


def _format_entity_text(entity: dict) -> str:
    """Format entity context for the prompt."""
    if not entity or not entity.get("found"):
        return "No verified entity record found for this owner."
    parts = [f"- Canonical name: {entity.get('canonical_name', '')}"]
    parts.append(f"- Entity type: {entity.get('entity_type', 'unknown')}")
    parts.append(f"- Verification status: {entity.get('verification_status', 'unknown')}")
    linked = entity.get("linked_names", [])
    if linked:
        parts.append(f"- Also known as: {', '.join(linked)}")
    rels = entity.get("relationships", {})
    if rels:
        for rel_type, rel_targets in rels.items():
            if isinstance(rel_targets, list):
                parts.append(f"- {rel_type}: {', '.join(rel_targets)}")
            else:
                parts.append(f"- {rel_type}: {rel_targets}")
    return "\n".join(parts)


def _build_optional_sections(context: dict) -> str:
    """Build optional prompt sections from context data."""
    sections = []

    tax_claims = context.get("tax_claims", [])
    if tax_claims:
        lines = []
        for tc in tax_claims:
            year = tc.get("year", "")
            authority = tc.get("authority", "")
            amount = tc.get("amount", 0)
            owner = tc.get("owner", "")
            lines.append(f"- {authority} tax {year}: ${amount:,.2f} (owner: {owner})")
        sections.append("TAX CLAIMS:\n" + "\n".join(lines))

    proceedings = context.get("proceedings", [])
    if proceedings:
        lines = []
        for p in proceedings:
            ptype = p.get("type", "")
            applicant = p.get("applicant", "")
            decision = p.get("decision", "")
            date = p.get("meeting_date", "")
            body = p.get("body", "")
            lines.append(f"- {ptype} by {applicant} | Decision: {decision} | {body} {date}")
            supporting = p.get("supporting_text", "")
            if supporting:
                lines.append(f"  Context: {supporting}")
        sections.append("PROCEEDINGS:\n" + "\n".join(lines))

    neighbors = context.get("neighbors", [])
    if neighbors:
        lines = []
        for n in neighbors:
            npidn = n.get("pidn", "")
            nowner = n.get("owner", "")
            nacres = n.get("acres", 0)
            nowed = n.get("total_owed", 0)
            lines.append(
                f"- PIDN {npidn} | Owner: {nowner} | {nacres} acres | Owed: ${nowed:,.2f}"
            )
        sections.append("ADJACENT PARCELS:\n" + "\n".join(lines))

    corporate = context.get("corporate", [])
    if corporate:
        lines = []
        for c in corporate:
            name = c.get("entity_name", "")
            number = c.get("entity_number", "")
            status = c.get("status", "")
            formed = c.get("formation_date", "")
            office = c.get("office_address", "")
            lines.append(
                f"- {name} (#{number}) | Status: {status} | Formed: {formed} | Office: {office}"
            )
        sections.append("CORPORATE RECORDS:\n" + "\n".join(lines))

    portfolio = context.get("portfolio", [])
    if portfolio:
        lines = []
        for pf in portfolio:
            pfpidn = pf.get("pidn", "")
            pfaddr = pf.get("address", "")
            pfval = pf.get("assessed_value", 0)
            lines.append(f"- PIDN {pfpidn} | {pfaddr} | Assessed: ${pfval:,.0f}")
        sections.append("OWNER PORTFOLIO:\n" + "\n".join(lines))

    return "\n\n".join(sections)


def _build_questions_text(signal_key: str, context: dict) -> str:
    """Build the validation questions section from templates."""
    template = SIGNAL_TEMPLATES.get(signal_key)
    if not template:
        return "- Evaluate whether this signal is meaningful for this parcel."

    questions = list(template["base_questions"])

    # Add conditional questions based on available data
    cond = template.get("conditional_questions", {})
    if cond.get("has_proceedings") and context.get("proceedings"):
        questions.extend(cond["has_proceedings"])
    if cond.get("has_corporate") and context.get("corporate"):
        questions.extend(cond["has_corporate"])
    if cond.get("has_neighbors") and context.get("neighbors"):
        questions.extend(cond["has_neighbors"])
    if cond.get("has_portfolio") and context.get("portfolio"):
        questions.extend(cond["has_portfolio"])
    if cond.get("has_deeds") and context.get("deeds"):
        questions.extend(cond["has_deeds"])

    return "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))


# =============================================================================
# PUBLIC FUNCTIONS
# =============================================================================

def build_signal_validation_prompt(context: dict) -> str:
    """Assemble the full validation prompt from a context dict.

    Args:
        context: Dict with keys: pidn, signal, parcel, entity, tax_claims,
                 proceedings, neighbors, corporate, portfolio.

    Returns:
        Fully formatted prompt string ready for LLM invocation.
    """
    signal = context.get("signal", {})
    parcel = context.get("parcel", {})
    entity = context.get("entity", {})

    signal_key = signal.get("signal_key", "unknown")
    evidence = signal.get("evidence", {})
    distance_m = signal.get("distance_m")
    distance_str = f"{distance_m:.1f}m" if distance_m is not None else "N/A (direct join)"

    evidence_text = _format_evidence(evidence)
    entity_text = _format_entity_text(entity)
    optional_sections = _build_optional_sections(context)
    questions_text = _build_questions_text(signal_key, context)

    return SIGNAL_VALIDATION_PROMPT.format(
        signal_key=signal_key,
        signal_weight=signal.get("signal_weight", 0),
        source_table=signal.get("source_table", ""),
        distance_m=distance_str,
        evidence_text=evidence_text,
        pidn=parcel.get("pidn", ""),
        owner=parcel.get("owner", ""),
        address=parcel.get("address", ""),
        assessed_value=parcel.get("assessed_value", 0),
        acres=parcel.get("acres", 0),
        property_class=parcel.get("property_class", ""),
        sale_date=parcel.get("sale_date", ""),
        sale_price=parcel.get("sale_price", 0),
        previous_owner=parcel.get("previous_owner", ""),
        municipality=parcel.get("municipality", ""),
        school_district=parcel.get("school_district", ""),
        entity_text=entity_text,
        optional_sections=optional_sections,
        questions_text=questions_text,
    )


def gather_signal_context(cursor, pidn: str, signal: dict) -> dict:
    """Gather all context needed to validate a signal on a parcel.

    Executes SQL queries from intelligence_common to collect parcel data,
    entity graph, tax claims, proceedings, neighbors, corporate records,
    and portfolio information.

    Args:
        cursor: psycopg2 cursor (RealDictCursor or similar).
        pidn: 13-char parcel identifier.
        signal: Dict with signal_key, signal_weight, source_table,
                source_id, distance_m, evidence.

    Returns:
        Context dict with keys: pidn, signal, parcel, entity, tax_claims,
        proceedings, neighbors, corporate, portfolio.
    """
    params = {"pidn": pidn}

    # Parcel context
    cursor.execute(PARCEL_QUERY, params)
    parcel_row = cursor.fetchone()
    parcel = format_parcel_context(dict(parcel_row)) if parcel_row else {
        "pidn": pidn, "owner": "", "address": "", "assessed_value": 0,
        "acres": 0, "property_class": "", "sale_date": "", "sale_price": 0,
        "previous_owner": "", "municipality": "", "school_district": "",
        "source_url": "",
    }

    # Entity graph
    owner_name = parcel.get("owner", "")
    cursor.execute(ENTITY_GRAPH_QUERY, {"name": owner_name})
    entity_row = cursor.fetchone()
    entity = format_entity_context(dict(entity_row) if entity_row else None)

    # Linked names for further queries
    linked_names = [owner_name]
    if entity.get("found"):
        linked_names.extend(entity.get("linked_names", []))
    linked_names = list(set(n for n in linked_names if n))

    # Tax claims
    cursor.execute(TAX_CLAIMS_QUERY, params)
    tax_rows = cursor.fetchall()
    tax_claims = format_tax_claims_context([dict(r) for r in tax_rows])

    # Proceedings for this parcel
    cursor.execute(PROCEEDINGS_FOR_PARCEL_QUERY, params)
    proc_rows = cursor.fetchall()
    proceedings = format_proceedings_context([dict(r) for r in proc_rows])

    # Neighbors
    cursor.execute(NEIGHBORS_QUERY, params)
    neighbor_rows = cursor.fetchall()
    neighbors = format_neighbors_context([dict(r) for r in neighbor_rows])

    # Corporate records for linked names
    cursor.execute(CORPORATE_FOR_NAMES_QUERY, {"names": linked_names})
    corp_rows = cursor.fetchall()
    corporate = format_corporate_context([dict(r) for r in corp_rows])

    # Portfolio (all parcels owned by linked names)
    cursor.execute(PORTFOLIO_QUERY, {"names": linked_names})
    portfolio_rows = cursor.fetchall()
    portfolio = format_portfolio_context([dict(r) for r in portfolio_rows])

    return {
        "pidn": pidn,
        "signal": signal,
        "parcel": parcel,
        "entity": entity,
        "tax_claims": tax_claims,
        "proceedings": proceedings,
        "neighbors": neighbors,
        "corporate": corporate,
        "portfolio": portfolio,
    }


def parse_signal_validation_output(output: object) -> dict:
    """Validate and normalize LLM signal validation output.

    Clamps validation_status to VALID_STATUSES (default: "confirmed").
    Clamps adjusted_significance to VALID_SIGNIFICANCE (default: "medium").
    Returns an error key if reasoning is missing.

    Args:
        output: Parsed JSON dict from LLM response.

    Returns:
        Normalized dict with signal_key, validation_status,
        adjusted_significance, reasoning, key_facts, cross_references.
        Or dict with 'error' key if the output is invalid.
    """
    if not isinstance(output, dict):
        return {"error": "Output is not a dict"}

    signal_key = output.get("signal_key")
    if not signal_key:
        return {"error": "Missing 'signal_key' in output"}

    reasoning = output.get("reasoning")
    if not reasoning:
        return {"error": "Missing or empty 'reasoning' in output"}

    # Clamp validation_status
    status = output.get("validation_status", "confirmed")
    if status not in VALID_STATUSES:
        status = "confirmed"

    # Clamp adjusted_significance
    significance = output.get("adjusted_significance", "medium")
    if significance not in VALID_SIGNIFICANCE:
        significance = "medium"

    # Normalize key_facts
    key_facts = output.get("key_facts", [])
    if not isinstance(key_facts, list):
        key_facts = []

    # Normalize cross_references
    cross_references = output.get("cross_references", [])
    if not isinstance(cross_references, list):
        cross_references = []

    return {
        "signal_key": signal_key,
        "validation_status": status,
        "adjusted_significance": significance,
        "reasoning": reasoning,
        "key_facts": key_facts,
        "cross_references": cross_references,
    }
