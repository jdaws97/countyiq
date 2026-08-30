"""PLCB liquor license browser."""

from fastapi import APIRouter, Query

from api.lib.database import get_cursor
from api.lib.source_policy import require_source_use

router = APIRouter(tags=["licenses"])


@router.get("")
def list_licenses(
    municipality: str | None = Query(default=None),
    license_type: str | None = Query(default=None),
    status: str = Query(default="Active"),
    limit: int = Query(default=200, ge=1, le=500),
) -> dict:
    """List PLCB liquor licenses with filtering."""
    where = "WHERE valid_to IS NULL"
    params: dict = {"limit": limit}

    if status:
        where += " AND UPPER(status) = UPPER(%(status)s)"
        params["status"] = status
    if municipality:
        where += " AND UPPER(municipality) LIKE UPPER(%(muni)s) || '%%'"
        params["muni"] = municipality
    if license_type:
        where += " AND UPPER(license_type) LIKE '%%' || UPPER(%(ltype)s) || '%%'"
        params["ltype"] = license_type

    with get_cursor() as cur:
        require_source_use(cur, "plcb_licenses", "derived_product", conceal=False)
        cur.execute(f"""
            SELECT NULL::text AS licensee, premises_name, premises_address, license_type,
                   status, municipality, last_issue_date, expiration_date
            FROM staging.plcb_licenses
            {where}
            ORDER BY premises_name NULLS LAST, premises_address
            LIMIT %(limit)s
        """, params)
        licenses = cur.fetchall()

        # Summary stats
        cur.execute("""
            SELECT license_type, COUNT(*) as count
            FROM staging.plcb_licenses
            WHERE valid_to IS NULL AND UPPER(status) = 'ACTIVE'
            GROUP BY license_type
            ORDER BY count DESC
        """)
        type_counts = cur.fetchall()

    # Real total from type_summary (not capped by limit)
    total_active = sum(r["count"] for r in type_counts)

    return {
        "licenses": [dict(r) for r in licenses],
        "type_summary": [dict(r) for r in type_counts],
        "total": total_active,
        "showing": len(licenses),
    }
