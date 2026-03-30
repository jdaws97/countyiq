"""Shared models for County Scout."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ScoutSeed:
    """A curated York County discovery entry point."""

    county_key: str
    slug: str
    name: str
    url: str
    discovery_method: str
    category_hints: tuple[str, ...]
    audience_hints: tuple[str, ...] = ()
    notes: str = ""
    allow_external_domains: tuple[str, ...] = ()
    max_discovery_links: int = 12
    monitor_interval_hours: int = 24


@dataclass
class ProbeResult:
    """The result of probing a candidate URL."""

    requested_url: str
    final_url: str
    status_code: int | None
    content_type: str
    title: str
    text_content: str
    response_ms: int | None
    content_hash: str | None
    etag: str | None
    last_modified: str | None
    probe_status: str
    error: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    html: str | None = None

    @property
    def normalized_text(self) -> str:
        return " ".join(self.text_content.split())


@dataclass
class CandidateRecord:
    """The current best-known classification for a public source."""

    source_key: str
    county_key: str
    seed_slug: str
    source_name: str
    source_url: str
    normalized_url: str
    parent_url: str | None
    discovery_method: str
    source_type: str
    platform: str
    extraction_method: str
    categories: list[str]
    audiences: list[str]
    value_score: int
    risk_level: str
    risk_memo: str
    alert_examples: list[str]
    product_examples: list[str]
    monitor_interval_hours: int
    classification_confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ObservationRecord:
    """A point-in-time observation for a monitored or discovered source."""

    source_key: str
    county_key: str
    source_url: str
    probe_status: str
    status_code: int | None
    final_url: str
    content_type: str
    extraction_method: str
    response_ms: int | None
    content_hash: str | None
    etag: str | None
    last_modified: str | None
    notes: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RegistryMonitorRecord:
    """A registry update after re-checking a promoted source."""

    source_key: str
    source_url: str
    health_status: str
    probe_status: str
    status_code: int | None
    content_hash: str | None
    last_changed: bool
    notes: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
