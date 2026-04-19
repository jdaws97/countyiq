"""County Scout discovery and monitoring helpers."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS = {
    "PROMOTION_THRESHOLD": ("countyiq.lib.scout.discovery", "PROMOTION_THRESHOLD"),
    "CandidateRecord": ("countyiq.lib.scout.models", "CandidateRecord"),
    "ObservationRecord": ("countyiq.lib.scout.models", "ObservationRecord"),
    "ProbeResult": ("countyiq.lib.scout.models", "ProbeResult"),
    "RegistryMonitorRecord": ("countyiq.lib.scout.models", "RegistryMonitorRecord"),
    "ScoutSeed": ("countyiq.lib.scout.models", "ScoutSeed"),
    "classify_candidate": ("countyiq.lib.scout.discovery", "classify_candidate"),
    "discover_county_sources": ("countyiq.lib.scout.discovery", "discover_county_sources"),
    "extract_relevant_links": ("countyiq.lib.scout.discovery", "extract_relevant_links"),
    "get_scout_seeds": ("countyiq.lib.scout.seeds", "get_scout_seeds"),
    "monitor_registry_sources": ("countyiq.lib.scout.discovery", "monitor_registry_sources"),
    "select_promoted_candidates": ("countyiq.lib.scout.discovery", "select_promoted_candidates"),
}


def __getattr__(name: str) -> Any:
    """Resolve package re-exports lazily to avoid import-order cycles."""
    try:
        module_path, attr_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc

    value = getattr(import_module(module_path), attr_name)
    globals()[name] = value
    return value

__all__ = [
    "PROMOTION_THRESHOLD",
    "CandidateRecord",
    "ObservationRecord",
    "ProbeResult",
    "RegistryMonitorRecord",
    "ScoutSeed",
    "classify_candidate",
    "discover_county_sources",
    "extract_relevant_links",
    "get_scout_seeds",
    "monitor_registry_sources",
    "select_promoted_candidates",
]
