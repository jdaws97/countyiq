"""The per-pass reasoning_effort setting must reach the OpenRouter payload.

resolve_pass_reasoning_effort() existed with zero callers for months while
production ran mercury-2 at effort=high — the exact setting the config
comments say wastes 2-3x output tokens. These tests pin the whole chain:
env/default -> HarnessConfig -> request payload.
"""

import math
import os
from unittest import mock

import pytest

from countyiq.lib.backfill_authorization import create_backfill_authorization
from countyiq.lib.llm_harness import (
    HarnessConfig,
    HarnessResult,
    build_openrouter_payload,
)
from countyiq.lib.pass_llm_config import (
    PassHarnessUnavailable,
    PassItemBudget,
    PassSpendBudget,
    PassSpendLimitExceeded,
    build_pass_harness_config,
    estimate_max_pass_call_cost,
    resolve_pass_harness,
    resolve_pass_item_limit,
)


def _clean_env():
    blocked = [
        k
        for k in os.environ
        if k.startswith("COUNTYIQ_PASS")
        or k in {"COUNTYIQ_OPENROUTER_MODEL", "COUNTYIQ_THINKING"}
    ]
    return mock.patch.dict(os.environ, {}, clear=False), blocked


def _configure_pass2_authorization(tmp_path, monkeypatch, *, maximum=0.10):
    import json
    from countyiq.lib.quality_release import release_identity

    path = tmp_path / "pass2-authorization.json"
    monkeypatch.setenv("COUNTYIQ_PASS2_MODEL", "openai/gpt-5.6-luna")
    import hashlib

    artifact = tmp_path / "evaluation.json"
    artifact.write_text("test evaluation record")
    quality = tmp_path / "quality.json"
    quality.write_text(
        json.dumps(
            {
                "identity": release_identity(2),
                "decision": "approved",
                "reviewer": "test reviewer",
                "reviewed_at": "2026-09-04",
                "evaluation_record": {
                    "path": artifact.name,
                    "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                },
                "catastrophic_errors": 0,
            }
        )
    )
    monkeypatch.setenv("COUNTYIQ_PASS2_QUALITY_RECEIPT", str(quality))

    create_backfill_authorization(
        path,
        pass_number=2,
        model="openai/gpt-5.6-luna",
        max_cost_usd=maximum,
        max_price_prompt=0.20,
        max_price_completion=1.20,
    )
    monkeypatch.setenv("COUNTYIQ_PASS2_BACKFILL_AUTHORIZATION_FILE", str(path))


def test_pass1_config_carries_high_effort():
    with mock.patch.dict(os.environ, {}, clear=False):
        for key in list(os.environ):
            if key.startswith("COUNTYIQ_PASS") or key in {
                "COUNTYIQ_OPENROUTER_MODEL",
                "COUNTYIQ_THINKING",
            }:
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
            if key.startswith("COUNTYIQ_PASS") or key in {
                "COUNTYIQ_OPENROUTER_MODEL",
                "COUNTYIQ_THINKING",
            }:
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
    monkeypatch.delenv("COUNTYIQ_PASS2_BACKFILL_MODE", raising=False)
    monkeypatch.delenv("COUNTYIQ_PASS2_MAX_ITEMS", raising=False)
    assert resolve_pass_item_limit(2) == 25
    monkeypatch.setenv("COUNTYIQ_PASS2_MAX_ITEMS", "0")
    assert resolve_pass_item_limit(2) == 25


def test_cost_only_backfill_requires_and_uses_explicit_dollar_ceiling(monkeypatch):
    monkeypatch.setenv("COUNTYIQ_PASS2_BACKFILL_MODE", "true")
    monkeypatch.delenv("COUNTYIQ_PASS2_MAX_COST_USD", raising=False)
    with pytest.raises(ValueError, match="MAX_COST_USD"):
        resolve_pass_item_limit(2)

    monkeypatch.setenv("COUNTYIQ_PASS2_MAX_COST_USD", "12.50")
    log = mock.Mock()
    budget = PassItemBudget(2)
    assert budget.limit is None
    assert budget.mode == "dollar_ceiling"
    assert all(budget.claim(log, label="parcels") for _ in range(30))
    assert budget.claimed == 30
    log.warning.assert_not_called()


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


def test_pass_spend_budget_reserves_worst_case_before_call():
    config = HarnessConfig(
        model_path="test/model",
        max_tokens=1_000,
        max_price_prompt=1.0,
        max_price_completion=2.0,
        system_prompt="rules",
    )
    maximum = estimate_max_pass_call_cost(config, "prompt", retries=1)
    budget = PassSpendBudget(2, maximum + 0.01)

    reservation = budget.reserve(config, "prompt", retries=1, pdf_bytes=None)
    budget.record(
        HarnessResult("{}", {}, True, metadata={"cost": 0.001}),
        reservation,
    )

    assert budget.calls == 1
    assert budget.spent_usd == 0.001
    assert budget.reserved_usd == 0


def test_pass_spend_budget_refuses_unbounded_or_unverifiable_calls():
    unpriced = HarnessConfig(model_path="test/model")
    budget = PassSpendBudget(2, 1.0)
    with pytest.raises(PassSpendLimitExceeded, match="MAX_PRICE"):
        budget.reserve(unpriced, "prompt", retries=1, pdf_bytes=None)

    priced = HarnessConfig(
        model_path="test/model",
        max_price_prompt=1.0,
        max_price_completion=1.0,
    )
    reservation = budget.reserve(priced, "prompt", retries=0, pdf_bytes=None)
    blocked_reason = budget.record(
        HarnessResult("", None, False, metadata={}), reservation
    )
    assert "omitted usage.cost" in (blocked_reason or "")
    assert budget.spent_usd == reservation
    assert budget.reserved_usd == 0
    with pytest.raises(PassSpendLimitExceeded, match="omitted usage.cost"):
        budget.reserve(priced, "prompt", retries=0, pdf_bytes=None)


@pytest.mark.parametrize("cost", [math.nan, math.inf, -1.0])
def test_pass_spend_budget_rejects_invalid_provider_cost(cost):
    config = HarnessConfig(
        model_path="test/model",
        max_tokens=100,
        max_price_prompt=1.0,
        max_price_completion=1.0,
    )
    budget = PassSpendBudget(2, 1.0)
    reservation = budget.reserve(config, "prompt", retries=0, pdf_bytes=None)

    reason = budget.record(
        HarnessResult("", None, False, metadata={"cost": cost}),
        reservation,
    )

    assert "invalid usage.cost" in (reason or "")
    assert budget.spent_usd == reservation
    with pytest.raises(PassSpendLimitExceeded, match="invalid usage.cost"):
        budget.reserve(config, "prompt", retries=0, pdf_bytes=None)


def test_enabled_pass_requires_explicit_runtime_dollar_limit(monkeypatch):
    monkeypatch.setenv("COUNTYIQ_PASS2_ENABLED", "true")
    monkeypatch.setenv("COUNTYIQ_MAX_PRICE_PROMPT", "0.20")
    monkeypatch.setenv("COUNTYIQ_MAX_PRICE_COMPLETION", "1.20")
    monkeypatch.delenv("COUNTYIQ_PASS2_BACKFILL_MODE", raising=False)
    monkeypatch.delenv("COUNTYIQ_PASS2_MAX_COST_USD", raising=False)
    with pytest.raises(PassHarnessUnavailable, match="MAX_COST_USD"):
        resolve_pass_harness(
            mock.Mock(),
            pass_number=2,
            archive_label="test",
            default_max_tokens=1_024,
        )


def test_every_paid_run_requires_durable_cumulative_authorization(monkeypatch):
    monkeypatch.setenv("COUNTYIQ_PASS2_ENABLED", "true")
    monkeypatch.setenv("COUNTYIQ_PASS2_MAX_COST_USD", "12.50")
    monkeypatch.setenv("COUNTYIQ_MAX_PRICE_PROMPT", "0.20")
    monkeypatch.setenv("COUNTYIQ_MAX_PRICE_COMPLETION", "1.20")
    monkeypatch.delenv("COUNTYIQ_PASS2_BACKFILL_AUTHORIZATION_FILE", raising=False)

    with pytest.raises(PassHarnessUnavailable, match="BACKFILL_AUTHORIZATION_FILE"):
        resolve_pass_harness(
            mock.Mock(),
            pass_number=2,
            archive_label="test",
            default_max_tokens=1_024,
        )


def test_resolved_harness_charges_provider_cost_to_pass_budget(tmp_path, monkeypatch):
    monkeypatch.setenv("COUNTYIQ_PASS2_ENABLED", "true")
    monkeypatch.setenv("COUNTYIQ_PASS2_MAX_COST_USD", "0.10")
    monkeypatch.setenv("COUNTYIQ_MAX_PRICE_PROMPT", "0.20")
    monkeypatch.setenv("COUNTYIQ_MAX_PRICE_COMPLETION", "1.20")
    _configure_pass2_authorization(tmp_path, monkeypatch)
    provider_call = mock.Mock(
        return_value=HarnessResult("{}", {}, True, metadata={"cost": 0.001})
    )
    monkeypatch.setattr("countyiq.lib.llm_harness.invoke_with_retry", provider_call)

    config, invoke = resolve_pass_harness(
        mock.Mock(),
        pass_number=2,
        archive_label="test",
        default_max_tokens=1_024,
    )
    result = invoke(config, "Return JSON", retries=0)

    assert result.success is True
    provider_call.assert_called_once()


def test_resolved_harness_blocks_after_provider_failure_without_cost(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("COUNTYIQ_PASS2_ENABLED", "true")
    monkeypatch.setenv("COUNTYIQ_PASS2_MAX_COST_USD", "0.10")
    monkeypatch.setenv("COUNTYIQ_MAX_PRICE_PROMPT", "0.20")
    monkeypatch.setenv("COUNTYIQ_MAX_PRICE_COMPLETION", "1.20")
    _configure_pass2_authorization(tmp_path, monkeypatch)
    provider_call = mock.Mock(side_effect=RuntimeError("connection reset"))
    monkeypatch.setattr("countyiq.lib.llm_harness.invoke_with_retry", provider_call)

    config, invoke = resolve_pass_harness(
        mock.Mock(),
        pass_number=2,
        archive_label="test",
        default_max_tokens=1_024,
    )

    with pytest.raises(RuntimeError, match="connection reset"):
        invoke(config, "test prompt", retries=0)
    with pytest.raises(PassSpendLimitExceeded, match="verifiable usage.cost"):
        invoke(config, "second prompt", retries=0)
    provider_call.assert_called_once()


def test_resolved_harness_retains_paid_result_before_blocking_later_calls(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("COUNTYIQ_PASS2_ENABLED", "true")
    monkeypatch.setenv("COUNTYIQ_PASS2_MAX_COST_USD", "0.10")
    monkeypatch.setenv("COUNTYIQ_MAX_PRICE_PROMPT", "0.20")
    monkeypatch.setenv("COUNTYIQ_MAX_PRICE_COMPLETION", "1.20")
    _configure_pass2_authorization(tmp_path, monkeypatch)
    paid_result = HarnessResult("{}", {}, True, metadata={})
    provider_call = mock.Mock(return_value=paid_result)
    monkeypatch.setattr("countyiq.lib.llm_harness.invoke_with_retry", provider_call)

    config, invoke = resolve_pass_harness(
        mock.Mock(),
        pass_number=2,
        archive_label="test",
        default_max_tokens=1_024,
    )

    assert invoke(config, "first prompt", retries=0) is paid_result
    with pytest.raises(PassSpendLimitExceeded, match="omitted usage.cost"):
        invoke(config, "second prompt", retries=0)
    provider_call.assert_called_once()


def test_explicit_effort_overrides_mercury_thinking_heuristic():
    config = HarnessConfig(
        model_path="inception/mercury-2",
        thinking=True,  # family heuristic alone would emit effort=high
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
    with mock.patch.dict(
        os.environ,
        {
            "COUNTYIQ_PASS2_ENABLED": "true",
            "COUNTYIQ_PASS2_REASONING_EFFORT": "medium",
        },
    ):
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
