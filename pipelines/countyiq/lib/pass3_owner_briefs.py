"""Owner-level brief generation.

Writes one portfolio-level brief per owner with enough parcels + alpha
signals for portfolio reasoning. Consumes ``public.evidence`` from Pass 2
(validated signals per parcel) and produces one record per owner in
``public.owner_briefs``.

See ``docs/decisions.md`` for why this
exists: owner rollups scored 4.75 vs 1.00 on pattern_insight versus
reading N parcel briefs separately.
"""
from __future__ import annotations

import hashlib as _hashlib

from countyiq.lib.county_config import county_prompt_context

# Static instruction block. Sent as a byte-identical system message on every
# rollup call so providers with implicit prompt caching can reuse it.
_P3B_SYSTEM_TEMPLATE = """You are analyzing a real-estate investor's entire portfolio of parcels in {county_context}. Your job is to write a single PORTFOLIO-level intelligence brief for another investor deciding whether the owner is a compelling acquisition target (buying them out) or competitor to watch.

TASKS:
1. Identify the portfolio strategy: accumulator | flipper | holder | distressed | institutional | unclear.
2. Identify concentration risk (geographic clustering, asset class concentration, timing).
3. Identify the single biggest pattern an outside investor should notice (e.g., "3 of 6 parcels show tax distress — owner appears to be deleveraging").
4. Commit to a recommendation: pursue_acquisition | monitor | compete | none. Only emit "monitor" when evidence_strength is "weak" — otherwise commit.
5. Output confidence in [0.0, 1.0] for the recommendation.

Return ONE JSON object:
{{
  "portfolio_strategy":  "accumulator|flipper|holder|distressed|institutional|unclear",
  "concentration_notes": "1 sentence",
  "key_pattern":         "1-2 sentences naming the portfolio-level pattern",
  "recommendation":      "pursue_acquisition|monitor|compete|none",
  "urgency":             "urgent_30d|near_term_90d|long_term_12mo|none",
  "top_risk":            "1 sentence",
  "evidence_strength":   "strong|moderate|weak",
  "confidence":          <float in [0.0, 1.0]>,
  "narrative": "3-5 paragraph portfolio brief citing signals as [Signal: key] and parcels as [Parcel: PIDN]. Must be consistent with the structured fields above.",
  "citations":        ["signal_key_1", "signal_key_2"],
  "parcel_citations": ["PIDN1", "PIDN2"]
}}

Return ONLY the JSON object."""

# Dynamic per-owner block. The trailing sentence keeps the word "JSON" in
# the user message (OpenAI-family endpoints require it for json_object).
OWNER_ROLLUP_USER_TEMPLATE = """OWNER: {owner_name} ({entity_type})
PORTFOLIO SIZE: {n_parcels} parcels
MUNICIPALITIES: {municipalities}

PER-PARCEL SIGNAL EVIDENCE (from Pass 2 validation):
{portfolio_signals}

Write the portfolio brief for this owner. Return ONLY the JSON object."""

# Final system string sent to the API (single braces).
OWNER_ROLLUP_SYSTEM_PROMPT = _P3B_SYSTEM_TEMPLATE.format(
    county_context=county_prompt_context()
)


# Covers both the system and user halves; recompute whenever either changes.
PROMPT_VERSION = _hashlib.sha256(
    (OWNER_ROLLUP_SYSTEM_PROMPT + "\n\n" + OWNER_ROLLUP_USER_TEMPLATE).encode("utf-8")
).hexdigest()[:12]


# Vocabulary clamps for safe parsing.
VALID_STRATEGIES     = {"accumulator", "flipper", "holder", "distressed", "institutional", "unclear"}
VALID_RECOMMENDATIONS = {"pursue_acquisition", "monitor", "compete", "none"}
VALID_URGENCY         = {"urgent_30d", "near_term_90d", "long_term_12mo", "none"}
VALID_EVIDENCE        = {"strong", "moderate", "weak"}


