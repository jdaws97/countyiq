"""Pass-level OpenRouter configuration helpers for the CountyIQ LLM pipeline."""

from __future__ import annotations

import dataclasses
import os
from collections.abc import Callable

from countyiq.lib.llm_harness import HarnessConfig, get_preset_for_model


class PassHarnessUnavailable(RuntimeError):
    """The pass LLM harness cannot be resolved (missing import or model)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _bool_env(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


# Evidence-backed per-pass model defaults.
# See ``docs/decisions.md`` for the eval evidence (expN fresh-data eval,
# expO Pass 3/4, luna effort sweep + stability probe, all 2026-08-06).
#
# FINAL LINEUP (2026-08-06, consolidation-first per the owner's
# model-churn concern): openai/gpt-5.6-luna for Passes 0-4.
# - Pass 0: perfect on positive+negative PDF controls (incumbent
#   gemini-2.5-flash-lite hallucinated proposals from a re-org agenda);
#   native file input.
# - Pass 1: 0 fabricated PIDNs, 20 abst/17 rej discipline, 20s; run at
#   effort=high (sweep: high adds decisiveness, xhigh regresses) with
#   N=3 partition voting (stability probe: 97% pair agreement).
# - Pass 2: 15-1 vs mercury-2 blind-judged. deepseek/deepseek-v4-flash-0731
#   stays the documented cost fallback (~$9.15/mo vs ~$20/mo at full
#   volume) if the bill matters more than lineup simplicity.
# - Pass 3: won 8/8 salvaged pairs vs minimax (expO), overturning the
#   provisional minimax pick.
# - Pass 4: split 1-1 vs minimax on direct adjudication; stays luna for
#   consolidation, provisional pending county-wide backfill.
# minimax/minimax-m3 is the cross-vendor second source (top-2 on P1/P2/P4).
#
# Override with COUNTYIQ_PASS{N}_MODEL env var when needed.
_PASS_MODEL_DEFAULTS = {
    0: "openai/gpt-5.6-luna",  # PDF extraction — native file input, perfect on controls
    1: "openai/gpt-5.6-luna",  # entity verification — effort=high + N=3 voting
    2: "openai/gpt-5.6-luna",  # signal validation — ds-v4-flash-0731 is the cost fallback
    3: "openai/gpt-5.6-luna",  # briefs — expO 8/8 vs minimax
    4: "openai/gpt-5.6-luna",  # county narratives — provisional (see decisions.md)
}

# Per-pass reasoning_effort defaults.
# Pass 1: "high" — luna effort sweep 2026-08-06 (high adds +6 rejections
#   at 44s; xhigh costs 27% more for default-level decisiveness).
# Pass 2: "low" — exp H; higher efforts blow up output tokens with no
#   quality gain.
_PASS_REASONING_DEFAULTS = {
    1: "high",
    2: "low",
}


def resolve_pass_model(pass_number: int) -> str | None:
    """Resolve the OpenRouter model slug for a pass.

    Precedence:
    1. ``COUNTYIQ_PASS{N}_MODEL`` environment variable (deliberate override).
    2. Per-pass default from the experimental Pareto frontier
       (see ``_PASS_MODEL_DEFAULTS``).
    3. ``COUNTYIQ_OPENROUTER_MODEL`` global env var (catch-all fallback).

    The global var deliberately ranks BELOW the per-pass defaults: it used
    to shadow them, which silently replaced every evidence-backed model
    choice in any environment built from ``.env.example``.
    """
    return (
        os.environ.get(f"COUNTYIQ_PASS{pass_number}_MODEL")
        or _PASS_MODEL_DEFAULTS.get(pass_number)
        or os.environ.get("COUNTYIQ_OPENROUTER_MODEL")
    )


def resolve_pass_thinking(pass_number: int, default: bool) -> bool:
    """Resolve the thinking toggle for a pass with a global fallback."""
    if f"COUNTYIQ_PASS{pass_number}_THINKING" in os.environ:
        return _bool_env(f"COUNTYIQ_PASS{pass_number}_THINKING", default)
    return _bool_env("COUNTYIQ_THINKING", default)


def resolve_pass_enabled(pass_number: int) -> bool:
    """Return whether a pass may make runtime LLM calls.

    Every paid pass is opt-in. Possessing an API key or materializing an
    enrichment group must never authorize spend; the operator must explicitly
    enable the specific pass after reviewing a fresh estimate.
    """
    return _bool_env(f"COUNTYIQ_PASS{pass_number}_ENABLED", False)


def resolve_pass_item_limit(pass_number: int) -> int:
    """Return a finite work-item ceiling for one explicitly enabled pass.

    The unit is the pass's outer work item (document, entity cluster, parcel,
    owner, or Pass 4 scan result). Invalid and non-positive values fall back to
    25; there is intentionally no environment value meaning "unbounded".
    """
    limit = _int_env(f"COUNTYIQ_PASS{pass_number}_MAX_ITEMS", 25)
    return limit if limit > 0 else 25


class PassItemBudget:
    """Finite budget for changed outer work items in one asset run.

    Callers claim only after their input-hash skip. That avoids a subtle
    starvation bug where an unchanged first page could consume the cap forever
    and prevent later changed records from being reached.
    """

    def __init__(self, pass_number: int) -> None:
        self.pass_number = pass_number
        self.limit = resolve_pass_item_limit(pass_number)
        self.claimed = 0
        self.denied = 0
        self._warned = False

    def claim(self, log, *, label: str) -> bool:
        if self.claimed >= self.limit:
            self.denied += 1
            if not self._warned:
                log.warning(
                    "Pass %d reached its %d-item run cap; remaining %s are deferred",
                    self.pass_number, self.limit, label,
                )
                self._warned = True
            return False
        self.claimed += 1
        return True


def resolve_pass_reasoning_effort(pass_number: int) -> str | None:
    """Resolve per-pass ``reasoning_effort`` ('low' | 'medium' | 'high').

    Precedence: ``COUNTYIQ_PASS{N}_REASONING_EFFORT`` env > per-pass
    default (see ``_PASS_REASONING_DEFAULTS``). Returns ``None`` when
    unset — the caller should omit the ``reasoning`` payload field
    rather than pass ``None`` explicitly.
    """
    value = os.environ.get(f"COUNTYIQ_PASS{pass_number}_REASONING_EFFORT")
    if value:
        return value.strip().lower() or None
    return _PASS_REASONING_DEFAULTS.get(pass_number)


def _float_env(name: str) -> float | None:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def build_pass_harness_config(
    *,
    pass_number: int,
    archive_label: str,
    reasoning_task: bool,
    default_max_tokens: int,
    default_thinking: bool = False,
    json_schema: dict | None = None,
    schema_name: str = "response",
    system_prompt: str | None = None,
    pdf_engine: str | None = None,
    require_enabled: bool = True,
) -> HarnessConfig | None:
    """Return a configured OpenRouter HarnessConfig for a pass.

    Global harness knobs resolved from env:
    - COUNTYIQ_STRICT_SCHEMA (default on): pass a strict json_schema
      through to OpenRouter; providers lacking support trigger a one-shot
      json_object fallback inside the harness.
    - COUNTYIQ_MAX_PRICE_PROMPT / COUNTYIQ_MAX_PRICE_COMPLETION ($/M):
      provider price ceilings so promotional rates can't expire into a
      silently larger bill.
    - COUNTYIQ_ZDR: restrict routing to zero-data-retention endpoints.
    """
    if require_enabled and not resolve_pass_enabled(pass_number):
        return None

    model_path = resolve_pass_model(pass_number)
    if not model_path:
        return None

    thinking = resolve_pass_thinking(pass_number, default_thinking)
    max_tokens = _int_env(f"COUNTYIQ_PASS{pass_number}_MAX_TOKENS", default_max_tokens)

    preset = get_preset_for_model(
        model_path,
        thinking=thinking,
        reasoning_task=reasoning_task,
    )

    strict_enabled = _bool_env("COUNTYIQ_STRICT_SCHEMA", True)

    return HarnessConfig(
        model_path=model_path,
        max_tokens=max_tokens,
        thinking=thinking,
        archive_label=archive_label,
        reasoning_effort=resolve_pass_reasoning_effort(pass_number),
        json_schema=json_schema if strict_enabled else None,
        schema_name=schema_name,
        system_prompt=system_prompt,
        pdf_engine=pdf_engine,
        max_price_prompt=_float_env("COUNTYIQ_MAX_PRICE_PROMPT"),
        max_price_completion=_float_env("COUNTYIQ_MAX_PRICE_COMPLETION"),
        zdr=_bool_env("COUNTYIQ_ZDR", False),
        **preset,
    )


def resolve_escalation_config(
    base: HarnessConfig,
    pass_number: int,
) -> HarnessConfig | None:
    """Build the escalation-tier config for a pass, if one is configured.

    ``COUNTYIQ_PASS{N}_ESCALATION_MODEL`` names a (typically frontier-class)
    model that re-processes only the items the primary model abstained on —
    the cascade from docs/open-items.md. Sampling presets are re-derived for
    the escalation model; everything else (schema, archive label, prices,
    system prompt) carries over from the base config.
    ``COUNTYIQ_PASS{N}_ESCALATION_REASONING_EFFORT`` optionally overrides
    the effort for the escalation call. Returns None when unset.
    """
    model = os.environ.get(f"COUNTYIQ_PASS{pass_number}_ESCALATION_MODEL")
    if not model or not model.strip():
        return None
    model = model.strip()

    preset = get_preset_for_model(model, thinking=base.thinking, reasoning_task=True)
    effort_env = os.environ.get(
        f"COUNTYIQ_PASS{pass_number}_ESCALATION_REASONING_EFFORT"
    )
    effort = (effort_env.strip().lower() or None) if effort_env else base.reasoning_effort

    return dataclasses.replace(
        base,
        model_path=model,
        model_family="auto",
        reasoning_effort=effort,
        **preset,
    )


def resolve_pass_harness(
    log,
    *,
    pass_number: int,
    archive_label: str,
    default_max_tokens: int,
    reasoning_task: bool = True,
    default_thinking: bool = False,
    json_schema: dict | None = None,
    schema_name: str = "response",
    system_prompt: str | None = None,
    pdf_engine: str | None = None,
) -> tuple[HarnessConfig, Callable]:
    """Resolve a pass's harness config and the ``invoke_with_retry`` callable.

    Handles the lazy ``llm_harness`` import and the model-env lookup. The
    caller should catch :class:`PassHarnessUnavailable` and emit the
    pass's ``_skipped_result`` using ``exc.reason``.
    """
    try:
        from countyiq.lib.llm_harness import invoke_with_retry
    except ImportError as exc:
        log.warning("llm_harness import failed (%s) — skipping", exc)
        raise PassHarnessUnavailable("llm_harness import failed") from exc

    config = build_pass_harness_config(
        pass_number=pass_number,
        archive_label=archive_label,
        reasoning_task=reasoning_task,
        default_max_tokens=default_max_tokens,
        default_thinking=default_thinking,
        json_schema=json_schema,
        schema_name=schema_name,
        system_prompt=system_prompt,
        pdf_engine=pdf_engine,
    )
    if config is None:
        log.info(
            "Pass %d is disabled or no model is configured — skipping pass %d.",
            pass_number,
            pass_number,
        )
        raise PassHarnessUnavailable("pass disabled or no model configured")

    log.info("Pass %d: OpenRouter model=%s", pass_number, config.model_path)
    return config, invoke_with_retry
