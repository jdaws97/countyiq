"""Unified evidence-backed intelligence feed."""

from typing import Annotated, Literal

from fastapi import APIRouter, Query

from api.lib.database import get_cursor
from api.lib.evidence import normalize_source_evidence
from api.lib.municipality_names import municipality_event_patterns
from api.lib.response_types import IntelligenceFeedResponse
from api.lib.serialization import serialize_temporal_fields
from api.lib.settings import open_data_source_key, restricted_distress_enabled
from api.lib.source_policy import require_source_use


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
    "policy_action",
    "update",
    "recommendation",
    "withdrawn",
    "removed",
    "scoped_decision",
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


def _municipality_patterns(value: str | None) -> list[str]:
    """ILIKE patterns for comma-separated municipality names.

    A value that already carries a wildcard is used verbatim. A plain name is
    expanded so the county spelling ("CARROLL TWP") and the public-body
    spelling used by extracted events ("Carroll Township") both match.
    """
    patterns: list[str] = []
    for value_part in _csv_values(value):
        if "%" in value_part:
            patterns.append(value_part)
        else:
            patterns.extend(municipality_event_patterns(value_part))
    return list(dict.fromkeys(patterns))


def _watched_entity_sql(parameter: str) -> str:
    # A source name must identify one owner across canonical names and aliases.
    # Verification of either candidate does not resolve a shared-name collision.
    return f"""
        EXISTS (
            SELECT 1
            FROM public.owners watched_owner
            CROSS JOIN LATERAL unnest(COALESCE(related_entities, ARRAY[]::text[])) event_entity
            WHERE watched_owner.owner_id = ANY(%({parameter})s::integer[])
              AND (lower(btrim(event_entity)) = lower(btrim(watched_owner.canonical_name))
                   OR lower(btrim(event_entity)) = ANY(ARRAY(SELECT lower(btrim(alias)) FROM
                       unnest(COALESCE(watched_owner.aliases, ARRAY[]::text[])) alias)))
              AND NOT EXISTS (
                  SELECT 1 FROM public.owners competing_owner
                  WHERE competing_owner.owner_id <> watched_owner.owner_id
                    AND (lower(btrim(event_entity)) = lower(btrim(competing_owner.canonical_name))
                         OR lower(btrim(event_entity)) = ANY(ARRAY(SELECT lower(btrim(alias)) FROM
                             unnest(COALESCE(competing_owner.aliases, ARRAY[]::text[])) alias)))
              )
        )
    """


_WATCHED_ENTITY_SQL = _watched_entity_sql("boost_entity_ids")

_WATCHED_MATCH_SQL = f"""
    (related_pidns && %(boost_pidns)s::text[]
     OR project_key = ANY(%(boost_project_keys)s::text[])
     OR {_WATCHED_ENTITY_SQL}
     OR municipality ILIKE ANY(%(boost_municipalities)s::text[]))
"""

_PRIORITY_SQL = f"""
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
    + CASE
        WHEN event_type = 'delinquency_change' THEN
            CASE COALESCE(source_evidence->0->'details'->>'change_kind', '')
                WHEN 'new' THEN 10
                WHEN 'increased' THEN 7
                WHEN 'decreased' THEN -5
                WHEN 'resolved' THEN -10
                ELSE 0
            END
        ELSE 0
      END
    -- Recency decay: a decision from ten months ago should not outrank this
    -- week's application forever. Two points per fortnight, capped at 25, so
    -- an old approval (90) still lands above a fresh delinquency change (55).
    - LEAST(
        GREATEST(CURRENT_DATE - COALESCE(event_date, detected_at::date), 0) / 14,
        25
      )
    -- Watched-subject boost: the caller passes its browser-local watches so
    -- the general feed leads with what this user already follows. A watched
    -- municipality is a broader interest than a watched parcel, project, or
    -- entity, so it earns a smaller boost.
    + CASE
        WHEN related_pidns && %(boost_pidns)s::text[] THEN 15
        WHEN project_key = ANY(%(boost_project_keys)s::text[]) THEN 15
        WHEN {_WATCHED_ENTITY_SQL} THEN 15
        WHEN municipality ILIKE ANY(%(boost_municipalities)s::text[]) THEN 8
        ELSE 0
      END
"""