def _clamp_enum(value: object, valid: set[str], default: str | None) -> str | None:
    if isinstance(value, str) and value in valid:
        return value
    return default


def _clamp_float_01(value: object) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:
        return None
    return max(0.0, min(1.0, f))


# ---------------------------------------------------------------------------
# SQL to pull a single owner's portfolio + validated signals
# ---------------------------------------------------------------------------

OWNERS_NEEDING_BRIEFS_QUERY = """
    -- Owners with ≥3 parcels under any alpha signal, and where the
    -- owner_briefs row is missing or older than the freshest Pass 2
    -- evidence. Alpha signals = ones the experiment-grade evidence
    -- shows actually drive investor decisions.
    -- Briefs join on canonical_name: owner_id is stable across rebuilds
    -- now, but canonical_name also survives cluster re-merges where a
    -- portfolio's owner row is replaced by a merged one.
    SELECT o.owner_id, o.canonical_name
    FROM public.owners o
    JOIN public.owner_source_links osl
         ON osl.owner_id = o.owner_id AND osl.source_type = 'parcel'
    JOIN public.evidence e
         ON e.pidn = osl.source_id
    LEFT JOIN public.owner_briefs ob ON ob.canonical_name = o.canonical_name
    WHERE e.adjusted_significance IN ('high', 'medium')
    GROUP BY o.owner_id, o.canonical_name, ob.canonical_name, ob.generated_at
    HAVING COUNT(DISTINCT osl.source_id) >= 3
       AND (
           ob.canonical_name IS NULL
           OR MAX(e.validated_at) > ob.generated_at
       )
    ORDER BY o.owner_id
"""


OWNER_PORTFOLIO_QUERY = """
    SELECT o.owner_id, o.canonical_name, o.entity_type,
           array_agg(DISTINCT osl.source_id ORDER BY osl.source_id) AS pidns,
           COUNT(DISTINCT osl.source_id) AS n_parcels
    FROM public.owners o
    JOIN public.owner_source_links osl
         ON osl.owner_id = o.owner_id AND osl.source_type = 'parcel'
    WHERE o.owner_id = %(owner_id)s
    GROUP BY o.owner_id, o.canonical_name, o.entity_type
"""


PORTFOLIO_EVIDENCE_QUERY = """
    SELECT e.pidn, e.signal_key, e.validation_status,
           e.adjusted_significance, e.validation_reasoning,
           e.validated_at, e.confidence,
           p.municipality
    FROM public.evidence e
    LEFT JOIN staging.parcels p ON p.pidn = e.pidn AND p.valid_to IS NULL
    WHERE e.pidn = ANY(%(pidns)s)
    ORDER BY e.pidn, e.signal_key
"""


UPSERT_OWNER_BRIEF = """
    INSERT INTO public.owner_briefs
        (canonical_name, owner_id, brief_text, portfolio_strategy,
         concentration_notes,
         key_pattern, recommendation, urgency, top_risk, evidence_strength,
         citations, parcel_citations, n_parcels,
         model_version, prompt_version, n_trials, trial_agreement, confidence,
         pass_metadata, generated_at)
    VALUES
        (%(canonical_name)s, %(owner_id)s, %(brief_text)s, %(portfolio_strategy)s,
         %(concentration_notes)s, %(key_pattern)s,
         %(recommendation)s, %(urgency)s, %(top_risk)s, %(evidence_strength)s,
         %(citations)s::jsonb, %(parcel_citations)s::jsonb, %(n_parcels)s,
         %(model_version)s, %(prompt_version)s,
         %(n_trials)s, %(trial_agreement)s, %(confidence)s,
         %(pass_metadata)s::jsonb, %(generated_at)s)
    ON CONFLICT (canonical_name)
    DO UPDATE SET
        owner_id              = EXCLUDED.owner_id,
        brief_text            = EXCLUDED.brief_text,
        portfolio_strategy    = EXCLUDED.portfolio_strategy,
        concentration_notes   = EXCLUDED.concentration_notes,
        key_pattern           = EXCLUDED.key_pattern,
        recommendation        = EXCLUDED.recommendation,
        urgency               = EXCLUDED.urgency,
        top_risk              = EXCLUDED.top_risk,
        evidence_strength     = EXCLUDED.evidence_strength,
        citations             = EXCLUDED.citations,
        parcel_citations      = EXCLUDED.parcel_citations,
        n_parcels             = EXCLUDED.n_parcels,
        model_version         = EXCLUDED.model_version,
        prompt_version        = EXCLUDED.prompt_version,
        n_trials              = EXCLUDED.n_trials,
        trial_agreement       = EXCLUDED.trial_agreement,
        confidence            = EXCLUDED.confidence,
        brief_version         = public.owner_briefs.brief_version + 1,
        pass_metadata         = EXCLUDED.pass_metadata,
        generated_at          = EXCLUDED.generated_at
"""


