"""Pass-level OpenRouter configuration helpers for the CountyIQ LLM pipeline."""

from __future__ import annotations

import dataclasses
import math
import os
import threading
from collections.abc import Callable
from pathlib import Path

from countyiq.lib.backfill_authorization import (
    BackfillAuthorization,
    BackfillAuthorizationError,
)
from countyiq.lib.llm_harness import HarnessConfig, get_preset_for_model


class PassHarnessUnavailable(RuntimeError):
    """The pass LLM harness cannot be resolved (missing import or model)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class PassSpendLimitExceeded(RuntimeError):
    """Raised before a call that could exceed the explicit pass budget."""


class SpendReservation(float):
    """Float-compatible reservation carrying its durable-ledger identifier."""

    def __new__(cls, amount: float, authorization_id: str | None = None):
        instance = super().__new__(cls, amount)
        instance.authorization_id = authorization_id
        return instance


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


def resolve_pass_item_limit(pass_number: int) -> int | None:
    """Return the work-item ceiling for one explicitly enabled pass.

    The unit is the pass's outer work item (document, entity cluster, parcel,
    owner, or Pass 4 scan result). Invalid and non-positive values fall back to
    25. Passes 0-3 may explicitly opt into a cost-only backfill: in that mode
    the mandatory dollar reservation ledger, rather than a second item cap,
    stops dispatch.
    """
    if _bool_env(f"COUNTYIQ_PASS{pass_number}_BACKFILL_MODE", False):
        if pass_number == 4:
            raise ValueError("Pass 4 is outside the approved backfill")
        max_cost_usd = _float_env(f"COUNTYIQ_PASS{pass_number}_MAX_COST_USD")
        if max_cost_usd is None or max_cost_usd <= 0:
            raise ValueError(
                f"COUNTYIQ_PASS{pass_number}_BACKFILL_MODE requires a positive "
                f"COUNTYIQ_PASS{pass_number}_MAX_COST_USD"
            )
        return None
    limit = _int_env(f"COUNTYIQ_PASS{pass_number}_MAX_ITEMS", 25)
    return limit if limit > 0 else 25


class PassItemBudget:
    """Budget for changed outer work items in one asset run.

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
        self._lock = threading.Lock()

    @property
    def mode(self) -> str:
        return "dollar_ceiling" if self.limit is None else "item_and_dollar"

    def claim(self, log, *, label: str) -> bool:
        with self._lock:
            if self.limit is None:
                self.claimed += 1
                return True
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


