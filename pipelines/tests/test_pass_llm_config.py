"""Tests for pass-level LLM environment resolution helpers."""

from countyiq.lib.pass_llm_config import resolve_pass_thinking


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
