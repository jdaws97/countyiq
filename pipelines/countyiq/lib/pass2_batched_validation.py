"""Pass 2 batched validation — validate all signals for a parcel in one LLM call.

This is the production-optimized version of Pass 2. Instead of making one
LLM call per signal (~80K calls for full backfill), it makes one call per
parcel (~20K calls) with all signals presented together.

Benefits:
  - 4x fewer LLM calls
  - Shared parcel context reduces per-call token cost ~40%
  - LLM sees all signals together → cross-signal reasoning patterns
  - Single input hash per parcel → simpler incremental processing

The per-signal version (pass2_signal_validation.py) is retained for A/B
comparison and for cases where individual validation is specifically needed.
"""
import json
from datetime import datetime, timezone
from typing import Any

from countyiq.lib.intelligence_common import (
    PARCEL_QUERY,
    TAX_CLAIMS_QUERY,
    PROCEEDINGS_FOR_PARCEL_QUERY,
    PROCEEDINGS_FOR_ENTITY_QUERY,
    NEIGHBORS_QUERY,
    CORPORATE_FOR_NAMES_QUERY,
    ENTITY_GRAPH_QUERY,
    PORTFOLIO_QUERY,
    format_parcel_context,
    format_tax_claims_context,
    format_entity_context,
    format_portfolio_context,
    format_proceedings_context,
    format_neighbors_context,
    format_corporate_context,
)
from countyiq.lib.pass2_signal_validation import (
    SIGNAL_TEMPLATES,
    VALID_STATUSES,
    VALID_SIGNIFICANCE,
    parse_signal_validation_output,
)

# ---------------------------------------------------------------------------
# Signal type classification — which sections of context each signal needs
# ---------------------------------------------------------------------------

SIGNAL_NEEDS_NEIGHBORS = {"assemblage", "zoning_mismatch", "ownership_change", "active_subdivision"}
SIGNAL_NEEDS_PORTFOLIO = {"tax_distress", "ownership_change", "assemblage"}
SIGNAL_NEEDS_PROCEEDINGS = {
    "active_subdivision",
    "zoning_mismatch",
    "ownership_change",
    "ecodev_candidate",
    "conservation_easement",
    "ag_security",
}


def _owner_is_business(name: str) -> bool:
    """Check if owner name matches common business entity patterns."""
    if not name:
        return False
    upper = name.upper()
    return any(
        pattern in upper
        for pattern in [
            "LLC", "L.L.C", "INC", "CORP", "LP", "L.P",
            "LTD", "HOLDINGS", "TRUST", "PARTNERS",
            "ASSOCIATES", "ENTERPRISES", "PROPERTIES",
            "GROUP", "VENTURES", "CAPITAL", "INVESTMENTS",
        ]
    )


# ---------------------------------------------------------------------------
# Context gatherer — runs each query ONCE per parcel
# ---------------------------------------------------------------------------

SIGNALS_FOR_PIDN_QUERY = """
    SELECT
        pidn,
        signal_key,
        signal_weight,
        source_table,
        source_id,
        distance_m,
        evidence
    FROM public.development_signals
    WHERE pidn = %(pidn)s
    ORDER BY signal_weight DESC, signal_key
"""


