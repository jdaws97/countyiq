"""County feed — Pass 4 narratives exposed as a paginated, filterable feed."""

from fastapi import APIRouter, Query

from api.lib.database import get_cursor

router = APIRouter(tags=["feed"])


_ALLOWED_TYPES = {"corridor", "distress", "municipal", "portfolio"}

# Trajectory vocabulary mirrors VALID_TRAJECTORIES in pass4_county_narratives.py.
# Keep in sync if new values are added there.
_ALLOWED_TRAJECTORIES = {
    "accelerating", "steady", "stalling",
    "growing", "stable", "declining", "transitioning",
    "expanding", "holding", "unwinding",
    "distressed", "concentrating", "spreading", "resolving",
}


@router.get("")
def county_feed(
    narrative_type: str | None = Query(default=None),
    trajectory: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """Return Pass 4 county narratives sorted newest first."""
    filters = ["(expires_at IS NULL OR expires_at > NOW())"]
    params: dict[str, object] = {"limit": limit, "offset": offset}

    if narrative_type and narrative_type in _ALLOWED_TYPES:
        filters.append("narrative_type = %(narrative_type)s")
        params["narrative_type"] = narrative_type
    if trajectory and trajectory in _ALLOWED_TRAJECTORIES:
        filters.append("trajectory = %(trajectory)s")
        params["trajectory"] = trajectory

    where_clause = " AND ".join(filters)

    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT
                narrative_id,
                title,
                body,
                narrative_type,
                trajectory,
                COALESCE(affected_pidns, ARRAY[]::text[]) AS affected_pidns,
                COALESCE(key_entities, ARRAY[]::text[]) AS key_entities,
                COALESCE(citations, '[]'::jsonb) AS citations,
                generated_at
            FROM public.county_narratives
            WHERE {where_clause}
            ORDER BY generated_at DESC NULLS LAST, narrative_id DESC
            LIMIT %(limit)s OFFSET %(offset)s
            """,
            params,
        )
        rows = cur.fetchall()

    return {
        "narratives": [dict(r) for r in rows],
        "limit": limit,
        "offset": offset,
    }
