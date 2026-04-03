"""Future land use designations from ArcGIS REST API -> staging.future_landuse.

Records: ~1,659 polygons
Schedule: Weekly (Sunday 02:00)
"""

import json
from datetime import datetime, timezone

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
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

KEY_COLUMNS = ["globalid"]
VALUE_COLUMNS = ["district", "future_lu", "general_lu", "adopt_date", "source_url"]


@asset(
    group_name="radar",
    description="Future land use designations from ArcGIS -> staging.future_landuse",
    kinds={"postgres", "arcgis"},
)
def future_landuse_arcgis(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Fetch future land use polygons, archive to S3, SCD2 upsert with geometry."""

    county = get_county_config()
    context.log.info(f"Querying ArcGIS future land use for {county.name}: {county.arcgis_future_landuse_url}")

    raw_features = query_all_features(
        url=county.arcgis_future_landuse_url,
        where="1=1",
        out_fields="*",
        out_sr=4326,
        batch_size=2000,
    )
    context.log.info(f"Fetched {len(raw_features)} raw features")

    s3.archive(f"{county.s3_prefix}/arcgis/future_landuse", raw_features)

    records = _parse(raw_features)
    for rec in records:
        rec["source_url"] = county.arcgis_future_landuse_url
    context.log.info(f"Parsed {len(records)} future land use records")

    if not records:
        context.log.warning("No records parsed -- skipping upsert")
        return MaterializeResult(metadata={"record_count": MetadataValue.int(0)})

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


def _parse(raw_features: list[dict]) -> list[dict]:
    """Parse ArcGIS attributes into staging column names."""
    records = []
    for feat in raw_features:
        a = feat.get("attributes", {})
        globalid = a.get("GlobalID")
        if not globalid:
            continue
        adopt_raw = a.get("ADOPT_DATE")
        records.append({
            "globalid": str(globalid).strip(),
            "district": a.get("DISTRICT"),
            "future_lu": a.get("FUTURE_LU"),
            "general_lu": a.get("GENERAL_LU"),
            "adopt_date": datetime.fromtimestamp(adopt_raw / 1000, tz=timezone.utc) if adopt_raw else None,
        })
    return records


def _geom_scd2_upsert(cursor, records: list[dict], raw_features: list[dict]) -> dict:
    """SCD2 upsert with PostGIS geometry for staging.future_landuse."""
    conn = cursor.connection
    was_autocommit = conn.autocommit
    if was_autocommit:
        conn.autocommit = False

    try:
        all_cols = KEY_COLUMNS + VALUE_COLUMNS
        fqn = "staging.future_landuse"

        cursor.execute("DROP TABLE IF EXISTS _tmp_future_landuse")
        cursor.execute(f"CREATE TEMP TABLE _tmp_future_landuse (LIKE {fqn} INCLUDING DEFAULTS)")

        # Build geometry lookup by globalid
        geom_lookup = {}
        for feat in raw_features:
            attrs = feat.get("attributes", {})
            globalid = attrs.get("GlobalID")
            geom = feat.get("geometry")
            if globalid is not None and geom:
                geojson = _arcgis_polygon_to_geojson(geom)
                if geojson:
                    geom_lookup[str(globalid).strip()] = json.dumps(geojson)

        insert_sql = f"""
            INSERT INTO _tmp_future_landuse ({', '.join(all_cols)}, geom)
            VALUES ({', '.join(['%s'] * len(all_cols))},
                    CASE WHEN %s IS NOT NULL
                         THEN ST_SetSRID(ST_Multi(ST_GeomFromGeoJSON(%s)), 4326)
                         ELSE NULL END)
        """
        rows = []
        for rec in records:
            row = [rec.get(c) for c in all_cols]
            geom_json = geom_lookup.get(rec["globalid"])
            row.extend([geom_json, geom_json])
            rows.append(row)
        execute_batch(cursor, insert_sql, rows, page_size=500)

        # Expire changed/deleted
        key_join = "c.globalid = t.globalid"
        value_diff = " OR ".join(f"c.{v}::text IS DISTINCT FROM t.{v}::text" for v in VALUE_COLUMNS)
        cursor.execute(f"""
            UPDATE {fqn} c SET valid_to = NOW()
            WHERE c.valid_to IS NULL
            AND (
                EXISTS (SELECT 1 FROM _tmp_future_landuse t WHERE {key_join} AND ({value_diff}))
                OR NOT EXISTS (SELECT 1 FROM _tmp_future_landuse t WHERE {key_join})
            )
        """)
        expired = cursor.rowcount

        # Insert new/changed
        col_list = ', '.join(all_cols)
        cursor.execute(f"""
            INSERT INTO {fqn} ({col_list}, geom, valid_from)
            SELECT {', '.join(f't.{c}' for c in all_cols)}, t.geom, NOW()
            FROM _tmp_future_landuse t
            WHERE NOT EXISTS (
                SELECT 1 FROM {fqn} c WHERE c.valid_to IS NULL AND {key_join}
            )
        """)
        inserted = cursor.rowcount

        cursor.execute("DROP TABLE IF EXISTS _tmp_future_landuse")
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
        elif sum((ring[i+1][0]-ring[i][0])*(ring[i+1][1]+ring[i][1]) for i in range(len(ring)-1)) > 0:
            polygons.append(current_polygon)
            current_polygon = [ring]
        else:
            current_polygon.append(ring)
    if current_polygon:
        polygons.append(current_polygon)
    return {"type": "MultiPolygon", "coordinates": polygons}


@asset_check(asset=future_landuse_arcgis)
def future_landuse_record_count_nonzero(database: DatabaseResource) -> AssetCheckResult:
    """Verify staging.future_landuse has at least one current record."""
    result = database.execute("SELECT COUNT(*) FROM staging.future_landuse WHERE valid_to IS NULL")
    count = result[0][0] if result else 0
    return AssetCheckResult(
        passed=count > 0,
        severity=AssetCheckSeverity.ERROR,
        metadata={"current_record_count": MetadataValue.int(count)},
    )
