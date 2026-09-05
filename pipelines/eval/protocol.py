"""Shared production-shaped configuration and spend tracking for LLM evals."""

from __future__ import annotations

from countyiq.lib.proceeding_claims import PASS0_CLAIMS_SCHEMA

import dataclasses
import json
import math
import threading
from dataclasses import dataclass, field

from countyiq.lib.llm_harness import (
    HarnessConfig,
    HarnessResult,
    get_preset_for_model,
    invoke_with_retry,
)
from countyiq.lib.pass0_templates import PASS0_SYSTEM_PROMPT
from countyiq.lib.pass1_entity_verification import ENTITY_VERIFICATION_SYSTEM_PROMPT
from countyiq.lib.pass2_batched_validation import BATCHED_VALIDATION_SYSTEM_PROMPT
from countyiq.lib.pass3_brief_generation import BRIEF_GENERATION_SYSTEM_PROMPT
from countyiq.lib.pass_llm_config import build_pass_harness_config
from countyiq.lib.pass_schemas import (
    PASS2_BATCHED_VALIDATION_SCHEMA,
    PASS3_BRIEF_SCHEMA,
)


@dataclass(frozen=True)
class PassEvalProtocol:
    max_tokens: int
    reasoning_task: bool
    default_thinking: bool
    system_prompt: str
    json_schema: dict | None = None
    schema_name: str = "response"
    pdf_engine: str | None = None


PASS_EVAL_PROTOCOLS = {
    0: PassEvalProtocol(
        max_tokens=8192,
        reasoning_task=False,
        default_thinking=False,
        system_prompt=PASS0_SYSTEM_PROMPT,
        json_schema=PASS0_CLAIMS_SCHEMA,
        schema_name="pass0_extractions",
        pdf_engine="native",
    ),
    1: PassEvalProtocol(
        max_tokens=8192,
        reasoning_task=True,
        default_thinking=True,
        system_prompt=ENTITY_VERIFICATION_SYSTEM_PROMPT,
    ),
    2: PassEvalProtocol(
        max_tokens=4096,
        reasoning_task=True,
        default_thinking=True,
        system_prompt=BATCHED_VALIDATION_SYSTEM_PROMPT,
        json_schema=PASS2_BATCHED_VALIDATION_SCHEMA,
        schema_name="pass2_validations",
    ),
    3: PassEvalProtocol(
        max_tokens=2048,
        reasoning_task=True,
        default_thinking=False,
        system_prompt=BRIEF_GENERATION_SYSTEM_PROMPT,
        json_schema=PASS3_BRIEF_SCHEMA,
        schema_name="pass3_brief",
    ),
}


# Conservative provider ceilings, in dollars per million tokens. These are
# intentionally the highest normal provider prices accepted for the evaluated
# routes, not temporary promotional prices. OpenRouter enforces them through
# provider.max_price; the reservation calculation below then turns the token
# ceilings into a pre-call absolute run-budget reservation.
EVAL_MODEL_PRICE_CEILINGS = {
    # Include the provider's $0.25/M cache-write tier, not just its $0.20/M
    # uncached input tier. Actual reported usage remains authoritative.
    "openai/gpt-5.6-luna": (0.28, 1.32),
    "z-ai/glm-5.3-flash": (0.16, 0.55),
    "x-ai/grok-4.6": (2.50, 8.00),
    # 2026-09-02 cost-reduction candidates (OpenRouter list price + ~10%,
    # rounded up; gpt-oss-120b allows the pricier hosted routes).
    "deepseek/deepseek-v4-flash-0731": (0.08, 0.20),
    "deepseek/deepseek-v4-flash": (0.10, 0.20),
    "qwen/qwen3.5-flash-02-23": (0.08, 0.30),
    "qwen/qwen3.8-flash": (0.17, 0.52),
    "openai/gpt-oss-120b": (0.10, 0.40),
    "upstage/solar-pro4": (0.04, 0.14),
    "google/gemini-2.5-flash-lite": (0.11, 0.44),
    "nvidia/nemotron-3-super-120b-a12b": (0.10, 0.45),
}


