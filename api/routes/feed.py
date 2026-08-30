"""Unified evidence-backed intelligence feed."""

import re

from typing import Literal

from fastapi import APIRouter, Query

from api.lib.database import get_cursor
from api.lib.response_types import IntelligenceFeedResponse
from api.lib.serialization import serialize_temporal_fields
from api.lib.settings import open_data_source_key
from api.lib.source_policy import (
    is_public_organization,
    require_source_use,
    source_use_allowed,
)


router = APIRouter(tags=["feed"])

_ALLOWED_EVENT_TYPES = {
    "transfer",
    "value_change",
    "structure_change",
    "delinquency_change",
    "application",
    "hearing",
    "revision",
    "continuance",
    "approval",
    "denial",
    "condition",
    "upcoming_decision",
}


def _csv_values(value: str | None, *, limit: int = 100) -> list[str]:
    if not value:
        return []
    return list(dict.fromkeys(part.strip() for part in value.split(",") if part.strip()))[:limit]


def _csv_ints(value: str | None, *, limit: int = 100) -> list[int]:
    values: list[int] = []
    for part in _csv_values(value, limit=limit):
        try:
            parsed = int(part)
        except ValueError:
            continue
        if parsed > 0 and parsed not in values:
            values.append(parsed)
    return values


_PRIORITY_SQL = """
    CASE
        WHEN event_type IN ('approval', 'denial', 'upcoming_decision') THEN 90
        WHEN event_type IN ('condition', 'application', 'hearing') THEN 80
        WHEN event_type IN ('revision', 'continuance') THEN 70
        WHEN event_type = 'transfer' THEN 65
        WHEN event_type IN ('delinquency_change', 'structure_change') THEN 55
        ELSE 45
    END
    + LEAST(COALESCE(cardinality(related_pidns), 0), 3) * 3
    + LEAST(COALESCE(cardinality(related_entities), 0), 3) * 3
    + CASE WHEN project_key IS NOT NULL THEN 5 ELSE 0 END
    + CASE WHEN jsonb_array_length(COALESCE(source_evidence, '[]'::jsonb)) > 0 THEN 5 ELSE 0 END
"""


def _importance_reasons(row: dict) -> list[str]:
    reasons: list[str] = []
    event_type = row.get("event_type")
    if event_type in {"approval", "denial", "upcoming_decision"}:
        reasons.append("Decision or deadline")
    elif event_type in {"condition", "application", "hearing"}:
        reasons.append("Active municipal action")
    elif event_type == "transfer":
        reasons.append("Ownership change")
    if row.get("project_key"):
        reasons.append("Linked project")
    if row.get("related_entities"):
        reasons.append("Named entity")
    if row.get("related_pidns"):
        reasons.append("Parcel linked")
    if row.get("source_evidence"):
        reasons.append("Primary evidence available")
    return reasons[:4]


def _redact_hidden_entities(text: str | None, hidden_entities: list[str]) -> str:
    """Preserve the useful event sentence while removing known natural people."""

    value = str(text or "").strip()
    for name in sorted(hidden_entities, key=len, reverse=True):
        if len(name.strip()) < 3:
            continue
        value = re.sub(re.escape(name.strip()), "a private party", value, flags=re.IGNORECASE)
    return value


def _resolve_entity_links(
    cur,
    rows: list[dict],
    *,
    allow_people: bool,
) -> dict[str, dict]:
    names = list(
        dict.fromkeys(
            name.strip()
            for row in rows
            for name in (row.get("related_entities") or [])
            if isinstance(name, str) and name.strip()
        )
    )
    if not names:
        return {}
    lower_names = [name.lower() for name in names]
    cur.execute(
        """
        SELECT owner_id, canonical_name, aliases, entity_type, verification_status
        FROM public.owners
        WHERE lower(canonical_name) = ANY(%(names)s)
           OR EXISTS (
                SELECT 1
                FROM unnest(COALESCE(aliases, ARRAY[]::text[])) alias
                WHERE lower(alias) = ANY(%(names)s)
           )
        """,
        {"names": lower_names},
    )
    links: dict[str, dict] = {}
    for owner in cur.fetchall():
        if not allow_people and not is_public_organization(owner.get("entity_type")):
            continue
        link = {
            "owner_id": owner["owner_id"],
            "name": owner["canonical_name"],
            "verification_status": owner.get("verification_status"),
        }
        for candidate in [owner["canonical_name"], *(owner.get("aliases") or [])]:
            links[str(candidate).strip().lower()] = link
    return links


