"""Parcel boundaries from ArcGIS REST API → staging.parcels.

Records: ~176,000 parcels with geometry + 40+ attribute fields
Schedule: Weekly (Monday 02:00)
"""

from dagster import asset, AssetExecutionContext, MaterializeResult, MetadataValue

from countyiq.lib.arcgis_client import query_all_features
from countyiq.lib.county_config import get_county_config
from countyiq.lib.parsers.arcgis_parcels import parse_parcels_features
from countyiq.lib.scd import scd2_upsert
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

# Columns that identify a unique parcel record
KEY_COLUMNS = ["pidn"]

# Columns compared for SCD2 change detection (subset — not all 40+ fields)
VALUE_COLUMNS = [
    "owner_full",
    "propadr",
    "aprtotal",
    "saledt",
    "price",
    "municipality",
    "school_dis",
    "acres",
    "class",
]


@asset(
    group_name="arcgis",
    description=f"{get_county_config().name} parcel boundaries from ArcGIS REST API → staging.parcels",
    kinds={"postgres", "arcgis"},
)
def parcels_arcgis(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Fetch all parcels, archive raw to S3, upsert to staging.parcels (SCD2)."""

    # 1. Fetch all features with pagination
    county = get_county_config()
    context.log.info(f"Querying ArcGIS parcels for {county.name}: {county.arcgis_parcels_url}")
    raw_features = query_all_features(
        url=county.arcgis_parcels_url,
        where="1=1",
        out_fields="*",
        out_sr=4326,
        batch_size=2000,
    )
    context.log.info(f"Fetched {len(raw_features)} raw features")

    # 2. Archive raw response to S3
    s3.archive(f"{county.s3_prefix}/arcgis/parcels", raw_features)

    # 3. Parse features into flat records
    records = parse_parcels_features(raw_features)
    context.log.info(f"Parsed {len(records)} parcel records")

    if not records:
        context.log.warning("No records parsed — skipping upsert")
        return MaterializeResult(
            metadata={"record_count": MetadataValue.int(0)}
        )

    # 4. SCD2 upsert to staging.parcels
    cur = database.cursor()
    try:
        stats = scd2_upsert(
            cursor=cur,
            schema="staging",
            table="parcels",
            records=records,
            key_columns=KEY_COLUMNS,
            value_columns=VALUE_COLUMNS,
        )

        # 5. Update geometry separately (SCD2 helper uses TEXT temp table)
        # Geometry is handled as WKT → PostGIS conversion
        _update_geometries(cur, raw_features)

    finally:
        cur.close()

    return MaterializeResult(
        metadata={
            "record_count": MetadataValue.int(len(records)),
            "inserted": MetadataValue.int(stats["inserted"]),
            "expired": MetadataValue.int(stats["expired"]),
            "unchanged": MetadataValue.int(stats["unchanged"]),
        }
    )


def _update_geometries(cursor, raw_features: list[dict]):
    """Set geometry on newly inserted records (valid_to IS NULL) from raw features."""
    update_sql = """
        UPDATE staging.parcels
        SET geom = ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)
        WHERE pidn = %s AND valid_to IS NULL AND geom IS NULL
    """
    import json

    batch = []
    for feat in raw_features:
        geom = feat.get("geometry")
        attrs = feat.get("attributes", {})
        pidn = attrs.get("PIDN")
        if geom and pidn:
            # Convert ArcGIS geometry to GeoJSON-like format
            geojson = _arcgis_geom_to_geojson(geom)
            if geojson:
                batch.append((json.dumps(geojson), pidn))

    if batch:
        cursor.executemany(update_sql, batch)


def _arcgis_geom_to_geojson(geom: dict) -> dict | None:
    """Convert ArcGIS JSON geometry to GeoJSON geometry."""
    rings = geom.get("rings")
    if not rings:
        return None

    # ArcGIS rings → GeoJSON MultiPolygon
    # Each ring is a list of [x, y] coordinates
    # First ring is exterior, subsequent rings are holes
    polygons = []
    current_polygon = []

    for ring in rings:
        # In ArcGIS, exterior rings are clockwise, holes are counter-clockwise
        # For simplicity, treat each ring as a separate polygon exterior
        # (handles most parcels which are simple polygons)
        if not current_polygon:
            current_polygon.append(ring)
        else:
            # Check if this is a hole (counter-clockwise) or new polygon
            if _is_clockwise(ring):
                polygons.append(current_polygon)
                current_polygon = [ring]
            else:
                current_polygon.append(ring)

    if current_polygon:
        polygons.append(current_polygon)

    return {"type": "MultiPolygon", "coordinates": [p for p in polygons]}


def _is_clockwise(ring: list[list[float]]) -> bool:
    """Determine if a ring is clockwise using the shoelace formula."""
    total = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[i + 1][0], ring[i + 1][1]
        total += (x2 - x1) * (y2 + y1)
    return total > 0
