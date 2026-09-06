"""Small environment-backed API settings with safe defaults."""

import os
from urllib.parse import urlsplit

LOCAL_CORS_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
LOCAL_TRUSTED_HOSTS = ("localhost", "127.0.0.1", "testserver")


def county_metadata() -> dict[str, str]:
    """Return the public county identity for this API deployment.

    ``COUNTY`` is shared with the pipeline.  A deployment may override the
    human-readable name/state without requiring a frontend rebuild.
    """
    county_key = os.environ.get("COUNTY", "york").strip().lower() or "york"
    default_name = f"{county_key.replace('_', ' ').replace('-', ' ').title()} County"
    return {
        "county_key": county_key,
        "county_name": os.environ.get("COUNTYIQ_COUNTY_NAME", default_name).strip()
        or default_name,
        "state": os.environ.get("COUNTYIQ_COUNTY_STATE", "PA").strip().upper() or "PA",
        "product_stage": os.environ.get("COUNTYIQ_PRODUCT_STAGE", "alpha")
        .strip()
        .lower()
        or "alpha",
    }


def open_data_source_key() -> str:
    """Return the active county GIS source key used by source-rights policy."""
    county_key = county_metadata()["county_key"]
    return (
        os.environ.get("COUNTYIQ_OPEN_DATA_SOURCE_KEY", "").strip()
        or f"{county_key}_open_data"
    )


def restricted_distress_enabled() -> bool:
    """Whether counsel-reviewed person-linked distress routes may be mounted."""
    return os.environ.get(
        "COUNTYIQ_ENABLE_RESTRICTED_DISTRESS", ""
    ).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def llm_search_enabled() -> bool:
    """Whether public search may spend provider credits on intent parsing."""
    return os.environ.get("COUNTYIQ_SEARCH_LLM_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def api_docs_enabled() -> bool:
    """Expose interactive API docs only when explicitly requested.

    The OpenAPI schema remains available to application code and tests even
    when the public documentation routes are disabled.
    """
    return os.environ.get("COUNTYIQ_EXPOSE_API_DOCS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def trusted_hosts() -> list[str]:
    """Return valid public hosts plus internal health-check hostnames."""
    configured = os.environ.get("COUNTYIQ_TRUSTED_HOSTS", "")
    candidates = configured.split(",") if configured.strip() else LOCAL_TRUSTED_HOSTS

    hosts: list[str] = []
    for candidate in candidates:
        host = candidate.strip().lower().rstrip(".")
        wildcard_target = host[2:] if host.startswith("*.") else host
        if (
            not host
            or host == "*"
            or "://" in host
            or any(char in host for char in "/?#@")
            or not wildcard_target
            or any(
                not (label.replace("-", "").isalnum())
                for label in wildcard_target.split(".")
            )
        ):
            continue
        if host not in hosts:
            hosts.append(host)
    if not hosts:
        return list(LOCAL_TRUSTED_HOSTS)
    for local_host in LOCAL_TRUSTED_HOSTS:
        if local_host not in hosts:
            hosts.append(local_host)
    return hosts


def cors_origins() -> list[str]:
    """Return explicit browser origins; wildcards and path-bearing URLs are rejected."""
    configured = os.environ.get("COUNTYIQ_CORS_ORIGINS", "")
    candidates = configured.split(",") if configured.strip() else LOCAL_CORS_ORIGINS

    origins: list[str] = []
    for candidate in candidates:
        origin = candidate.strip().rstrip("/")
        parsed = urlsplit(origin)
        if (
            origin == "*"
            or parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            continue
        if origin not in origins:
            origins.append(origin)
    return origins
