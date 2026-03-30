"""Spatial join enrichment: populate staging.parcels.municipality from staging.municipalities.

Uses ST_Centroid on parcel polygons so each parcel maps to exactly one municipality,
even when a polygon spans a boundary.

Depends on: parcels_arcgis, municipalities_arcgis
Schedule: enrichment_refresh job
"""

from dagster import (
    asset,
    asset_check,
    AssetCheckResult,
    AssetCheckSeverity,
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
)

from countyiq.resources.database import DatabaseResource


@asset(
    group_name="enrichment",
    deps=["parcels_arcgis", "municipalities_arcgis"],
    description="Spatial join: set staging.parcels.municipality from staging.municipalities polygons",
    kinds={"postgres"},
)
def municipality_join(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> MaterializeResult:
    """Update parcels with their municipality via ST_Centroid spatial join."""

    # Count NULLs before
    result = database.execute(
        "SELECT COUNT(*) FROM staging.parcels WHERE valid_to IS NULL AND municipality IS NULL"
    )
    nulls_before = result[0][0] if result else 0
    context.log.info(f"Parcels with NULL municipality before join: {nulls_before}")

    if nulls_before == 0:
        context.log.info("All current parcels already have a municipality — skipping")
        return MaterializeResult(
            metadata={
                "nulls_before": MetadataValue.int(0),
                "rows_updated": MetadataValue.int(0),
                "nulls_after": MetadataValue.int(0),
            }
        )

    # Run spatial join — ST_Centroid picks one municipality per parcel
    cur = database.cursor()
    conn = cur.connection
    was_autocommit = conn.autocommit
    if was_autocommit:
        conn.autocommit = False

    try:
        cur.execute("""
            UPDATE staging.parcels p
            SET municipality = m.name
            FROM staging.municipalities m
            WHERE ST_Intersects(ST_Centroid(p.geom), m.geom)
              AND p.valid_to IS NULL
              AND m.valid_to IS NULL
              AND p.municipality IS NULL
        """)
        rows_updated = cur.rowcount
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        if was_autocommit:
            conn.autocommit = True
        cur.close()

    context.log.info(f"Updated {rows_updated} parcels with municipality")

    # Count remaining NULLs
    result = database.execute(
        "SELECT COUNT(*) FROM staging.parcels WHERE valid_to IS NULL AND municipality IS NULL"
    )
    nulls_after = result[0][0] if result else 0
    if nulls_after > 0:
        context.log.warning(f"{nulls_after} parcels still have NULL municipality (centroid outside all municipality polygons)")

    # Distinct municipality count
    result = database.execute(
        "SELECT COUNT(DISTINCT municipality) FROM staging.parcels WHERE valid_to IS NULL AND municipality IS NOT NULL"
    )
    distinct_munis = result[0][0] if result else 0
    context.log.info(f"Distinct municipalities assigned: {distinct_munis}")

    return MaterializeResult(
        metadata={
            "nulls_before": MetadataValue.int(nulls_before),
            "rows_updated": MetadataValue.int(rows_updated),
            "nulls_after": MetadataValue.int(nulls_after),
            "distinct_municipalities": MetadataValue.int(distinct_munis),
        }
    )


@asset_check(asset=municipality_join)
def municipality_join_coverage(database: DatabaseResource) -> AssetCheckResult:
    """Verify most parcels have a municipality assigned after the join."""
    result = database.execute("""
        SELECT
            COUNT(*) FILTER (WHERE municipality IS NOT NULL) AS assigned,
            COUNT(*) AS total
        FROM staging.parcels
        WHERE valid_to IS NULL
    """)
    assigned, total = result[0] if result else (0, 0)
    pct = (assigned / total * 100) if total > 0 else 0
    return AssetCheckResult(
        passed=pct >= 95.0,
        severity=AssetCheckSeverity.WARN,
        metadata={
            "assigned": MetadataValue.int(assigned),
            "total": MetadataValue.int(total),
            "coverage_pct": MetadataValue.float(pct),
        },
    )
