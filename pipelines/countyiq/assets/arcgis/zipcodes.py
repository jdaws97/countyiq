"""York County zip code polygons from GIS → staging.zipcodes.

Source: OPEN_DATA/Zipcodes FeatureServer
Records: ~51 zip code polygons
Schedule: Monthly (bulk_refresh job)
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

from countyiq.lib.county_config import get_county_config
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


@asset_check(asset=zipcodes_arcgis)
def zipcodes_record_count(database: DatabaseResource) -> AssetCheckResult:
    result = database.execute("SELECT COUNT(*) FROM staging.zipcodes WHERE valid_to IS NULL")
    count = result[0][0] if result else 0
    return AssetCheckResult(passed=count > 10, severity=AssetCheckSeverity.ERROR,
                            metadata={"count": MetadataValue.int(count)})
