"""Municipality listing and profile endpoints."""

from fastapi import APIRouter, HTTPException

from api.lib.database import get_cursor
from api.lib.response_types import MunicipalityProfileResponse, MunicipalitySummary
from api.lib.settings import open_data_source_key
from api.lib.source_policy import require_source_use

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


def _fetch_municipality_stats(cur, municipality_name: str) -> dict:
    cur.execute(
        """
        SELECT
            COUNT(DISTINCT pidn) AS parcel_count,
            COALESCE(SUM(COALESCE(aprtotal, 0)), 0) AS total_assessed
        FROM staging.parcels
        WHERE valid_to IS NULL
          AND UPPER(municipality) LIKE UPPER(%(municipality)s) || '%%'
        """,
        {"municipality": municipality_name},
    )
    row = cur.fetchone() or {}
    return {
        "parcel_count": row.get("parcel_count", 0) or 0,
        "total_assessed": float(row.get("total_assessed", 0) or 0),
    }


def _fetch_municipality_delinquency(cur, district_pattern: str) -> dict:
    cur.execute(
        """
        SELECT
            COUNT(DISTINCT pidn) AS delinquent_parcels,
            COALESCE(SUM(CASE WHEN total > 0 THEN total ELSE 0 END), 0) AS total_delinquent,
            MIN(tax_year) AS oldest_delinquent_year,
            COUNT(DISTINCT tax_year) AS delinquent_years
        FROM staging.tax_claims
        WHERE valid_to IS NULL
          AND UPPER(tax_district_name) LIKE UPPER(%(pattern)s)
        """,
        {"pattern": district_pattern},
    )
    row = cur.fetchone() or {}
    return {
        "delinquent_parcels": row.get("delinquent_parcels", 0) or 0,
        "total_delinquent": float(row.get("total_delinquent", 0) or 0),
        "oldest_delinquent_year": row.get("oldest_delinquent_year"),
        "delinquent_years": row.get("delinquent_years", 0) or 0,
    }


def _fetch_municipality_licenses(cur, municipality_name: str, *, limit: int = 50) -> list[dict]:
    cur.execute(
        """
        SELECT
            NULL::text AS licensee,
            premises_name,
            premises_address,
            license_type,
            status,
            municipality,
            last_issue_date,
            expiration_date
        FROM staging.plcb_licenses
        WHERE valid_to IS NULL
          AND UPPER(status) = 'ACTIVE'
          AND UPPER(municipality) LIKE UPPER(%(municipality)s) || '%%'
        ORDER BY premises_name NULLS LAST, premises_address
        LIMIT %(limit)s
        """,
        {"municipality": municipality_name, "limit": limit},
    )
    return [dict(row) for row in cur.fetchall()]


@router.get("", response_model=None)
def list_municipalities() -> list[MunicipalitySummary]:
    """List all municipalities with delinquency stats."""
    with get_cursor() as cur:
        require_source_use(cur, open_data_source_key(), "derived_product", conceal=False)
        require_source_use(cur, "tax_claims", "derived_product", conceal=False)
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
def get_municipality(name: str) -> MunicipalityProfileResponse:
    """Get a single municipality profile."""
    with get_cursor() as cur:
        require_source_use(cur, open_data_source_key(), "derived_product", conceal=False)
        require_source_use(cur, "tax_claims", "derived_product", conceal=False)
        require_source_use(cur, "plcb_licenses", "derived_product", conceal=False)
        cur.execute(
            """
            SELECT name, muni_type, county
            FROM staging.municipalities
            WHERE valid_to IS NULL AND UPPER(name) = UPPER(%s)
            """,
            (name,),
        )
        muni = cur.fetchone()
        if not muni:
            raise HTTPException(status_code=404, detail=f"Municipality not found: {name}")

        pattern = _muni_name_to_pattern(muni["name"])
        stats = _fetch_municipality_stats(cur, muni["name"])
        delinquency = _fetch_municipality_delinquency(cur, pattern)
        licenses = _fetch_municipality_licenses(cur, muni["name"], limit=50)

    return {
        **dict(muni),
        "stats": stats,
        "delinquency": delinquency,
        "licenses": licenses,
    }
