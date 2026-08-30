"""The per-pass reasoning_effort setting must reach the OpenRouter payload.

resolve_pass_reasoning_effort() existed with zero callers for months while
production ran mercury-2 at effort=high — the exact setting the config
comments say wastes 2-3x output tokens. These tests pin the whole chain:
env/default -> HarnessConfig -> request payload.
"""

import os
from unittest import mock

from countyiq.lib.llm_harness import HarnessConfig, build_openrouter_payload
from countyiq.lib.pass_llm_config import (
    PassItemBudget,
    build_pass_harness_config,
    resolve_pass_item_limit,
)


def _clean_env():
    blocked = [
        k for k in os.environ
        if k.startswith("COUNTYIQ_PASS") or k in {"COUNTYIQ_OPENROUTER_MODEL", "COUNTYIQ_THINKING"}
    ]
    return mock.patch.dict(os.environ, {}, clear=False), blocked


def test_pass1_config_carries_high_effort():
    with mock.patch.dict(os.environ, {}, clear=False):
        for key in list(os.environ):
            if key.startswith("COUNTYIQ_PASS") or key in {"COUNTYIQ_OPENROUTER_MODEL", "COUNTYIQ_THINKING"}:
                del os.environ[key]
        os.environ["COUNTYIQ_PASS1_ENABLED"] = "true"
        config = build_pass_harness_config(
            pass_number=1,
            archive_label="test",
            reasoning_task=True,
            default_max_tokens=8192,
            default_thinking=True,
        )
    assert config is not None
    assert config.reasoning_effort == "high"


def test_pass2_config_carries_low_effort():
    with mock.patch.dict(os.environ, {}, clear=False):
        for key in list(os.environ):
            if key.startswith("COUNTYIQ_PASS") or key in {"COUNTYIQ_OPENROUTER_MODEL", "COUNTYIQ_THINKING"}:
                del os.environ[key]
        os.environ["COUNTYIQ_PASS2_ENABLED"] = "true"
        config = build_pass_harness_config(
            pass_number=2,
            archive_label="test",
            reasoning_task=True,
            default_max_tokens=4096,
            default_thinking=True,
        )
    assert config is not None
    assert config.reasoning_effort == "low"


def test_all_passes_are_opt_in_but_can_be_enabled():
    for pass_number in range(5):
        with mock.patch.dict(os.environ, {}, clear=False):
            for key in list(os.environ):
                if key.startswith(f"COUNTYIQ_PASS{pass_number}_"):
                    del os.environ[key]
            disabled = build_pass_harness_config(
                pass_number=pass_number,
                archive_label="test",
                reasoning_task=True,
                default_max_tokens=4096,
            )
        assert disabled is None

    with mock.patch.dict(os.environ, {}, clear=False):
        for key in list(os.environ):
            if key.startswith("COUNTYIQ_PASS4_"):
                del os.environ[key]
        disabled = build_pass_harness_config(
            pass_number=4,
            archive_label="test",
            reasoning_task=True,
            default_max_tokens=4096,
        )
    assert disabled is None

    with mock.patch.dict(os.environ, {"COUNTYIQ_PASS4_ENABLED": "true"}):
        enabled = build_pass_harness_config(
            pass_number=4,
            archive_label="test",
            reasoning_task=True,
            default_max_tokens=4096,
        )
    assert enabled is not None


def test_pass_item_limit_defaults_to_finite_and_zero_cannot_unbound(monkeypatch):
    monkeypatch.delenv("COUNTYIQ_PASS2_MAX_ITEMS", raising=False)
    assert resolve_pass_item_limit(2) == 25
    monkeypatch.setenv("COUNTYIQ_PASS2_MAX_ITEMS", "0")
    assert resolve_pass_item_limit(2) == 25


def test_pass_item_budget_caps_changed_items(monkeypatch):
    monkeypatch.setenv("COUNTYIQ_PASS1_MAX_ITEMS", "2")
    log = mock.Mock()
    budget = PassItemBudget(1)

    assert budget.claim(log, label="clusters")
    assert budget.claim(log, label="clusters")
    assert not budget.claim(log, label="clusters")
    assert budget.claimed == 2
    assert budget.denied == 1
    log.warning.assert_called_once()


def test_explicit_effort_overrides_mercury_thinking_heuristic():
    config = HarnessConfig(
        model_path="inception/mercury-2",
        thinking=True,          # family heuristic alone would emit effort=high
        reasoning_effort="low",
    )
    payload = build_openrouter_payload(config, "prompt")
    assert payload["reasoning"] == {"effort": "low"}


def test_no_effort_keeps_family_default():
    config = HarnessConfig(model_path="inception/mercury-2", thinking=True)
    payload = build_openrouter_payload(config, "prompt")
    assert payload["reasoning"] == {"effort": "high"}


def test_effort_replaces_gpt_oss_hardcoded_key():
    config = HarnessConfig(
        model_path="openai/gpt-oss-120b", model_family="gpt_oss", reasoning_effort="low"
    )
    payload = build_openrouter_payload(config, "prompt")
    assert "reasoning_effort" not in payload
    assert payload["reasoning"] == {"effort": "low"}


def test_env_override_beats_default():
    with mock.patch.dict(os.environ, {
        "COUNTYIQ_PASS2_ENABLED": "true",
        "COUNTYIQ_PASS2_REASONING_EFFORT": "medium",
    }):
        config = build_pass_harness_config(
            pass_number=2,
            archive_label="test",
            reasoning_task=True,
            default_max_tokens=4096,
        )
    assert config is not None
    assert config.reasoning_effort == "medium"


def test_grok_nonthinking_omits_reasoning_field():
    # grok-4.5+ has mandatory reasoning: {"enabled": false} is a hard 400,
    # so non-thinking configs must not emit the field at all (2026-08-06).
    payload = build_openrouter_payload(
        HarnessConfig(model_path="x-ai/grok-4.5", thinking=False), "say JSON"
    )
    assert "reasoning" not in payload


def test_grok_thinking_enables_reasoning():
    payload = build_openrouter_payload(
        HarnessConfig(model_path="x-ai/grok-4.5", thinking=True), "say JSON"
    )
    assert payload["reasoning"] == {"enabled": True}