def build_production_eval_config(
    model: str,
    pass_number: int,
    *,
    archive_label: str,
    max_tokens: int | None = None,
    thinking: bool | None = None,
    reasoning_effort: str | None = None,
    provider_quantizations: tuple[str, ...] | None = None,
) -> HarnessConfig:
    """Build an eval config with the same system/schema contract as production."""
    try:
        protocol = PASS_EVAL_PROTOCOLS[pass_number]
    except KeyError as exc:
        raise ValueError(f"No eval protocol for Pass {pass_number}") from exc

    resolved_max_tokens = max_tokens or protocol.max_tokens
    base = build_pass_harness_config(
        pass_number=pass_number,
        archive_label=archive_label,
        reasoning_task=protocol.reasoning_task,
        default_max_tokens=resolved_max_tokens,
        default_thinking=protocol.default_thinking,
        json_schema=protocol.json_schema,
        schema_name=protocol.schema_name,
        system_prompt=protocol.system_prompt,
        pdf_engine=protocol.pdf_engine,
        # Evaluation is already an explicit operator action with an explicit
        # model. Reuse the production contract without coupling config
        # construction to the runtime asset spend gate.
        require_enabled=False,
    )
    if base is None:
        raise ValueError(f"Pass {pass_number} has no configured model")

    resolved_thinking = base.thinking if thinking is None else thinking
    preset = get_preset_for_model(
        model,
        thinking=resolved_thinking,
        reasoning_task=protocol.reasoning_task,
    )
    return dataclasses.replace(
        base,
        model_path=model,
        model_family="auto",
        max_tokens=resolved_max_tokens,
        thinking=resolved_thinking,
        reasoning_effort=(
            base.reasoning_effort
            if reasoning_effort is None
            else reasoning_effort
        ),
        provider_quantizations=provider_quantizations,
        max_price_prompt=(
            EVAL_MODEL_PRICE_CEILINGS.get(model, (base.max_price_prompt, None))[0]
            if base.max_price_prompt is None
            else base.max_price_prompt
        ),
        max_price_completion=(
            EVAL_MODEL_PRICE_CEILINGS.get(model, (None, base.max_price_completion))[1]
            if base.max_price_completion is None
            else base.max_price_completion
        ),
        **preset,
    )


class EvalCostLimitExceeded(RuntimeError):
    """The provider-reported eval spend reached the configured ceiling."""


class EvalCostUnavailable(RuntimeError):
    """A paid eval response omitted provider cost accounting."""


@dataclass(frozen=True)
class EvalCostReservation:
    """One pre-authorized maximum charge held against the run budget."""

    amount_usd: float


def estimate_max_call_cost(
    config: HarnessConfig,
    prompt: str,
    *,
    pdf_bytes: bytes | None = None,
    retries: int = 1,
) -> float:
    """Return a conservative maximum charge for one tracked invocation.

    UTF-8/base64 bytes are an upper bound on tokenizer pieces for ordinary
    provider tokenizers. We include the system message, strict schema, wrapper
    overhead, inline PDF expansion, and the adaptive doubled completion budget
    used by ``invoke_with_retry``. Combined with OpenRouter ``max_price`` this
    lets the ledger reserve an absolute amount *before* dispatch.
    """
    if config.max_price_prompt is None or config.max_price_completion is None:
        raise EvalCostUnavailable(
            f"No eval price ceiling is configured for {config.model_path}; "
            "refusing a paid call whose maximum charge cannot be reserved."
        )
    if retries < 0:
        raise ValueError("retries must be non-negative")

    schema_text = json.dumps(config.json_schema, sort_keys=True) if config.json_schema else ""
    prompt_bytes = len(
        ((config.system_prompt or "") + prompt + schema_text).encode("utf-8")
    )
    # Account for chat/response wrappers and provider-side labels.
    prompt_token_upper = prompt_bytes + 2048
    if pdf_bytes:
        # Inline transport is base64. The native parser may tokenize fewer
        # units, never more than this deliberately loose byte upper bound.
        prompt_token_upper += math.ceil(len(pdf_bytes) * 4 / 3) + 1024

    completion_budgets = [config.max_tokens]
    for _ in range(retries):
        completion_budgets.append(min(completion_budgets[-1] * 2, 16384))
    attempts = retries + 1
    maximum = (
        prompt_token_upper * attempts * config.max_price_prompt
        + sum(completion_budgets) * config.max_price_completion
    ) / 1_000_000
    # A small billing cushion covers provider token-accounting differences.
    return round(maximum * 1.10 + 0.000001, 9)


