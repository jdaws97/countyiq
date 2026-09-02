"""Tests for pass-level LLM environment resolution helpers."""

import math

import pytest

from countyiq.lib.llm_harness import HarnessConfig
from countyiq.lib.pass_llm_config import (
    PassSpendBudget,
    PassSpendLimitExceeded,
    estimate_max_pass_call_cost,
    resolve_pass_thinking,
)


def test_resolve_pass_thinking_uses_default_when_env_missing(monkeypatch):
    monkeypatch.delenv("COUNTYIQ_THINKING", raising=False)
    monkeypatch.delenv("COUNTYIQ_PASS2_THINKING", raising=False)

    assert resolve_pass_thinking(2, True) is True


def test_resolve_pass_thinking_treats_blank_global_env_as_unset(monkeypatch):
    monkeypatch.setenv("COUNTYIQ_THINKING", "")
    monkeypatch.delenv("COUNTYIQ_PASS2_THINKING", raising=False)

    assert resolve_pass_thinking(2, True) is True


def test_resolve_pass_thinking_pass_specific_override_wins(monkeypatch):
    monkeypatch.setenv("COUNTYIQ_THINKING", "false")
    monkeypatch.setenv("COUNTYIQ_PASS2_THINKING", "true")

    assert resolve_pass_thinking(2, False) is True


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, 0.0, -1.0])
def test_spend_budget_rejects_non_finite_or_non_positive_limit(value):
    with pytest.raises(ValueError, match="positive and finite"):
        PassSpendBudget(2, value)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, 0.0, -1.0])
def test_call_estimate_rejects_invalid_provider_price(value):
    config = HarnessConfig(
        model_path="provider/model",
        max_price_prompt=value,
        max_price_completion=1.0,
    )

    with pytest.raises(PassSpendLimitExceeded, match="positive finite"):
        estimate_max_pass_call_cost(config, "prompt")
