"""Distressed Acquisition Score — ranked parcel intelligence for investors."""

from fastapi import APIRouter, Query

from api.lib.database import get_cursor

router = APIRouter(tags=["scores"])


@router.get("/distressed")
def distressed_parcels(
    min_score: float = Query(default=0.2, ge=0, le=1),
    municipality: str | None = Query(default=None),
    min_acres: float | None = Query(default=None),
    parcel_class: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
) -> dict:
    """Rank parcels by distressed acquisition opportunity score.

    Score components (0-1 each, weighted):
    - Tax delinquency: 0.30 weight (years × normalized amount)
    - Vacancy: 0.20 weight (no building footprint + low value signals)
    - Not in flood zone: 0.10 weight (more developable)
    - Acreage: 0.15 weight (larger = more opportunity)
    - Commercial/Industrial class: 0.10 weight
    - Long hold time: 0.15 weight (stale ownership = motivated seller)
    """
    params: dict = {"min_score": min_score, "limit": limit}

    extra_where = ""
    if municipality:
        extra_where += " AND UPPER(tc.tax_district_name) LIKE UPPER(%(municipality)s) || '%%'"
        params["municipality"] = municipality
    if min_acres:
        extra_where += " AND p.acres::numeric >= %(min_acres)s"
        params["min_acres"] = min_acres
    if parcel_class:
        extra_where += " AND p.class = %(parcel_class)s"
        params["parcel_class"] = parcel_class

    with get_cursor() as cur:
        cur.execute(f"""
            WITH delinquency AS (
                SELECT pidn,
                       COUNT(DISTINCT tax_year) AS years_delinquent,
                       SUM(CASE WHEN total > 0 THEN total ELSE 0 END) AS total_owed
                FROM staging.tax_claims
                WHERE valid_to IS NULL
                GROUP BY pidn
            ),
            vacancy AS (
                SELECT p.pidn,
                       CASE WHEN NOT EXISTS (
                           SELECT 1 FROM staging.structures s
                           WHERE s.valid_to IS NULL AND s.geom IS NOT NULL
                             AND ST_Intersects(s.geom, p.geom)
                       ) THEN 1.0 ELSE 0.0 END AS vacant_score
                FROM staging.parcels p
                WHERE p.valid_to IS NULL AND p.geom IS NOT NULL
            ),
            flood AS (
                SELECT p.pidn,
                       CASE WHEN NOT EXISTS (
                           SELECT 1 FROM staging.flood_zones f
                           WHERE f.valid_to IS NULL AND f.sfha_tf = 'T'
                             AND ST_Intersects(f.geom, p.geom)
                       ) THEN 1.0 ELSE 0.0 END AS no_flood_score
                FROM staging.parcels p
                WHERE p.valid_to IS NULL AND p.geom IS NOT NULL
            ),
            scored AS (
                SELECT
                    p.pidn, p.owner_full, p.propadr, p.class, p.acres,
                    p.aprtotal, p.saledt, p.price, p.school_dis,
                    d.years_delinquent, d.total_owed,
                    v.vacant_score,
                    fl.no_flood_score,

                    -- Delinquency score (0-1): years normalized to max 10, amount normalized to max $100K
                    LEAST(COALESCE(d.years_delinquent, 0)::numeric / 10, 1.0) * 0.5 +
                    LEAST(COALESCE(d.total_owed, 0)::numeric / 100000, 1.0) * 0.5
                    AS delinquency_score,

                    -- Acreage score (0-1): normalized to 50 acres
                    LEAST(COALESCE(p.acres::numeric, 0) / 50, 1.0)
                    AS acreage_score,

                    -- Class score: commercial/industrial = 1, farm = 0.7, else 0.3
                    CASE p.class
                        WHEN 'C' THEN 1.0 WHEN 'I' THEN 1.0
                        WHEN 'F' THEN 0.7 WHEN 'A' THEN 0.7
                        WHEN 'E' THEN 0.5
                        ELSE 0.3
                    END AS class_score,

                    -- Hold time score (0-1): years since last sale, max 20
                    CASE WHEN p.saledt IS NOT NULL THEN
                        LEAST((EXTRACT(EPOCH FROM NOW()) - EXTRACT(EPOCH FROM TO_DATE(p.saledt, 'DD-MON-YYYY')))
                              / (86400 * 365 * 20), 1.0)
                    ELSE 0.8 END AS hold_score

                FROM staging.parcels p
                LEFT JOIN delinquency d ON p.pidn = d.pidn
                LEFT JOIN vacancy v ON p.pidn = v.pidn
                LEFT JOIN flood fl ON p.pidn = fl.pidn
                WHERE p.valid_to IS NULL
                  AND d.total_owed > 0
                  {extra_where}
            )
            SELECT *,
                -- Weighted composite score
                ROUND((
                    delinquency_score * 0.30 +
                    COALESCE(vacant_score, 0) * 0.20 +
                    COALESCE(no_flood_score, 0) * 0.10 +
                    acreage_score * 0.15 +
                    class_score * 0.10 +
                    hold_score * 0.15
                )::numeric, 3) AS distress_score
            FROM scored
            WHERE (
                delinquency_score * 0.30 +
                COALESCE(vacant_score, 0) * 0.20 +
                COALESCE(no_flood_score, 0) * 0.10 +
                acreage_score * 0.15 +
                class_score * 0.10 +
                hold_score * 0.15
            ) >= %(min_score)s
            ORDER BY distress_score DESC
            LIMIT %(limit)s
        """, params)
        rows = cur.fetchall()

    results = []
    for r in rows:
        d = dict(r)
        for k in ("total_owed", "acres", "aprtotal", "price", "distress_score",
                  "delinquency_score", "acreage_score", "class_score", "hold_score",
                  "vacant_score", "no_flood_score"):
            if d.get(k) is not None:
                d[k] = float(d[k])
        results.append(d)

    return {
        "count": len(results),
        "parcels": results,
    }