def _require_entity_filter_policy(
    cur,
    *,
    names: list[str],
    owner_ids: list[int],
    allow_people: bool,
) -> None:
    """Allow organization watch filters while keeping natural people hidden."""

    if allow_people or not (names or owner_ids):
        return
    cur.execute(
        """
        SELECT owner_id, canonical_name, aliases, entity_type
        FROM public.owners
        WHERE owner_id = ANY(%(owner_ids)s::integer[])
           OR lower(canonical_name) = ANY(%(names)s::text[])
           OR EXISTS (
                SELECT 1 FROM unnest(COALESCE(aliases, ARRAY[]::text[])) alias
                WHERE lower(alias) = ANY(%(names)s::text[])
           )
        """,
        {"owner_ids": owner_ids, "names": names},
    )
    rows = cur.fetchall()
    matched_ids = {row["owner_id"] for row in rows}
    matched_names = {
        str(candidate).strip().lower()
        for row in rows
        for candidate in [row["canonical_name"], *(row.get("aliases") or [])]
    }
    if (
        not set(owner_ids) <= matched_ids
        or not set(names) <= matched_names
        or not all(is_public_organization(row.get("entity_type")) for row in rows)
    ):
        require_source_use(cur, open_data_source_key(), "person_level_display")


@router.get("")
def intelligence_feed(
    category: Literal["parcel", "development"] | None = Query(default=None),
    event_type: str | None = Query(
        default=None,
        description="Comma-separated event types or tags",
    ),
    municipality: str | None = Query(default=None),
    since_days: int | None = Query(default=90, ge=1, le=3650),
    pidns: str | None = Query(default=None, description="Comma-separated watched PIDNs"),
    project_keys: str | None = Query(
        default=None,
        description="Comma-separated locally watched project keys",
    ),
    entity_names: str | None = Query(
        default=None,
        description="Comma-separated canonical or alias names for locally watched entities",
    ),
    entity_ids: str | None = Query(
        default=None,
        description="Comma-separated stable owner/entity IDs for locally watched entities",
    ),
    sort: Literal["priority", "latest"] = Query(default="priority"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> IntelligenceFeedResponse:
    """Return parcel facts and LLM-extracted development events in one contract."""
    filters = ["TRUE"]
    params: dict[str, object] = {"fetch_limit": limit + 1, "offset": offset}

    if category:
        filters.append("category = %(category)s")
        params["category"] = category

    event_types = [
        value for value in _csv_values(event_type, limit=len(_ALLOWED_EVENT_TYPES))
        if value in _ALLOWED_EVENT_TYPES
    ]
    if event_types:
        filters.append("event_tags && %(event_types)s::text[]")
        params["event_types"] = event_types

    if municipality and municipality.strip():
        filters.append("municipality ILIKE %(municipality)s")
        params["municipality"] = municipality.strip()

    if since_days is not None:
        filters.append("detected_at >= NOW() - MAKE_INTERVAL(days => %(since_days)s)")
        params["since_days"] = since_days

    pidn_values = _csv_values(pidns)
    if pidn_values:
        filters.append("related_pidns && %(pidns)s::text[]")
        params["pidns"] = pidn_values

    project_values = _csv_values(project_keys)
    if project_values:
        filters.append("project_key = ANY(%(project_keys)s::text[])")
        params["project_keys"] = project_values

    entity_values = [value.lower() for value in _csv_values(entity_names)]
    if entity_values:
        filters.append(
            "EXISTS (SELECT 1 FROM unnest(COALESCE(related_entities, ARRAY[]::text[])) "
            "entity_name WHERE lower(entity_name) = ANY(%(entity_names)s))"
        )
        params["entity_names"] = entity_values

    entity_id_values = _csv_ints(entity_ids)
    if entity_id_values:
        filters.append(
            "EXISTS ("
            "SELECT 1 FROM public.owners watched_owner "
            "CROSS JOIN LATERAL unnest(COALESCE(related_entities, ARRAY[]::text[])) event_entity "
            "WHERE watched_owner.owner_id = ANY(%(entity_ids)s::integer[]) "
            "AND (lower(event_entity) = lower(watched_owner.canonical_name) "
            "OR lower(event_entity) = ANY(ARRAY(SELECT lower(alias) FROM "
            "unnest(COALESCE(watched_owner.aliases, ARRAY[]::text[])) alias)))"
            ")"
        )
        params["entity_ids"] = entity_id_values

    order_clause = (
        "priority_score DESC, COALESCE(event_date, detected_at::date) DESC, "
        "detected_at DESC, event_key DESC"
        if sort == "priority"
        else "COALESCE(event_date, detected_at::date) DESC, detected_at DESC, event_key DESC"
    )

    with get_cursor() as cur:
        parcel_source = open_data_source_key()
        for source_key in (
            parcel_source,
            "tax_claims",
            "sheriff_sales",
            "public_proceedings",
        ):
            require_source_use(cur, source_key, "derived_product", conceal=False)
        show_parcel_people = source_use_allowed(
            cur, parcel_source, "person_level_display"
        )
        show_proceeding_people = source_use_allowed(
            cur, "public_proceedings", "person_level_display"
        )
        _require_entity_filter_policy(
            cur,
            names=entity_values,
            owner_ids=entity_id_values,
            allow_people=show_parcel_people,
        )
        cur.execute(
            f"""
            SELECT
                event_key,
                category,
                event_type,
                event_tags,
                title,
                what_happened,
                why_it_matters,
                what_happens_next,
                event_date,
                detected_at,
                confidence,
                municipality,
                project_key,
                project_name,
                related_entities,
                related_pidns,
                source_evidence,
                interpretation_kind,
                interpretation_model,
                interpretation_generated_at,
                ({_PRIORITY_SQL})::integer AS priority_score
            FROM public.intelligence_events
            WHERE {' AND '.join(filters)}
            ORDER BY {order_clause}
            LIMIT %(fetch_limit)s OFFSET %(offset)s
            """,
            params,
        )
        rows = [dict(row) for row in cur.fetchall()]
        entity_links_by_name = _resolve_entity_links(
            cur,
            rows,
            allow_people=show_parcel_people and show_proceeding_people,
        )

    has_more = len(rows) > limit
    rows = rows[:limit]
    events = []
    for row in rows:
        serialize_temporal_fields(
            row,
            "event_date",
            "detected_at",
            "interpretation_generated_at",
        )
        show_people = (
            show_parcel_people
            if row["category"] == "parcel"
            else show_proceeding_people
        )
        project = None
        if row.get("project_key"):
            project = {
                "key": row["project_key"],
                "name": row.get("project_name") or row["project_key"],
            }
        related_entities = [
            str(name)
            for name in (row.get("related_entities") or [])
            if str(name).strip().lower() in entity_links_by_name
        ]
        if show_people:
            title = row["title"]
            what_happened = row["what_happened"]
            why_it_matters = row["why_it_matters"]
            what_happens_next = row["what_happens_next"]
            sources = list(row.get("source_evidence") or [])
        else:
            event_label = str(row["event_type"]).replace("_", " ")
            location = row.get("municipality") or "York County"
            hidden_entities = [
                str(name)
                for name in (row.get("related_entities") or [])
                if str(name).strip().lower() not in entity_links_by_name
            ]
            title = _redact_hidden_entities(row.get("title"), hidden_entities) or (
                f"{event_label.title()} · {row.get('project_name') or location}"
            )
            what_happened = _redact_hidden_entities(
                row.get("what_happened"), hidden_entities
            ) or f"A {event_label} was recorded for {row.get('project_name') or location}."
            why_it_matters = _redact_hidden_entities(
                row.get("why_it_matters"), hidden_entities
            ) or "The recorded action changes the status of the linked project or parcel."
            what_happens_next = _redact_hidden_entities(
                row.get("what_happens_next"), hidden_entities
            ) or "Review the official source and monitor the next municipal action."
            sources = [
                {
                    "label": source.get("label") or "Official source",
                    "url": source.get("url"),
                    "document_url": source.get("document_url"),
                    "excerpt": None,
                    "details": {},
                }
                for source in (row.get("source_evidence") or [])
                if isinstance(source, dict)
            ]
        display_row = {**row, "related_entities": related_entities}
        events.append(
            {
                "event_key": row["event_key"],
                "category": row["category"],
                "event_type": row["event_type"],
                "event_tags": list(row.get("event_tags") or []),
                "title": title,
                "what_happened": what_happened,
                "why_it_matters": why_it_matters,
                "what_happens_next": what_happens_next,
                "event_date": row.get("event_date"),
                "detected_at": row["detected_at"],
                "confidence": row.get("confidence"),
                "municipality": row.get("municipality"),
                "project": project,
                "related_entities": related_entities,
                "entity_links": list(
                    {
                        link["owner_id"]: {**link, "matched_name": str(name)}
                        for name in related_entities
                        if (link := entity_links_by_name.get(str(name).strip().lower()))
                    }.values()
                ),
                "related_pidns": list(row.get("related_pidns") or []),
                "importance_score": row["priority_score"],
                "importance_reasons": _importance_reasons(display_row),
                "sources": sources,
                "interpretation": {
                    "kind": row["interpretation_kind"],
                    "model": row.get("interpretation_model"),
                    "generated_at": row.get("interpretation_generated_at"),
                },
            }
        )

    return {
        "events": events,
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
    }
