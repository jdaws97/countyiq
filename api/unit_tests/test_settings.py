"""Tests for environment-backed API settings."""

from api.lib.settings import (
    LOCAL_CORS_ORIGINS,
    LOCAL_TRUSTED_HOSTS,
    api_docs_enabled,
    county_metadata,
    cors_origins,
    llm_search_enabled,
    open_data_source_key,
    restricted_distress_enabled,
    trusted_hosts,
)


def test_cors_defaults_to_local_frontend_origins(monkeypatch):
    monkeypatch.delenv("COUNTYIQ_CORS_ORIGINS", raising=False)

    assert cors_origins() == list(LOCAL_CORS_ORIGINS)


def test_cors_accepts_explicit_origins_and_rejects_wildcards(monkeypatch):
    monkeypatch.setenv(
        "COUNTYIQ_CORS_ORIGINS",
        "https://countyiq.example, *, https://app.example/, ftp://invalid, "
        "https://example.com/path",
    )

    assert cors_origins() == ["https://countyiq.example", "https://app.example"]


def test_restricted_distress_defaults_off_and_requires_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("COUNTYIQ_ENABLE_RESTRICTED_DISTRESS", raising=False)
    assert restricted_distress_enabled() is False

    monkeypatch.setenv("COUNTYIQ_ENABLE_RESTRICTED_DISTRESS", "true")
    assert restricted_distress_enabled() is True


def test_llm_search_defaults_off_and_requires_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("COUNTYIQ_SEARCH_LLM_ENABLED", raising=False)
    assert llm_search_enabled() is False

    monkeypatch.setenv("COUNTYIQ_SEARCH_LLM_ENABLED", "true")
    assert llm_search_enabled() is True


def test_api_docs_default_off_and_require_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("COUNTYIQ_EXPOSE_API_DOCS", raising=False)
    assert api_docs_enabled() is False

    monkeypatch.setenv("COUNTYIQ_EXPOSE_API_DOCS", "true")
    assert api_docs_enabled() is True


def test_trusted_hosts_rejects_wildcard_urls_and_paths(monkeypatch):
    monkeypatch.setenv(
        "COUNTYIQ_TRUSTED_HOSTS",
        "api.countyiq.example, *.internal.example, *, https://bad.example, "
        "bad.example/path",
    )

    assert trusted_hosts() == [
        "api.countyiq.example",
        "*.internal.example",
        *LOCAL_TRUSTED_HOSTS,
    ]

    monkeypatch.setenv("COUNTYIQ_TRUSTED_HOSTS", "*, https://bad.example")
    assert trusted_hosts() == list(LOCAL_TRUSTED_HOSTS)


def test_county_metadata_defaults_and_non_york_derivation(monkeypatch):
    for key in ("COUNTY", "COUNTYIQ_COUNTY_NAME", "COUNTYIQ_COUNTY_STATE"):
        monkeypatch.delenv(key, raising=False)
    assert county_metadata() == {
        "county_key": "york",
        "county_name": "York County",
        "state": "PA",
        "product_stage": "alpha",
    }

    monkeypatch.setenv("COUNTY", "cumberland")
    monkeypatch.setenv("COUNTYIQ_COUNTY_STATE", "pa")
    assert county_metadata()["county_name"] == "Cumberland County"
    assert county_metadata()["state"] == "PA"


def test_open_data_source_key_tracks_county_and_allows_override(monkeypatch):
    monkeypatch.setenv("COUNTY", "adams")
    monkeypatch.delenv("COUNTYIQ_OPEN_DATA_SOURCE_KEY", raising=False)
    assert open_data_source_key() == "adams_open_data"

    monkeypatch.setenv("COUNTYIQ_OPEN_DATA_SOURCE_KEY", "adams_gis_approved")
    assert open_data_source_key() == "adams_gis_approved"
