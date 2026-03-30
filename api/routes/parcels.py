"""Parcel endpoints — bbox query, property report card, delinquency overlay."""

from fastapi import APIRouter, HTTPException, Query

from api.lib.database import get_cursor

router = APIRouter(tags=["parcels"])


@router.get("/bbox")
def parcels_bbox(
    west: float = Query(...),
    south: float = Query(...),
    east: float = Query(...),
    north: float = Query(...),
    layer: str | None = Query(default=None),
) -> dict:
    """Return parcels within a bounding box as GeoJSON.

    Optional layer=delinquent adds tax delinquency status.
    """
    with get_cursor() as cur:
        if layer == "delinquent":
            cur.execute("""
                SELECT
                    ST_AsGeoJSON(p.geom)::json AS geometry,
                    p.pidn, p.owner_full, p.propadr, p.aprtotal, p.municipality,
                    p.class, p.saledt, p.price,
                    COALESCE(tc.total_owed, 0) AS delinquent_total,
                    tc.years_delinquent
                FROM staging.parcels p
                LEFT JOIN (
                    SELECT pidn,
                           SUM(CASE WHEN total > 0 THEN total ELSE 0 END) AS total_owed,
                           COUNT(DISTINCT tax_year) AS years_delinquent
                    FROM staging.tax_claims
                    WHERE valid_to IS NULL
                    GROUP BY pidn
                ) tc ON p.pidn = tc.pidn
                WHERE p.valid_to IS NULL
                  AND p.geom IS NOT NULL
                  AND p.geom && ST_MakeEnvelope(%(west)s, %(south)s, %(east)s, %(north)s, 4326)
            """, {"west": west, "south": south, "east": east, "north": north})
        elif layer == "vacant":
            cur.execute("""
                SELECT
                    ST_AsGeoJSON(p.geom)::json AS geometry,
                    p.pidn, p.owner_full, p.propadr, p.aprtotal, p.municipality,
                    p.class, p.saledt, p.price,
                    COALESCE(tc.total_owed, 0) AS delinquent_total
                FROM staging.parcels p
                LEFT JOIN (
                    SELECT pidn, SUM(CASE WHEN total > 0 THEN total ELSE 0 END) AS total_owed
                    FROM staging.tax_claims WHERE valid_to IS NULL GROUP BY pidn
                ) tc ON p.pidn = tc.pidn
                WHERE p.valid_to IS NULL
                  AND p.geom IS NOT NULL
                  AND p.geom && ST_MakeEnvelope(%(west)s, %(south)s, %(east)s, %(north)s, 4326)
                  AND NOT EXISTS (
                      SELECT 1 FROM staging.structures s
                      WHERE s.valid_to IS NULL AND s.geom IS NOT NULL
                        AND ST_Intersects(s.geom, p.geom)
                  )
            """, {"west": west, "south": south, "east": east, "north": north})
        else:
            cur.execute("""
                SELECT
                    ST_AsGeoJSON(p.geom)::json AS geometry,
                    p.pidn, p.owner_full, p.propadr, p.aprtotal, p.municipality,
                    p.class, p.saledt, p.price
                FROM staging.parcels p
                WHERE p.valid_to IS NULL
                  AND p.geom IS NOT NULL
                  AND p.geom && ST_MakeEnvelope(%(west)s, %(south)s, %(east)s, %(north)s, 4326)
            """, {"west": west, "south": south, "east": east, "north": north})
        rows = cur.fetchall()

    features = []
    for row in rows:
        geom = row.pop("geometry")
        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {k: (float(v) if k in ("aprtotal", "price", "delinquent_total") and v is not None else v)
                           for k, v in dict(row).items()},
        })

    return {"type": "FeatureCollection", "features": features}


@router.get("/{pidn}")
def parcel_detail(pidn: str) -> dict:
    """Full property report card for a single parcel."""
    with get_cursor() as cur:
        # Core parcel data
        cur.execute("""
            SELECT pidn, owner_full, own_name1, own_name2, prev_owner,
                   propadr, mail_addr_full, municipality, school_dis,
                   class, luc, acres, style, num_stories, res_living_area,
                   yrblt, heatsys, fuel, clean_green, grade, cdu,
                   aprland, aprbldg, aprtotal, saledt, price, prev_price,
                   deed_bk, deed_pg, comm_struc, comm_year_built, comm_building_sq_ft
            FROM staging.parcels
            WHERE pidn = %(pidn)s AND valid_to IS NULL
        """, {"pidn": pidn})
        parcel = cur.fetchone()
        if not parcel:
            raise HTTPException(status_code=404, detail=f"Parcel not found: {pidn}")

        # Tax delinquency
        cur.execute("""
            SELECT tax_year, authority_name, tax_owed, penalty_owed,
                   interest_owed, fees_owed, total, owner_name, property_address
            FROM staging.tax_claims
            WHERE pidn = %(pidn)s AND valid_to IS NULL AND total > 0
            ORDER BY tax_year DESC, authority_name
        """, {"pidn": pidn})
        tax_claims = cur.fetchall()

        # Flood zone check
        cur.execute("""
            SELECT fld_zone, zone_subty, sfha_tf
            FROM staging.flood_zones
            WHERE valid_to IS NULL
              AND geom IS NOT NULL
              AND ST_Intersects(geom, (
                  SELECT geom FROM staging.parcels WHERE pidn = %(pidn)s AND valid_to IS NULL
              ))
            LIMIT 1
        """, {"pidn": pidn})
        flood = cur.fetchone()

        # Building footprints with detail
        cur.execute("""
            SELECT s.building_type,
                   ROUND(ST_Area(ST_Transform(s.geom, 32617))::numeric) AS sqm
            FROM staging.structures s
            WHERE s.valid_to IS NULL
              AND s.geom IS NOT NULL
              AND ST_Intersects(s.geom, (
                  SELECT geom FROM staging.parcels WHERE pidn = %(pidn)s AND valid_to IS NULL
              ))
            ORDER BY ST_Area(s.geom) DESC
        """, {"pidn": pidn})
        structure_rows = cur.fetchall()

        # Backward compat
        cur.execute("""
            SELECT COUNT(*) AS structure_count
            FROM staging.structures
            WHERE valid_to IS NULL
              AND geom IS NOT NULL
              AND ST_Intersects(geom, (
                  SELECT geom FROM staging.parcels WHERE pidn = %(pidn)s AND valid_to IS NULL
              ))
        """, {"pidn": pidn})
        structures = cur.fetchone()

    # Build response
    p = dict(parcel)
    for key in ("aprland", "aprbldg", "aprtotal", "price", "prev_price", "acres"):
        if p.get(key):
            p[key] = float(p[key])

    delinquent_total = sum(float(r["total"]) for r in tax_claims)

    return {
        "parcel": p,
        "tax_delinquency": {
            "is_delinquent": len(tax_claims) > 0,
            "total_owed": delinquent_total,
            "records": [dict(r) for r in tax_claims],
        },
        "flood_zone": {
            "in_flood_zone": flood is not None,
            "zone": flood["fld_zone"] if flood else None,
            "sfha": flood["sfha_tf"] == "T" if flood else False,
        },
        "structures": {
            "count": structures["structure_count"] if structures else 0,
            "likely_vacant": structures["structure_count"] == 0 if structures else True,
            "buildings": [
                {
                    "type": r["building_type"] or "Unknown",
                    "sqm": int(r["sqm"]) if r["sqm"] else 0,
                    "sqft": int(float(r["sqm"]) * 10.764) if r["sqm"] else 0,
                }
                for r in structure_rows
            ],
        },
    }
