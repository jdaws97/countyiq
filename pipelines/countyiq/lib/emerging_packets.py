"""Gather bounded, reproducible evidence without inventing project identity."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

from countyiq.lib.intelligence_integrity import content_hash

DEFAULT_SETTINGS = {
    "open_data_key": "york_open_data",
    "planning_radius_m": 500,
    "environmental_radius_m": 500,
    "neighbor_limit": 6,
}


def fetch_scope(cur, bundle_key: str, settings: dict | None = None) -> dict:
    from countyiq.lib.county_config import county_open_data_source_key

    if settings is None:
        settings = {**DEFAULT_SETTINGS, "open_data_key": county_open_data_source_key()}
    if settings.get("open_data_key") != county_open_data_source_key():
        raise ValueError(
            "Evidence scope must use the configured county parcel-source policy"
        )
    cur.execute(
        "SELECT public.emerging_scope_source(%s, %s, %s, %s, %s) AS source",
        (bundle_key, *[settings[key] for key in DEFAULT_SETTINGS]),
    )
    row = cur.fetchone()
    source = row["source"] if isinstance(row, dict) else row[0]
    if not source:
        raise ValueError("No current permitted source scope exists for this key")
    return source


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def build_packet(
    source: dict, *, captured_at: str | None = None, cutoff: str | None = None
) -> dict:
    """Historical mode requires both record date and observed date by cutoff.

    Present-day geographic layers lack complete historical availability metadata,
    so replay excludes them and all inferred retrieval relationships.
    """
    captured_at = captured_at or datetime.now(UTC).isoformat()
    boundary = _instant(cutoff) if cutoff else None
    if boundary and boundary > _instant(captured_at):
        raise ValueError("Historical cutoff cannot follow packet capture")
    sources = []
    seen = set()
    properties = []
    municipalities = set()
    availability = source.get("record_availability", {})

    def add(item: dict, record_key: str, **context):
        original = deepcopy(item)
        signature = content_hash(
            {key: original.get(key) for key in ("url", "text", "facts")}
        )
        if signature in seen:
            return
        seen.add(signature)
        original_id = original.pop("id")
        sources.append(
            {
                **original,
                **context,
                "id": f"S{len(sources) + 1}",
                "original_id": original_id,
                "record_key": record_key,
                "document_identity": original.get("url") or record_key,
            }
        )

    for bundle in source["municipal_bundles"]:
        if boundary and bundle.get("subject_key") != source["seed_bundle"]:
            # Current adjoining-parcel discovery must not select replay evidence.
            continue
        municipality = bundle.get("municipality")
        if municipality:
            municipalities.add(municipality)
        for item in bundle.get("sources") or []:
            observed = availability.get(item["record_key"])
            record_date = item.get("meeting_date")
            if boundary and (
                not observed
                or not record_date
                or _instant(observed) > boundary
                or _instant(record_date) > boundary
            ):
                continue
            add(item, item["record_key"], available_at=observed)
    if not boundary:
        for bundle in source["property_bundles"]:
            context = bundle.get("source")
            if not context:
                continue
            for item in context.get("sources") or []:
                # Municipal evidence enters with its own dated provenance above.
                if "text" not in item:
                    add(
                        item,
                        f"parcel:{bundle['pidn']}:{item['id']}",
                        pidn=bundle["pidn"],
                    )
                if item["id"] == "parcel":
                    facts = item.get("facts", {})
                    properties.append(
                        {
                            "pidn": bundle["pidn"],
                            "relationship": bundle["relationship"],
                            "address": facts.get("address"),
                            "owner": facts.get("recorded_owner"),
                            "acres": facts.get("acres"),
                        }
                    )
        if source["relationships"]:
            add(
                {
                    "id": "retrieval_relationships",
                    "label": "Parcel boundary relationships",
                    "facts": {"relationships": source["relationships"]},
                },
                "parcel_boundaries",
            )
    return {
        "contract_version": 1,
        "temporal_mode": "observed_cutoff" if boundary else "current",
        "captured_at": captured_at,
        "as_of": cutoff or captured_at,
        "source": source,
        "sources": sources,
        "municipalities": sorted(municipalities),
        "properties": properties,
        "scope_note": (
            "Retrospectively selected seed-scope municipal excerpts dated and observed by the cutoff. "
            "Current property context, adjoining-scope retrieval and relationships are excluded. "
            "This reconstruction does not establish what the production pipeline knew then."
            if boundary
            else "A bounded review of linked municipal excerpts and up to "
            f"{source['settings']['neighbor_limit']} adjoining parcels. "
            "Candidate groupings and boundary overlap do not establish one project or common control."
        ),
        "scope_limits": (
            {
                "historical_sources_included": len(sources),
                "current_property_context_included": False,
            }
            if boundary
            else source["scope_limits"]
        ),
    }


def verify_packet(cur, packet: dict) -> None:
    source = packet["source"]
    current = fetch_scope(cur, source["seed_bundle"], source["settings"])
    if current != source:
        raise ValueError("Evidence changed; export and assess a fresh packet")
    rebuilt = build_packet(
        current,
        captured_at=packet["captured_at"],
        cutoff=packet["as_of"]
        if packet["temporal_mode"] == "observed_cutoff"
        else None,
    )
    if rebuilt != packet:
        raise ValueError("Packet differs from its canonical source mapping")
    if _instant(packet["captured_at"]) > datetime.now(UTC):
        raise ValueError("Packet capture time is in the future")
