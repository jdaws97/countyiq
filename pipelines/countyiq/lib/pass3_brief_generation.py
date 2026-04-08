"""Pass 3 — Brief Generation.

Synthesizes validated signals into intelligence briefs for parcels that have
at least one medium- or high-significance validated signal.

Two public entry points:
  - build_brief_generation_prompt(context) -> str
  - parse_brief_output(output)             -> dict

Plus helpers:
  - should_generate_brief(validated_signals) -> bool
  - gather_brief_context(cursor, pidn)       -> dict
"""

from __future__ import annotations

import json
from typing import Any

from countyiq.lib.intelligence_common import (
    PARCEL_QUERY,
    ENTITY_GRAPH_QUERY,
    PORTFOLIO_QUERY,
    format_parcel_context,
    format_entity_context,
)


# =============================================================================
# CONSTANTS
# =============================================================================

VALID_ASSESSMENTS = {
    "strong_opportunity",
    "emerging",
    "speculative",
    "constrained",
    "not_actionable",
}

BRIEF_QUALIFYING_SIGNIFICANCE = {"high", "medium"}


# =============================================================================
# PROMPT TEMPLATE
# =============================================================================

BRIEF_GENERATION_TEMPLATE = """You are a county intelligence analyst writing a development brief for a parcel in York County, PA.

Your job is to synthesize the validated signals below into a concise, evidence-based intelligence brief that helps a decision-maker understand what is happening at this parcel and whether it represents an opportunity.

PARCEL:
- PIDN: {pidn}
- Address: {address}
- Owner: {owner} ({entity_type})
- Municipality: {municipality}
- Acres: {acres}
- Class: {property_class}
- Assessed value: ${assessed_value:,.0f}
- Last sale: {sale_date} for ${sale_price:,.0f}

ENTITY PROFILE:
{entity_text}

VALIDATED SIGNALS:
{signals_text}

CONSTRAINTS:
1. Every claim in the brief MUST cite its source signal using the format [Signal: signal_key].
2. Do not invent market values, price projections, cap rates, or any numbers not present in the data above.
3. Do not provide legal or financial advice.
4. If signals conflict with each other (e.g., opportunity vs. constraint), you MUST acknowledge and address the tension explicitly.

TASKS:
1. Write a narrative brief of 2-4 paragraphs that synthesizes the signals into a coherent picture of what is happening at this parcel. Lead with the most significant finding.
2. Provide an overall assessment: strong_opportunity | emerging | speculative | constrained | not_actionable.
3. List 2-3 key questions that a decision-maker should investigate further.

OUTPUT FORMAT:
Return ONLY valid JSON with this structure:
{{
  "brief": "2-4 paragraph narrative text with [Signal: signal_key] citations",
  "assessment": "strong_opportunity|emerging|speculative|constrained|not_actionable",
  "assessment_reasoning": "1-2 sentence explanation of the assessment",
  "key_questions": ["question 1", "question 2", "question 3"],
  "citations": ["signal_key_1", "signal_key_2"]
}}

Return ONLY valid JSON. Do not include commentary outside the JSON object."""


# =============================================================================
# PRIVATE HELPERS
# =============================================================================

def _format_entity_text(entity: dict, portfolio: dict) -> str:
    """Format entity profile and portfolio stats for the prompt."""
    if not entity or not entity.get("found"):
        return "No verified entity record found for this owner."

    parts = [f"- Canonical name: {entity.get('canonical_name', '')}"]
    parts.append(f"- Entity type: {entity.get('entity_type', 'unknown')}")

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

    # Portfolio stats
    if portfolio:
        count = portfolio.get("portfolio_count", 0)
        value = portfolio.get("portfolio_value", 0)
        delinquency = portfolio.get("portfolio_delinquency", 0)
        parts.append(f"- Portfolio: {count} parcels, total value ${value:,.0f}")
        if delinquency > 0:
            parts.append(f"- Portfolio delinquency: ${delinquency:,.0f}")

    return "\n".join(parts)


