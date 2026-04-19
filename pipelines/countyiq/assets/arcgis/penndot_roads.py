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

from countyiq.lib.arcgis_client import query_all_features
from countyiq.lib.checks import make_row_count_check
from countyiq.lib.county_config import get_county_config
from countyiq.lib.geometry import paths_to_multilinestring_geojson
from countyiq.lib.parsers.penndot_roads import parse_penndot_roads_features
from countyiq.lib.scd import scd2_upsert_geom
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

KEY_COLUMNS = ["road_id"]
VALUE_COLUMNS = [
    "route_number", "road_name", "road_class", "municipality",
    "speed_limit", "surface_type", "source_url",
]

EXPECTED_FIELDS = {
    "ST_RT_NO", "SEG_NO", "STREET_NAME", "FAC_TYPE", "SURF_TYPE", "CTY_CODE",
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
) -> MaterializeResult:
    """Fetch PennDOT road segments, archive to S3, SCD2 upsert with geometry."""

    county = get_county_config()
    context.log.info(f"Querying PennDOT roads for {county.name}: {county.penndot_roads_url}")

    raw_features = query_all_features(
        url=county.penndot_roads_url,
        where=f"CTY_CODE='{county.penndot_roads_cty_code}'",
        out_fields="*",
        out_sr=4326,
        batch_size=2000,
    )
    context.log.info(f"Fetched {len(raw_features)} raw features")

    s3.archive(f"{county.s3_prefix}/penndot/roads", raw_features)

    records = parse_penndot_roads_features(raw_features)
    for rec in records:
        rec["source_url"] = county.penndot_roads_url
    context.log.info(f"Parsed {len(records)} PennDOT road records")

    if not records:
        context.log.warning("No records parsed -- skipping upsert")
        return MaterializeResult(metadata={"record_count": MetadataValue.int(0)})

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
def penndot_roads_schema_drift() -> AssetCheckResult:
    """Verify PennDOT MapServer still has expected fields."""
    county = get_county_config()
    try:
        resp = requests.get(f"{county.penndot_roads_url}?f=json", timeout=30)
        resp.raise_for_status()
        actual_fields = {f["name"] for f in resp.json().get("fields", [])}
        missing = EXPECTED_FIELDS - actual_fields
        return AssetCheckResult(
            passed=len(missing) == 0,
            severity=AssetCheckSeverity.WARN,
            metadata={
                "missing_fields": MetadataValue.text(str(missing) if missing else "none"),
            },
        )
    except requests.exceptions.RequestException as e:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.WARN,
            metadata={"error": MetadataValue.text(f"Network error: {e}")},
        )
