"""Municipality listing and profile endpoints."""

from fastapi import APIRouter, HTTPException

from api.lib.database import get_cursor
from api.lib.response_types import MunicipalitySummary

router = APIRouter(tags=["municipalities"])


def _muni_name_to_pattern(name: str) -> str:
    """Convert municipality short name to a LIKE pattern matching tax districts.

    'CARROLL TWP'  → 'CARROLL TOWNSHIP%'
    'YORK CITY'    → 'YORK CITY%'
    'DELTA BORO'   → 'DELTA BOROUGH%'
    'YORKANA BORO' → 'YORKANA BOROUGH%'
    """
    upper = name.upper()
    if upper.endswith(" TWP"):
        return name[:-4] + " TOWNSHIP%"
    if upper.endswith(" BORO"):
        return name[:-5] + " BOROUGH%"
    return name + "%"


@router.get("", response_model=None)
def list_municipalities() -> list[MunicipalitySummary]:
    """List all municipalities with delinquency stats."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT name, muni_type
            FROM staging.municipalities
            WHERE valid_to IS NULL
            ORDER BY name
        """)
        munis = cur.fetchall()

        cur.execute("""
            SELECT
                tax_district_name,
                COUNT(DISTINCT pidn) AS delinquent_parcels,
                COALESCE(SUM(CASE WHEN total > 0 THEN total ELSE 0 END), 0) AS total_delinquent
            FROM staging.tax_claims
            WHERE valid_to IS NULL
            GROUP BY tax_district_name
        """)
        district_stats = {row["tax_district_name"]: row for row in cur.fetchall()}

    results = []
    for muni in munis:
        pattern = _muni_name_to_pattern(muni["name"])
        base = pattern.rstrip("%").upper()
        delinquent_parcels = 0
        total_delinquent = 0.0
        for dist_name, stats in district_stats.items():
            if dist_name.upper().startswith(base):
                delinquent_parcels += stats["delinquent_parcels"]
                total_delinquent += float(stats["total_delinquent"])

        results.append({
            "name": muni["name"],
            "muni_type": muni["muni_type"],
            "delinquent_parcels": delinquent_parcels,
            "total_delinquent": round(total_delinquent, 2),
        })

    return results


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

        pattern = _muni_name_to_pattern(muni["name"])
        cur.execute("""
            SELECT
                COUNT(DISTINCT pidn) AS delinquent_parcels,
                COALESCE(SUM(CASE WHEN total > 0 THEN total ELSE 0 END), 0) AS total_delinquent,
                MIN(tax_year) AS oldest_delinquent_year,
                COUNT(DISTINCT tax_year) AS delinquent_years
            FROM staging.tax_claims
            WHERE valid_to IS NULL
              AND UPPER(tax_district_name) LIKE UPPER(%s)
        """, (pattern,))
        delinquency = cur.fetchone()

    return {
        **dict(muni),
        "delinquency": {
            "delinquent_parcels": delinquency["delinquent_parcels"],
            "total_delinquent": float(delinquency["total_delinquent"]),
            "oldest_delinquent_year": delinquency["oldest_delinquent_year"],
            "delinquent_years": delinquency["delinquent_years"],
        } if delinquency else {},
    }
