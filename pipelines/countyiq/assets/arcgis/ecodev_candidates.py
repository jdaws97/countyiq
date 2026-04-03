"""Economic development candidate parcels from ArcGIS REST API -> staging.ecodev_candidates.

Records: ~70 polygons
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

KEY_COLUMNS = ["pidn"]
VALUE_COLUMNS = [
    "percent_underutilized", "buildable_acres", "functional_class",
    "interchange", "railroad", "primary_grwth_area", "secondary_grwth_area",
    "future_grwth_area", "sewer_water_availability", "broadband",
    "transit_route", "lev_suitability", "ga_type", "owner_full",
    "propadr", "class", "acres", "aprtotal", "yrblt", "comm_building_sq_ft",
    "source_url",
]


@asset(
    group_name="radar",
    description="Economic development candidate parcels from ArcGIS -> staging.ecodev_candidates",
    kinds={"postgres", "arcgis"},
)
def ecodev_candidates_arcgis(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Fetch ecodev candidate polygons, archive to S3, SCD2 upsert with geometry."""

    county = get_county_config()
    context.log.info(f"Querying ArcGIS ecodev candidates for {county.name}: {county.arcgis_ecodev_candidates_url}")

    raw_features = query_all_features(
        url=county.arcgis_ecodev_candidates_url,
        where="1=1",
        out_fields="*",
        out_sr=4326,
        batch_size=2000,
    )
    context.log.info(f"Fetched {len(raw_features)} raw features")

    s3.archive(f"{county.s3_prefix}/arcgis/ecodev_candidates", raw_features)

    records = _parse(raw_features)
    for rec in records:
        rec["source_url"] = county.arcgis_ecodev_candidates_url
    context.log.info(f"Parsed {len(records)} ecodev candidate records")

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
        records.append({
            "pidn": str(pidn).strip(),
            "percent_underutilized": a.get("Percent_Underutilized"),
            "buildable_acres": a.get("Buildable_Acres"),
            "functional_class": a.get("Functional_Class"),
            "interchange": a.get("Interchange"),
            "railroad": a.get("Railroad"),
            "primary_grwth_area": a.get("Primary_Grwth_Area"),
            "secondary_grwth_area": a.get("Secondary_Grwth_Area"),
            "future_grwth_area": a.get("Future_Grwth_Area"),
            "sewer_water_availability": a.get("Sewer_Water_Availability"),
            "broadband": a.get("Broadband"),
            "transit_route": a.get("Transit_Route"),
            "lev_suitability": a.get("LEV_Suitability"),
            "ga_type": a.get("GA_Type"),
            "owner_full": a.get("OWNER_FULL"),
            "propadr": a.get("PROPADR"),
            "class": a.get("CLASS"),
            "acres": a.get("ACRES"),
            "aprtotal": a.get("APRTOTAL"),
            "yrblt": a.get("YRBLT"),
            "comm_building_sq_ft": a.get("Comm_Building_Sq_Ft"),
        })
    return records


def _geom_scd2_upsert(cursor, records: list[dict], raw_features: list[dict]) -> dict:
    """SCD2 upsert with PostGIS geometry for staging.ecodev_candidates."""
    conn = cursor.connection
    was_autocommit = conn.autocommit
    if was_autocommit:
        conn.autocommit = False

    try:
        all_cols = KEY_COLUMNS + VALUE_COLUMNS
        fqn = "staging.ecodev_candidates"

        cursor.execute("DROP TABLE IF EXISTS _tmp_ecodev_candidates")
        cursor.execute(f"CREATE TEMP TABLE _tmp_ecodev_candidates (LIKE {fqn} INCLUDING DEFAULTS)")

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
            INSERT INTO _tmp_ecodev_candidates ({', '.join(all_cols)}, geom)
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
                EXISTS (SELECT 1 FROM _tmp_ecodev_candidates t WHERE {key_join} AND ({value_diff}))
                OR NOT EXISTS (SELECT 1 FROM _tmp_ecodev_candidates t WHERE {key_join})
            )
        """)
        expired = cursor.rowcount

        # Insert new/changed
        col_list = ', '.join(all_cols)
        cursor.execute(f"""
            INSERT INTO {fqn} ({col_list}, geom, valid_from)
            SELECT {', '.join(f't.{c}' for c in all_cols)}, t.geom, NOW()
            FROM _tmp_ecodev_candidates t
            WHERE NOT EXISTS (
                SELECT 1 FROM {fqn} c WHERE c.valid_to IS NULL AND {key_join}
            )
        """)
        inserted = cursor.rowcount

        cursor.execute("DROP TABLE IF EXISTS _tmp_ecodev_candidates")
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


@asset_check(asset=ecodev_candidates_arcgis)
def ecodev_candidates_record_count_nonzero(database: DatabaseResource) -> AssetCheckResult:
    """Verify staging.ecodev_candidates has at least one current record."""
    result = database.execute("SELECT COUNT(*) FROM staging.ecodev_candidates WHERE valid_to IS NULL")
    count = result[0][0] if result else 0
    return AssetCheckResult(
        passed=count > 0,
        severity=AssetCheckSeverity.ERROR,
        metadata={"current_record_count": MetadataValue.int(count)},
    )
