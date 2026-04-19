"""Pass-level OpenRouter configuration helpers for the CountyIQ LLM pipeline."""

from __future__ import annotations

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


def resolve_pass_model(pass_number: int) -> str | None:
    """Resolve the OpenRouter model slug for a pass."""
    return (
        os.environ.get(f"COUNTYIQ_PASS{pass_number}_MODEL")
        or os.environ.get("COUNTYIQ_OPENROUTER_MODEL")
    )


def resolve_pass_thinking(pass_number: int, default: bool) -> bool:
    """Resolve the thinking toggle for a pass with a global fallback."""
    if f"COUNTYIQ_PASS{pass_number}_THINKING" in os.environ:
        return _bool_env(f"COUNTYIQ_PASS{pass_number}_THINKING", default)
    return _bool_env("COUNTYIQ_THINKING", default)


def build_pass_harness_config(
    *,
    pass_number: int,
    archive_label: str,
    reasoning_task: bool,
    default_max_tokens: int,
    default_thinking: bool = False,
) -> HarnessConfig | None:
    """Return a configured OpenRouter HarnessConfig for a pass."""
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

    return HarnessConfig(
        model_path=model_path,
        max_tokens=max_tokens,
        thinking=thinking,
        archive_label=archive_label,
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
    )
    if config is None:
        log.info(
            "Neither COUNTYIQ_PASS%d_MODEL nor COUNTYIQ_OPENROUTER_MODEL is set — skipping pass %d.",
            pass_number,
            pass_number,
        )
        raise PassHarnessUnavailable("no model configured")

    log.info("Pass %d: OpenRouter model=%s", pass_number, config.model_path)
    return config, invoke_with_retry
