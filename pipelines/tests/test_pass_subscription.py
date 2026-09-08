"""Backend selection cannot silently enable paid work or duplicate a cached vote."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from countyiq.lib.llm_harness import HarnessConfig
from countyiq.lib.pass_llm_config import (
    PassHarnessUnavailable,
    PassSubscriptionPaused,
    resolve_pass_harness,
    resolve_pass_item_limit,
    resolve_pass_model,
)
from countyiq.lib.pass_subscription import SubscriptionPassRunner


@pytest.fixture
def subscription(monkeypatch, tmp_path):
    monkeypatch.setenv("COUNTYIQ_LLM_BACKEND", "codex_subscription")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "login"))
    monkeypatch.setenv("COUNTYIQ_SUBSCRIPTION_STATE_DIR", str(tmp_path / "receipts"))
    monkeypatch.setenv("OPENROUTER_API_KEY", "must-not-reach-codex")
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        assert "OPENROUTER_API_KEY" not in kwargs["env"]
        if command[1] == "login":
            return SimpleNamespace(
                returncode=0, stdout="Logged in using ChatGPT", stderr=""
            )
        output = Path(command[command.index("--output-last-message") + 1])
        output.write_text('{"items": []}')
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", run)
    return commands


def configuration(effort="medium", schema=None):
    return HarnessConfig(
        model_path="codex/subscription:gpt-6-astra",
        reasoning_effort=effort,
        json_schema=schema,
        system_prompt="Return JSON source selections.",
    )


def test_backend_preserves_openrouter_choice_and_does_not_enable_pass(
    subscription, monkeypatch
):
    monkeypatch.setenv("COUNTYIQ_PASS3_MODEL", "openai/paid-model")
    assert resolve_pass_model(3) == "codex/subscription:gpt-6-astra"
    with pytest.raises(PassHarnessUnavailable, match="disabled"):
        resolve_pass_harness(
            Mock(), pass_number=3, archive_label="test", default_max_tokens=500
        )
    assert subscription == []
    monkeypatch.setenv("COUNTYIQ_PASS3_BACKEND", "openrouter")
    assert resolve_pass_model(3) == "openai/paid-model"


def test_subscription_requires_current_quality_before_login(subscription, monkeypatch):
    monkeypatch.setenv("COUNTYIQ_PASS0_ENABLED", "true")
    monkeypatch.setattr(
        "countyiq.lib.quality_release.check_quality_release",
        lambda _: {"ok": False, "reason": "quality receipt is stale"},
    )
    with pytest.raises(PassHarnessUnavailable, match="stale"):
        resolve_pass_harness(
            Mock(), pass_number=0, archive_label="test", default_max_tokens=500
        )
    assert subscription == []


def test_subscription_resolves_without_api_dollar_authorization(
    subscription, monkeypatch
):
    monkeypatch.setenv("COUNTYIQ_PASS0_ENABLED", "true")
    monkeypatch.setenv("COUNTYIQ_PASS0_MAX_COST_USD", "")
    monkeypatch.setattr(
        "countyiq.lib.quality_release.check_quality_release",
        lambda _: {"ok": True},
    )
    config, runner = resolve_pass_harness(
        Mock(), pass_number=0, archive_label="test", default_max_tokens=500
    )
    assert config.model_path == "codex/subscription:gpt-6-astra"
    assert isinstance(runner, SubscriptionPassRunner)
    monkeypatch.setenv("COUNTYIQ_PASS0_BACKFILL_MODE", "true")
    monkeypatch.setenv("COUNTYIQ_PASS0_MAX_ITEMS", "37")
    assert resolve_pass_item_limit(0) == 37


def test_call_cap_allows_cached_resume_but_never_paid_fallback(
    subscription, monkeypatch
):
    monkeypatch.setenv("COUNTYIQ_PASS0_CODEX_MAX_CALLS", "1")
    runner = SubscriptionPassRunner(0)
    assert runner(configuration(), "first source").success
    assert runner(configuration(), "first source").success
    with pytest.raises(PassSubscriptionPaused, match="call limit"):
        runner(configuration(), "second source")
    with pytest.raises(PassSubscriptionPaused, match="API model"):
        runner(HarnessConfig(model_path="openai/paid-model"), "source")
    assert sum(command[1] == "exec" for command in subscription) == 1


def test_vote_trials_have_separate_receipts_and_honor_reasoning(subscription):
    runner = SubscriptionPassRunner(1)
    runner(configuration("high"), "same evidence", archive_key="cluster:trial-0")
    runner(configuration("high"), "same evidence", archive_key="cluster:trial-1")
    runner(configuration("high"), "same evidence", archive_key="cluster:trial-0")
    executions = [command for command in subscription if command[1] == "exec"]
    assert len(executions) == 2
    assert all('model_reasoning_effort="high"' in command for command in executions)
    assert all("--output-schema" not in command for command in executions)


def test_item_provenance_does_not_include_the_previous_subject(subscription):
    runner = SubscriptionPassRunner(3)
    runner.start_item()
    runner(configuration(), "first source")
    previous = runner.provenance()["artifacts"][0]["artifact"]
    runner.start_item()
    runner(configuration(), "second source")
    provenance = runner.provenance()
    assert provenance["provider"] == "codex_subscription"
    assert len(provenance["artifacts"]) == 1
    assert provenance["artifacts"][0]["artifact"] != previous
    assert provenance["api_calls"] == 0


def test_lost_subscription_login_stops_without_api_attempt(subscription, monkeypatch):
    monkeypatch.setattr(
        "subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=1, stdout="", stderr="session expired"
        ),
    )
    with pytest.raises(PassSubscriptionPaused, match="login is unavailable"):
        SubscriptionPassRunner(0).check_login()
    assert subscription == []
