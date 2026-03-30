"""Distressed Acquisition Score + Assemblage Finder — ranked parcel intelligence."""

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
    - Tax delinquency: 0.25 (years × normalized amount)
    - Sheriff sale/foreclosure: 0.15 (active = 1.0, postponed = 0.7)
    - Tax sale stage: 0.10 (2+ years = upset eligible, 5+ = judicial)
    - Vacancy: 0.15 (no building footprint + value signals)
    - Traffic proximity: 0.10 (near high-AADT roads)
    - Not in flood zone: 0.05 (more developable)
    - Acreage: 0.10 (larger = more opportunity)
    - Class: 0.05 (commercial/industrial weighted)
    - Hold time: 0.05 (stale ownership)
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
                       ) AND (p.class NOT IN ('R') OR p.aprtotal IS NULL OR p.aprtotal::numeric < 50000)
                       AND (p.price IS NULL OR p.price::numeric < 100000)
                       THEN 1.0 ELSE 0.0 END AS vacant_score
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
            sheriff AS (
                SELECT DISTINCT ON (ss.property_address)
                       ss.property_address,
                       CASE
                           WHEN ss.status IN ('Active', 'Active (P)') THEN 1.0
                           WHEN ss.status = 'Postponed' THEN 0.7
                           ELSE 0.0
                       END AS sheriff_score,
                       ss.judgment_amount
                FROM staging.sheriff_sales ss
                WHERE ss.valid_to IS NULL
                ORDER BY ss.property_address, ss.status DESC
            ),
            traffic AS (
                SELECT p.pidn,
                       LEAST(MAX(COALESCE(tc.aadt, 0))::numeric / 30000, 1.0) AS traffic_score
                FROM staging.parcels p
                LEFT JOIN staging.traffic_counts tc
                    ON tc.valid_to IS NULL AND tc.geom IS NOT NULL
                    AND ST_DWithin(p.geom, tc.geom, 0.005)
                WHERE p.valid_to IS NULL AND p.geom IS NOT NULL
                GROUP BY p.pidn
            ),
            scored AS (
                SELECT
                    p.pidn, p.owner_full, p.propadr, p.class, p.acres,
                    p.aprtotal, p.saledt, p.price, p.school_dis,
                    d.years_delinquent, d.total_owed,
                    v.vacant_score,
                    fl.no_flood_score,
                    COALESCE(sh.sheriff_score, 0) AS sheriff_score,
                    sh.judgment_amount AS sheriff_judgment,
                    COALESCE(tr.traffic_score, 0) AS traffic_score,

                    -- Delinquency score (0-1)
                    LEAST(COALESCE(d.years_delinquent, 0)::numeric / 10, 1.0) * 0.5 +
                    LEAST(COALESCE(d.total_owed, 0)::numeric / 100000, 1.0) * 0.5
                    AS delinquency_score,

                    -- Tax sale stage (inferred from years delinquent)
                    CASE
                        WHEN COALESCE(d.years_delinquent, 0) >= 5 THEN 1.0
                        WHEN COALESCE(d.years_delinquent, 0) >= 3 THEN 0.7
                        WHEN COALESCE(d.years_delinquent, 0) >= 2 THEN 0.5
                        ELSE 0.2
                    END AS sale_stage_score,

                    -- Acreage score (0-1)
                    LEAST(COALESCE(p.acres::numeric, 0) / 50, 1.0) AS acreage_score,

                    -- Class score
                    CASE p.class
                        WHEN 'C' THEN 1.0 WHEN 'I' THEN 1.0
                        WHEN 'F' THEN 0.7 WHEN 'A' THEN 0.7
                        WHEN 'E' THEN 0.5 ELSE 0.3
                    END AS class_score,

                    -- Hold time score (0-1)
                    CASE WHEN p.saledt IS NOT NULL THEN
                        LEAST((EXTRACT(EPOCH FROM NOW()) - EXTRACT(EPOCH FROM TO_DATE(p.saledt, 'DD-MON-YYYY')))
                              / (86400 * 365 * 20), 1.0)
                    ELSE 0.8 END AS hold_score

                FROM staging.parcels p
                LEFT JOIN delinquency d ON p.pidn = d.pidn
                LEFT JOIN vacancy v ON p.pidn = v.pidn
                LEFT JOIN flood fl ON p.pidn = fl.pidn
                LEFT JOIN sheriff sh ON UPPER(p.propadr) = UPPER(sh.property_address)
                LEFT JOIN traffic tr ON p.pidn = tr.pidn
                WHERE p.valid_to IS NULL
                  AND d.total_owed > 0
                  {extra_where}
            )
            SELECT *,
                ROUND((
                    delinquency_score * 0.25 +
                    COALESCE(sheriff_score, 0) * 0.15 +
                    sale_stage_score * 0.10 +
                    COALESCE(vacant_score, 0) * 0.15 +
                    COALESCE(traffic_score, 0) * 0.10 +
                    COALESCE(no_flood_score, 0) * 0.05 +
                    acreage_score * 0.10 +
                    class_score * 0.05 +
                    hold_score * 0.05
                )::numeric, 3) AS distress_score
            FROM scored
            WHERE (
                delinquency_score * 0.25 +
                COALESCE(sheriff_score, 0) * 0.15 +
                sale_stage_score * 0.10 +
                COALESCE(vacant_score, 0) * 0.15 +
                COALESCE(traffic_score, 0) * 0.10 +
                COALESCE(no_flood_score, 0) * 0.05 +
                acreage_score * 0.10 +
                class_score * 0.05 +
                hold_score * 0.05
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
                  "vacant_score", "no_flood_score", "sheriff_score", "sheriff_judgment",
                  "traffic_score", "sale_stage_score"):
            if d.get(k) is not None:
                d[k] = float(d[k])
        results.append(d)

    return {"count": len(results), "parcels": results}


