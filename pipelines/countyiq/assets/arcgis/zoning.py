"""Zoning districts from ArcGIS REST API → staging.zoning.

Records: ~1,694 polygons
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
from countyiq.lib.parsers.zoning import parse_zoning_features
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

KEY_COLUMNS = ["zrecid"]
VALUE_COLUMNS = [
    "muni_name", "district", "zcode", "zname", "ztype",
    "gen_zcode", "gen_zname", "changetype", "prj_num",
    "muni_ord", "adpt_date", "prev_zcode", "prev_zname",
]

EXPECTED_FIELDS = {
    "ZRECID", "MUNI_NAME", "DISTRICT", "ZCODE", "ZNAME", "ZTYPE",
    "GEN_ZCODE", "GEN_ZNAME", "CHANGETYPE", "PRJ_NUM", "MUNI_ORD",
    "ADPT_DATE", "PREV_ZCODE", "PREV_ZNAME",
}


@asset(
    group_name="arcgis",
    description=f"{get_county_config().name} zoning districts from ArcGIS REST API → staging.zoning",
    kinds={"postgres", "arcgis"},
)
def zoning_arcgis(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Fetch zoning polygons, archive to S3, SCD2 upsert with geometry."""

    county = get_county_config()
    context.log.info(f"Querying ArcGIS zoning for {county.name}: {county.arcgis_zoning_url}")

    raw_features = query_all_features(
        url=county.arcgis_zoning_url,
        where="1=1",
        out_fields="*",
        out_sr=4326,
        batch_size=2000,
    )
    context.log.info(f"Fetched {len(raw_features)} raw features")

    s3.archive(f"{county.s3_prefix}/arcgis/zoning", raw_features)

    records = parse_zoning_features(raw_features)
    context.log.info(f"Parsed {len(records)} zoning records")

    if not records:
        context.log.warning("No records parsed — skipping upsert")
        return MaterializeResult(metadata={"record_count": MetadataValue.int(0)})

    if len(records) < county.arcgis_zoning_min_records:
        raise RuntimeError(
            f"Only {len(records)} zoning records (expected >= {county.arcgis_zoning_min_records}). "
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
    """SCD2 upsert with PostGIS geometry for staging.zoning."""
    conn = cursor.connection
    was_autocommit = conn.autocommit
    if was_autocommit:
        conn.autocommit = False

    try:
        all_cols = KEY_COLUMNS + VALUE_COLUMNS
        fqn = "staging.zoning"

        cursor.execute("DROP TABLE IF EXISTS _tmp_zoning")
        cursor.execute(f"CREATE TEMP TABLE _tmp_zoning (LIKE {fqn} INCLUDING DEFAULTS)")

        # Build geometry lookup by zrecid
        geom_lookup = {}
        for feat in raw_features:
            attrs = feat.get("attributes", {})
            zrecid = attrs.get("ZRECID")
            geom = feat.get("geometry")
            if zrecid is not None and geom:
                geojson = _arcgis_polygon_to_geojson(geom)
                if geojson:
                    geom_lookup[zrecid] = json.dumps(geojson)

        insert_sql = f"""
            INSERT INTO _tmp_zoning ({', '.join(all_cols)}, geom)
            VALUES ({', '.join(['%s'] * len(all_cols))},
                    CASE WHEN %s IS NOT NULL
                         THEN ST_SetSRID(ST_Multi(ST_GeomFromGeoJSON(%s)), 4326)
                         ELSE NULL END)
        """
        rows = []
        for rec in records:
            row = [rec.get(c) for c in all_cols]
            geom_json = geom_lookup.get(rec["zrecid"])
            row.extend([geom_json, geom_json])
            rows.append(row)
        execute_batch(cursor, insert_sql, rows, page_size=500)

        # Expire changed/deleted
        key_join = "c.zrecid = t.zrecid"
        value_diff = " OR ".join(f"c.{v}::text IS DISTINCT FROM t.{v}::text" for v in VALUE_COLUMNS)
        cursor.execute(f"""
            UPDATE {fqn} c SET valid_to = NOW()
            WHERE c.valid_to IS NULL
            AND (
                EXISTS (SELECT 1 FROM _tmp_zoning t WHERE {key_join} AND ({value_diff}))
                OR NOT EXISTS (SELECT 1 FROM _tmp_zoning t WHERE {key_join})
            )
        """)
        expired = cursor.rowcount

        # Insert new/changed
        col_list = ', '.join(all_cols)
        cursor.execute(f"""
            INSERT INTO {fqn} ({col_list}, geom, valid_from)
            SELECT {', '.join(f't.{c}' for c in all_cols)}, t.geom, NOW()
            FROM _tmp_zoning t
            WHERE NOT EXISTS (
                SELECT 1 FROM {fqn} c WHERE c.valid_to IS NULL AND {key_join}
            )
        """)
        inserted = cursor.rowcount

        cursor.execute("DROP TABLE IF EXISTS _tmp_zoning")
        conn.commit()

        if was_autocommit:
            conn.autocommit = True

        return {"inserted": inserted, "expired": expired, "unchanged": len(records) - inserted}
    except Exception:
        conn.rollback()
        if was_autocommit:
            conn.autocommit = True
        raise


def _arcgis_polygon_to_geojson(geom: dict) -> dict | None:
    """Convert ArcGIS polygon geometry to GeoJSON MultiPolygon."""
    rings = geom.get("rings")
    if not rings:
        return None
    polygons = []
    current_polygon = []
    for ring in rings:
        if not current_polygon:
            current_polygon.append(ring)
        elif _is_clockwise(ring):
            polygons.append(current_polygon)
            current_polygon = [ring]
        else:
            current_polygon.append(ring)
    if current_polygon:
        polygons.append(current_polygon)
    return {"type": "MultiPolygon", "coordinates": polygons}


def _is_clockwise(ring: list[list[float]]) -> bool:
    """Shoelace formula to determine ring orientation."""
    total = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[i + 1][0], ring[i + 1][1]
        total += (x2 - x1) * (y2 + y1)
    return total > 0


@asset_check(asset=zoning_arcgis)
def zoning_record_count_nonzero(database: DatabaseResource) -> AssetCheckResult:
    """Verify staging.zoning has at least one current record."""
    result = database.execute("SELECT COUNT(*) FROM staging.zoning WHERE valid_to IS NULL")
    count = result[0][0] if result else 0
    return AssetCheckResult(
        passed=count > 0,
        severity=AssetCheckSeverity.ERROR,
        metadata={"current_record_count": MetadataValue.int(count)},
    )


@asset_check(asset=zoning_arcgis)
def zoning_schema_drift() -> AssetCheckResult:
    """Verify ArcGIS Zoning layer still has expected fields."""
    county = get_county_config()
    try:
        resp = requests.get(f"{county.arcgis_zoning_url}?f=json", timeout=30)
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