def _format_portfolio_evidence(rows: list[dict]) -> str:
    """Group evidence rows by parcel for the prompt."""
    by_pidn: dict[str, list[dict]] = {}
    for r in rows:
        by_pidn.setdefault(r["pidn"], []).append(r)

    chunks = []
    for pidn, sigs in by_pidn.items():
        muni = sigs[0].get("municipality") or "?"
        sig_lines = [
            f"  - {s['signal_key']}: {s['validation_status']} "
            f"({s['adjusted_significance']}) — "
            f"{(s.get('validation_reasoning') or '')[:180]}"
            for s in sigs
        ]
        chunks.append(f"### Parcel {pidn} — {muni}\n" + "\n".join(sig_lines))
    return "\n\n".join(chunks)


def build_owner_rollup_prompt(owner: dict, evidence_rows: list[dict]) -> str:
    municipalities = sorted({
        r.get("municipality") for r in evidence_rows if r.get("municipality")
    })
    # Returns only the dynamic user block; the static instructions travel
    # as OWNER_ROLLUP_SYSTEM_PROMPT via the harness system_prompt.
    return OWNER_ROLLUP_USER_TEMPLATE.format(
        owner_name=owner.get("canonical_name", "?"),
        entity_type=owner.get("entity_type", "unknown"),
        n_parcels=owner.get("n_parcels", 0),
        municipalities=", ".join(municipalities) or "(unknown)",
        portfolio_signals=_format_portfolio_evidence(evidence_rows),
    )


def parse_owner_brief_output(output: object) -> dict:
    if not isinstance(output, dict):
        return {"error": "Output is not a dict"}
    narrative = output.get("narrative") or output.get("brief")
    if not narrative:
        return {"error": "Missing narrative"}

    citations = output.get("citations") or []
    if not isinstance(citations, list):
        citations = []
    parcel_citations = output.get("parcel_citations") or []
    if not isinstance(parcel_citations, list):
        parcel_citations = []

    return {
        "brief_text":          narrative,
        "portfolio_strategy":  _clamp_enum(output.get("portfolio_strategy"), VALID_STRATEGIES, "unclear"),
        "concentration_notes": output.get("concentration_notes") or "",
        "key_pattern":         output.get("key_pattern") or "",
        "recommendation":      _clamp_enum(output.get("recommendation"), VALID_RECOMMENDATIONS, "monitor"),
        "urgency":             _clamp_enum(output.get("urgency"), VALID_URGENCY, "none"),
        "top_risk":            output.get("top_risk") or "",
        "evidence_strength":   _clamp_enum(output.get("evidence_strength"), VALID_EVIDENCE, "moderate"),
        "confidence":          _clamp_float_01(output.get("confidence")),
        "citations":           [c for c in citations if isinstance(c, str)],
        "parcel_citations":    [c for c in parcel_citations if isinstance(c, str)],
    }
