"""York County zip code polygons from GIS → staging.zipcodes.

Source: OPEN_DATA/Zipcodes FeatureServer
Records: ~51 zip code polygons
Schedule: Monthly (bulk_refresh job)
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
from countyiq.lib.county_config import county_open_data_source_key, get_county_config
from countyiq.lib.source_rights import authorize_source, require_source_use
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

REQUEST_TIMEOUT = 60
KEY_COLUMNS = ["zipcode"]
VALUE_COLUMNS = ["po_name"]


@asset(
    group_name="arcgis",
    description="York County zip code polygons → staging.zipcodes",
    kinds={"postgres", "geojson"},
)
def zipcodes_arcgis(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Fetch zip code polygons from GIS, upsert to staging.zipcodes."""
    county = get_county_config()
    authorization = authorize_source(database, source_key=county_open_data_source_key(), acquisition_method="arcgis_rest", asset_key="zipcodes_arcgis", dagster_run_id=context.run_id)
    require_source_use(authorization, "derived_product")
    require_source_use(authorization, "raw_retention")

    url = (
        f"{county.arcgis_zipcodes_url}/query"
        f"?where=1%3D1&outFields=ZIPCODE,PO_NAME&outSR=4326&f=json&returnGeometry=true"
    )
    context.log.info(f"Fetching zip codes from {county.arcgis_zipcodes_url}")
    resp = requests.get(url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    features = data.get("features", [])
    context.log.info(f"Fetched {len(features)} zip code polygons")

    s3.archive(f"{county.s3_prefix}/arcgis/zipcodes", data, filename="zipcodes.json")

    # Upsert with geometry
    cur = database.cursor()
    conn = cur.connection
    was_autocommit = conn.autocommit
    if was_autocommit:
        conn.autocommit = False

    try:
        # Clear and reload (small table, full refresh is fine)
        cur.execute("UPDATE staging.zipcodes SET valid_to = NOW() WHERE valid_to IS NULL")
        expired = cur.rowcount

        inserted = 0
        for f in features:
            a = f.get("attributes", {})
            geom = f.get("geometry")
            zipcode = str(a.get("ZIPCODE", ""))
            po_name = a.get("PO_NAME", "")

            if geom and "rings" in geom:
                geojson = json.dumps({"type": "Polygon", "coordinates": geom["rings"]})
                cur.execute("""
                    INSERT INTO staging.zipcodes (zipcode, po_name, source_url, geom)
                    VALUES (%s, %s, %s, ST_SetSRID(ST_Multi(ST_GeomFromGeoJSON(%s)), 4326))
                """, (zipcode, po_name, county.arcgis_zipcodes_url, geojson))
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


zipcodes_record_count = make_row_count_check(
    zipcodes_arcgis,
    table="zipcodes",
    min_count=11,
    metadata_key="count",
    name="zipcodes_record_count",
)
