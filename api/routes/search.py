"""Fuzzy search across addresses using pg_trgm."""

from fastapi import APIRouter, Query

from api.lib.database import get_cursor

router = APIRouter(tags=["search"])


@router.get("")
def search(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(default=20, le=100),
) -> list[dict]:
    """Fuzzy search on address points using pg_trgm similarity."""
    search_term = q.strip()

    with get_cursor() as cur:
        cur.execute("""
            SELECT
                add_number,
                street_name,
                st_pos_typ,
                inc_muni,
                CONCAT_WS(' ', add_number, street_name, st_pos_typ) AS full_address,
                similarity(
                    CONCAT_WS(' ', add_number, street_name, st_pos_typ),
                    %(q)s
                ) AS score
            FROM staging.address_points
            WHERE valid_to IS NULL
              AND CONCAT_WS(' ', add_number, street_name, st_pos_typ) %% %(q)s
            ORDER BY score DESC
            LIMIT %(limit)s
        """, {"q": search_term, "limit": limit})
        return cur.fetchall()
