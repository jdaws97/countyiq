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
from collections import Counter as _Counter
import hashlib as _hashlib
import json

from countyiq.lib.county_config import county_prompt_context
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
    "conservation_easement",
    "ag_security",
}


# Deterministic spatial facts and constraints are context, not claims to
# validate. They remain visible to the LLM without consuming validation slots
# or producing evidence rows.
CONTEXT_ONLY_SIGNALS = {
    "economic_development_park",
    "tax_distress",
    "penndot_project",
    "growth_area",
    "development_overlay",
    "local_traffic_activity",
    "soil_constraint",
    "zoning_constraint",
    "flood_zone",
    "environmental_diligence",
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

    context_signals = [s for s in signals if s["signal_key"] in CONTEXT_ONLY_SIGNALS]
    signals = [s for s in signals if s["signal_key"] not in CONTEXT_ONLY_SIGNALS]

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
        # Dedupe by extraction_id when available so distinct same-day agenda
        # items from the same applicant do not collapse into one record.
        seen = set()
        merged = []
        for p in parcel_procs + entity_procs:
            key = p.get("extraction_id") or (
                p.get("extraction_type"),
                str(p.get("meeting_date", "")),
                p.get("applicant_name"),
                p.get("parcel_reference"),
                p.get("decision"),
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
        "context_signals": context_signals,
    }


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

# Static instruction block. Sent as a byte-identical system message on every
# parcel call so providers with implicit prompt caching can reuse it.
_P2_SYSTEM_TEMPLATE = """You are a real estate intelligence analyst validating development signals for parcels in {county_context}.

Your task: for EACH signal listed under "SIGNALS TO VALIDATE", determine if it is meaningful, stale, misclassified, or irrelevant for THIS specific parcel. Consider how the signals INTERACT — a parcel with overlapping signals tells a different story than any single signal alone.

Rules:
1. Do arithmetic carefully — ratios, percentages, and distances matter for calibration.
2. If a signal label doesn't match its evidence (e.g., active_subdivision for a plan with 0 lots), downgrade it.
3. Consider portfolio and neighbor context — a solo delinquency differs from systemic distress.
4. Never invent facts. If context is missing, note it in reasoning.
5. Return exactly one validation per listed signal, in the same order.

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

# Dynamic per-parcel block. The trailing sentence keeps the word "JSON" in
# the user message (OpenAI-family endpoints require it for json_object).
BATCHED_VALIDATION_USER_TEMPLATE = """PARCEL:
{parcel_section}

ENTITY CONTEXT:
{entity_section}

{optional_sections}

SIGNALS TO VALIDATE ({n_signals} signal{plural}):
{signals_list}

Validate each signal above. Return ONLY the JSON object."""

# Final system string sent to the API (single braces).
BATCHED_VALIDATION_SYSTEM_PROMPT = _P2_SYSTEM_TEMPLATE.format(
    county_context=county_prompt_context()
)


# Prompt version hash — travels with every persisted evidence row so we can
# trace a regression to a specific prompt change without diffing git history.
# Covers both the system and user halves; recompute whenever either changes.
PROMPT_VERSION = _hashlib.sha256(
    (BATCHED_VALIDATION_SYSTEM_PROMPT + "\n\n" + BATCHED_VALIDATION_USER_TEMPLATE).encode("utf-8")
).hexdigest()[:12]


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
    rels = entity.get("relationships", {})
    if rels and isinstance(rels, dict):
        # Normalized form: {"controls": ["Entity A"], "officer_of": ["Entity B"]}
        for rel_type, targets in list(rels.items())[:3]:
            if isinstance(targets, list):
                lines.append(f"Relationship: {rel_type} -> {', '.join(targets)}")
            else:
                lines.append(f"Relationship: {rel_type} -> {targets}")
    elif rels and isinstance(rels, list):
        # Legacy form: [{"related_entity": "...", "relationship_type": "..."}]
        for rel in rels[:3]:
            lines.append(
                f"Relationship: {rel.get('relationship_type', '?')} -> {rel.get('related_entity', '?')}"
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


def _format_context_signals(context_signals: list[dict]) -> str:
    """Render context-only signals as background, not validation targets."""
    if not context_signals:
        return ""
    lines = ["AREA CONTEXT (background only — do NOT validate these):"]
    for s in context_signals:
        evidence = s.get("evidence") or {}
        detail = ", ".join(f"{k}={v}" for k, v in list(evidence.items())[:4])
        lines.append(f"- {s['signal_key']}: {detail}" if detail else f"- {s['signal_key']}")
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

    context_signal_section = _format_context_signals(context.get("context_signals") or [])
    if context_signal_section:
        optional_parts.append(context_signal_section)

    # Returns only the dynamic user block; the static instructions travel
    # as BATCHED_VALIDATION_SYSTEM_PROMPT via the harness system_prompt.
    return BATCHED_VALIDATION_USER_TEMPLATE.format(
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
    output: object, expected_signals: list[dict]
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


# ---------------------------------------------------------------------------
# N-trial voting (ships trust metadata with every persisted validation)
#
# The evaluation summarized by docs/decisions.md showed temperature=0 is NOT
# deterministic on shared LLM APIs — the same parcel can flip validation
# status between runs. The fix is evidence-based voting: run N trials,
# majority-vote status+significance per signal, and persist the agreement
# rate as the native confidence score. Agreement IS the calibration.
#
# SIGNIFICANCE_WEIGHT tunes how much the "strength" of the modal
# significance bends the confidence score upward. A signal with 3/3
# agreement on "high" significance is more trustworthy than 3/3 on "none".
# ---------------------------------------------------------------------------

SIGNIFICANCE_WEIGHT = {
    "high":   1.00,
    "medium": 0.85,
    "low":    0.65,
    "none":   0.50,
}


def merge_trial_validations(
    trials_parsed: list[dict],
    expected_signals: list[dict],
) -> dict:
    """Aggregate N parsed validation runs into a single set with confidence.

    Args:
        trials_parsed: list of ``parse_batched_signal_output`` results, one
            per LLM call. Each must have a ``validations`` list.
        expected_signals: the full set of signals we asked about.

    Returns:
        Dict with:
          * ``validations``: one row per expected signal_key that was
            answered in at least one trial. Each row includes
            ``validation_status``, ``adjusted_significance``, ``reasoning``
            (from the modal trial), and trust metadata: ``n_trials``
            (how many trials returned this signal), ``trial_agreement``
            (modal count / n_trials for this signal), and ``confidence``
            (agreement × significance weight — roughly, how much a
            consumer should trust this row).
          * ``cross_signal_insight``: the modal non-empty insight string.
          * ``missing``: signal_keys that NO trial returned.
          * ``n_trials``: total number of trials supplied.
    """
    n_trials = len(trials_parsed)
    by_key: dict[str, list[dict]] = {}
    for t in trials_parsed:
        for v in t.get("validations", []):
            key = v.get("signal_key")
            if key:
                by_key.setdefault(key, []).append(v)

    merged = []
    missing = []

    for expected in expected_signals:
        key = expected["signal_key"]
        entries = by_key.get(key, [])
        if not entries:
            missing.append(key)
            continue

        statuses = _Counter(v.get("validation_status") for v in entries)
        sigs = _Counter(v.get("adjusted_significance") for v in entries)
        modal_status, modal_count = statuses.most_common(1)[0]
        modal_sig, _ = sigs.most_common(1)[0]

        n_called = len(entries)
        agreement = round(modal_count / n_called, 2) if n_called else 0.0

        # Pick reasoning from any trial that returned the modal status.
        reasoning = next(
            (v.get("reasoning", "") for v in entries
             if v.get("validation_status") == modal_status and v.get("reasoning")),
            entries[0].get("reasoning", ""),
        )
        # Union of all unique key_facts / cross_references across trials.
        key_facts = []
        seen_facts: set = set()
        cross_refs = []
        seen_refs: set = set()
        for v in entries:
            for fact in v.get("key_facts", []) or []:
                if fact and fact not in seen_facts:
                    seen_facts.add(fact)
                    key_facts.append(fact)
            for ref in v.get("cross_references", []) or []:
                frozen = repr(ref) if not isinstance(ref, str) else ref
                if frozen not in seen_refs:
                    seen_refs.add(frozen)
                    cross_refs.append(ref)

        sig_weight = SIGNIFICANCE_WEIGHT.get(modal_sig, 0.5)
        confidence = round(agreement * sig_weight, 2)

        merged.append({
            "signal_key": key,
            "validation_status": modal_status,
            "adjusted_significance": modal_sig,
            "reasoning": reasoning,
            "key_facts": key_facts,
            "cross_references": cross_refs,
            "n_trials": n_called,
            "trial_agreement": agreement,
            "confidence": confidence,
        })

    # Modal cross_signal_insight (pick the most commonly emitted non-empty one).
    insights = _Counter(
        (t.get("cross_signal_insight") or "").strip()
        for t in trials_parsed
        if (t.get("cross_signal_insight") or "").strip()
    )
    cross_insight = insights.most_common(1)[0][0] if insights else ""

    return {
        "validations": merged,
        "cross_signal_insight": cross_insight,
        "missing": missing,
        "n_trials": n_trials,
    }
