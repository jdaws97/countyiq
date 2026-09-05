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
import json

from countyiq.lib.county_config import county_prompt_context
from countyiq.lib.prompt_prefix import CITATION_FORMAT_BLOCK, PASS3B_FIELD_CONTRACT
from countyiq.lib.signal_policy import INTERPRETIVE_SIGNAL_KEYS_SQL

# Static instruction block. Sent as a byte-identical system message on every
# rollup call so providers with implicit prompt caching can reuse it.
_P3B_SYSTEM_TEMPLATE = """You are summarizing documented portfolio activity in {county_context}. Help a customer verify ownership, concentration, material changes, and missing evidence. Do not recommend buying an owner out or competing with them.

TASKS:
0. Set urgency to none. Do not infer seller motivation, willingness to sell, beneficial ownership, financing, or development intent. A strategy other than unclear requires explicit longitudinal records. State missing evidence and a concrete verification step.
1. Identify the portfolio strategy: accumulator | flipper | holder | distressed | institutional | unclear.
2. Identify concentration risk (geographic clustering, asset class concentration, timing).
3. Identify the single biggest pattern an outside investor should notice (e.g., "3 of 6 parcels have recorded tax claims; seller motivation is unknown").
4. Commit to a recommendation: investigate | watch | insufficient_evidence. Investigate requires a specific documented portfolio activity and a concrete unresolved question, such as verifying repeated acquisitions or recorded claims across parcels. Watch a documented change without corroborated activity needing follow-up now. Use insufficient_evidence for static concentration, neighboring ownership, or missing records alone. A generic suggestion to check deeds or zoning does not justify investigation. Watching is valid at any evidence strength. Investigate means verify the records, never buy or compete.
5. Output confidence in [0.0, 1.0] for the recommendation.
6. concentration_notes, key_pattern, top_risk, and narrative must each cite
   at least one listed signal as [Signal: key] and/or one listed parcel as
   [Parcel: PIDN]; end each factual sentence with its marker. Copy
   identifiers exactly and include every used identifier in
   citations/parcel_citations.

Return ONE JSON object:
{{
  "portfolio_strategy":  "accumulator|flipper|holder|distressed|institutional|unclear",
  "concentration_notes": "1 cited sentence",
  "key_pattern":         "1-2 cited sentences naming the portfolio-level pattern",
  "recommendation":      "investigate|watch|insufficient_evidence",
  "urgency":             "none",
  "top_risk":            "1 cited sentence",
  "evidence_strength":   "strong|moderate|weak",
  "confidence":          <float in [0.0, 1.0]>,
  "narrative": "1-2 short paragraph portfolio activity summary citing signals as [Signal: key] and parcels as [Parcel: PIDN]. Must be consistent with the structured fields above.",
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

# Final system string sent to the API (single braces). The static field
# contract and citation-format blocks restate the enforced contract and push
# the byte-identical prefix past the provider caching minimum
# (prompt_prefix.py). pass_schemas imports this module, so the schema itself
# cannot be rendered here.
OWNER_ROLLUP_SYSTEM_PROMPT = (
    _P3B_SYSTEM_TEMPLATE.format(county_context=county_prompt_context())
    + "\n\n"
    + PASS3B_FIELD_CONTRACT
    + "\n\n"
    + CITATION_FORMAT_BLOCK
)


# Covers both the system and user halves; recompute whenever either changes.
PROMPT_VERSION = _hashlib.sha256(
    (OWNER_ROLLUP_SYSTEM_PROMPT + "\n\n" + OWNER_ROLLUP_USER_TEMPLATE).encode("utf-8")
).hexdigest()[:12]


# Vocabulary clamps for safe parsing.
VALID_STRATEGIES     = {"accumulator", "flipper", "holder", "distressed", "institutional", "unclear"}
VALID_RECOMMENDATIONS = {"investigate", "watch", "insufficient_evidence"}
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

OWNERS_NEEDING_BRIEFS_QUERY = f"""
    -- All owners with ≥3 parcels under any alpha signal. Python's immutable
    -- source/model/prompt hash skips unchanged owners; selecting the full
    -- eligible set ensures prompt or model changes are not hidden by timestamps.
    -- Briefs join on canonical_name: owner_id is stable across rebuilds
    -- now, but canonical_name also survives cluster re-merges where a
    -- portfolio's owner row is replaced by a merged one.
    SELECT o.owner_id, o.canonical_name
    FROM public.owners o
    JOIN public.owner_source_links osl
         ON osl.owner_id = o.owner_id AND osl.source_type = 'parcel'
    JOIN public.evidence e
         ON e.pidn = osl.source_id
    WHERE e.validation_status IN ('confirmed', 'upgraded', 'downgraded')
      AND e.signal_key IN ({INTERPRETIVE_SIGNAL_KEYS_SQL})
      AND e.adjusted_significance IN ('high', 'medium')
    GROUP BY o.owner_id, o.canonical_name
    HAVING COUNT(DISTINCT osl.source_id) >= 3
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