def _display_event_copy(row: dict, *, allow_restricted_distress: bool) -> dict:
    """Remove exact debt detail from public delinquency transitions.

    The event and source breadcrumb remain visible. The restricted flag controls
    whether CountyIQ itself serves balances, claim counts, and tax-year history.
    """
    if row.get("source_kind") != "delinquency_event" or allow_restricted_distress:
        return row

    raw_sources = row.get("source_evidence") or []
    change_kind = str(
        ((raw_sources[0].get("details") or {}).get("change_kind"))
        if raw_sources and isinstance(raw_sources[0], dict)
        else "changed"
    )
    happened = {
        "new": "The county tax-claim listing added a reported delinquency.",
        "resolved": "A previously reported delinquency no longer appears in the current county listing.",
        "increased": "The reported delinquency increased since the prior county listing.",
        "decreased": "The reported delinquency decreased since the prior county listing.",
    }.get(change_kind, "The reported delinquency changed since the prior county listing.")
    safe_sources = [
        {
            **source,
            "excerpt": None,
            "details": {"change_kind": change_kind},
        }
        for source in raw_sources
        if isinstance(source, dict)
    ]
    return {
        **row,
        "what_happened": happened,
        "why_it_matters": (
            "A change in the public listing can warrant source review, but it does not "
            "establish the balance, lien priority, willingness to sell, or other obligations."
        ),
        "what_happens_next": "Use the cited county listing to verify the current source status.",
        "source_evidence": safe_sources,
    }


def _importance_reasons(row: dict) -> list[str]:
    reasons: list[str] = []
    if row.get("watched_match"):
        reasons.append("Watched subject")
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


