"""Homepage stats endpoint."""

from fastapi import APIRouter

from api.lib.database import get_cursor

router = APIRouter(tags=["stats"])


@router.get("")
def get_stats() -> dict:
    """Aggregate stats for homepage cards."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT
                (SELECT COUNT(*) FROM staging.municipalities WHERE valid_to IS NULL) AS municipality_count,
                (SELECT COUNT(DISTINCT pidn) FROM staging.tax_claims WHERE valid_to IS NULL) AS delinquent_parcels,
                (SELECT COALESCE(SUM(total), 0) FROM staging.tax_claims WHERE valid_to IS NULL AND total > 0) AS total_delinquent,
                (SELECT COUNT(*) FROM staging.flood_zones WHERE valid_to IS NULL) AS flood_zone_count,
                (SELECT COUNT(*) FROM staging.plcb_licenses WHERE valid_to IS NULL AND UPPER(status) = 'ACTIVE') AS liquor_license_count,
                (SELECT COUNT(*) FROM staging.address_points WHERE valid_to IS NULL) AS address_point_count,
                (SELECT COUNT(*) FROM staging.structures WHERE valid_to IS NULL) AS structure_count,
                (SELECT COUNT(*) FROM staging.parcels WHERE valid_to IS NULL) AS parcel_count,
                (SELECT COALESCE(SUM(aprtotal::numeric), 0) FROM staging.parcels WHERE valid_to IS NULL AND aprtotal IS NOT NULL) AS total_assessed
        """)
        row = cur.fetchone()

        # Tax delinquency breakdown by authority
        cur.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN authority_name = 'COUNTY' AND total > 0 THEN total ELSE 0 END), 0) AS county_tax_owed,
                COALESCE(SUM(CASE WHEN authority_name = 'SCHOOL' AND total > 0 THEN total ELSE 0 END), 0) AS school_tax_owed,
                COALESCE(SUM(CASE WHEN authority_name = 'MUNICIPAL' AND total > 0 THEN total ELSE 0 END), 0) AS municipal_tax_owed,
                MIN(tax_year) AS oldest_delinquent_year,
                COUNT(DISTINCT tax_district_code) AS districts_affected
            FROM staging.tax_claims
            WHERE valid_to IS NULL
        """)
        tax_breakdown = cur.fetchone()

    total_records = sum(v for v in row.values() if isinstance(v, (int, float)))

    return {
        "total_records": total_records,
        "parcel_count": row["parcel_count"],
        "municipality_count": row["municipality_count"],
        "delinquent_parcels": row["delinquent_parcels"],
        "total_delinquent": float(row["total_delinquent"]),
        "flood_zone_count": row["flood_zone_count"],
        "liquor_license_count": row["liquor_license_count"],
        "address_point_count": row["address_point_count"],
        "structure_count": row["structure_count"],
        "total_assessed": float(row["total_assessed"]),
        "county_tax_owed": float(tax_breakdown["county_tax_owed"]),
        "school_tax_owed": float(tax_breakdown["school_tax_owed"]),
        "municipal_tax_owed": float(tax_breakdown["municipal_tax_owed"]),
        "oldest_delinquent_year": tax_breakdown["oldest_delinquent_year"],
        "districts_affected": tax_breakdown["districts_affected"],
    }
