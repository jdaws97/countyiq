"""PennDOT traffic counts → staging.traffic_counts.

Source: PennDOT opendata/roadwaytraffic MapServer
Records: ~1,818 segments for York County
Schedule: Monthly (bulk_refresh job) — traffic data updates annually
"""

import json

import requests
from dagster import (
    asset,
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
)

from countyiq.lib.checks import make_row_count_check
from countyiq.lib.county_config import get_county_config
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource
from countyiq.lib.source_rights import authorize_source, require_source_use

REQUEST_TIMEOUT = 60
PAGE_SIZE = 1000


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
    authorization = authorize_source(database, source_key="penndot_open_data", acquisition_method="arcgis_rest", asset_key="traffic_counts_arcgis", dagster_run_id=context.run_id)
    require_source_use(authorization, "derived_product")
    require_source_use(authorization, "raw_retention")

    # Paginate through all segments
    all_features = []
    offset = 0
    while True:
        url = (
            f"{county.traffic_counts_url}/query"
            f"?where=CTY_CODE%3D%27{county.traffic_counts_cty_code}%27"
            f"&outFields=OBJECTID,ST_RT_NO,CUR_AADT,ADTT_CUR,SEG_LNGTH_FEET"
            f"&outSR=4326&returnGeometry=true&f=json"
            f"&resultRecordCount={PAGE_SIZE}&resultOffset={offset}"
        )
        context.log.info(f"Fetching traffic page at offset {offset}")
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        features = data.get("features", [])
        all_features.extend(features)
        context.log.info(f"  Got {len(features)} segments (total: {len(all_features)})")
        if len(features) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    context.log.info(f"Total: {len(all_features)} traffic segments")

    s3.archive(f"{county.s3_prefix}/arcgis/traffic_counts",
               {"features": all_features}, filename="traffic_counts.json")

    if len(all_features) < county.traffic_counts_min_records:
        raise RuntimeError(
            f"Only {len(all_features)} traffic segments "
            f"(expected >= {county.traffic_counts_min_records})")

    # Upsert with geometry
    cur = database.cursor()
    conn = cur.connection
    was_autocommit = conn.autocommit
    if was_autocommit:
        conn.autocommit = False

    try:
        cur.execute("UPDATE staging.traffic_counts SET valid_to = NOW() WHERE valid_to IS NULL")
        expired = cur.rowcount

        inserted = 0
        for f in all_features:
            a = f.get("attributes", {})
            geom = f.get("geometry")
            if not geom or "paths" not in geom:
                continue
            geojson = json.dumps({"type": "MultiLineString", "coordinates": geom["paths"]})
            cur.execute("""
                INSERT INTO staging.traffic_counts (objectid, route_number, aadt, truck_aadt, segment_length, source_url, geom)
                VALUES (%s, %s, %s, %s, %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
            """, (a.get("OBJECTID"), a.get("ST_RT_NO"), a.get("CUR_AADT"),
                  a.get("ADTT_CUR"), a.get("SEG_LNGTH_FEET"), county.traffic_counts_url, geojson))
            inserted += 1

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        if was_autocommit:
            conn.autocommit = True
        cur.close()

    return MaterializeResult(
        metadata={
            "record_count": MetadataValue.int(inserted),
            "expired": MetadataValue.int(expired),
        }
    )


traffic_counts_record_count = make_row_count_check(
    traffic_counts_arcgis,
    table="traffic_counts",
    threshold_fn=lambda: get_county_config().traffic_counts_min_records,
    metadata_key="count",
    name="traffic_counts_record_count",
)