def _resolve_entity_links(cur, rows: list[dict]) -> dict[str, dict]:
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
        WHERE lower(btrim(canonical_name)) = ANY(%(names)s)
           OR EXISTS (
                SELECT 1
                FROM unnest(COALESCE(aliases, ARRAY[]::text[])) alias
                WHERE lower(btrim(alias)) = ANY(%(names)s)
           )
        """,
        {"names": lower_names},
    )
    candidates: dict[str, dict[int, dict]] = {}
    for owner in cur.fetchall():
        link = {
            "owner_id": owner["owner_id"],
            "name": owner["canonical_name"],
            "verification_status": owner.get("verification_status"),
        }
        for candidate in [owner["canonical_name"], *(owner.get("aliases") or [])]:
            name = str(candidate).strip().lower()
            if name in lower_names:
                candidates.setdefault(name, {})[owner["owner_id"]] = link
    return {name: next(iter(owners.values())) for name, owners in candidates.items()
            if len(owners) == 1}


@router.get("")
def intelligence_feed(
    category: Literal["parcel", "development"] | None = Query(default=None),
    event_type: str | None = Query(
        default=None,
        description="Comma-separated event types or tags",
    ),
    municipality: str | None = Query(
        default=None,
        description="Comma-separated municipality names; a value with % is used as an ILIKE pattern",
    ),
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
    boost_pidns: str | None = Query(
        default=None,
        description="Comma-separated watched PIDNs to rank first without filtering",
    ),
    boost_project_keys: str | None = Query(
        default=None,
        description="Comma-separated watched project keys to rank first without filtering",
    ),
    boost_entity_ids: str | None = Query(
        default=None,
        description="Comma-separated watched entity IDs to rank first without filtering",
    ),
    boost_municipalities: str | None = Query(
        default=None,
        description="Comma-separated watched municipality names to rank early without filtering",
    ),
    near_pidns: str | None = Query(
        default=None,
        description="Comma-separated PIDNs; keep only events on other parcels within near_radius_m of them",
    ),
    near_radius_m: int = Query(default=400, ge=50, le=3000),
    sort: Literal["priority", "latest"] = Query(default="priority"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    matter_category: Annotated[Literal["development", "minor_property", "landuse_policy", "public_works", "context_only"] | None, Query()] = None,
) -> IntelligenceFeedResponse:
    return fetch_feed(**locals())


def fetch_feed(
    category: Literal['parcel', 'development'] | None = None,
    event_type: str | None = None,
    municipality: str | None = None,
    since_days: int | None = 90,
    pidns: str | None = None,
    project_keys: str | None = None,
    entity_names: str | None = None,
    entity_ids: str | None = None,
    boost_pidns: str | None = None,
    boost_project_keys: str | None = None,
    boost_entity_ids: str | None = None,
    boost_municipalities: str | None = None,
    near_pidns: str | None = None,
    near_radius_m: int = 400,
    sort: Literal['priority', 'latest'] = 'priority',
    limit: int = 50,
    offset: int = 0,
    event_keys: list[str] | None = None,
    include_distress: bool = False,
    text_query: str | None = None,
    matter_category: str | None = None,
) -> IntelligenceFeedResponse:
    """Return parcel facts and LLM-extracted development events in one contract."""
    filters = [
        """
        (
            source_kind <> 'proceeding_extraction'
            OR EXISTS (
                SELECT 1
                FROM staging.proceeding_extractions serving_extraction
                JOIN staging.public_proceedings serving_proceeding
                  ON serving_proceeding.id = serving_extraction.proceeding_id
                JOIN meta.municipality_source_rights serving_policy
                  ON serving_policy.body_name = serving_proceeding.body_name
                WHERE serving_extraction.id::text = intelligence_events.source_record_id
                  AND serving_proceeding.valid_to IS NULL
                  AND serving_proceeding.metadata_quality->>'status' = 'ready'
                  AND LEFT(serving_extraction.extraction_type, 1) <> '_'
                  AND serving_policy.rights_status <> 'paused'
                  AND serving_policy.derived_product_allowed = TRUE
                  AND serving_policy.review_due_on >= CURRENT_DATE
            )
        )
        """,
        """
        NOT (
            source_kind = 'delinquency_event'
            AND COALESCE(source_evidence->0->'details'->>'change_kind', '') = 'new'
            AND detected_at = (
                SELECT MIN(baseline.detected_at)
                FROM public.intelligence_events AS baseline
                WHERE baseline.source_kind = 'delinquency_event'
            )
        )
        """,
        """
        NOT (
            source_kind = 'delinquency_event'
            AND COALESCE(source_evidence->0->'details'->>'change_kind', '')
                IN ('increased', 'decreased')
            AND ABS(
                COALESCE((source_evidence->0->'details'->>'new_affected_total')::numeric, 0)
                - COALESCE((source_evidence->0->'details'->>'old_affected_total')::numeric, 0)
            ) < GREATEST(
                100::numeric,
                ABS(COALESCE((source_evidence->0->'details'->>'old_affected_total')::numeric, 0))
                    * 0.10
            )
        )
        """
    ]
    if matter_category:
        filters.append("source_evidence->0->'details'->>'matter_category' = %(matter_category)s")
    elif not any((pidns, project_keys, entity_names, entity_ids, event_keys)):
        # Discovery suppresses context-only matters; explicit history stays complete.
        filters.append("source_evidence->0->'details'->>'discovery_eligible' IS DISTINCT FROM 'false'")
    if text_query:
        filters.append("(strpos(lower(COALESCE(project_name,'')), lower(%(text_query)s))>0 OR strpos(lower(title),lower(%(text_query)s))>0)")
    params: dict[str, object] = {
        "text_query": text_query,
        "matter_category": matter_category,
        "fetch_limit": limit + 1,
        "offset": offset,
        "boost_pidns": _csv_values(boost_pidns),
        "boost_project_keys": _csv_values(boost_project_keys),
        "boost_entity_ids": _csv_ints(boost_entity_ids),
        "boost_municipalities": _municipality_patterns(boost_municipalities),
    }

    if event_keys is not None:
        filters.append("event_key = ANY(%(event_keys)s::text[])")
        params["event_keys"] = event_keys

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
    elif category is None and not include_distress:
        # Keep debt inventory out of the general intelligence queue. Customers
        # can still request the delinquency filter or the parcel category.
        filters.append("source_kind <> 'delinquency_event'")

    municipality_patterns = _municipality_patterns(municipality)
    if municipality_patterns:
        filters.append("municipality ILIKE ANY(%(municipalities)s::text[])")
        params["municipalities"] = municipality_patterns

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

    near_values = _csv_values(near_pidns, limit=50)
    if near_values:
        # "Something happened next door": events on parcels within the radius
        # of a watched parcel, excluding events on the watched parcel itself.
        filters.append(
            "NOT (related_pidns && %(near_pidns)s::text[]) AND EXISTS ("
            "SELECT 1 FROM staging.parcels anchor "
            "JOIN staging.parcels linked ON linked.valid_to IS NULL "
            "AND linked.geom IS NOT NULL "
            "AND linked.pidn = ANY(COALESCE(related_pidns, ARRAY[]::text[])) "
            "WHERE anchor.valid_to IS NULL AND anchor.geom IS NOT NULL "
            "AND anchor.pidn = ANY(%(near_pidns)s::text[]) "
            "AND ST_DWithin(anchor.geom::geography, linked.geom::geography, %(near_radius_m)s))"
        )
        params["near_pidns"] = near_values
        params["near_radius_m"] = near_radius_m

    entity_values = [value.lower() for value in _csv_values(entity_names)]
    if entity_values:
        filters.append(
            "EXISTS (SELECT 1 FROM unnest(COALESCE(related_entities, ARRAY[]::text[])) "
            "entity_name WHERE lower(entity_name) = ANY(%(entity_names)s))"
        )
        params["entity_names"] = entity_values

    entity_id_values = _csv_ints(entity_ids)
    if entity_id_values:
        filters.append(_watched_entity_sql("entity_ids"))
        params["entity_ids"] = entity_id_values

    order_clause = (
        "priority_score DESC, COALESCE(event_date, detected_at::date) DESC, "
        "detected_at DESC, event_key DESC"
        if sort == "priority"
        else "COALESCE(event_date, detected_at::date) DESC, detected_at DESC, event_key DESC"
    )

    with get_cursor() as cur:
        parcel_source = open_data_source_key()
        required_sources = [parcel_source]
        if category != "development":
            required_sources.extend(("tax_claims", "sheriff_sales"))
        if category != "parcel":
            required_sources.append("public_proceedings")
        for source_key in required_sources:
            require_source_use(cur, source_key, "derived_product", conceal=False)
        cur.execute(
            f"""
            SELECT
                event_key,
                source_kind,
                source_record_id,
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
                ({_PRIORITY_SQL})::integer AS priority_score,
                ({_WATCHED_MATCH_SQL}) AS watched_match
            FROM public.intelligence_events
            WHERE {' AND '.join(filters)}
            ORDER BY {order_clause}
            LIMIT %(fetch_limit)s OFFSET %(offset)s
            """,
            params,
        )
        rows = [dict(row) for row in cur.fetchall()]
        entity_links_by_name = _resolve_entity_links(cur, rows)

    has_more = len(rows) > limit
    rows = rows[:limit]
    allow_restricted_distress = restricted_distress_enabled()
    events = []
    for row in rows:
        row = _display_event_copy(
            row,
            allow_restricted_distress=allow_restricted_distress,
        )
        display_confidence = (
            row.get("confidence")
            if row["interpretation_kind"] == "llm"
            else None
        )
        serialize_temporal_fields(
            row,
            "event_date",
            "detected_at",
            "interpretation_generated_at",
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
        title = row["title"]
        what_happened = row["what_happened"]
        why_it_matters = row["why_it_matters"]
        what_happens_next = row["what_happens_next"]
        raw_sources = list(row.get("source_evidence") or [])
        sources = [
            normalize_source_evidence(
                source,
                scope=f"event:{row['event_key']}",
                index=index,
                source_kind=str(row.get("source_kind") or f"{row['category']}_event"),
                source_record_id=row.get("source_record_id") or row["event_key"],
                effective_at=row.get("event_date"),
                observed_at=row["detected_at"],
                interpretation_kind=str(row["interpretation_kind"]),
                confidence=display_confidence,
                # Parcel-record events cite the county parcel layer; deep-link
                # the customer to the parcel's own record, not the layer root.
                record_query=(
                    ("PIDN", list(row.get("related_pidns") or [])[:1])
                    if row.get("source_kind") == "parcel_event" and row.get("related_pidns")
                    else None
                ),
            )
            for index, source in enumerate(raw_sources)
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
                "confidence": display_confidence,
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
