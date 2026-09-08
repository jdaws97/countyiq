"""Subscription authoring must never become an unapproved paid fallback."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from countyiq.lib.llm_harness import HarnessConfig
from countyiq.lib.subscription_backfill import (
    SubscriptionAuthor,
    SubscriptionUnavailable,
)


def config():
    return HarnessConfig(
        model_path="codex/subscription:test",
        system_prompt="Select source spans.",
        json_schema={"type": "object", "properties": {}},
    )


def test_subscription_rejects_api_authentication(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout="", stderr="Logged in using an API key"
        ),
    )
    author = SubscriptionAuthor(tmp_path, model="test")
    with pytest.raises(SubscriptionUnavailable, match="ChatGPT"):
        author.check_login()


def test_receipt_reuse_avoids_second_request_and_detects_tampering(
    tmp_path, monkeypatch
):
    calls = []
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-reach-child")
    monkeypatch.setenv("CODEX_API_KEY", "must-not-reach-child")
    monkeypatch.setenv("DATABASE_PASSWORD", "must-not-reach-child")

    def run(command, **kwargs):
        calls.append(command)
        assert "OPENAI_API_KEY" not in kwargs["env"]
        assert "CODEX_API_KEY" not in kwargs["env"]
        assert "DATABASE_PASSWORD" not in kwargs["env"]
        if command[1] == "login":
            return SimpleNamespace(
                returncode=0, stdout="", stderr="Logged in using ChatGPT"
            )
        assert "--ignore-user-config" in command
        assert command[command.index("--sandbox") + 1] == "read-only"
        output = Path(command[command.index("--output-last-message") + 1])
        output.write_text('{"items": []}')
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", run)
    author = SubscriptionAuthor(tmp_path, model="test")
    first = author(config(), "SOURCE")
    second = author(config(), "SOURCE")
    assert first.parsed == second.parsed == {"items": []}
    assert sum(command[1] == "exec" for command in calls) == 1
    assert author.provenance()["api_calls"] == 0
    artifact = next(tmp_path.glob("*.json"))
    payload = json.loads(artifact.read_text())
    payload["response"] = {"items": ["invented"]}
    artifact.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="modified"):
        author(config(), "SOURCE")


def test_failed_subscription_stops_without_retry_or_paid_fallback(
    tmp_path, monkeypatch
):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if command[1] == "login":
            return SimpleNamespace(
                returncode=0, stdout="Logged in using ChatGPT", stderr=""
            )
        return SimpleNamespace(returncode=1, stdout="", stderr="usage limit")

    monkeypatch.setattr("subprocess.run", run)
    with pytest.raises(SubscriptionUnavailable, match="Codex stopped"):
        SubscriptionAuthor(tmp_path, model="test")(config(), "SOURCE")
    assert sum(command[1] == "exec" for command in calls) == 1
    assert len(list(tmp_path.glob("*.error.txt"))) == 1
    assert not list(tmp_path.glob("*.json"))


@pytest.mark.parametrize("omit_source", [False, True])
def test_batch_keeps_source_identity_and_rejects_incomplete_results(
    tmp_path, monkeypatch, omit_source
):
    def run(command, **kwargs):
        if command[1] == "login":
            return SimpleNamespace(
                returncode=0, stdout="Logged in using ChatGPT", stderr=""
            )
        schema_path = Path(command[command.index("--output-schema") + 1])
        schema = json.loads(schema_path.read_text())
        keys = schema["properties"]["results"]["items"]["properties"]["key"]["enum"]
        if omit_source:
            keys = keys[:1]
        payload = {"results": [{"key": key, "response": {"items": []}} for key in keys]}
        output = Path(command[command.index("--output-last-message") + 1])
        output.write_text(json.dumps(payload))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", run)
    author = SubscriptionAuthor(tmp_path, model="test")
    if omit_source:
        with pytest.raises(ValueError, match="omitted"):
            author.prefetch(config(), ["first source", "second source"])
        assert len(list(tmp_path.glob("*.json"))) == 1
    else:
        author.prefetch(config(), ["first source", "second source"])
        assert author(config(), "first source").parsed == {"items": []}
        assert author(config(), "second source").parsed == {"items": []}
        assert len(list(tmp_path.glob("*.json"))) == 3
