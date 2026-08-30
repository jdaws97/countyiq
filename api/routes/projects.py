"""PennDOT project list endpoint."""

from fastapi import APIRouter, Query

from api.lib.database import get_cursor
from api.lib.source_policy import require_source_use

router = APIRouter(tags=["projects"])


@router.get("")
def list_projects(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
) -> list[dict]:
    """List PennDOT projects with full details."""
    where = "WHERE valid_to IS NULL"
    params: dict = {"limit": limit}
    if status:
        where += " AND UPPER(status) = UPPER(%(status)s)"
        params["status"] = status

    with get_cursor() as cur:
        require_source_use(cur, "penndot_open_data", "derived_product", conceal=False)
        cur.execute(f"""
            SELECT
                project_id, project_name, description, status,
                start_date, end_date, cost, project_type,
                data->>'PRJCT_GRPHY_DC' AS location_desc,
                data->>'ACT_89_BREAKDOWN' AS act89_status,
                data->>'UNDER_CONSTRUCTION' AS under_construction
            FROM staging.penndot_projects
            {where}
            ORDER BY
                CASE WHEN status = 'Active' THEN 0
                     WHEN status = 'Programmed' THEN 1
                     WHEN status = 'Candidate' THEN 2
                     ELSE 3 END,
                cost DESC NULLS LAST
            LIMIT %(limit)s
        """, params)
        rows = cur.fetchall()

    return [
        {**dict(r), "cost": float(r["cost"]) if r["cost"] else None}
        for r in rows
    ]
