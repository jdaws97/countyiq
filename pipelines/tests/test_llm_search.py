"""Tests for API LLM search model selection helpers."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.lib.llm_search import DEFAULT_MODELS, resolve_search_models


def test_resolve_search_models_uses_search_override_only_for_primary_slot(monkeypatch):
    monkeypatch.setenv("COUNTYIQ_SEARCH_MODEL", "search/model")
    monkeypatch.setenv("COUNTYIQ_OPENROUTER_MODEL", "passes/model")

    models = resolve_search_models()

    assert models[0] == "search/model"
    assert "passes/model" not in models
    assert models[1:] == DEFAULT_MODELS


def test_resolve_search_models_falls_back_to_defaults_not_general_pass_model(monkeypatch):
    monkeypatch.delenv("COUNTYIQ_SEARCH_MODEL", raising=False)
    monkeypatch.setenv("COUNTYIQ_OPENROUTER_MODEL", "passes/model")

    assert resolve_search_models() == DEFAULT_MODELS


def test_resolve_search_models_deduplicates_override_against_defaults(monkeypatch):
    monkeypatch.setenv("COUNTYIQ_SEARCH_MODEL", DEFAULT_MODELS[0])

    assert resolve_search_models() == DEFAULT_MODELS
