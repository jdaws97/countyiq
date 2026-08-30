"""Tests for environment-only Slack webhook configuration."""

import pytest

from countyiq.lib import slack


def test_webhook_comes_from_environment(monkeypatch):
    slack._webhook_cache.clear()
    monkeypatch.setenv("SLACK_WEBHOOK_CRITICAL", "https://hooks.example/critical")

    assert slack.get_slack_webhook_url("critical") == "https://hooks.example/critical"


def test_missing_webhook_disables_notifications(monkeypatch):
    slack._webhook_cache.clear()
    monkeypatch.delenv("SLACK_WEBHOOK_PIPELINE", raising=False)

    assert slack.get_slack_webhook_url("pipeline") is None


def test_unknown_channel_is_rejected():
    with pytest.raises(ValueError, match="Unknown Slack channel"):
        slack.get_slack_webhook_url("other")
