"""Small environment-backed API settings with safe defaults."""

import os
from urllib.parse import urlsplit

LOCAL_CORS_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")


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
        "product_stage": os.environ.get("COUNTYIQ_PRODUCT_STAGE", "alpha").strip().lower()
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
    return os.environ.get("COUNTYIQ_ENABLE_RESTRICTED_DISTRESS", "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def llm_search_enabled() -> bool:
    """Whether public search may spend provider credits on intent parsing."""
    return os.environ.get("COUNTYIQ_SEARCH_LLM_ENABLED", "").strip().lower() in {
        "1", "true", "yes", "on",
    }


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
