"""PennDOT state road segments from ArcGIS MapServer -> staging.penndot_roads.

Records: ~2,500 polylines (York County, CTY_CODE='67')
Schedule: Weekly (Sunday 02:00)
"""

import json

import requests
from psycopg2.extras import execute_batch
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
from countyiq.lib.county_config import get_county_config
from countyiq.lib.parsers.penndot_roads import parse_penndot_roads_features
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

KEY_COLUMNS = ["road_id"]
VALUE_COLUMNS = [
    "route_number", "road_name", "road_class", "municipality",
    "speed_limit", "surface_type",
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
    context.log.info(f"Parsed {len(records)} PennDOT road records")

    if not records:
        context.log.warning("No records parsed -- skipping upsert")
        return MaterializeResult(metadata={"record_count": MetadataValue.int(0)})

    if len(records) < county.penndot_roads_min_records:
        raise RuntimeError(
            f"Only {len(records)} PennDOT road records (expected >= {county.penndot_roads_min_records}). "
            f"Possible truncated response -- aborting."
        )

    cur = database.cursor()
    try:
        stats = _geom_scd2_upsert(cur, records, raw_features)
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


def _geom_scd2_upsert(cursor, records: list[dict], raw_features: list[dict]) -> dict:
    """SCD2 upsert with PostGIS geometry for staging.penndot_roads (MULTILINESTRING)."""
    conn = cursor.connection
    was_autocommit = conn.autocommit
    if was_autocommit:
        conn.autocommit = False

    try:
        all_cols = KEY_COLUMNS + VALUE_COLUMNS
        fqn = "staging.penndot_roads"

        cursor.execute("DROP TABLE IF EXISTS _tmp_penndot_roads")
        cursor.execute(f"CREATE TEMP TABLE _tmp_penndot_roads (LIKE {fqn} INCLUDING DEFAULTS)")

        # Build geometry lookup by road_id (ST_RT_NO-SEG_NO)
        geom_lookup = {}
        for feat in raw_features:
            attrs = feat.get("attributes", {})
            st_rt_no = attrs.get("ST_RT_NO")
            seg_no = attrs.get("SEG_NO")
            geom = feat.get("geometry")
            if st_rt_no and seg_no and geom:
                geojson = _arcgis_polyline_to_geojson(geom)
                if geojson:
                    geom_lookup[f"{st_rt_no}-{seg_no}"] = json.dumps(geojson)

        insert_sql = f"""
            INSERT INTO _tmp_penndot_roads ({', '.join(all_cols)}, geom)
            VALUES ({', '.join(['%s'] * len(all_cols))},
                    CASE WHEN %s IS NOT NULL
                         THEN ST_SetSRID(ST_Multi(ST_GeomFromGeoJSON(%s)), 4326)
                         ELSE NULL END)
        """
        rows = []
        for rec in records:
            row = [rec.get(c) for c in all_cols]
            geom_json = geom_lookup.get(rec["road_id"])
            row.extend([geom_json, geom_json])
            rows.append(row)
        execute_batch(cursor, insert_sql, rows, page_size=500)

        # Expire changed/deleted
        key_join = "c.road_id = t.road_id"
        value_diff = " OR ".join(f"c.{v}::text IS DISTINCT FROM t.{v}::text" for v in VALUE_COLUMNS)
        cursor.execute(f"""
            UPDATE {fqn} c SET valid_to = NOW()
            WHERE c.valid_to IS NULL
            AND (
                EXISTS (SELECT 1 FROM _tmp_penndot_roads t WHERE {key_join} AND ({value_diff}))
                OR NOT EXISTS (SELECT 1 FROM _tmp_penndot_roads t WHERE {key_join})
            )
        """)
        expired = cursor.rowcount

        # Insert new/changed
        col_list = ', '.join(all_cols)
        cursor.execute(f"""
            INSERT INTO {fqn} ({col_list}, geom, valid_from)
            SELECT {', '.join(f't.{c}' for c in all_cols)}, t.geom, NOW()
            FROM _tmp_penndot_roads t
            WHERE NOT EXISTS (
                SELECT 1 FROM {fqn} c WHERE c.valid_to IS NULL AND {key_join}
            )
        """)
        inserted = cursor.rowcount

        cursor.execute("DROP TABLE IF EXISTS _tmp_penndot_roads")
        conn.commit()

        if was_autocommit:
            conn.autocommit = True

        return {"inserted": inserted, "expired": expired, "unchanged": len(records) - inserted}
    except Exception:
        conn.rollback()
        if was_autocommit:
            conn.autocommit = True
        raise


def _arcgis_polyline_to_geojson(geom: dict) -> dict | None:
    """Convert ArcGIS polyline geometry to GeoJSON MultiLineString."""
    paths = geom.get("paths")
    if not paths:
        return None
    return {"type": "MultiLineString", "coordinates": paths}


@asset_check(asset=penndot_roads_arcgis)
def penndot_roads_record_count_nonzero(database: DatabaseResource) -> AssetCheckResult:
    """Verify staging.penndot_roads has at least one current record."""
    result = database.execute("SELECT COUNT(*) FROM staging.penndot_roads WHERE valid_to IS NULL")
    count = result[0][0] if result else 0
    return AssetCheckResult(
        passed=count > 0,
        severity=AssetCheckSeverity.ERROR,
        metadata={"current_record_count": MetadataValue.int(count)},
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
