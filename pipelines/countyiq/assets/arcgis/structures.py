"""Building footprints from ArcGIS REST API → staging.structures.

Records: ~213,041 polygons
Schedule: Weekly (Sunday 02:00)

Memory-optimized: streams ArcGIS pages directly into DB temp table.
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

from countyiq.lib.arcgis_client import iterate_feature_pages
from countyiq.lib.county_config import get_county_config
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

KEY_COLUMNS = ["objectid"]
VALUE_COLUMNS = ["index_id", "building_type"]
ALL_COLUMNS = KEY_COLUMNS + VALUE_COLUMNS

EXPECTED_FIELDS = {"OBJECTID", "INDEX_", "BUILDING_TYPE"}
OUT_FIELDS = "OBJECTID,INDEX_,BUILDING_TYPE"


@asset(
    group_name="arcgis",
    description=f"{get_county_config().name} building footprints → staging.structures",
    kinds={"postgres", "arcgis"},
)
def structures_arcgis(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Stream building footprints page-by-page into DB. Memory-efficient."""
    county = get_county_config()
    context.log.info(f"Querying ArcGIS structures: {county.arcgis_structures_url}")

    cur = database.cursor()
    conn = cur.connection
    was_autocommit = conn.autocommit
    if was_autocommit:
        conn.autocommit = False

    try:
        cur.execute("DROP TABLE IF EXISTS _tmp_structures")
        cur.execute("CREATE TEMP TABLE _tmp_structures (LIKE staging.structures INCLUDING DEFAULTS)")

        # Stream pages into temp table with geometry
        total_staged = 0
        insert_sql = f"""
            INSERT INTO _tmp_structures ({', '.join(ALL_COLUMNS)}, geom)
            VALUES ({', '.join(['%s'] * len(ALL_COLUMNS))},
                    CASE WHEN %s IS NOT NULL
                         THEN ST_SetSRID(ST_Multi(ST_GeomFromGeoJSON(%s)), 4326)
                         ELSE NULL END)
        """

        for page_features in iterate_feature_pages(
            url=county.arcgis_structures_url,
            where="1=1",
            out_fields=OUT_FIELDS,
            out_sr=4326,
            batch_size=2000,
        ):
            batch = []
            for feat in page_features:
                attrs = feat.get("attributes", {})
                oid = attrs.get("OBJECTID")
                if oid is None:
                    continue

                row = [
                    oid,
                    attrs.get("INDEX_"),
                    attrs.get("BUILDING_TYPE"),
                ]
                geom = feat.get("geometry")
                geom_json = None
                if geom and geom.get("rings"):
                    geom_json = json.dumps(_arcgis_rings_to_geojson(geom["rings"]))
                row.extend([geom_json, geom_json])
                batch.append(row)

            execute_batch(cur, insert_sql, batch, page_size=500)
            total_staged += len(batch)
            context.log.info(f"  Staged {total_staged} structures")

        context.log.info(f"Total staged: {total_staged}")

        if total_staged < county.arcgis_structures_min_records:
            raise RuntimeError(f"Only {total_staged} structures (expected >= {county.arcgis_structures_min_records})")

        # SCD2 expire + insert
        key_join = "c.objectid = t.objectid"
        value_diff = " OR ".join(f"c.{v}::text IS DISTINCT FROM t.{v}::text" for v in VALUE_COLUMNS)

        cur.execute(f"""
            UPDATE staging.structures c SET valid_to = NOW()
            WHERE c.valid_to IS NULL
            AND (
                EXISTS (SELECT 1 FROM _tmp_structures t WHERE {key_join} AND ({value_diff}))
                OR NOT EXISTS (SELECT 1 FROM _tmp_structures t WHERE {key_join})
            )
        """)
        expired = cur.rowcount

        col_list = ', '.join(ALL_COLUMNS)
        cur.execute(f"""
            INSERT INTO staging.structures ({col_list}, geom, valid_from)
            SELECT {', '.join(f't.{c}' for c in ALL_COLUMNS)}, t.geom, NOW()
            FROM _tmp_structures t
            WHERE NOT EXISTS (
                SELECT 1 FROM staging.structures c WHERE c.valid_to IS NULL AND {key_join}
            )
        """)
        inserted = cur.rowcount

        cur.execute("DROP TABLE IF EXISTS _tmp_structures")
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
            "record_count": MetadataValue.int(total_staged),
            "inserted": MetadataValue.int(inserted),
            "expired": MetadataValue.int(expired),
            "unchanged": MetadataValue.int(total_staged - inserted),
        }
    )


def _arcgis_rings_to_geojson(rings: list) -> dict:
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
    total = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[i + 1][0], ring[i + 1][1]
        total += (x2 - x1) * (y2 + y1)
    return total > 0


@asset_check(asset=structures_arcgis)
def structures_record_count_nonzero(database: DatabaseResource) -> AssetCheckResult:
    result = database.execute("SELECT COUNT(*) FROM staging.structures WHERE valid_to IS NULL")
    count = result[0][0] if result else 0
    return AssetCheckResult(passed=count > 0, severity=AssetCheckSeverity.ERROR,
                            metadata={"current_record_count": MetadataValue.int(count)})


@asset_check(asset=structures_arcgis)
def structures_schema_drift() -> AssetCheckResult:
    county = get_county_config()
    try:
        resp = requests.get(f"{county.arcgis_structures_url}?f=json", timeout=30)
        resp.raise_for_status()
        actual_fields = {f["name"] for f in resp.json().get("fields", [])}
        missing = EXPECTED_FIELDS - actual_fields
        return AssetCheckResult(passed=len(missing) == 0, severity=AssetCheckSeverity.WARN,
                                metadata={"missing_fields": MetadataValue.text(str(missing) if missing else "none")})
    except requests.exceptions.RequestException as e:
        return AssetCheckResult(passed=False, severity=AssetCheckSeverity.WARN,
                                metadata={"error": MetadataValue.text(f"Network error: {e}")})
