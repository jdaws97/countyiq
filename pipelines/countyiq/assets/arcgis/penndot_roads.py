"""PennDOT state road segments from ArcGIS MapServer -> staging.penndot_roads.

Records: ~2,500 polylines (York County, CTY_CODE='67')
Schedule: Weekly (Sunday 02:00)
"""

import json

import requests
from dagster import (
    asset,
    asset_check,
    AssetCheckResult,
    AssetCheckSeverity,
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
)

from countyiq.lib.checks import make_row_count_check
from countyiq.lib.county_config import get_county_config
from countyiq.lib.geometry import paths_to_multilinestring_geojson
from countyiq.lib.parsers.penndot_roads import parse_penndot_roads_features
from countyiq.lib.scd import scd2_upsert_geom
from countyiq.lib.source_rights import authorize_source, require_source_use
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource
from countyiq.resources.source_snapshots import SourceSnapshotsResource

KEY_COLUMNS = ["road_id"]
VALUE_COLUMNS = [
    "route_number",
    "road_name",
    "road_class",
    "municipality",
    "speed_limit",
    "surface_type",
    "source_url",
]

EXPECTED_FIELDS = {
    "ST_RT_NO",
    "SEG_NO",
    "STREET_NAME",
    "FAC_TYPE",
    "SURF_TYPE",
    "CTY_CODE",
}


@asset(
    group_name="arcgis",
    description=f"{get_county_config().name} PennDOT road segments from ArcGIS MapServer -> staging.penndot_roads",
    kinds={"postgres", "arcgis"},
)
def penndot_roads_arcgis(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
    source_snapshots: SourceSnapshotsResource,
) -> MaterializeResult:
    """Fetch PennDOT road segments, archive to S3, SCD2 upsert with geometry."""

    county = get_county_config()
    authorization = authorize_source(
        database,
        source_key="penndot_open_data",
        acquisition_method="arcgis_rest",
        asset_key="penndot_roads_arcgis",
        dagster_run_id=context.run_id,
    )
    require_source_use(authorization, "derived_product")
    require_source_use(authorization, "raw_retention")
    context.log.info(
        f"Querying PennDOT roads for {county.name}: {county.penndot_roads_url}"
    )

    raw_features = source_snapshots.arcgis("penndot_roads", context)
    context.log.info(f"Fetched {len(raw_features)} raw features")

    source_snapshots.archive_receipt(s3, context)
    s3.archive(f"{county.s3_prefix}/penndot/roads", raw_features)

    records = parse_penndot_roads_features(raw_features)
    for rec in records:
        rec["source_url"] = county.penndot_roads_url
    context.log.info(f"Parsed {len(records)} PennDOT road records")

    if not records:
        raise RuntimeError("No PennDOT road records parsed; refusing an empty refresh")

    if len(records) < county.penndot_roads_min_records:
        raise RuntimeError(
            f"Only {len(records)} PennDOT road records (expected >= {county.penndot_roads_min_records}). "
            f"Possible truncated response -- aborting."
        )

    geom_lookup = _build_geom_lookup(raw_features)

    cur = database.cursor()
    try:
        stats = scd2_upsert_geom(
            cursor=cur,
            schema="staging",
            table="penndot_roads",
            records=records,
            key_columns=KEY_COLUMNS,
            value_columns=VALUE_COLUMNS,
            geom_lookup=geom_lookup,
            geom_kind="multilinestring",
            snapshot_started_at=source_snapshots.acquisition_time(),
            snapshot_id=source_snapshots.snapshot_identity(),
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


def _build_geom_lookup(raw_features: list[dict]) -> dict:
    """Build composite road_id (ST_RT_NO-SEG_NO) -> GeoJSON MultiLineString lookup."""
    lookup: dict = {}
    for feat in raw_features:
        attrs = feat.get("attributes", {})
        st_rt_no = attrs.get("ST_RT_NO")
        seg_no = attrs.get("SEG_NO")
        geom = feat.get("geometry")
        if not (st_rt_no and seg_no and geom):
            continue
        geojson = paths_to_multilinestring_geojson(geom.get("paths"))
        if geojson:
            lookup[f"{st_rt_no}-{seg_no}"] = json.dumps(geojson)
    return lookup


penndot_roads_record_count_nonzero = make_row_count_check(
    penndot_roads_arcgis, table="penndot_roads"
)


@asset_check(asset=penndot_roads_arcgis)
def penndot_roads_schema_drift(
    database: DatabaseResource, source_snapshots: SourceSnapshotsResource
) -> AssetCheckResult:
    """Verify PennDOT MapServer still has expected fields."""
    authorize_source(
        database,
        source_key="penndot_open_data",
        acquisition_method="arcgis_rest",
        asset_key="penndot_roads_schema_drift",
    )
    try:
        metadata = source_snapshots.metadata("penndot_roads")
        actual_fields = {field["name"] for field in metadata.get("fields", [])}
        missing = EXPECTED_FIELDS - actual_fields
        return AssetCheckResult(
            passed=len(missing) == 0,
            severity=AssetCheckSeverity.WARN,
            metadata={
                "missing_fields": MetadataValue.text(
                    str(missing) if missing else "none"
                ),
            },
        )
    except requests.exceptions.RequestException as e:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.WARN,
            metadata={"error": MetadataValue.text(f"Network error: {e}")},
        )
