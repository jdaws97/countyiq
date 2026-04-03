"""CDBG housing development locations from ArcGIS REST API -> staging.cdbg_housing.

Records: ~63 points
Schedule: Weekly (Sunday 02:00)
"""

import json

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

KEY_COLUMNS = ["housingdevid"]
VALUE_COLUMNS = [
    "prj_id", "address", "constructi", "units",
    "date_of_oc", "affordabil", "name", "source_url",
]


@asset(
    group_name="radar",
    description="CDBG housing development locations from ArcGIS -> staging.cdbg_housing",
    kinds={"postgres", "arcgis"},
)
def cdbg_housing_arcgis(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Fetch CDBG housing points, archive to S3, SCD2 upsert with geometry."""

    county = get_county_config()
    context.log.info(f"Querying ArcGIS CDBG housing for {county.name}: {county.arcgis_cdbg_housing_url}")

    raw_features = query_all_features(
        url=county.arcgis_cdbg_housing_url,
        where="1=1",
        out_fields="*",
        out_sr=4326,
        batch_size=2000,
    )
    context.log.info(f"Fetched {len(raw_features)} raw features")

    s3.archive(f"{county.s3_prefix}/arcgis/cdbg_housing", raw_features)

    records = _parse(raw_features)
    for rec in records:
        rec["source_url"] = county.arcgis_cdbg_housing_url
    context.log.info(f"Parsed {len(records)} CDBG housing records")

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
        housingdevid = a.get("HousingDevID")
        if not housingdevid:
            continue
        records.append({
            "housingdevid": str(housingdevid).strip(),
            "prj_id": a.get("PRJ_ID"),
            "address": a.get("Address"),
            "constructi": a.get("Constructi"),
            "units": a.get("Units"),
            "date_of_oc": a.get("Date_of_OC"),
            "affordabil": a.get("Affordabil"),
            "name": a.get("Name"),
        })
    return records


def _geom_scd2_upsert(cursor, records: list[dict], raw_features: list[dict]) -> dict:
    """SCD2 upsert with PostGIS point geometry for staging.cdbg_housing."""
    conn = cursor.connection
    was_autocommit = conn.autocommit
    if was_autocommit:
        conn.autocommit = False

    try:
        all_cols = KEY_COLUMNS + VALUE_COLUMNS
        fqn = "staging.cdbg_housing"

        cursor.execute("DROP TABLE IF EXISTS _tmp_cdbg_housing")
        cursor.execute(f"CREATE TEMP TABLE _tmp_cdbg_housing (LIKE {fqn} INCLUDING DEFAULTS)")

        # Build geometry lookup by housingdevid
        geom_lookup = {}
        for feat in raw_features:
            attrs = feat.get("attributes", {})
            housingdevid = attrs.get("HousingDevID")
            geom = feat.get("geometry")
            if housingdevid is not None and geom:
                geojson = _arcgis_point_to_geojson(geom)
                if geojson:
                    geom_lookup[str(housingdevid).strip()] = json.dumps(geojson)

        insert_sql = f"""
            INSERT INTO _tmp_cdbg_housing ({', '.join(all_cols)}, geom)
            VALUES ({', '.join(['%s'] * len(all_cols))},
                    CASE WHEN %s IS NOT NULL
                         THEN ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)
                         ELSE NULL END)
        """
        rows = []
        for rec in records:
            row = [rec.get(c) for c in all_cols]
            geom_json = geom_lookup.get(rec["housingdevid"])
            row.extend([geom_json, geom_json])
            rows.append(row)
        execute_batch(cursor, insert_sql, rows, page_size=500)

        # Expire changed/deleted
        key_join = "c.housingdevid = t.housingdevid"
        value_diff = " OR ".join(f"c.{v}::text IS DISTINCT FROM t.{v}::text" for v in VALUE_COLUMNS)
        cursor.execute(f"""
            UPDATE {fqn} c SET valid_to = NOW()
            WHERE c.valid_to IS NULL
            AND (
                EXISTS (SELECT 1 FROM _tmp_cdbg_housing t WHERE {key_join} AND ({value_diff}))
                OR NOT EXISTS (SELECT 1 FROM _tmp_cdbg_housing t WHERE {key_join})
            )
        """)
        expired = cursor.rowcount

        # Insert new/changed
        col_list = ', '.join(all_cols)
        cursor.execute(f"""
            INSERT INTO {fqn} ({col_list}, geom, valid_from)
            SELECT {', '.join(f't.{c}' for c in all_cols)}, t.geom, NOW()
            FROM _tmp_cdbg_housing t
            WHERE NOT EXISTS (
                SELECT 1 FROM {fqn} c WHERE c.valid_to IS NULL AND {key_join}
            )
        """)
        inserted = cursor.rowcount

        cursor.execute("DROP TABLE IF EXISTS _tmp_cdbg_housing")
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
    if geom and geom.get("x") is not None:
        return {"type": "Point", "coordinates": [geom["x"], geom["y"]]}
    return None


@asset_check(asset=cdbg_housing_arcgis)
def cdbg_housing_record_count_nonzero(database: DatabaseResource) -> AssetCheckResult:
    """Verify staging.cdbg_housing has at least one current record."""
    result = database.execute("SELECT COUNT(*) FROM staging.cdbg_housing WHERE valid_to IS NULL")
    count = result[0][0] if result else 0
    return AssetCheckResult(
        passed=count > 0,
        severity=AssetCheckSeverity.ERROR,
        metadata={"current_record_count": MetadataValue.int(count)},
    )
