"""Municipality listing and profile endpoints."""

from fastapi import APIRouter, HTTPException

from api.lib.database import get_cursor

router = APIRouter(tags=["municipalities"])


@router.get("")
def list_municipalities() -> list[dict]:
    """List all municipalities with delinquency stats."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT
                m.name,
                m.muni_type,
                COUNT(DISTINCT tc.pidn) AS delinquent_parcels,
                COALESCE(SUM(CASE WHEN tc.total > 0 THEN tc.total ELSE 0 END), 0) AS total_delinquent
            FROM staging.municipalities m
            LEFT JOIN staging.tax_claims tc
                ON UPPER(tc.tax_district_name) LIKE UPPER(m.name) || '%'
                AND tc.valid_to IS NULL
            WHERE m.valid_to IS NULL
            GROUP BY m.name, m.muni_type
            ORDER BY m.name
        """)
        return cur.fetchall()


@router.get("/{name}")
def get_municipality(name: str) -> dict:
    """Get a single municipality profile."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT name, muni_type, county
            FROM staging.municipalities
            WHERE valid_to IS NULL AND UPPER(name) = UPPER(%s)
        """, (name,))
        muni = cur.fetchone()
        if not muni:
            raise HTTPException(status_code=404, detail=f"Municipality not found: {name}")

        cur.execute("""
            SELECT
                COUNT(DISTINCT pidn) AS delinquent_parcels,
                COALESCE(SUM(CASE WHEN total > 0 THEN total ELSE 0 END), 0) AS total_delinquent,
                MIN(tax_year) AS oldest_delinquent_year,
                COUNT(DISTINCT tax_year) AS delinquent_years
            FROM staging.tax_claims
            WHERE valid_to IS NULL
              AND UPPER(tax_district_name) LIKE UPPER(%s) || '%%'
        """, (muni["name"],))
        delinquency = cur.fetchone()

    return {
        **dict(muni),
        "delinquency": dict(delinquency) if delinquency else {},
    }
