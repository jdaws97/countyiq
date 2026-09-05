"""Customer-facing evidence receipts built from existing serving data."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import urlencode

from api.lib.development_radar import SIGNAL_CAVEATS, format_signal_label

# A bare ArcGIS layer endpoint (".../FeatureServer/0"). Linking a customer to
# it shows the whole layer's REST page, not their record. When the record's
# key is known we deep-link to the layer's HTML query for that record instead.
_ARCGIS_LAYER_RE = re.compile(r"^(https://[^?#\s]+/(?:FeatureServer|MapServer)/\d+)/?$")
_ARCGIS_SERVICE_RE = re.compile(r"^(https://[^?#\s]+/(?:FeatureServer|MapServer))/?$")
_ARCGIS_FIELD_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ARCGIS_VALUE_RE = re.compile(r"^[A-Za-z0-9_\-{}.]+$")
# Only ArcGIS object-id fields are integers; every other key we link on
# (PIDN, FLD_AR_ID, GlobalID, SEQU_NUM) is text and must stay quoted even when
# its value happens to be all digits.
_ARCGIS_INTEGER_FIELDS = {"OBJECTID", "OBJECTID_1"}

# FEMA NFHL MapServer layer for S_Fld_Haz_Ar (flood hazard areas). The staging
# rows store the service root; the layer index is a fixed part of the national
# NFHL service, not a county setting.
NFHL_FLOOD_HAZARD_LAYER = 28


def with_arcgis_layer(service_url: object, layer: int) -> str | None:
    """Append a layer index to a bare ArcGIS service URL; pass layer URLs through."""

    text = str(service_url or "").strip()
    if not text:
        return None
    if _ARCGIS_LAYER_RE.match(text):
        return text
    match = _ARCGIS_SERVICE_RE.match(text)
    return f"{match.group(1)}/{layer}" if match else text

# Signal key -> the source layer's record key field, for deterministic signals
# whose ``source_id`` is that layer's key (see assets/enrichment/development_signals.py).
SIGNAL_RECORD_FIELDS: dict[str, str] = {
    "active_subdivision": "SEQU_NUM",
    "nearby_subdivision": "SEQU_NUM",
    "economic_development_park": "OBJECTID",
    "flood_zone": "FLD_AR_ID",
    "growth_area": "GlobalID",
    "development_overlay": "GlobalID",
    "zoning_mismatch": "GlobalID",
    "zoning_constraint": "GlobalID",
    "soil_constraint": "OBJECTID_1",
    "local_traffic_activity": "GlobalID",
    "conservation_easement": "EASE_ID",
    "ag_security": "RESOLUTION",
}


def arcgis_record_url(layer_url: object, field: str, values: Iterable[object]) -> str | None:
    """Return an HTML deep link to specific records in an ArcGIS layer.

    Returns None when ``layer_url`` is not a bare layer endpoint, the field is
    not a plain identifier, or any value contains characters outside the
    identifier alphabet (so a value can never alter the WHERE clause).
    """

    match = _ARCGIS_LAYER_RE.match(str(layer_url or "").strip())
    if not match or not _ARCGIS_FIELD_RE.match(field):
        return None
    cleaned = [str(value).strip() for value in values if str(value or "").strip()]
    if not cleaned or any(not _ARCGIS_VALUE_RE.match(value) for value in cleaned):
        return None
    integer_field = field.upper() in _ARCGIS_INTEGER_FIELDS
    literals = [
        value if integer_field and value.isdigit() else f"'{value}'"
        for value in cleaned[:25]
    ]
    where = f"{field}={literals[0]}" if len(literals) == 1 else f"{field} IN ({','.join(literals)})"
    query = urlencode({"where": where, "outFields": "*", "f": "html"})
    return f"{match.group(1)}/query?{query}"


def _mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _text(value: object) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def evidence_id(scope: str, citation_key: str) -> str:
    """Return a stable, HTML-anchor-safe evidence identifier."""

    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", f"{scope}-{citation_key}")
    return normalized.strip("-").lower()


def evidence_item(
    *,
    scope: str,
    citation_key: str,
    label: str,
    source_kind: str,
    source_record_id: object = None,
    url: object = None,
    document_url: object = None,
    internal_url: object = None,
    excerpt: object = None,
    details: Mapping[str, object] | None = None,
    effective_at: object = None,
    observed_at: object = None,
    method: str,
    caveat: str | None = None,
    confidence: object = None,
    record_query: tuple[str, Iterable[object]] | None = None,
) -> dict[str, Any]:
    """Build the shared API contract for one customer-verifiable receipt.

    ``record_query`` is ``(field, values)`` identifying this receipt's records
    inside an ArcGIS layer; when ``url`` is a bare layer endpoint it is
    replaced with a record-level HTML query so the link opens the actual
    record rather than the layer index.
    """

    if record_query is not None:
        field, values = record_query
        url = arcgis_record_url(url, field, values) or url

    return {
        "evidence_id": evidence_id(scope, citation_key),
        "citation_key": citation_key,
        "label": label,
        "source_kind": source_kind,
        "source_record_id": _text(source_record_id),
        "url": _text(url),
        "document_url": _text(document_url),
        "internal_url": _text(internal_url),
        "excerpt": _text(excerpt),
        "details": dict(details or {}),
        "effective_at": effective_at,
        "observed_at": observed_at,
        "method": method,
        "caveat": caveat,
        "confidence": confidence,
    }


def signal_evidence_items(
    signals: Mapping[str, object] | None,
    citation_keys: Iterable[str],
    *,
    scope: str,
    pidn: str | None = None,
    observed_at: object = None,
) -> list[dict[str, Any]]:
    """Resolve brief citation keys to the public-safe signal evidence already served."""

    signal_map = _mapping(signals)
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_key in citation_keys:
        key = str(raw_key).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        signal = _mapping(signal_map.get(key))
        raw_evidence = _mapping(signal.get("evidence"))
        facts = dict(raw_evidence or signal)

        detail_url = facts.pop("detail_url", None)
        evidence_source_url = facts.pop("source_url", None)
        document_url = facts.pop("document_url", None)
        for field in (
            "claim",
            "validation_status",
            "adjusted_significance",
            "validation_reasoning",
            "weight",
            "base_weight",
            "distance_m",
        ):
            if signal.get(field) is not None:
                facts[field] = signal[field]

        source_url = detail_url or signal.get("source_url") or evidence_source_url
        record_field = SIGNAL_RECORD_FIELDS.get(key)
        source_values = raw_evidence.get("source_record_ids")
        if not isinstance(source_values, (list, tuple)):
            source_values = [signal.get("source_id")]
        source_records = raw_evidence.get("source_records")
        if isinstance(source_records, (list, tuple)) and source_records:
            first_record = _mapping(source_records[0])
            source_url = first_record.get("source_url") or source_url
            if first_record.get("objectid") is not None:
                source_values = [first_record["objectid"]]
        record_query = (
            (record_field, source_values)
            if record_field and not detail_url and any(value not in (None, "") for value in source_values)
            else None
        )
        internal_url = signal.get("internal_url") or (f"/property/{pidn}" if pidn else None)
        validated = bool(signal.get("validation_status") or signal.get("validation_reasoning"))
        items.append(
            evidence_item(
                scope=scope,
                citation_key=f"signal:{key}",
                label=format_signal_label(key, signal) if signal else key.replace("_", " ").title(),
                source_kind="validated_signal" if validated else "derived_signal",
                source_record_id=signal.get("source_id") or (f"{pidn}:{key}" if pidn else key),
                url=source_url,
                document_url=document_url,
                internal_url=internal_url,
                details=facts,
                observed_at=signal.get("validated_at") or observed_at,
                method=(
                    "CountyIQ validated this signal against the cited source facts."
                    if validated
                    else "CountyIQ derived this signal deterministically from the cited public record."
                ),
                caveat=SIGNAL_CAVEATS.get(key),
                confidence=signal.get("confidence"),
                record_query=record_query,
            )
        )
    return items


def normalize_source_evidence(
    source: Mapping[str, object],
    *,
    scope: str,
    index: int,
    source_kind: str,
    source_record_id: object,
    effective_at: object,
    observed_at: object,
    interpretation_kind: str,
    confidence: object,
    record_query: tuple[str, Iterable[object]] | None = None,
) -> dict[str, Any]:
    """Upgrade legacy feed source JSON to the shared evidence receipt contract."""

    details = _mapping(source.get("details"))
    return evidence_item(
        record_query=record_query,
        scope=scope,
        citation_key=f"source:{index + 1}",
        label=_text(source.get("label")) or "Official source",
        source_kind=source_kind,
        source_record_id=source_record_id,
        url=source.get("url"),
        document_url=source.get("document_url"),
        internal_url=source.get("internal_url"),
        excerpt=source.get("excerpt"),
        details=details,
        effective_at=effective_at,
        observed_at=observed_at,
        method=(
            "CountyIQ used a language model to extract this event from the cited source. Consult the source passage for its full context."
            if interpretation_kind == "llm"
            else "CountyIQ detected this change deterministically from versioned source records."
        ),
        caveat=(
            "LLM interpretation is visibly separated from the underlying source facts."
            if interpretation_kind == "llm"
            else None
        ),
        confidence=confidence,
    )
