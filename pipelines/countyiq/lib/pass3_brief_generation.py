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

import hashlib as _hashlib
import json

from countyiq.lib.county_config import county_prompt_context
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

# Static instruction block. Sent as a byte-identical system message on every
# brief call so providers with implicit prompt caching can reuse it.
_P3_SYSTEM_TEMPLATE = """You are a county intelligence analyst writing a development brief for a parcel in {county_context}. A real-estate investor will read this brief and decide whether to pursue, watchlist, or pass on the parcel.

CONSTRAINTS:
1. Every claim in the brief MUST cite its source signal using the format [Signal: signal_key].
2. Do not invent market values, price projections, cap rates, or any numbers not present in the data above.
3. Do not provide legal or financial advice.
4. If signals conflict (opportunity vs constraint), you MUST acknowledge the tension explicitly.
5. The narrative MUST be consistent with the structured fields below — if recommendation="pass", the brief cannot read like an opportunity pitch.

OUTPUT FORMAT — return ONE valid JSON object. Emit fields in this exact order and commit to a single value for each:

{{
  "recommendation": "pursue_now" | "watchlist" | "pass",
  "urgency": "urgent_30d" | "near_term_90d" | "long_term_12mo" | "none",
  "top_signal_key": "<the single most load-bearing signal_key, or null>",
  "top_risk": "<one-sentence description of the biggest risk>",
  "evidence_strength": "strong" | "moderate" | "weak",
  "confidence": <float in [0.0, 1.0] — how sure you are the recommendation is correct given only the signals>,
  "assessment": "strong_opportunity" | "emerging" | "speculative" | "constrained" | "not_actionable",
  "assessment_reasoning": "1-2 sentences, MUST cite at least one signal as [Signal: key]",
  "brief": "2-4 paragraph narrative tying the structured fields together. MUST cite signals as [Signal: key] and MUST stay consistent with recommendation, urgency, and confidence.",
  "key_questions": ["question 1", "question 2", "question 3"],
  "citations": ["signal_key_1", "signal_key_2"]
}}

Think step by step before writing, then emit ONLY the JSON object."""

# Dynamic per-parcel block. The trailing sentence keeps the word "JSON" in
# the user message (OpenAI-family endpoints require it for json_object).
BRIEF_GENERATION_USER_TEMPLATE = """PARCEL:
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

Write the brief for this parcel. Emit ONLY the JSON object."""

# Final system string sent to the API (single braces).
BRIEF_GENERATION_SYSTEM_PROMPT = _P3_SYSTEM_TEMPLATE.format(
    county_context=county_prompt_context()
)


# Prompt version hash — travels with every persisted parcel_briefs row
# so regressions can be traced to the exact prompt that produced them.
# Covers both the system and user halves; recompute whenever either changes.
PROMPT_VERSION = _hashlib.sha256(
    (BRIEF_GENERATION_SYSTEM_PROMPT + "\n\n" + BRIEF_GENERATION_USER_TEMPLATE).encode("utf-8")
).hexdigest()[:12]


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

    # Returns only the dynamic user block; the static instructions travel
    # as BRIEF_GENERATION_SYSTEM_PROMPT via the harness system_prompt.
    return BRIEF_GENERATION_USER_TEMPLATE.format(
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


# Structured-first contract — see the LLM decision in docs/decisions.md.
# These sets clamp free-form LLM output to known vocabulary.
VALID_RECOMMENDATIONS = {"pursue_now", "watchlist", "pass"}
VALID_URGENCY         = {"urgent_30d", "near_term_90d", "long_term_12mo", "none"}
VALID_EVIDENCE        = {"strong", "moderate", "weak"}


def _clamp_float_01(value: object, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    if f != f:  # NaN
        return default
    return max(0.0, min(1.0, f))


def _clamp_enum(value: object, valid: set[str], default: str) -> str:
    if isinstance(value, str) and value in valid:
        return value
    return default


def parse_brief_output(output: object) -> dict:
    """Validate and normalize LLM brief generation output.

    Accepts both the legacy narrative-first schema and the
    structured-first schema introduced by experiment C. Structured
    fields are returned when present; legacy fields always populated.

    Returns an error key if ``brief`` text is missing or empty.
    """
    if not isinstance(output, dict):
        return {"error": "Output is not a dict"}

    brief = output.get("brief")
    if not brief:
        return {"error": "Missing or empty 'brief' in output"}

    assessment = _clamp_enum(output.get("assessment"), VALID_ASSESSMENTS, "speculative")
    assessment_reasoning = output.get("assessment_reasoning", "")
    key_questions = output.get("key_questions") or []
    if not isinstance(key_questions, list):
        key_questions = []
    citations = output.get("citations") or []
    if not isinstance(citations, list):
        citations = []

    # Structured-first fields (optional for legacy outputs).
    recommendation = _clamp_enum(output.get("recommendation"), VALID_RECOMMENDATIONS, None)
    urgency = _clamp_enum(output.get("urgency"), VALID_URGENCY, None)
    evidence_strength = _clamp_enum(output.get("evidence_strength"), VALID_EVIDENCE, None)
    confidence = _clamp_float_01(output.get("confidence"))
    top_signal_key = output.get("top_signal_key")
    if top_signal_key is not None and not isinstance(top_signal_key, str):
        top_signal_key = None
    top_risk = output.get("top_risk") or None

    return {
        "brief": brief,
        "assessment": assessment,
        "assessment_reasoning": assessment_reasoning,
        "key_questions": key_questions,
        "citations": citations,
        "recommendation": recommendation,
        "urgency": urgency,
        "evidence_strength": evidence_strength,
        "confidence": confidence,
        "top_signal_key": top_signal_key,
        "top_risk": top_risk,
    }
