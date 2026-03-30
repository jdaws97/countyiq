"""Unified search across addresses, tax claim owners, and PLCB licensees."""

from fastapi import APIRouter, Query

from api.lib.database import get_cursor

router = APIRouter(tags=["search"])


@router.get("")
def search(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(default=20, le=100),
) -> list[dict]:
    """Search across address points, tax claim owners, and PLCB licensees."""
    search_term = q.strip()

    with get_cursor() as cur:
        # Address points
        cur.execute("""
            SELECT
                'address' AS result_type,
                CONCAT_WS(' ', add_number, street_name, st_pos_typ) AS title,
                inc_muni AS subtitle,
                lat, long AS lng,
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
        addresses = cur.fetchall()

        # Tax claim owners
        cur.execute("""
            SELECT
                'tax_claim' AS result_type,
                owner_name AS title,
                tax_district_name || ' · ' || COUNT(DISTINCT pidn) || ' parcels · $' ||
                    TRIM(TO_CHAR(SUM(CASE WHEN total > 0 THEN total ELSE 0 END), 'FM999,999,999')) AS subtitle,
                NULL::float AS lat, NULL::float AS lng,
                similarity(owner_name, %(q)s) AS score
            FROM staging.tax_claims
            WHERE valid_to IS NULL
              AND owner_name %% %(q)s
            GROUP BY owner_name, tax_district_name
            ORDER BY score DESC
            LIMIT %(limit)s
        """, {"q": search_term, "limit": limit})
        tax_owners = cur.fetchall()

        # PLCB licensees
        cur.execute("""
            SELECT
                'license' AS result_type,
                COALESCE(premises_name, licensee) AS title,
                license_type || ' · ' || municipality AS subtitle,
                NULL::float AS lat, NULL::float AS lng,
                similarity(COALESCE(premises_name, licensee), %(q)s) AS score
            FROM staging.plcb_licenses
            WHERE valid_to IS NULL
              AND (premises_name %% %(q)s OR licensee %% %(q)s)
            ORDER BY score DESC
            LIMIT %(limit)s
        """, {"q": search_term, "limit": limit})
        licenses = cur.fetchall()

    # Merge and sort by score
    all_results = [dict(r) for r in addresses + tax_owners + licenses]
    all_results.sort(key=lambda r: r["score"], reverse=True)
    return all_results[:limit]
