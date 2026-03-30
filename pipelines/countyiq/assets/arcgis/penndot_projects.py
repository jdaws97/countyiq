"""PennDOT transportation projects from PA Projects MapServer -> staging.penndot_projects.

Records: ~20-80 points across 4 layers (Underway, Four Year Plan, Under Development, Under Construction)
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
from countyiq.lib.parsers.penndot_projects import parse_penndot_projects_features
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

KEY_COLUMNS = ["project_id"]
VALUE_COLUMNS = [
    "project_name", "description", "status", "project_type",
    "start_date", "end_date", "cost", "municipality", "county", "data",
]

EXPECTED_FIELDS = {
    "PROJ_ID", "PROJECT_TITLE", "IMPROVEMENT_CODE_DESC", "PROJ_STATUS_DESC",
    "PROJ_CLASS", "PHS_EST_COST_AM", "COUNTY_NAME",
}


@asset(
    group_name="arcgis",
    description=f"PennDOT transportation projects for {get_county_config().name} -> staging.penndot_projects",
    kinds={"postgres", "arcgis"},
)
def penndot_projects_arcgis(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Fetch PennDOT projects from multiple MapServer layers, archive to S3, SCD2 upsert with geometry."""

    county = get_county_config()
    context.log.info(
        f"Querying PennDOT projects for {county.name}: {county.penndot_projects_url} "
        f"layers={county.penndot_projects_layers}"
    )

    all_features = []
    for layer_id in county.penndot_projects_layers:
        layer_url = f"{county.penndot_projects_url}/{layer_id}"
        features = query_all_features(
            url=layer_url,
            where=f"COUNTY_NAME='{county.penndot_projects_county_filter}'",
            out_fields="*",
            out_sr=4326,
            batch_size=2000,
        )
        context.log.info(f"Layer {layer_id}: {len(features)} features")
        all_features.extend(features)

    context.log.info(f"Fetched {len(all_features)} total raw features across all layers")

    s3.archive(f"{county.s3_prefix}/penndot/projects", all_features)

    records = parse_penndot_projects_features(all_features)
    context.log.info(f"Parsed {len(records)} project records (deduplicated)")

    if not records:
        context.log.warning("No records parsed — skipping upsert")
        return MaterializeResult(metadata={"record_count": MetadataValue.int(0)})

    if len(records) < county.penndot_projects_min_records:
        raise RuntimeError(
            f"Only {len(records)} project records (expected >= {county.penndot_projects_min_records}). "
            f"Possible truncated response — aborting."
        )

    cur = database.cursor()
    try:
        stats = _geom_scd2_upsert(cur, records, all_features)
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
    """SCD2 upsert with PostGIS geometry for staging.penndot_projects (POINT)."""
    conn = cursor.connection
    was_autocommit = conn.autocommit
    if was_autocommit:
        conn.autocommit = False

    try:
        all_cols = KEY_COLUMNS + VALUE_COLUMNS
        fqn = "staging.penndot_projects"

        cursor.execute("DROP TABLE IF EXISTS _tmp_penndot_projects")
        cursor.execute(f"CREATE TEMP TABLE _tmp_penndot_projects (LIKE {fqn} INCLUDING DEFAULTS)")

        # Build geometry lookup by project_id
        geom_lookup = {}
        for feat in raw_features:
            attrs = feat.get("attributes", {})
            proj_id = attrs.get("PROJ_ID")
            geom = feat.get("geometry")
            if proj_id is not None and geom:
                geojson = _arcgis_point_to_geojson(geom)
                if geojson:
                    geom_lookup[str(proj_id)] = json.dumps(geojson)

        insert_sql = f"""
            INSERT INTO _tmp_penndot_projects ({', '.join(all_cols)}, geom)
            VALUES ({', '.join(['%s' if c != 'data' else '%s::jsonb' for c in all_cols])},
                    CASE WHEN %s IS NOT NULL
                         THEN ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)
                         ELSE NULL END)
        """
        rows = []
        for rec in records:
            row = []
            for c in all_cols:
                if c == "data":
                    row.append(json.dumps(rec.get("data")) if rec.get("data") is not None else None)
                else:
                    row.append(rec.get(c))
            geom_json = geom_lookup.get(rec["project_id"])
            row.extend([geom_json, geom_json])
            rows.append(row)
        execute_batch(cursor, insert_sql, rows, page_size=500)

        # Expire changed/deleted
        key_join = "c.project_id = t.project_id"
        value_diff = " OR ".join(
            f"c.{v}::text IS DISTINCT FROM t.{v}::text" for v in VALUE_COLUMNS
        )
        cursor.execute(f"""
            UPDATE {fqn} c SET valid_to = NOW()
            WHERE c.valid_to IS NULL
            AND (
                EXISTS (SELECT 1 FROM _tmp_penndot_projects t WHERE {key_join} AND ({value_diff}))
                OR NOT EXISTS (SELECT 1 FROM _tmp_penndot_projects t WHERE {key_join})
            )
        """)
        expired = cursor.rowcount

        # Insert new/changed
        col_list = ', '.join(all_cols)
        cursor.execute(f"""
            INSERT INTO {fqn} ({col_list}, geom, valid_from)
            SELECT {', '.join(f't.{c}' for c in all_cols)}, t.geom, NOW()
            FROM _tmp_penndot_projects t
            WHERE NOT EXISTS (
                SELECT 1 FROM {fqn} c WHERE c.valid_to IS NULL AND {key_join}
            )
        """)
        inserted = cursor.rowcount

        cursor.execute("DROP TABLE IF EXISTS _tmp_penndot_projects")
        conn.commit()

        if was_autocommit:
            conn.autocommit = True

        return {"inserted": inserted, "expired": expired, "unchanged": len(records) - inserted}
    except Exception:
        conn.rollback()
        if was_autocommit:
            conn.autocommit = True
        raise


def _arcgis_point_to_geojson(geom: dict) -> dict | None:
    """Convert ArcGIS point geometry to GeoJSON Point."""
    x = geom.get("x")
    y = geom.get("y")
    if x is None or y is None:
        return None
    return {"type": "Point", "coordinates": [x, y]}


@asset_check(asset=penndot_projects_arcgis)
def penndot_projects_record_count_nonzero(database: DatabaseResource) -> AssetCheckResult:
    """Verify staging.penndot_projects has at least one current record."""
    result = database.execute("SELECT COUNT(*) FROM staging.penndot_projects WHERE valid_to IS NULL")
    count = result[0][0] if result else 0
    return AssetCheckResult(
        passed=count > 0,
        severity=AssetCheckSeverity.ERROR,
        metadata={"current_record_count": MetadataValue.int(count)},
    )


@asset_check(asset=penndot_projects_arcgis)
def penndot_projects_schema_drift() -> AssetCheckResult:
    """Verify PennDOT Projects MapServer layer 1 still has expected fields."""
    county = get_county_config()
    try:
        resp = requests.get(f"{county.penndot_projects_url}/1?f=json", timeout=30)
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
