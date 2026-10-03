"""PennDOT traffic counts → staging.traffic_counts.

Source: PennDOT opendata/roadwaytraffic MapServer
Records: ~1,818 segments for York County
"""

import json
from datetime import UTC, datetime

from dagster import (
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
)

from countyiq.lib.arcgis_snapshot import fetch_arcgis_snapshot
from countyiq.lib.checks import make_row_count_check
from countyiq.lib.county_config import get_county_config
from countyiq.lib.geometry import paths_to_multilinestring_geojson
from countyiq.lib.scd import scd2_upsert_geom
from countyiq.lib.source_rights import authorize_source, require_source_use
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

VALUE_COLUMNS = [
    "route_number",
    "aadt",
    "truck_aadt",
    "segment_length",
    "source_url",
]


def parse_traffic_features(
    features: list[dict], source_url: str
) -> tuple[list[dict], dict]:
    records = []
    geometries = {}
    for feature in features:
        attributes = feature.get("attributes") or {}
        required = {"OBJECTID", "ST_RT_NO", "CUR_AADT", "ADTT_CUR", "SEG_LNGTH_FEET"}
        geometry = paths_to_multilinestring_geojson(
            (feature.get("geometry") or {}).get("paths")
        )
        objectid = attributes.get("OBJECTID")
        if required - attributes.keys() or objectid is None or geometry is None:
            raise ValueError(
                "Traffic snapshot contains an unusable row; refusing to expire current data"
            )
        if objectid in geometries:
            raise ValueError("Traffic snapshot contains duplicate object IDs")
        geometries[objectid] = json.dumps(geometry)
        records.append(
            {
                "objectid": objectid,
                "route_number": attributes["ST_RT_NO"],
                "aadt": attributes["CUR_AADT"],
                "truck_aadt": attributes["ADTT_CUR"],
                "segment_length": attributes["SEG_LNGTH_FEET"],
                "source_url": source_url,
            }
        )
    return records, geometries


@asset(
    group_name="arcgis",
    description="PennDOT traffic counts (AADT) → staging.traffic_counts",
    kinds={"postgres", "geojson"},
)
def traffic_counts_arcgis(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Fetch traffic count segments, upsert to staging.traffic_counts."""
    county = get_county_config()
    authorization = authorize_source(
        database,
        source_key="penndot_open_data",
        acquisition_method="arcgis_rest",
        asset_key="traffic_counts_arcgis",
        dagster_run_id=context.run_id,
    )
    require_source_use(authorization, "derived_product")
    require_source_use(authorization, "raw_retention")

    snapshot_started_at = datetime.now(UTC)
    all_features = fetch_arcgis_snapshot(
        county.traffic_counts_url,
        where=f"CTY_CODE='{county.traffic_counts_cty_code}'",
    )
    context.log.info(f"Total: {len(all_features)} traffic segments")

    s3.archive(
        f"{county.s3_prefix}/arcgis/traffic_counts",
        {"features": all_features},
        filename="traffic_counts.json",
    )

    if len(all_features) < county.traffic_counts_min_records:
        raise RuntimeError(
            f"Only {len(all_features)} traffic segments "
            f"(expected >= {county.traffic_counts_min_records})"
        )

    records, geometries = parse_traffic_features(
        all_features, county.traffic_counts_url
    )
    cur = database.cursor()
    try:
        stats = scd2_upsert_geom(
            cursor=cur,
            schema="staging",
            table="traffic_counts",
            records=records,
            key_columns=["objectid"],
            value_columns=VALUE_COLUMNS,
            geom_lookup=geometries,
            geom_kind="multilinestring",
            snapshot_started_at=snapshot_started_at,
            snapshot_id=context.run_id,
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


traffic_counts_record_count = make_row_count_check(
    traffic_counts_arcgis,
    table="traffic_counts",
    threshold_fn=lambda: get_county_config().traffic_counts_min_records,
    metadata_key="count",
    name="traffic_counts_record_count",
)