PORTFOLIO_EVIDENCE_QUERY = f"""
    SELECT e.pidn, e.signal_key, e.active_inference_id, e.validation_status,
           e.adjusted_significance,
           e.evidence_data, e.validated_at, e.confidence,
           p.municipality
    FROM public.evidence e
    LEFT JOIN staging.parcels p ON p.pidn = e.pidn AND p.valid_to IS NULL
    WHERE e.pidn = ANY(%(pidns)s)
      AND e.signal_key IN ({INTERPRETIVE_SIGNAL_KEYS_SQL})
      AND e.validation_status IN ('confirmed', 'upgraded', 'downgraded')
      AND e.adjusted_significance IN ('high', 'medium', 'low')
    ORDER BY e.pidn, e.signal_key
"""


UPSERT_OWNER_BRIEF = """
    INSERT INTO public.owner_briefs
        (canonical_name, owner_id, brief_text, portfolio_strategy,
         concentration_notes,
         key_pattern, recommendation, urgency, top_risk, evidence_strength,
         citations, parcel_citations, n_parcels,
         model_version, prompt_version, n_trials, trial_agreement, confidence,
         pass_metadata, generated_at, active_inference_id)
    VALUES
        (%(canonical_name)s, %(owner_id)s, %(brief_text)s, %(portfolio_strategy)s,
         %(concentration_notes)s, %(key_pattern)s,
         %(recommendation)s, %(urgency)s, %(top_risk)s, %(evidence_strength)s,
         %(citations)s::jsonb, %(parcel_citations)s::jsonb, %(n_parcels)s,
         %(model_version)s, %(prompt_version)s,
         %(n_trials)s, %(trial_agreement)s, %(confidence)s,
         %(pass_metadata)s::jsonb, %(generated_at)s, %(active_inference_id)s)
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
        generated_at          = EXCLUDED.generated_at,
        active_inference_id   = EXCLUDED.active_inference_id
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
            f"  - Evidence refs: [Signal: {s['signal_key']}] [Parcel: {pidn}]\n"
            f"    {s['signal_key']}: {s['validation_status']} "
            f"({s['adjusted_significance']}) — "
            f"source="
            f"{json.dumps(s.get('evidence_data') or {}, sort_keys=True, default=str)}"
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
        "recommendation":      _clamp_enum(output.get("recommendation"), VALID_RECOMMENDATIONS, "insufficient_evidence"),
        "urgency":             _clamp_enum(output.get("urgency"), VALID_URGENCY, "none"),
        "top_risk":            output.get("top_risk") or "",
        "evidence_strength":   _clamp_enum(output.get("evidence_strength"), VALID_EVIDENCE, "moderate"),
        "confidence":          _clamp_float_01(output.get("confidence")),
        "citations":           [c for c in citations if isinstance(c, str)],
        "parcel_citations":    [c for c in parcel_citations if isinstance(c, str)],
    }


def owner_brief_context(owner: dict, evidence_rows: list[dict]) -> dict:
    """Stable non-signal facts supplied to the portfolio brief prompt."""
    return {
        **owner,
        "signal_municipalities": {
            row["pidn"]: row.get("municipality") or None
            for row in evidence_rows
        },
    }
