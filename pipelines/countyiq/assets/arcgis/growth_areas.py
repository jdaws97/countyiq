"""Growth area boundaries from ArcGIS REST API -> staging.growth_areas.

Records: ~27 polygons
Schedule: Weekly (Sunday 02:00)
"""

import json

from dagster import (
    asset,
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
)

from countyiq.lib.arcgis_client import query_all_features
from countyiq.lib.checks import make_row_count_check
from countyiq.lib.county_config import get_county_config
from countyiq.lib.geometry import rings_to_multipolygon_geojson
from countyiq.lib.scd import scd2_upsert_geom
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

KEY_COLUMNS = ["globalid"]
VALUE_COLUMNS = ["ga_type", "district", "ga_status", "source_url"]


@asset(
    group_name="radar",
    description="Growth area boundaries from ArcGIS -> staging.growth_areas",
    kinds={"postgres", "arcgis"},
)
def growth_areas_arcgis(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Fetch growth area polygons, archive to S3, SCD2 upsert with geometry."""

    county = get_county_config()
    context.log.info(f"Querying ArcGIS growth areas for {county.name}: {county.arcgis_growth_areas_url}")

    raw_features = query_all_features(
        url=county.arcgis_growth_areas_url,
        where="1=1",
        out_fields="*",
        out_sr=4326,
        batch_size=2000,
    )
    context.log.info(f"Fetched {len(raw_features)} raw features")

    s3.archive(f"{county.s3_prefix}/arcgis/growth_areas", raw_features)

    records = _parse(raw_features)
    for rec in records:
        rec["source_url"] = county.arcgis_growth_areas_url
    context.log.info(f"Parsed {len(records)} growth area records")

    if not records:
        context.log.warning("No records parsed -- skipping upsert")
        return MaterializeResult(metadata={"record_count": MetadataValue.int(0)})

    geom_lookup = _build_geom_lookup(raw_features)

    cur = database.cursor()
    try:
        stats = scd2_upsert_geom(
            cursor=cur,
            schema="staging",
            table="growth_areas",
            records=records,
            key_columns=KEY_COLUMNS,
            value_columns=VALUE_COLUMNS,
            geom_lookup=geom_lookup,
            geom_kind="multipolygon",
        )
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


def _parse(raw_features: list[dict]) -> list[dict]:
    """Parse ArcGIS attributes into staging column names."""
    records = []
    for feat in raw_features:
        a = feat.get("attributes", {})
        globalid = a.get("GlobalID")
        if not globalid:
            continue
        records.append({
            "globalid": str(globalid).strip(),
            "ga_type": a.get("GA_TYPE"),
            "district": a.get("DISTRICT"),
            "ga_status": a.get("GA_STATUS"),
        })
    return records


def _build_geom_lookup(raw_features: list[dict]) -> dict[str, str]:
    """Build globalid -> JSON-encoded GeoJSON MultiPolygon lookup."""
    lookup: dict[str, str] = {}
    for feat in raw_features:
        attrs = feat.get("attributes", {})
        globalid = attrs.get("GlobalID")
        geom = feat.get("geometry")
        if globalid is None or not geom:
            continue
        geojson = rings_to_multipolygon_geojson(geom.get("rings"))
        if geojson:
            lookup[str(globalid).strip()] = json.dumps(geojson)
    return lookup


growth_areas_record_count_nonzero = make_row_count_check(
    growth_areas_arcgis, table="growth_areas"
)