class PassSpendBudget:
    """Pre-call reservation ledger for one paid asset invocation."""

    def __init__(
        self,
        pass_number: int,
        max_cost_usd: float,
        limit_label: str | None = None,
        authorization: BackfillAuthorization | None = None,
    ) -> None:
        if not math.isfinite(max_cost_usd) or max_cost_usd <= 0:
            raise ValueError("max_cost_usd must be positive and finite")
        self.pass_number = pass_number
        self.max_cost_usd = max_cost_usd
        self.authorization = authorization
        self.limit_label = limit_label or f"COUNTYIQ_PASS{pass_number}_MAX_COST_USD"
        self.spent_usd = 0.0
        self.reserved_usd = 0.0
        self.calls = 0
        self.blocked_reason: str | None = None
        # Passes may overlap provider calls (COUNTYIQ_PASS2_CONCURRENCY); the
        # ledger must stay consistent under concurrent reserve/record.
        self._lock = threading.Lock()

    def reserve(
        self,
        config: HarnessConfig,
        prompt: str,
        *,
        retries: int,
        pdf_bytes: bytes | None,
    ) -> SpendReservation:
        amount = estimate_max_pass_call_cost(
            config, prompt, retries=retries, pdf_bytes=pdf_bytes
        )
        with self._lock:
            if self.blocked_reason:
                raise PassSpendLimitExceeded(self.blocked_reason)
            if self.spent_usd + self.reserved_usd + amount > self.max_cost_usd:
                raise PassSpendLimitExceeded(
                    f"Pass {self.pass_number} cost reservation would exceed "
                    f"{self.limit_label}: "
                    f"spent=${self.spent_usd:.6f}, next_max=${amount:.6f}, "
                    f"limit=${self.max_cost_usd:.6f}"
                )
            authorization_id = None
            if self.authorization is not None:
                try:
                    authorization_id = self.authorization.reserve(amount)
                except BackfillAuthorizationError as exc:
                    raise PassSpendLimitExceeded(str(exc)) from exc
            self.reserved_usd += amount
        return SpendReservation(amount, authorization_id)

    def release(self, reservation: SpendReservation) -> None:
        authorization_id = getattr(reservation, "authorization_id", None)
        if self.authorization is not None and authorization_id is not None:
            try:
                self.authorization.cancel(authorization_id)
            except BackfillAuthorizationError as exc:
                with self._lock:
                    self.blocked_reason = (
                        "cumulative authorization could not release a "
                        f"non-dispatched reservation: {exc}"
                    )
                raise PassSpendLimitExceeded(self.blocked_reason) from exc
        with self._lock:
            self._release_locked(reservation)

    def _release_locked(self, reservation: SpendReservation) -> None:
        self.reserved_usd = max(0.0, self.reserved_usd - float(reservation))

    def block_unverified(
        self, reservation: SpendReservation, reason: str
    ) -> None:
        """Conservatively charge a dispatched call whose spend is unknowable."""

        authorization_id = getattr(reservation, "authorization_id", None)
        if self.authorization is not None and authorization_id is not None:
            try:
                self.authorization.forfeit(authorization_id)
            except BackfillAuthorizationError as exc:
                reason = f"{reason}; cumulative authorization update failed: {exc}"
        with self._lock:
            self._release_locked(reservation)
            self.spent_usd += float(reservation)
            self.calls += 1
            self.blocked_reason = reason

    def record(self, result, reservation: SpendReservation) -> str | None:
        """Charge a completed call and return any reason to block later calls.

        A provider-accounting anomaly must never discard the paid response that
        exposed it. The current result remains available to the caller; the
        next reservation fails closed through ``blocked_reason``.
        """
        cost = result.metadata.get("cost")
        if not isinstance(cost, (int, float)):
            reason = (
                "OpenRouter omitted usage.cost; stopping because runtime spend "
                "can no longer be verified"
            )
            self.block_unverified(reservation, reason)
            return reason
        if not math.isfinite(float(cost)) or float(cost) < 0:
            reason = (
                "OpenRouter returned an invalid usage.cost; stopping because "
                "runtime spend can no longer be verified"
            )
            self.block_unverified(reservation, reason)
            return reason
        persistent_reason = None
        authorization_id = getattr(reservation, "authorization_id", None)
        if self.authorization is not None and authorization_id is not None:
            try:
                self.authorization.settle(authorization_id, float(cost))
            except BackfillAuthorizationError as exc:
                persistent_reason = (
                    f"cumulative authorization update failed after dispatch: {exc}"
                )
        with self._lock:
            self._release_locked(reservation)
            self.calls += 1
            self.spent_usd += float(cost)
            if persistent_reason:
                self.blocked_reason = persistent_reason
                return self.blocked_reason
            if (
                float(cost) > float(reservation)
                or self.spent_usd > self.max_cost_usd
            ):
                self.blocked_reason = (
                    f"provider-reported spend exceeded its reservation or pass limit: "
                    f"call=${float(cost):.6f}, "
                    f"reservation=${float(reservation):.6f}, "
                    f"spent=${self.spent_usd:.6f}, limit=${self.max_cost_usd:.6f}"
                )
                return self.blocked_reason
        return None


def estimate_max_pass_call_cost(
    config: HarnessConfig,
    prompt: str,
    *,
    retries: int = 1,
    pdf_bytes: bytes | None = None,
) -> float:
    """Conservative provider-price-bounded reservation for one work item."""

    prices = (config.max_price_prompt, config.max_price_completion)
    if any(
        price is None or not math.isfinite(price) or price <= 0
        for price in prices
    ):
        raise PassSpendLimitExceeded(
            "COUNTYIQ_MAX_PRICE_PROMPT and COUNTYIQ_MAX_PRICE_COMPLETION are "
            "required as positive finite values when a paid pass is enabled"
        )
    characters = len(prompt) + len(config.system_prompt or "")
    prompt_tokens = math.ceil(characters / 3)
    if pdf_bytes is not None:
        prompt_tokens += max(
            _int_env("COUNTYIQ_PASS0_PDF_TOKEN_CEILING", 50_000), 1
        )
    return estimate_reserved_call_cost(
        prompt_tokens=prompt_tokens,
        max_tokens=config.max_tokens,
        max_price_prompt=config.max_price_prompt,
        max_price_completion=config.max_price_completion,
        retries=retries,
    )


