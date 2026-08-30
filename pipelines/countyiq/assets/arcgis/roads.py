"""Road centerlines from ArcGIS REST API → staging.roads.

Records: ~33,748 polylines
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
from countyiq.lib.county_config import county_open_data_source_key, get_county_config
from countyiq.lib.geometry import paths_to_multilinestring_geojson
from countyiq.lib.parsers.roads import parse_roads_features
from countyiq.lib.scd import scd2_upsert_geom
from countyiq.lib.source_rights import authorize_source, require_source_use
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

KEY_COLUMNS = ["rcl_nguid"]
VALUE_COLUMNS = [
    "street_name", "st_pre_dir", "st_pre_typ", "st_pos_typ", "st_pos_dir",
    "road_class", "speed_limit", "one_way", "rte_num",
    "from_addr_l", "to_addr_l", "from_addr_r", "to_addr_r",
    "inc_muni_l", "inc_muni_r", "post_code_l", "post_code_r", "source_url",
]

EXPECTED_FIELDS = {
    "RCL_NGUID", "StreetName", "St_PreDir", "St_PreTyp", "St_PosTyp",
    "St_PosDir", "RoadClass", "SpeedLimit", "OneWay", "RTE_NUM",
    "FromAddr_L", "ToAddr_L", "FromAddr_R", "ToAddr_R",
    "IncMuni_L", "IncMuni_R", "PostCode_L", "PostCode_R",
}


@asset(
    group_name="arcgis",
    description=f"{get_county_config().name} road centerlines from ArcGIS REST API → staging.roads",
    kinds={"postgres", "arcgis"},
)
def roads_arcgis(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Fetch road centerlines, archive to S3, SCD2 upsert with geometry."""

    county = get_county_config()
    authorization = authorize_source(database, source_key=county_open_data_source_key(), acquisition_method="arcgis_rest", asset_key="roads_arcgis", dagster_run_id=context.run_id)
    require_source_use(authorization, "derived_product")
    require_source_use(authorization, "raw_retention")
    context.log.info(f"Querying ArcGIS roads for {county.name}: {county.arcgis_roads_url}")

    raw_features = query_all_features(
        url=county.arcgis_roads_url,
        where="1=1",
        out_fields="*",
        out_sr=4326,
        batch_size=2000,
    )
    context.log.info(f"Fetched {len(raw_features)} raw features")

    s3.archive(f"{county.s3_prefix}/arcgis/roads", raw_features)

    records = parse_roads_features(raw_features)
    for rec in records:
        rec["source_url"] = county.arcgis_roads_url
    context.log.info(f"Parsed {len(records)} road records")

    if not records:
        context.log.warning("No records parsed — skipping upsert")
        return MaterializeResult(metadata={"record_count": MetadataValue.int(0)})

    if len(records) < county.arcgis_roads_min_records:
        raise RuntimeError(
            f"Only {len(records)} road records (expected >= {county.arcgis_roads_min_records}). "
            f"Possible truncated response — aborting."
        )

    geom_lookup = _build_geom_lookup(raw_features)

    cur = database.cursor()
    try:
        stats = scd2_upsert_geom(
            cursor=cur,
            schema="staging",
            table="roads",
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
    """Build rcl_nguid -> JSON-encoded GeoJSON MultiLineString lookup."""
    lookup: dict = {}
    for feat in raw_features:
        attrs = feat.get("attributes", {})
        nguid = attrs.get("RCL_NGUID")
        geom = feat.get("geometry")
        if not (nguid and geom):
            continue
        geojson = paths_to_multilinestring_geojson(geom.get("paths"))
        if geojson:
            lookup[nguid] = json.dumps(geojson)
    return lookup


roads_record_count_nonzero = make_row_count_check(roads_arcgis, table="roads")


@asset_check(asset=roads_arcgis)
def roads_schema_drift(database: DatabaseResource) -> AssetCheckResult:
    """Verify ArcGIS Roads layer still has expected fields."""
    authorize_source(
        database,
        source_key=county_open_data_source_key(),
        acquisition_method="arcgis_rest",
        asset_key="roads_schema_drift",
    )
    county = get_county_config()
    try:
        resp = requests.get(f"{county.arcgis_roads_url}?f=json", timeout=30)
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