@dataclass
class EvalCostLedger:
    """Thread-safe ledger over provider-returned ``usage.cost`` values."""

    max_cost_usd: float | None
    spent_usd: float = 0.0
    reserved_usd: float = 0.0
    calls: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def reserve(self, amount_usd: float) -> EvalCostReservation:
        if amount_usd <= 0:
            raise ValueError("reservation must be positive")
        with self._lock:
            if (
                self.max_cost_usd is not None
                and self.spent_usd + self.reserved_usd + amount_usd
                > self.max_cost_usd
            ):
                raise EvalCostLimitExceeded(
                    "eval cost reservation would exceed limit: "
                    f"spent=${self.spent_usd:.6f}, "
                    f"reserved=${self.reserved_usd:.6f}, "
                    f"next_max=${amount_usd:.6f}, "
                    f"limit=${self.max_cost_usd:.6f}"
                )
            self.reserved_usd += amount_usd
        return EvalCostReservation(amount_usd=amount_usd)

    def release(self, reservation: EvalCostReservation) -> None:
        with self._lock:
            self.reserved_usd = max(
                0.0, self.reserved_usd - reservation.amount_usd
            )

    def record(
        self,
        result: HarnessResult,
        reservation: EvalCostReservation | None = None,
    ) -> None:
        cost = result.metadata.get("cost")
        if not isinstance(cost, (int, float)):
            if reservation:
                self.release(reservation)
            detail = f" Provider error: {result.error}" if result.error else ""
            raise EvalCostUnavailable(
                "OpenRouter response omitted usage.cost; stopping because the "
                f"eval budget can no longer be verified.{detail}"
            )
        with self._lock:
            reserved = reservation.amount_usd if reservation else 0.0
            self.reserved_usd = max(0.0, self.reserved_usd - reserved)
            self.calls += 1
            self.spent_usd += float(cost)
            if reservation and float(cost) > reserved:
                raise EvalCostLimitExceeded(
                    "provider-reported cost exceeded its pre-call reservation: "
                    f"${float(cost):.6f} > ${reserved:.6f}"
                )
            if (
                self.max_cost_usd is not None
                and self.spent_usd > self.max_cost_usd
            ):
                raise EvalCostLimitExceeded(
                    f"eval cost limit exceeded after call {self.calls}: "
                    f"${self.spent_usd:.6f} / ${self.max_cost_usd:.6f}"
                )

    def summary(self) -> dict:
        with self._lock:
            return {
                "calls": self.calls,
                "spend_usd": round(self.spent_usd, 9),
                "reserved_usd": round(self.reserved_usd, 9),
                "max_cost_usd": self.max_cost_usd,
            }


def invoke_tracked(
    ledger: EvalCostLedger,
    config: HarnessConfig,
    prompt: str,
    **kwargs,
) -> HarnessResult:
    """Reserve the maximum, invoke, then charge complete provider usage."""
    retries = int(kwargs.get("retries", 1))
    reservation = ledger.reserve(
        estimate_max_call_cost(
            config,
            prompt,
            pdf_bytes=kwargs.get("pdf_bytes"),
            retries=retries,
        )
    )
    try:
        result = invoke_with_retry(config, prompt, **kwargs)
    except Exception:
        ledger.release(reservation)
        raise
    ledger.record(result, reservation)
    return result
