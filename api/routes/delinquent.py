"""Top delinquent owners and delinquent parcel browser."""

from fastapi import APIRouter, Query

from api.lib.database import get_cursor
from api.lib.source_policy import require_source_use

router = APIRouter(tags=["delinquent"])


@router.get("/top-owners")
def top_delinquent_owners(
    municipality: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict]:
    """Top delinquent property owners by total owed."""
    where = "WHERE tc.valid_to IS NULL AND tc.total > 0"
    params: dict = {"limit": limit}
    if municipality:
        where += " AND UPPER(tc.tax_district_name) LIKE UPPER(%(muni)s) || '%%'"
        params["muni"] = municipality

    with get_cursor() as cur:
        require_source_use(cur, "tax_claims", "derived_product")
        cur.execute(f"""
            SELECT
                tc.owner_name,
                COUNT(DISTINCT tc.pidn) AS parcel_count,
                SUM(tc.total) AS total_owed,
                MIN(tc.tax_year) AS oldest_year,
                MAX(tc.tax_year) AS newest_year,
                COUNT(DISTINCT tc.tax_year) AS years_delinquent,
                array_agg(DISTINCT tc.tax_district_name) AS districts
            FROM staging.tax_claims tc
            {where}
            GROUP BY tc.owner_name
            ORDER BY SUM(tc.total) DESC
            LIMIT %(limit)s
        """, params)
        rows = cur.fetchall()

    return [
        {
            **dict(r),
            "total_owed": float(r["total_owed"]),
            "districts": list(r["districts"]),
        }
        for r in rows
    ]


@router.get("/parcels")
def delinquent_parcels(
    municipality: str | None = Query(default=None),
    min_owed: float | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict]:
    """Browse individual delinquent parcels."""
    where = "WHERE tc.valid_to IS NULL AND tc.total > 0"
    params: dict = {"limit": limit}
    if municipality:
        where += " AND UPPER(tc.tax_district_name) LIKE UPPER(%(muni)s) || '%%'"
        params["muni"] = municipality
    if min_owed:
        params["min_owed"] = min_owed

    with get_cursor() as cur:
        require_source_use(cur, "tax_claims", "derived_product")
        cur.execute(f"""
            SELECT
                tc.pidn,
                tc.owner_name,
                tc.property_address,
                tc.tax_district_name,
                SUM(tc.total) AS total_owed,
                MIN(tc.tax_year) AS oldest_year,
                COUNT(DISTINCT tc.tax_year) AS years_delinquent
            FROM staging.tax_claims tc
            {where}
            GROUP BY tc.pidn, tc.owner_name, tc.property_address, tc.tax_district_name
            {"HAVING SUM(tc.total) >= %(min_owed)s" if min_owed else ""}
            ORDER BY SUM(tc.total) DESC
            LIMIT %(limit)s
        """, params)
        rows = cur.fetchall()

    return [
        {**dict(r), "total_owed": float(r["total_owed"])}
        for r in rows
    ]