def gather_parcel_batch_context(cursor, pidn: str) -> dict:
    """Gather all signals and context needed for batched validation.

    Runs SQL queries once per parcel (vs once per signal in the old flow).
    Smart-skips optional sections based on which signal types are present.

    Returns dict with keys: pidn, parcel, entity, portfolio, tax_claims,
    neighbors, corporate, proceedings, signals.
    """
    # All signals for this parcel
    cursor.execute(SIGNALS_FOR_PIDN_QUERY, {"pidn": pidn})
    signal_rows = [dict(row) for row in cursor.fetchall()]

    signals = []
    for row in signal_rows:
        evidence = row.get("evidence") or {}
        if isinstance(evidence, str):
            try:
                evidence = json.loads(evidence) if evidence else {}
            except (json.JSONDecodeError, TypeError):
                evidence = {}
        signals.append(
            {
                "signal_key": row["signal_key"],
                "signal_weight": float(row.get("signal_weight") or 0),
                "source_table": row.get("source_table") or "",
                "source_id": row.get("source_id"),
                "distance_m": row.get("distance_m"),
                "evidence": evidence,
            }
        )

    signal_keys = {s["signal_key"] for s in signals}

    # Parcel fundamentals — always needed
    cursor.execute(PARCEL_QUERY, {"pidn": pidn})
    parcel_row = cursor.fetchone()
    parcel = format_parcel_context(dict(parcel_row)) if parcel_row else {}

    # Entity graph — always needed
    owner_name = parcel.get("owner", "")
    cursor.execute(ENTITY_GRAPH_QUERY, {"name": owner_name})
    entity_row = cursor.fetchone()
    entity = format_entity_context(dict(entity_row) if entity_row else None)

    linked_names = (
        entity.get("linked_names") or [owner_name]
        if entity.get("found")
        else [owner_name]
    )

    # Tax claims — always gather (small query, widely used)
    cursor.execute(TAX_CLAIMS_QUERY, {"pidn": pidn})
    tax_claims = format_tax_claims_context([dict(r) for r in cursor.fetchall()])

    # Portfolio — only if needed
    portfolio = []
    if signal_keys & SIGNAL_NEEDS_PORTFOLIO and entity.get("found"):
        cursor.execute(PORTFOLIO_QUERY, {"names": linked_names})
        portfolio = format_portfolio_context([dict(r) for r in cursor.fetchall()])

    # Neighbors — only if an assemblage-type signal exists
    neighbors = []
    if signal_keys & SIGNAL_NEEDS_NEIGHBORS:
        cursor.execute(NEIGHBORS_QUERY, {"pidn": pidn})
        neighbors = format_neighbors_context([dict(r) for r in cursor.fetchall()])

    # Corporate records — only if owner looks like a business
    corporate = []
    if _owner_is_business(owner_name):
        cursor.execute(CORPORATE_FOR_NAMES_QUERY, {"names": linked_names})
        corporate = format_corporate_context([dict(r) for r in cursor.fetchall()])

    # Proceedings — only if relevant signal types exist
    proceedings = []
    if signal_keys & SIGNAL_NEEDS_PROCEEDINGS:
        cursor.execute(PROCEEDINGS_FOR_PARCEL_QUERY, {"pidn": pidn})
        parcel_procs = [dict(r) for r in cursor.fetchall()]
        cursor.execute(PROCEEDINGS_FOR_ENTITY_QUERY, {"names": linked_names})
        entity_procs = [dict(r) for r in cursor.fetchall()]
        # Dedupe by (extraction_type, meeting_date, applicant_name)
        seen = set()
        merged = []
        for p in parcel_procs + entity_procs:
            key = (
                p.get("extraction_type"),
                str(p.get("meeting_date", "")),
                p.get("applicant_name"),
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(p)
        proceedings = format_proceedings_context(merged)

    return {
        "pidn": pidn,
        "parcel": parcel,
        "entity": entity,
        "portfolio": portfolio,
        "tax_claims": tax_claims,
        "neighbors": neighbors,
        "corporate": corporate,
        "proceedings": proceedings,
        "signals": signals,
    }


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

BATCHED_VALIDATION_TEMPLATE = """You are a real estate intelligence analyst validating development signals for a parcel in York County, PA.

PARCEL:
{parcel_section}

ENTITY CONTEXT:
{entity_section}

{optional_sections}

SIGNALS TO VALIDATE ({n_signals} signal{plural}):
{signals_list}

Your task: for EACH signal above, determine if it is meaningful, stale, misclassified, or irrelevant for THIS specific parcel. Consider how the signals INTERACT — a parcel with overlapping signals tells a different story than any single signal alone.

Rules:
1. Do arithmetic carefully — ratios, percentages, and distances matter for calibration.
2. If a signal label doesn't match its evidence (e.g., active_subdivision for a plan with 0 lots), downgrade it.
3. Consider portfolio and neighbor context — a solo delinquency differs from systemic distress.
4. Never invent facts. If context is missing, note it in reasoning.
5. Return exactly one validation per signal above, in the same order.

OUTPUT — return ONLY valid JSON with this exact structure:
{{
  "validations": [
    {{
      "signal_key": "exact signal_key from above",
      "validation_status": "confirmed|upgraded|downgraded|stale|irrelevant",
      "adjusted_significance": "high|medium|low|none",
      "reasoning": "2-3 sentence explanation specific to this parcel",
      "key_facts": ["fact 1", "fact 2"],
      "cross_references": ["optional: other signals or context that informed this judgment"]
    }}
  ],
  "cross_signal_insight": "optional: observation about signal combinations on this parcel, or empty string"
}}"""


def _format_parcel_section(parcel: dict) -> str:
    return "\n".join(
        [
            f"PIDN: {parcel.get('pidn', '?')}",
            f"Owner: {parcel.get('owner', '?')}",
            f"Address: {parcel.get('address', '?')}",
            f"Municipality: {parcel.get('municipality', '?')}",
            f"Class: {parcel.get('property_class', '?')} | Acres: {parcel.get('acres', '?')}",
            f"Assessed value: ${parcel.get('assessed_value', 0):,}",
            f"Last sale: {parcel.get('sale_date', '?')} for ${parcel.get('sale_price', 0):,}",
        ]
    )


def _format_entity_section(entity: dict) -> str:
    if not entity.get("found"):
        return "No verified entity record for this owner."
    lines = [
        f"Canonical name: {entity.get('canonical_name', '?')}",
        f"Entity type: {entity.get('entity_type', '?')}",
    ]
    if entity.get("linked_names"):
        lines.append(f"Linked names: {', '.join(entity['linked_names'])}")
    if entity.get("relationships"):
        for rel in entity["relationships"][:3]:
            lines.append(
                f"Relationship: {rel.get('relationship', '?')} -> {rel.get('related_entity', '?')}"
            )
    return "\n".join(lines)


def _format_tax_claims(claims: list[dict]) -> str:
    if not claims:
        return ""
    lines = ["TAX CLAIMS:"]
    for c in claims[:15]:
        lines.append(
            f"- {c.get('authority', '?')} {c.get('year', '?')}: ${c.get('amount', 0):,.2f}"
        )
    return "\n".join(lines)


def _format_portfolio(portfolio: list[dict]) -> str:
    if not portfolio or len(portfolio) <= 1:
        return ""
    lines = [f"OWNER PORTFOLIO ({len(portfolio)} parcels):"]
    for p in portfolio[:10]:
        lines.append(
            f"- {p.get('pidn', '?')} | {p.get('address', '?')} | ${p.get('assessed_value', 0):,}"
        )
    return "\n".join(lines)


def _format_neighbors(neighbors: list[dict]) -> str:
    if not neighbors:
        return ""
    lines = [f"ADJACENT PARCELS ({len(neighbors)} neighbors):"]
    # Cap to 15 to avoid huge prompts on dense blocks
    for n in neighbors[:15]:
        owed = f" | Owed: ${n.get('total_owed', 0):,.0f}" if n.get("total_owed") else ""
        lines.append(
            f"- {n.get('pidn', '?')} | {n.get('owner', '?')} | {n.get('acres', 0)} ac{owed}"
        )
    if len(neighbors) > 15:
        lines.append(f"... ({len(neighbors) - 15} more neighbors)")
    return "\n".join(lines)


def _format_corporate(corporate: list[dict]) -> str:
    if not corporate:
        return ""
    lines = ["CORPORATE RECORDS (PA DOS):"]
    for c in corporate[:10]:
        lines.append(
            f"- {c.get('entity_name', '?')} | Status: {c.get('status', '?')} | "
            f"Formed: {c.get('formation_date', '?')} | Office: {c.get('office_address', '?')}"
        )
    return "\n".join(lines)


def _format_proceedings(proceedings: list[dict]) -> str:
    if not proceedings:
        return ""
    lines = ["PUBLIC PROCEEDINGS:"]
    for p in proceedings[:10]:
        lines.append(
            f"- {p.get('type', '?')} by {p.get('applicant', '?')} | "
            f"Decision: {p.get('decision', '?')} | "
            f"{p.get('body', '?')} {p.get('meeting_date', '?')}"
        )
    return "\n".join(lines)


def _format_signals_list(signals: list[dict]) -> str:
    """Format the numbered list of signals with per-signal validation questions."""
    lines = []
    for i, sig in enumerate(signals, 1):
        key = sig["signal_key"]
        weight = sig.get("signal_weight", 0)
        distance = sig.get("distance_m")
        evidence = sig.get("evidence") or {}

        # Flatten evidence into compact key=value pairs
        ev_parts = []
        for k, v in list(evidence.items())[:6]:
            if v is None:
                continue
            v_str = str(v)
            if len(v_str) > 60:
                v_str = v_str[:57] + "..."
            ev_parts.append(f"{k}={v_str}")
        ev_str = ", ".join(ev_parts) if ev_parts else "(no evidence)"

        dist_str = f" | distance: {distance:.0f}m" if distance is not None else ""
        lines.append(
            f"\nSignal {i}: {key} (weight {weight:.2f}{dist_str})\n  Evidence: {ev_str}"
        )

        # Include base questions for this signal type (if we have them)
        template = SIGNAL_TEMPLATES.get(key, {})
        base_questions = template.get("base_questions", [])
        if base_questions:
            lines.append("  Questions:")
            for q in base_questions[:3]:  # Top 3 to keep prompt tight
                lines.append(f"    - {q}")

    return "\n".join(lines)


def build_batched_signal_prompt(context: dict, signals_override: list[dict] | None = None) -> str:
    """Build the batched validation prompt for signals on a parcel.

    Args:
        context: Output of gather_parcel_batch_context().
        signals_override: If provided, use this subset of signals instead of
            context['signals']. Used by the retry path when the LLM dropped
            some signals in the first call.

    Returns:
        Formatted prompt string ready for LLM invocation.
    """
    signals = signals_override if signals_override is not None else context.get("signals", [])
    parcel = context.get("parcel", {})
    entity = context.get("entity", {})

    optional_parts = []
    for formatter, data in [
        (_format_tax_claims, context.get("tax_claims")),
        (_format_portfolio, context.get("portfolio")),
        (_format_neighbors, context.get("neighbors")),
        (_format_corporate, context.get("corporate")),
        (_format_proceedings, context.get("proceedings")),
    ]:
        section = formatter(data or [])
        if section:
            optional_parts.append(section)

    return BATCHED_VALIDATION_TEMPLATE.format(
        parcel_section=_format_parcel_section(parcel),
        entity_section=_format_entity_section(entity),
        optional_sections="\n\n".join(optional_parts) if optional_parts else "",
        signals_list=_format_signals_list(signals),
        n_signals=len(signals),
        plural="s" if len(signals) != 1 else "",
    )


# ---------------------------------------------------------------------------
# Output parser
# ---------------------------------------------------------------------------

def parse_batched_signal_output(
    output: Any, expected_signals: list[dict]
) -> dict:
    """Parse and normalize the batched validation response.

    Args:
        output: Parsed JSON from LLM.
        expected_signals: The signals we asked it to validate.

    Returns:
        Dict with keys:
          validations: list of normalized per-signal dicts (one per expected signal)
          cross_signal_insight: str (optional observation from LLM)
          errors: list of signal_keys that failed to parse
          missing: list of signal_keys the LLM did not return
    """
    if not isinstance(output, dict):
        return {
            "validations": [],
            "cross_signal_insight": "",
            "errors": [s["signal_key"] for s in expected_signals],
            "missing": [s["signal_key"] for s in expected_signals],
            "parse_error": "Output is not a dict",
        }

    raw_validations = output.get("validations", [])
    if not isinstance(raw_validations, list):
        return {
            "validations": [],
            "cross_signal_insight": output.get("cross_signal_insight", ""),
            "errors": [s["signal_key"] for s in expected_signals],
            "missing": [s["signal_key"] for s in expected_signals],
            "parse_error": "Missing or invalid 'validations' array",
        }

    # Index returned validations by signal_key for lookup
    returned_by_key = {}
    for v in raw_validations:
        if isinstance(v, dict) and v.get("signal_key"):
            returned_by_key[v["signal_key"]] = v

    # Match against expected signals in order, normalize each
    normalized = []
    errors = []
    missing = []

    for expected in expected_signals:
        key = expected["signal_key"]
        raw = returned_by_key.get(key)

        if raw is None:
            missing.append(key)
            continue

        # Reuse single-signal parser for status/significance normalization
        single = parse_signal_validation_output(
            {
                "signal_key": key,
                "validation_status": raw.get("validation_status", "confirmed"),
                "adjusted_significance": raw.get("adjusted_significance", "medium"),
                "reasoning": raw.get("reasoning", ""),
                "key_facts": raw.get("key_facts", []),
                "cross_references": raw.get("cross_references", []),
            }
        )

        if "error" in single:
            errors.append(key)
            continue

        normalized.append(single)

    return {
        "validations": normalized,
        "cross_signal_insight": output.get("cross_signal_insight", "") or "",
        "errors": errors,
        "missing": missing,
    }
