"""Direct discovery of organizations and source-backed project case files."""

from fastapi import APIRouter, Query
from typing import Literal
from api.lib.database import get_cursor
from api.lib.settings import open_data_source_key
from api.lib.source_policy import require_source_use
from api.routes.feed import fetch_feed

router = APIRouter()


@router.get("/organizations")
def organizations(
    q: str = Query(default="", max_length=160),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
):
    with get_cursor() as cur:
        require_source_use(
            cur, open_data_source_key(), "derived_product", conceal=False
        )
        cur.execute(
            """SELECT owner_id,canonical_name,entity_type,parcel_count,municipality,verification_status
            FROM public.owners WHERE entity_type IN ('business','government')
            AND (strpos(lower(canonical_name),lower(%s))>0 OR EXISTS(
                SELECT 1 FROM unnest(aliases) alias WHERE strpos(lower(alias),lower(%s))>0))
            ORDER BY parcel_count DESC,canonical_name,owner_id LIMIT %s OFFSET %s""",
            (q, q, limit + 1, offset),
        )
        rows = [dict(row) for row in cur.fetchall()]
    return {"organizations": rows[:limit], "has_more": len(rows) > limit}


@router.get("/projects")
def projects(
    q: str = Query(default="", max_length=160),
    limit: int = Query(default=20, ge=1, le=100),
    kind: Literal[
        "all", "development", "minor_property", "landuse_policy", "public_works"
    ] = Query(default="all"),
):
    feed = fetch_feed(
        category="development",
        since_days=None,
        sort="latest",
        limit=500,
        text_query=q or None,
        matter_category=kind if kind != "all" else None,
    )
    grouped = {}
    for event in feed["events"]:
        categories = {
            source.get("details", {}).get("matter_category")
            for source in event.get("sources", [])
            if isinstance(source.get("details"), dict)
        }
        if kind != "all" and kind not in categories:
            continue
        project = event.get("project")
        if not project or project["key"] in grouped:
            continue
        grouped[project["key"]] = {
            "key": project["key"],
            "name": project["name"],
            "municipality": event.get("municipality"),
            "latest_date": event.get("event_date"),
            "latest_activity": event.get("what_happened"),
        }
    values = list(grouped.values())
    return {
        "projects": values[:limit],
        "has_more": len(values) > limit or feed["has_more"],
    }