def _format_signals_text(validated_signals: list[dict]) -> str:
    """Format validated signals into readable text for the prompt."""
    if not validated_signals:
        return "(no validated signals)"

    sections = []
    for i, sig in enumerate(validated_signals, 1):
        signal_key = sig.get("signal_key", "unknown")
        status = sig.get("validation_status", "unknown")
        significance = sig.get("adjusted_significance", "unknown")
        reasoning = sig.get("reasoning", "")
        key_facts = sig.get("key_facts", [])
        cross_refs = sig.get("cross_references", [])
        source_url = sig.get("source_url", "")
        internal_url = sig.get("internal_url", "")

        lines = [
            f"Signal {i}: {signal_key}",
            f"  Status: {status} | Significance: {significance}",
            f"  Reasoning: {reasoning}",
        ]

        if key_facts:
            lines.append("  Key facts:")
            for fact in key_facts:
                lines.append(f"    - {fact}")

        if cross_refs:
            lines.append("  Cross-references:")
            for ref in cross_refs:
                if isinstance(ref, dict):
                    lines.append(f"    - {ref.get('source', '')}: {ref.get('detail', '')}")
                else:
                    lines.append(f"    - {ref}")

        if source_url:
            lines.append(f"  Source URL: {source_url}")
        if internal_url:
            lines.append(f"  Internal URL: {internal_url}")

        sections.append("\n".join(lines))

    return "\n\n".join(sections)


# =============================================================================
# PUBLIC FUNCTIONS
# =============================================================================

def should_generate_brief(validated_signals: list[dict]) -> bool:
    """Check whether a parcel qualifies for brief generation.

    Returns True if at least one validated signal has adjusted_significance
    of "high" or "medium".

    Args:
        validated_signals: List of validated signal dicts, each with
                          an 'adjusted_significance' key.

    Returns:
        True if the parcel qualifies for a brief, False otherwise.
    """
    if not validated_signals:
        return False
    return any(
        sig.get("adjusted_significance") in BRIEF_QUALIFYING_SIGNIFICANCE
        for sig in validated_signals
    )


def build_brief_generation_prompt(context: dict) -> str:
    """Assemble the full brief generation prompt from a context dict.

    Args:
        context: Dict with keys: pidn, parcel, entity, portfolio,
                 validated_signals.

    Returns:
        Fully formatted prompt string ready for LLM invocation.
    """
    parcel = context.get("parcel", {})
    entity = context.get("entity", {})
    portfolio = context.get("portfolio", {})
    validated_signals = context.get("validated_signals", [])

    entity_type = entity.get("entity_type", "unknown") if entity.get("found") else "unknown"
    entity_text = _format_entity_text(entity, portfolio)
    signals_text = _format_signals_text(validated_signals)

    return BRIEF_GENERATION_TEMPLATE.format(
        pidn=parcel.get("pidn", ""),
        address=parcel.get("address", ""),
        owner=parcel.get("owner", ""),
        entity_type=entity_type,
        municipality=parcel.get("municipality", ""),
        acres=parcel.get("acres", 0),
        property_class=parcel.get("property_class", ""),
        assessed_value=parcel.get("assessed_value", 0),
        sale_date=parcel.get("sale_date", ""),
        sale_price=parcel.get("sale_price", 0),
        entity_text=entity_text,
        signals_text=signals_text,
    )


