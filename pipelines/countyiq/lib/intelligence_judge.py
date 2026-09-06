"""Optional judge model for quarantined intelligence contradictions.

The judge never decides alone. The policy in
:mod:`countyiq.lib.intelligence_autoresolve` chooses a rule default; the judge
either confirms it (the contradiction auto-resolves) or disagrees (a person
reviews it with the judge's reasoning attached). The judge is disabled unless
``COUNTYIQ_JUDGE_MODEL`` is set, and its spend is bounded by
``COUNTYIQ_JUDGE_MAX_COST_USD`` per process using the same reservation ledger
as the paid passes.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from countyiq.lib.llm_harness import HarnessConfig, get_preset_for_model
from countyiq.lib.pass_llm_config import (
    PassSpendBudget,
    PassSpendLimitExceeded,
    _float_env,
)

JUDGE_PASS_NUMBER = 9  # ledger label only; the judge is not a pipeline pass

JUDGE_SYSTEM_PROMPT = """You are an evidence auditor for a county real-estate intelligence system.

Two model runs produced different decisions from the SAME source evidence. Your
job is to say which decision the evidence supports better, or that the evidence
does not settle it.

Rules:
1. Judge only against the SOURCE EVIDENCE block. Do not use outside knowledge.
2. Prefer the decision whose claims are fully supported by the evidence.
   A decision that asserts something the evidence does not show loses, even if
   it sounds more useful.
3. If both decisions are defensible readings of the evidence, answer "unclear".
4. Never rewrite either decision; only choose.

Return ONLY a JSON object:
{"winner": "prior" | "challenger" | "unclear", "confidence": 0.0-1.0, "reason": "one or two sentences citing the evidence"}"""

JUDGE_USER_TEMPLATE = """OUTPUT KIND: {output_kind}

SOURCE EVIDENCE:
{evidence}

PRIOR DECISION:
{prior}

CHALLENGER DECISION:
{challenger}

Which decision does the source evidence support better? Return ONLY the JSON object."""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "winner": {"type": "string", "enum": ["prior", "challenger", "unclear"]},
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": ["winner", "confidence", "reason"],
    "additionalProperties": False,
}

_MAX_EVIDENCE_CHARS = 24_000
_MAX_DECISION_CHARS = 6_000


@dataclass(frozen=True)
class JudgeVerdict:
    model: str
    winner: str  # prior | challenger | unclear
    confidence: float
    reason: str


def judge_model() -> str | None:
    value = os.environ.get("COUNTYIQ_JUDGE_MODEL", "").strip()
    return value or None


def judge_enabled() -> bool:
    return judge_model() is not None


_budget: PassSpendBudget | None = None


def _spend_budget() -> PassSpendBudget:
    global _budget
    if _budget is None:
        max_cost = _float_env("COUNTYIQ_JUDGE_MAX_COST_USD")
        if max_cost is None or max_cost <= 0:
            raise PassSpendLimitExceeded(
                "COUNTYIQ_JUDGE_MAX_COST_USD must be a positive dollar limit when "
                "COUNTYIQ_JUDGE_MODEL is set"
            )
        _budget = PassSpendBudget(
            JUDGE_PASS_NUMBER, max_cost, limit_label="COUNTYIQ_JUDGE_MAX_COST_USD"
        )
    return _budget


def build_judge_config() -> HarnessConfig:
    model = judge_model()
    if model is None:
        raise RuntimeError("COUNTYIQ_JUDGE_MODEL is not set")
    preset = get_preset_for_model(model, thinking=False, reasoning_task=True)
    effort = (
        os.environ.get("COUNTYIQ_JUDGE_REASONING_EFFORT", "").strip().lower()
        or "medium"
    )
    return HarnessConfig(
        model_path=model,
        max_tokens=1_500,
        archive_label="contradiction_judge",
        reasoning_effort=effort,
        json_schema=JUDGE_SCHEMA,
        schema_name="contradiction_judge",
        system_prompt=JUDGE_SYSTEM_PROMPT,
        max_price_prompt=_float_env("COUNTYIQ_MAX_PRICE_PROMPT"),
        max_price_completion=_float_env("COUNTYIQ_MAX_PRICE_COMPLETION"),
        zdr=os.environ.get("COUNTYIQ_ZDR", "").strip().lower()
        in {"1", "true", "yes", "on"},
        **preset,
    )


def _trim(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 15] + "\n…[truncated]"


def build_judge_prompt(
    *,
    output_kind: str,
    evidence_text: str,
    prior_decision: object,
    challenger_decision: object,
) -> str:
    return JUDGE_USER_TEMPLATE.format(
        output_kind=output_kind,
        evidence=_trim(
            evidence_text or "(no source evidence could be gathered)",
            _MAX_EVIDENCE_CHARS,
        ),
        prior=_trim(
            json.dumps(prior_decision, indent=1, default=str, sort_keys=True),
            _MAX_DECISION_CHARS,
        ),
        challenger=_trim(
            json.dumps(challenger_decision, indent=1, default=str, sort_keys=True),
            _MAX_DECISION_CHARS,
        ),
    )


def parse_judge_output(output: object) -> tuple[str, float, str] | None:
    if not isinstance(output, dict):
        return None
    winner = str(output.get("winner") or "").strip().lower()
    if winner not in {"prior", "challenger", "unclear"}:
        return None
    try:
        confidence = float(output.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    reason = str(output.get("reason") or "").strip()
    return winner, confidence, reason


def ask_judge(
    *,
    contradiction_id: int,
    output_kind: str,
    evidence_text: str,
    prior_decision: object,
    challenger_decision: object,
) -> JudgeVerdict | None:
    """Call the judge once. Returns None when disabled, over budget, or invalid."""

    if not judge_enabled():
        return None
    from countyiq.lib.llm_harness import invoke_with_retry

    config = build_judge_config()
    prompt = build_judge_prompt(
        output_kind=output_kind,
        evidence_text=evidence_text,
        prior_decision=prior_decision,
        challenger_decision=challenger_decision,
    )
    budget = _spend_budget()
    reservation = budget.reserve(config, prompt, retries=1, pdf_bytes=None)
    try:
        result = invoke_with_retry(
            config, prompt, retries=1, archive_key=f"contradiction:{contradiction_id}"
        )
    except Exception:
        budget.block_unverified(
            reservation, "judge call failed before usage.cost was returned"
        )
        raise
    budget.record(result, reservation)
    if not result.success:
        return None
    parsed = parse_judge_output(result.parsed)
    if parsed is None:
        return None
    winner, confidence, reason = parsed
    return JudgeVerdict(
        model=config.model_path, winner=winner, confidence=confidence, reason=reason
    )
