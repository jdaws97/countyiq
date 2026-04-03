"""Conservation easements from ArcGIS REST API -> staging.conservation_easements.

Records: ~960 polygons
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

KEY_COLUMNS = ["pidn"]
VALUE_COLUMNS = [
    "ease_id", "ease_code", "exclusion", "federal", "ease_acres",
    "grantor", "curr_owner", "pres_date", "district", "source_url",
]


@asset(
    group_name="radar",
    description="Conservation easements from ArcGIS -> staging.conservation_easements",
    kinds={"postgres", "arcgis"},
)
def conservation_easements_arcgis(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Fetch conservation easement polygons, archive to S3, SCD2 upsert with geometry."""

    county = get_county_config()
    context.log.info(f"Querying ArcGIS conservation easements for {county.name}: {county.arcgis_conservation_easements_url}")

    raw_features = query_all_features(
        url=county.arcgis_conservation_easements_url,
        where="1=1",
        out_fields="*",
        out_sr=4326,
        batch_size=2000,
    )
    context.log.info(f"Fetched {len(raw_features)} raw features")

    s3.archive(f"{county.s3_prefix}/arcgis/conservation_easements", raw_features)

    records = _parse(raw_features)
    for rec in records:
        rec["source_url"] = county.arcgis_conservation_easements_url
    context.log.info(f"Parsed {len(records)} conservation easement records")

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
        pidn = a.get("PIDN")
        if not pidn:
            continue
        pres_raw = a.get("PRES_DATE")
        records.append({
            "pidn": str(pidn).strip(),
            "ease_id": a.get("EASE_ID"),
            "ease_code": a.get("EASE_CODE"),
            "exclusion": a.get("EXCLUSION"),
            "federal": a.get("FEDERAL"),
            "ease_acres": a.get("EASE_ACRES"),
            "grantor": a.get("GRANTOR"),
            "curr_owner": a.get("CURR_OWNER"),
            "pres_date": datetime.fromtimestamp(pres_raw / 1000, tz=timezone.utc) if pres_raw else None,
            "district": a.get("DISTRICT"),
        })
    return records


def _geom_scd2_upsert(cursor, records: list[dict], raw_features: list[dict]) -> dict:
    """SCD2 upsert with PostGIS geometry for staging.conservation_easements."""
    conn = cursor.connection
    was_autocommit = conn.autocommit
    if was_autocommit:
        conn.autocommit = False

    try:
        all_cols = KEY_COLUMNS + VALUE_COLUMNS
        fqn = "staging.conservation_easements"

        cursor.execute("DROP TABLE IF EXISTS _tmp_conservation_easements")
        cursor.execute(f"CREATE TEMP TABLE _tmp_conservation_easements (LIKE {fqn} INCLUDING DEFAULTS)")

        # Build geometry lookup by pidn
        geom_lookup = {}
        for feat in raw_features:
            attrs = feat.get("attributes", {})
            pidn = attrs.get("PIDN")
            geom = feat.get("geometry")
            if pidn is not None and geom:
                geojson = _arcgis_polygon_to_geojson(geom)
                if geojson:
                    geom_lookup[str(pidn).strip()] = json.dumps(geojson)

        insert_sql = f"""
            INSERT INTO _tmp_conservation_easements ({', '.join(all_cols)}, geom)
            VALUES ({', '.join(['%s'] * len(all_cols))},
                    CASE WHEN %s IS NOT NULL
                         THEN ST_SetSRID(ST_Multi(ST_GeomFromGeoJSON(%s)), 4326)
                         ELSE NULL END)
        """
        rows = []
        for rec in records:
            row = [rec.get(c) for c in all_cols]
            geom_json = geom_lookup.get(rec["pidn"])
            row.extend([geom_json, geom_json])
            rows.append(row)
        execute_batch(cursor, insert_sql, rows, page_size=500)

        # Expire changed/deleted
        key_join = "c.pidn = t.pidn"
        value_diff = " OR ".join(f"c.{v}::text IS DISTINCT FROM t.{v}::text" for v in VALUE_COLUMNS)
        cursor.execute(f"""
            UPDATE {fqn} c SET valid_to = NOW()
            WHERE c.valid_to IS NULL
            AND (
                EXISTS (SELECT 1 FROM _tmp_conservation_easements t WHERE {key_join} AND ({value_diff}))
                OR NOT EXISTS (SELECT 1 FROM _tmp_conservation_easements t WHERE {key_join})
            )
        """)
        expired = cursor.rowcount

        # Insert new/changed
        col_list = ', '.join(all_cols)
        cursor.execute(f"""
            INSERT INTO {fqn} ({col_list}, geom, valid_from)
            SELECT {', '.join(f't.{c}' for c in all_cols)}, t.geom, NOW()
            FROM _tmp_conservation_easements t
            WHERE NOT EXISTS (
                SELECT 1 FROM {fqn} c WHERE c.valid_to IS NULL AND {key_join}
            )
        """)
        inserted = cursor.rowcount

        cursor.execute("DROP TABLE IF EXISTS _tmp_conservation_easements")
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


@asset_check(asset=conservation_easements_arcgis)
def conservation_easements_record_count_nonzero(database: DatabaseResource) -> AssetCheckResult:
    """Verify staging.conservation_easements has at least one current record."""
    result = database.execute("SELECT COUNT(*) FROM staging.conservation_easements WHERE valid_to IS NULL")
    count = result[0][0] if result else 0
    return AssetCheckResult(
        passed=count > 0,
        severity=AssetCheckSeverity.ERROR,
        metadata={"current_record_count": MetadataValue.int(count)},
    )