def gather_brief_context(cursor, pidn: str) -> dict:
    """Gather all context needed to generate a brief for a parcel.

    Queries parcel data, entity graph, portfolio stats, and validated
    signals from public.evidence.

    Args:
        cursor: psycopg2 cursor (RealDictCursor or similar).
        pidn: 13-char parcel identifier.

    Returns:
        Context dict with keys: pidn, parcel, entity, portfolio,
        validated_signals.
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

    # Portfolio stats — all parcels owned by linked names
    linked_names = [owner_name]
    if entity.get("found"):
        linked_names.extend(entity.get("linked_names", []))
    linked_names = list(set(n for n in linked_names if n))

    cursor.execute(PORTFOLIO_QUERY, {"names": linked_names})
    portfolio_rows = cursor.fetchall()

    portfolio_count = len(portfolio_rows)
    portfolio_value = sum(
        (dict(r).get("aprtotal") or 0) for r in portfolio_rows
    )

    # Portfolio delinquency — sum of tax claims across portfolio
    portfolio_pidns = [dict(r).get("pidn") for r in portfolio_rows]
    portfolio_delinquency = 0
    if portfolio_pidns:
        cursor.execute(
            """
            SELECT COALESCE(SUM(total), 0) AS total_owed
            FROM staging.tax_claims
            WHERE pidn = ANY(%(pidns)s)
              AND valid_to IS NULL
            """,
            {"pidns": portfolio_pidns},
        )
        delinquency_row = cursor.fetchone()
        if delinquency_row:
            portfolio_delinquency = dict(delinquency_row).get("total_owed", 0) or 0

    portfolio = {
        "portfolio_count": portfolio_count,
        "portfolio_value": portfolio_value,
        "portfolio_delinquency": portfolio_delinquency,
    }

    # Validated signals from public.evidence
    cursor.execute(
        """
        SELECT
            signal_key,
            validation_status,
            adjusted_significance,
            validation_reasoning,
            claim,
            cross_references,
            source_url,
            internal_url
        FROM public.evidence
        WHERE pidn = %(pidn)s
          AND adjusted_significance IN ('high', 'medium', 'low')
        ORDER BY
            CASE adjusted_significance
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 3
            END
        """,
        params,
    )
    evidence_rows = cursor.fetchall()

    validated_signals = []
    for row in evidence_rows:
        r = dict(row)
        # Parse key_facts from claim (semicolon-delimited)
        claim = r.get("claim") or ""
        key_facts = [f.strip() for f in claim.split(";") if f.strip()] if claim else []

        # Parse cross_references from JSON
        cross_refs = r.get("cross_references")
        if isinstance(cross_refs, str):
            try:
                cross_refs = json.loads(cross_refs)
            except (json.JSONDecodeError, TypeError):
                cross_refs = []
        elif not isinstance(cross_refs, list):
            cross_refs = []

        validated_signals.append({
            "signal_key": r.get("signal_key", ""),
            "validation_status": r.get("validation_status", ""),
            "adjusted_significance": r.get("adjusted_significance", ""),
            "reasoning": r.get("validation_reasoning", ""),
            "key_facts": key_facts,
            "cross_references": cross_refs,
            "source_url": r.get("source_url") or "",
            "internal_url": r.get("internal_url") or "",
        })

    return {
        "pidn": pidn,
        "parcel": parcel,
        "entity": entity,
        "portfolio": portfolio,
        "validated_signals": validated_signals,
    }


def parse_brief_output(output: Any) -> dict:
    """Validate and normalize LLM brief generation output.

    Clamps assessment to VALID_ASSESSMENTS (default: "speculative").
    Returns an error key if brief text is missing or empty.

    Args:
        output: Parsed JSON dict from LLM response.

    Returns:
        Normalized dict with brief, assessment, assessment_reasoning,
        key_questions, citations.
        Or dict with 'error' key if the output is invalid.
    """
    if not isinstance(output, dict):
        return {"error": "Output is not a dict"}

    brief = output.get("brief")
    if not brief:
        return {"error": "Missing or empty 'brief' in output"}

    # Clamp assessment
    assessment = output.get("assessment", "speculative")
    if assessment not in VALID_ASSESSMENTS:
        assessment = "speculative"

    # Normalize assessment_reasoning
    assessment_reasoning = output.get("assessment_reasoning", "")

    # Normalize key_questions
    key_questions = output.get("key_questions", [])
    if not isinstance(key_questions, list):
        key_questions = []

    # Normalize citations
    citations = output.get("citations", [])
    if not isinstance(citations, list):
        citations = []

    return {
        "brief": brief,
        "assessment": assessment,
        "assessment_reasoning": assessment_reasoning,
        "key_questions": key_questions,
        "citations": citations,
    }


# =============================================================================
# MEGA-BATCH: N parcels per LLM call
# =============================================================================

MEGA_BRIEF_TEMPLATE = """You are a county intelligence analyst writing development briefs for {n_parcels} parcels in York County, PA.

