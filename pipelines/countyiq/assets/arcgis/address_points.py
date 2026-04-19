"""Address points from ArcGIS REST API → staging.address_points.

Records: ~189,876 points
Schedule: Weekly (Sunday 02:00) via arcgis_refresh
"""

import json
import os
import tempfile

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

from countyiq.lib.arcgis_client import iterate_feature_pages
from countyiq.lib.checks import make_row_count_check
from countyiq.lib.county_config import get_county_config
from countyiq.lib.parsers.address_points import parse_address_point_feature
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

KEY_COLUMNS = ["site_nguid"]
VALUE_COLUMNS = [
    "add_number", "addnum_suf", "st_pre_dir", "st_pre_typ",
    "street_name", "st_pos_typ", "st_pos_dir",
    "inc_muni", "post_comm", "post_code", "post_code4",
    "building", "floor", "unit", "place_type", "long", "lat", "source_url",
]

EXPECTED_FIELDS = {
    "Site_NGUID", "Add_Number", "AddNum_Suf", "St_PreDir", "St_PreTyp",
    "StreetName", "St_PosTyp", "St_PosDir", "Inc_Muni", "Post_Comm",
    "Post_Code", "Post_Code4", "Building", "Floor", "Unit",
    "Place_Type", "Long", "Lat",
}


@asset(
    group_name="arcgis",
    description=f"{get_county_config().name} address points from ArcGIS REST API → staging.address_points",
    kinds={"postgres", "arcgis"},
)
def address_points_arcgis(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Fetch address points, archive to S3, SCD2 upsert with geometry.

    The loader streams one ArcGIS page at a time into a temp table so the
    asset does not hold the full raw payload, parsed records, and DB rows in
    memory at once.
    """

    county = get_county_config()
    context.log.info(f"Querying ArcGIS address points for {county.name}: {county.arcgis_address_pts_url}")

    cur = database.cursor()
    archive_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".ndjson",
            prefix="address_points_",
            delete=False,
            encoding="utf-8",
        ) as archive_file:
            archive_path = archive_file.name
            stats = _geom_scd2_upsert_streaming(
                cursor=cur,
                feature_pages=iterate_feature_pages(
                    url=county.arcgis_address_pts_url,
                    where="1=1",
                    out_fields="*",
                    out_sr=4326,
                    batch_size=2000,
                ),
                archive_handle=archive_file,
                min_records=county.arcgis_address_pts_min_records,
                context=context,
                source_url=county.arcgis_address_pts_url,
            )

        s3.archive_file(
            f"{county.s3_prefix}/arcgis/address_points",
            archive_path,
            filename="response.ndjson",
        )
    finally:
        cur.close()
        if archive_path and os.path.exists(archive_path):
            os.unlink(archive_path)

    return MaterializeResult(
        metadata={
            "record_count": MetadataValue.int(stats["record_count"]),
            "raw_feature_count": MetadataValue.int(stats["raw_feature_count"]),
            "inserted": MetadataValue.int(stats["inserted"]),
            "expired": MetadataValue.int(stats["expired"]),
            "unchanged": MetadataValue.int(stats["unchanged"]),
        }
    )


def _geom_scd2_upsert_streaming(cursor, feature_pages, archive_handle, min_records: int, context, source_url: str = "") -> dict:
    """Stream ArcGIS pages into a temp table and finalize one SCD2 upsert."""
    conn = cursor.connection
    was_autocommit = conn.autocommit
    if was_autocommit:
        conn.autocommit = False

    try:
        all_cols = KEY_COLUMNS + VALUE_COLUMNS
        fqn = "staging.address_points"

        cursor.execute("DROP TABLE IF EXISTS _tmp_address_points")
        cursor.execute(f"CREATE TEMP TABLE _tmp_address_points (LIKE {fqn} INCLUDING DEFAULTS)")

        insert_sql = f"""
            INSERT INTO _tmp_address_points ({', '.join(all_cols)}, geom)
            VALUES ({', '.join(['%s'] * len(all_cols))},
                    CASE WHEN %s IS NOT NULL
                         THEN ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)
                         ELSE NULL END)
        """

        record_count = 0
        raw_feature_count = 0
        for page_num, raw_features in enumerate(feature_pages, start=1):
            raw_feature_count += len(raw_features)
            page_record_count = _stage_address_points_page(cursor, insert_sql, all_cols, raw_features, archive_handle, source_url)
            record_count += page_record_count
            context.log.info(
                f"Staged address_points page {page_num}: {page_record_count} parsed records "
                f"({record_count} cumulative)"
            )

        if record_count == 0:
            context.log.warning("No records parsed — skipping upsert")
            cursor.execute("DROP TABLE IF EXISTS _tmp_address_points")
            conn.commit()
            return {
                "record_count": 0,
                "raw_feature_count": raw_feature_count,
                "inserted": 0,
                "expired": 0,
                "unchanged": 0,
            }

        if record_count < min_records:
            raise RuntimeError(
                f"Only {record_count} address point records (expected >= {min_records}). "
                f"Possible truncated response — aborting."
            )

        archive_handle.flush()

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

        return {
            "record_count": record_count,
            "raw_feature_count": raw_feature_count,
            "inserted": inserted,
            "expired": expired,
            "unchanged": record_count - inserted,
        }
    except Exception:
        conn.rollback()
        if was_autocommit:
            conn.autocommit = True
        raise


def _stage_address_points_page(cursor, insert_sql: str, all_cols: list[str], raw_features: list[dict], archive_handle, source_url: str = "") -> int:
    """Parse one ArcGIS page and bulk insert it into the temp table."""
    rows = []
    record_count = 0

    for feat in raw_features:
        archive_handle.write(json.dumps(feat, default=str))
        archive_handle.write("\n")

        record = parse_address_point_feature(feat)
        if record is None:
            continue

        record["source_url"] = source_url

        geom = feat.get("geometry")
        geom_json = None
        if geom and geom.get("x") is not None and geom.get("y") is not None:
            geom_json = json.dumps({"type": "Point", "coordinates": [geom["x"], geom["y"]]})

        row = [record.get(c) for c in all_cols]
        row.extend([geom_json, geom_json])
        rows.append(row)
        record_count += 1

    if rows:
        execute_batch(cursor, insert_sql, rows, page_size=500)

    return record_count


address_points_record_count_nonzero = make_row_count_check(
    address_points_arcgis, table="address_points"
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
