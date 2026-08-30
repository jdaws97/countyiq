"""Tests for API LLM search configuration."""

from types import SimpleNamespace

from starlette.requests import Request

from api.lib.llm_search import (
    ALLOWED_REDIRECT_PATHS,
    DEFAULT_MODELS,
    SYSTEM_PROMPT,
    resolve_search_models,
)
from api.routes import search as search_route


def test_redirect_paths_match_the_frontend_watch_route():
    assert "/watch" in ALLOWED_REDIRECT_PATHS
    assert "/watchlist" not in ALLOWED_REDIRECT_PATHS
    assert all(path in SYSTEM_PROMPT for path in ALLOWED_REDIRECT_PATHS)


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


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/search",
            "headers": [],
            "client": ("127.0.0.1", 50000),
            "scheme": "http",
            "server": ("testserver", 80),
            "query_string": b"",
        }
    )


def test_search_does_not_use_llm_just_because_provider_key_exists(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "configured-for-offline-passes")
    monkeypatch.delenv("COUNTYIQ_SEARCH_LLM_ENABLED", raising=False)
    monkeypatch.setattr(
        search_route,
        "_trgm_search_with_reversal",
        lambda query, limit: [{"query": query, "limit": limit}],
    )
    monkeypatch.setattr(
        search_route,
        "parse_query_with_llm",
        lambda query: (_ for _ in ()).throw(AssertionError("LLM should be disabled")),
    )

    response = search_route.search(
        request=_request(), q="vacant delinquent land", limit=20
    )

    assert response["mode"] == "fuzzy"


def test_search_llm_requires_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("COUNTYIQ_SEARCH_LLM_ENABLED", "true")
    monkeypatch.setattr(
        search_route,
        "llm_search_limiter",
        SimpleNamespace(allow=lambda client: True),
    )
    monkeypatch.setattr(
        search_route,
        "llm_search_daily_budget",
        SimpleNamespace(spend=lambda: True),
    )
    monkeypatch.setattr(
        search_route,
        "parse_query_with_llm",
        lambda query: {
            "intent": "redirect",
            "redirect_path": "/feed",
            "description": "Current intelligence",
        },
    )

    response = search_route.search(
        request=_request(), q="show current intelligence", limit=20
    )

    assert response["mode"] == "redirect"
    assert response["redirect_path"] == "/feed"
