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
                (SELECT COUNT(*) FROM staging.plcb_licenses WHERE valid_to IS NULL) AS liquor_license_count,
                (SELECT COUNT(*) FROM staging.address_points WHERE valid_to IS NULL) AS address_point_count,
                (SELECT COUNT(*) FROM staging.structures WHERE valid_to IS NULL) AS structure_count,
                (SELECT COUNT(*) FROM staging.parcels WHERE valid_to IS NULL) AS parcel_count
        """)
        row = cur.fetchone()

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
    }