@router.get("/assemblage")
def assemblage_opportunities(
    min_parcels: int = Query(default=3, ge=2, le=20),
    min_acres: float = Query(default=1.0),
    limit: int = Query(default=50, le=200),
) -> dict:
    """Find clusters of adjacent parcels that could be assembled.

    Identifies groups of touching parcels where multiple are distressed,
    vacant, or share fragmented ownership. Ranked by total cluster value.
    """
    with get_cursor() as cur:
        cur.execute("""
            WITH delinquent_parcels AS (
                SELECT DISTINCT pidn
                FROM staging.tax_claims
                WHERE valid_to IS NULL AND total > 0
            ),
            -- Find all pairs of adjacent parcels (ST_Touches)
            adjacent_pairs AS (
                SELECT
                    a.pidn AS pidn_a,
                    b.pidn AS pidn_b
                FROM staging.parcels a
                JOIN staging.parcels b ON ST_Touches(a.geom, b.geom)
                WHERE a.valid_to IS NULL AND b.valid_to IS NULL
                  AND a.pidn < b.pidn
                  AND a.geom IS NOT NULL AND b.geom IS NOT NULL
            ),
            -- Build clusters via connected components (simplified: use seed parcel)
            -- For each delinquent parcel, find all adjacent parcels
            cluster_seeds AS (
                SELECT
                    dp.pidn AS seed_pidn,
                    p.owner_full AS seed_owner,
                    p.propadr AS seed_address,
                    p.class AS seed_class,
                    p.acres AS seed_acres,
                    p.aprtotal AS seed_assessed,
                    p.school_dis
                FROM delinquent_parcels dp
                JOIN staging.parcels p ON p.pidn = dp.pidn AND p.valid_to IS NULL
                WHERE p.geom IS NOT NULL
            ),
            cluster_members AS (
                SELECT
                    cs.seed_pidn,
                    cs.seed_owner,
                    cs.seed_address,
                    cs.seed_class,
                    cs.seed_acres,
                    cs.seed_assessed,
                    cs.school_dis,
                    n.pidn AS neighbor_pidn,
                    n.owner_full AS neighbor_owner,
                    n.propadr AS neighbor_address,
                    n.acres AS neighbor_acres,
                    n.aprtotal AS neighbor_assessed,
                    n.class AS neighbor_class,
                    CASE WHEN dp2.pidn IS NOT NULL THEN true ELSE false END AS neighbor_delinquent,
                    CASE WHEN NOT EXISTS (
                        SELECT 1 FROM staging.structures s
                        WHERE s.valid_to IS NULL AND s.geom IS NOT NULL
                          AND ST_Intersects(s.geom, n.geom)
                    ) THEN true ELSE false END AS neighbor_vacant,
                    cs.seed_owner != n.owner_full AS different_owner
                FROM cluster_seeds cs
                JOIN staging.parcels seed_p ON seed_p.pidn = cs.seed_pidn AND seed_p.valid_to IS NULL
                JOIN staging.parcels n ON ST_Touches(seed_p.geom, n.geom) AND n.valid_to IS NULL AND n.geom IS NOT NULL
                LEFT JOIN delinquent_parcels dp2 ON n.pidn = dp2.pidn
            )
            SELECT
                seed_pidn,
                seed_owner,
                seed_address,
                seed_class,
                school_dis,
                COALESCE(seed_acres::numeric, 0) AS seed_acres,
                COALESCE(seed_assessed::numeric, 0) AS seed_assessed,
                -- Centroid for map linking (from seed parcel geometry)
                (SELECT ST_Y(ST_Centroid(p2.geom)) FROM staging.parcels p2 WHERE p2.pidn = seed_pidn AND p2.valid_to IS NULL) AS lat,
                (SELECT ST_X(ST_Centroid(p2.geom)) FROM staging.parcels p2 WHERE p2.pidn = seed_pidn AND p2.valid_to IS NULL) AS lng,
                COUNT(*) AS adjacent_count,
                SUM(CASE WHEN neighbor_delinquent THEN 1 ELSE 0 END) AS delinquent_neighbors,
                SUM(CASE WHEN neighbor_vacant THEN 1 ELSE 0 END) AS vacant_neighbors,
                SUM(CASE WHEN different_owner THEN 1 ELSE 0 END) AS different_owners,
                COALESCE(SUM(neighbor_acres::numeric), 0) AS total_neighbor_acres,
                COALESCE(SUM(neighbor_assessed::numeric), 0) AS total_neighbor_assessed,
                COALESCE(seed_acres::numeric, 0) + COALESCE(SUM(neighbor_acres::numeric), 0) AS total_acres,
                COALESCE(seed_assessed::numeric, 0) + COALESCE(SUM(neighbor_assessed::numeric), 0) AS total_assessed,
                -- Count unique owners (lower = easier assemblage)
                COUNT(DISTINCT neighbor_owner) + 1 AS unique_owners,
                json_agg(json_build_object(
                    'pidn', neighbor_pidn,
                    'owner', neighbor_owner,
                    'address', neighbor_address,
                    'acres', neighbor_acres,
                    'assessed', neighbor_assessed,
                    'class', neighbor_class,
                    'delinquent', neighbor_delinquent,
                    'vacant', neighbor_vacant
                )) AS neighbors
            FROM cluster_members
            GROUP BY seed_pidn, seed_owner, seed_address, seed_class, seed_acres, seed_assessed, school_dis
            HAVING COUNT(*) >= %(min_parcels)s
               AND COALESCE(seed_acres::numeric, 0) + COALESCE(SUM(neighbor_acres::numeric), 0) >= %(min_acres)s
            ORDER BY
                SUM(CASE WHEN neighbor_delinquent THEN 1 ELSE 0 END) DESC,
                COUNT(*) DESC,
                total_acres DESC
            LIMIT %(limit)s
        """, {"min_parcels": min_parcels, "min_acres": min_acres, "limit": limit})
        rows = cur.fetchall()

    results = []
    for r in rows:
        d = dict(r)
        for k in ("seed_acres", "seed_assessed", "total_neighbor_acres",
                  "total_neighbor_assessed", "total_acres", "total_assessed",
                  "lat", "lng"):
            if d.get(k) is not None:
                d[k] = float(d[k])
        results.append(d)

    return {"count": len(results), "clusters": results}