def estimate_reserved_call_cost(
    *,
    prompt_tokens: int,
    max_tokens: int,
    max_price_prompt: float,
    max_price_completion: float,
    retries: int = 1,
) -> float:
    """Mirror the runtime reservation math for estimators and tests."""

    attempts = max(int(retries), 0) + 1
    completion_budgets = [max(int(max_tokens), 1)]
    for _ in range(attempts - 1):
        completion_budgets.append(min(completion_budgets[-1] * 2, 16_384))
    maximum = (
        max(int(prompt_tokens), 0) * attempts * max_price_prompt
        + sum(completion_budgets) * max_price_completion
    ) / 1_000_000
    return round(maximum * 1.10 + 0.000001, 9)


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
        parsed = float(value)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


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

    if (
        config.max_price_prompt is None
        or config.max_price_prompt <= 0
        or config.max_price_completion is None
        or config.max_price_completion <= 0
    ):
        raise PassHarnessUnavailable(
            "COUNTYIQ_MAX_PRICE_PROMPT and COUNTYIQ_MAX_PRICE_COMPLETION must "
            "be explicitly set to positive finite values before enabling paid inference"
        )

    max_cost_usd = _float_env(f"COUNTYIQ_PASS{pass_number}_MAX_COST_USD")
    if max_cost_usd is None or max_cost_usd <= 0:
        raise PassHarnessUnavailable(
            f"COUNTYIQ_PASS{pass_number}_MAX_COST_USD must be explicitly set "
            "to a positive dollar limit before enabling paid inference"
        )
    authorization_path = os.environ.get(
        f"COUNTYIQ_PASS{pass_number}_BACKFILL_AUTHORIZATION_FILE", ""
    ).strip()
    if not authorization_path:
        raise PassHarnessUnavailable(
            f"COUNTYIQ_PASS{pass_number}_BACKFILL_AUTHORIZATION_FILE is "
            "required for every paid canary or backfill run"
        )
    try:
        authorization = BackfillAuthorization(
            Path(authorization_path),
            pass_number=pass_number,
            model=config.model_path,
            max_cost_usd=max_cost_usd,
            max_price_prompt=config.max_price_prompt,
            max_price_completion=config.max_price_completion,
        )
        authorization.snapshot()
    except BackfillAuthorizationError as exc:
        raise PassHarnessUnavailable(
            f"invalid cumulative paid-pass authorization: {exc}"
        ) from exc

    spend_budget = PassSpendBudget(
        pass_number,
        max_cost_usd,
        authorization=authorization,
    )

    def invoke_with_budget(call_config, prompt, **kwargs):
        retries = int(kwargs.get("retries", 1))
        reservation = spend_budget.reserve(
            call_config,
            prompt,
            retries=retries,
            pdf_bytes=kwargs.get("pdf_bytes"),
        )
        try:
            result = invoke_with_retry(call_config, prompt, **kwargs)
        except Exception:
            spend_budget.block_unverified(
                reservation,
                "provider call failed before verifiable usage.cost was returned; "
                "stopping subsequent calls",
            )
            raise
        blocked_reason = spend_budget.record(result, reservation)
        log.info(
            "Pass %d spend: $%.6f / $%.6f across %d call(s)",
            pass_number,
            spend_budget.spent_usd,
            spend_budget.max_cost_usd,
            spend_budget.calls,
        )
        if blocked_reason:
            log.warning(
                "Pass %d retained the completed call result but blocked "
                "subsequent calls: %s",
                pass_number,
                blocked_reason,
            )
        return result

    log.info("Pass %d: OpenRouter model=%s", pass_number, config.model_path)
    return config, invoke_with_budget
