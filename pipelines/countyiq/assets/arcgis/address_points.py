"""Address points from ArcGIS REST API → staging.address_points.

Records: ~189,876 points
Schedule: Weekly (Sunday 02:00) via arcgis_refresh
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
from countyiq.lib.parsers.address_points import parse_address_points_features
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

KEY_COLUMNS = ["site_nguid"]
VALUE_COLUMNS = [
    "add_number", "addnum_suf", "st_pre_dir", "st_pre_typ",
    "street_name", "st_pos_typ", "st_pos_dir",
    "inc_muni", "post_comm", "post_code", "post_code4",
    "building", "floor", "unit", "place_type", "long", "lat",
]

EXPECTED_FIELDS = {
    "Site_NGUID", "Add_Number", "AddNum_Suf", "St_PreDir", "St_PreTyp",
    "StreetName", "St_PosTyp", "St_PosDir", "Inc_Muni", "Post_Comm",
    "Post_Code", "Post_Code4", "Building", "Floor", "Unit",
    "Place_Type", "Long", "Lat",
}


@asset(
    group_name="gis_layers",
    description=f"{get_county_config().name} address points from ArcGIS REST API → staging.address_points",
    kinds={"postgres", "arcgis"},
)
def address_points_arcgis(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Fetch address points, archive to S3, SCD2 upsert with geometry."""

    county = get_county_config()
    context.log.info(f"Querying ArcGIS address points for {county.name}: {county.arcgis_address_pts_url}")

    raw_features = query_all_features(
        url=county.arcgis_address_pts_url,
        where="1=1",
        out_fields="*",
        out_sr=4326,
        batch_size=2000,
    )
    context.log.info(f"Fetched {len(raw_features)} raw features")

    s3.archive(f"{county.s3_prefix}/arcgis/address_points", raw_features)

    records = parse_address_points_features(raw_features)
    context.log.info(f"Parsed {len(records)} address point records")

    if not records:
        context.log.warning("No records parsed — skipping upsert")
        return MaterializeResult(metadata={"record_count": MetadataValue.int(0)})

    if len(records) < county.arcgis_address_pts_min_records:
        raise RuntimeError(
            f"Only {len(records)} address point records (expected >= {county.arcgis_address_pts_min_records}). "
            f"Possible truncated response — aborting."
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
    """SCD2 upsert with PostGIS POINT geometry for staging.address_points."""
    conn = cursor.connection
    was_autocommit = conn.autocommit
    if was_autocommit:
        conn.autocommit = False

    try:
        all_cols = KEY_COLUMNS + VALUE_COLUMNS
        fqn = "staging.address_points"

        cursor.execute("DROP TABLE IF EXISTS _tmp_address_points")
        cursor.execute(f"CREATE TEMP TABLE _tmp_address_points (LIKE {fqn} INCLUDING DEFAULTS)")

        # Build geometry lookup by site_nguid
        # ArcGIS points come as {"x": lon, "y": lat} — convert to GeoJSON Point
        geom_lookup = {}
        for feat in raw_features:
            attrs = feat.get("attributes", {})
            nguid = attrs.get("Site_NGUID")
            geom = feat.get("geometry")
            if nguid and geom and geom.get("x") is not None and geom.get("y") is not None:
                geojson = {"type": "Point", "coordinates": [geom["x"], geom["y"]]}
                geom_lookup[nguid] = json.dumps(geojson)

        insert_sql = f"""
            INSERT INTO _tmp_address_points ({', '.join(all_cols)}, geom)
            VALUES ({', '.join(['%s'] * len(all_cols))},
                    CASE WHEN %s IS NOT NULL
                         THEN ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)
                         ELSE NULL END)
        """
        rows = []
        for rec in records:
            row = [rec.get(c) for c in all_cols]
            geom_json = geom_lookup.get(rec["site_nguid"])
            row.extend([geom_json, geom_json])
            rows.append(row)
        execute_batch(cursor, insert_sql, rows, page_size=500)

        key_join = "c.site_nguid = t.site_nguid"
        value_diff = " OR ".join(f"c.{v}::text IS DISTINCT FROM t.{v}::text" for v in VALUE_COLUMNS)
        cursor.execute(f"""
            UPDATE {fqn} c SET valid_to = NOW()
            WHERE c.valid_to IS NULL
            AND (
                EXISTS (SELECT 1 FROM _tmp_address_points t WHERE {key_join} AND ({value_diff}))
                OR NOT EXISTS (SELECT 1 FROM _tmp_address_points t WHERE {key_join})
            )
        """)
        expired = cursor.rowcount

        col_list = ', '.join(all_cols)
        cursor.execute(f"""
            INSERT INTO {fqn} ({col_list}, geom, valid_from)
            SELECT {', '.join(f't.{c}' for c in all_cols)}, t.geom, NOW()
            FROM _tmp_address_points t
            WHERE NOT EXISTS (
                SELECT 1 FROM {fqn} c WHERE c.valid_to IS NULL AND {key_join}
            )
        """)
        inserted = cursor.rowcount

        cursor.execute("DROP TABLE IF EXISTS _tmp_address_points")
        conn.commit()

        if was_autocommit:
            conn.autocommit = True

        return {"inserted": inserted, "expired": expired, "unchanged": len(records) - inserted}
    except Exception:
        conn.rollback()
        if was_autocommit:
            conn.autocommit = True
        raise


@asset_check(asset=address_points_arcgis)
def address_points_record_count_nonzero(database: DatabaseResource) -> AssetCheckResult:
    result = database.execute("SELECT COUNT(*) FROM staging.address_points WHERE valid_to IS NULL")
    count = result[0][0] if result else 0
    return AssetCheckResult(
        passed=count > 0,
        severity=AssetCheckSeverity.ERROR,
        metadata={"current_record_count": MetadataValue.int(count)},
    )


@asset_check(asset=address_points_arcgis)
def address_points_schema_drift() -> AssetCheckResult:
    county = get_county_config()
    try:
        resp = requests.get(f"{county.arcgis_address_pts_url}?f=json", timeout=30)
        resp.raise_for_status()
        actual_fields = {f["name"] for f in resp.json().get("fields", [])}
        missing = EXPECTED_FIELDS - actual_fields
        return AssetCheckResult(
            passed=len(missing) == 0,
            severity=AssetCheckSeverity.WARN,
            metadata={"missing_fields": MetadataValue.text(str(missing) if missing else "none")},
        )
    except requests.exceptions.RequestException as e:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.WARN,
            metadata={"error": MetadataValue.text(f"Network error: {e}")},
        )