{parcel_blocks}

For EACH parcel above, write a concise intelligence brief based on its validated signals.

RULES:
1. Every claim MUST cite its source signal using [Signal: signal_key].
2. Do not invent numbers not present in the data.
3. If signals conflict, acknowledge the tension.

OUTPUT — return ONLY valid JSON:
{{
  "briefs": [
    {{
      "pidn": "...",
      "brief": "2-4 paragraph narrative with [Signal: signal_key] citations",
      "assessment": "strong_opportunity|emerging|speculative|constrained|not_actionable",
      "assessment_reasoning": "1-2 sentence explanation",
      "key_questions": ["q1", "q2", "q3"],
      "citations": ["signal_key_1", "signal_key_2"]
    }}
  ]
}}"""


def _format_brief_parcel_block(context: dict) -> str:
    """Format one parcel's context for the mega-brief prompt."""
    parcel = context.get("parcel", {})
    entity = context.get("entity", {})
    portfolio = context.get("portfolio", {})
    signals = context.get("validated_signals", [])

    lines = [
        f"PARCEL: {parcel.get('pidn', '?')}",
        f"  Address: {parcel.get('address', '?')} | Owner: {parcel.get('owner', '?')}",
        f"  Class: {parcel.get('property_class', '?')} | Acres: {parcel.get('acres', 0)} | Assessed: ${parcel.get('assessed_value', 0):,.0f}",
        f"  Last sale: {parcel.get('sale_date', '?')} for ${parcel.get('sale_price', 0):,.0f}",
    ]

    if entity.get("found"):
        lines.append(f"  Entity: {entity.get('canonical_name', '?')} ({entity.get('entity_type', '?')})")
    if portfolio.get("portfolio_count", 0) > 1:
        lines.append(f"  Portfolio: {portfolio['portfolio_count']} parcels, ${portfolio.get('portfolio_value', 0):,.0f}")

    lines.append(f"  Validated signals ({len(signals)}):")
    for s in signals:
        lines.append(
            f"    - {s.get('signal_key', '?')} [{s.get('validation_status', '?')}/{s.get('adjusted_significance', '?')}]: "
            f"{s.get('reasoning', '')[:100]}"
        )

    return "\n".join(lines)


def build_mega_brief_prompt(contexts: list[dict]) -> str:
    """Build a mega-batch prompt for N parcels' briefs in a single LLM call.

    Args:
        contexts: List of gather_brief_context() outputs.

    Returns:
        Formatted prompt string.
    """
    parcel_blocks = "\n\n".join(_format_brief_parcel_block(ctx) for ctx in contexts)
    return MEGA_BRIEF_TEMPLATE.format(
        n_parcels=len(contexts),
        parcel_blocks=parcel_blocks,
    )


def parse_mega_brief_output(output: Any, contexts: list[dict]) -> dict:
    """Parse mega-batch brief output into per-parcel records.

    Args:
        output: Parsed JSON from LLM.
        contexts: The contexts that were sent.

    Returns:
        Dict with keys: briefs (list of normalized per-parcel dicts), missing, errors.
    """
    if not isinstance(output, dict):
        return {"briefs": [], "missing": [c["pidn"] for c in contexts], "errors": [], "parse_error": "not a dict"}

    raw_briefs = output.get("briefs", [])
    if not isinstance(raw_briefs, list):
        return {"briefs": [], "missing": [c["pidn"] for c in contexts], "errors": [], "parse_error": "missing briefs array"}

    # Index by pidn
    by_pidn = {}
    for b in raw_briefs:
        if isinstance(b, dict) and b.get("pidn"):
            by_pidn[b["pidn"]] = b

    briefs = []
    missing = []
    errors = []

    for ctx in contexts:
        pidn = ctx["pidn"]
        raw = by_pidn.get(pidn)
        if not raw:
            missing.append(pidn)
            continue

        parsed = parse_brief_output(raw)
        if "error" in parsed:
            errors.append(pidn)
            continue

        parsed["pidn"] = pidn
        briefs.append(parsed)

    return {"briefs": briefs, "missing": missing, "errors": errors}
