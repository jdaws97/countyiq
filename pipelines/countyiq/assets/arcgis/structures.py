"""Building footprints from ArcGIS REST API → staging.structures.

Records: ~213,041 polygons
Schedule: Weekly (Sunday 02:00)

Memory-optimized: streams ArcGIS pages directly into DB temp table.
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
from countyiq.lib.county_config import county_open_data_source_key, get_county_config
from countyiq.lib.geometry import rings_to_multipolygon_geojson
from countyiq.lib.source_rights import authorize_source, require_source_use
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

KEY_COLUMNS = ["objectid"]
VALUE_COLUMNS = ["index_id", "building_type", "source_url"]
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
    authorization = authorize_source(
        database,
        source_key=county_open_data_source_key(),
        acquisition_method="arcgis_rest",
        asset_key="structures_arcgis",
        dagster_run_id=context.run_id,
    )
    require_source_use(authorization, "derived_product")
    require_source_use(authorization, "raw_retention")
    context.log.info(f"Querying ArcGIS structures: {county.arcgis_structures_url}")

    cur = database.cursor()
    conn = cur.connection
    was_autocommit = conn.autocommit
    archive_file = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".ndjson",
        prefix="structures_",
        delete=False,
        encoding="utf-8",
    )
    archive_path = archive_file.name
    if was_autocommit:
        conn.autocommit = False

    try:
        cur.execute("DROP TABLE IF EXISTS _tmp_structures")
        cur.execute(
            "CREATE TEMP TABLE _tmp_structures (LIKE staging.structures INCLUDING DEFAULTS)"
        )

        # Stream pages into temp table with geometry
        total_staged = 0
        raw_feature_count = 0
        insert_sql = f"""
            INSERT INTO _tmp_structures ({", ".join(ALL_COLUMNS)}, geom)
            VALUES ({", ".join(["%s"] * len(ALL_COLUMNS))},
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
                archive_file.write(json.dumps(feat, default=str))
                archive_file.write("\n")
                raw_feature_count += 1
                attrs = feat.get("attributes", {})
                oid = attrs.get("OBJECTID")
                if oid is None:
                    continue

                row = [
                    oid,
                    attrs.get("INDEX_"),
                    attrs.get("BUILDING_TYPE"),
                    county.arcgis_structures_url,
                ]
                geom = feat.get("geometry")
                geom_json = None
                if geom:
                    geojson = rings_to_multipolygon_geojson(geom.get("rings"))
                    if geojson:
                        geom_json = json.dumps(geojson)
                row.extend([geom_json, geom_json])
                batch.append(row)

            execute_batch(cur, insert_sql, batch, page_size=500)
            total_staged += len(batch)
            context.log.info(f"  Staged {total_staged} structures")

        context.log.info(f"Total staged: {total_staged}")

        # Index temp table for fast SCD2 expire query
        cur.execute("CREATE INDEX ON _tmp_structures (objectid)")
        cur.execute("ANALYZE _tmp_structures")
        context.log.info("Temp table indexed")

        if total_staged < county.arcgis_structures_min_records:
            raise RuntimeError(
                f"Only {total_staged} structures (expected >= {county.arcgis_structures_min_records})"
            )

        # ── DATA LOSS GUARD ──────────────────────────────────────────
        # Mirrors the guard in lib/scd.py:scd2_upsert_geom — refuse to
        # expire if the incoming dataset is suspiciously smaller than
        # what's already current. Prevents partial fetches (network
        # errors, rate limits) from wiping existing records.
        cur.execute("SELECT COUNT(*) FROM staging.structures WHERE valid_to IS NULL")
        existing_count = cur.fetchone()[0]
        if existing_count > 100 and total_staged < existing_count * 0.5:
            cur.execute("DROP TABLE IF EXISTS _tmp_structures")
            conn.commit()
            msg = (
                f"DATA LOSS GUARD on staging.structures: incoming {total_staged:,} "
                f"vs {existing_count:,} existing "
                f"({total_staged / existing_count * 100:.0f}%). "
                f"Refusing to expire — likely a partial fetch."
            )
            context.log.error(msg)
            raise RuntimeError(msg)

        archive_file.flush()
        os.fsync(archive_file.fileno())
        archive_file.close()
        s3.archive_file(
            f"{county.s3_prefix}/arcgis/structures",
            archive_path,
            filename="response.ndjson",
        )

        # SCD2 expire + insert
        key_join = "c.objectid = t.objectid"
        value_diff = " OR ".join(
            f"c.{v}::text IS DISTINCT FROM t.{v}::text" for v in VALUE_COLUMNS
        )

        cur.execute(f"""
            UPDATE staging.structures c SET valid_to = NOW()
            WHERE c.valid_to IS NULL
            AND (
                EXISTS (SELECT 1 FROM _tmp_structures t WHERE {key_join} AND ({value_diff}))
                OR NOT EXISTS (SELECT 1 FROM _tmp_structures t WHERE {key_join})
            )
        """)
        expired = cur.rowcount

        col_list = ", ".join(ALL_COLUMNS)
        cur.execute(f"""
            INSERT INTO staging.structures ({col_list}, geom, valid_from)
            SELECT {", ".join(f"t.{c}" for c in ALL_COLUMNS)}, t.geom, NOW()
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
        if not archive_file.closed:
            archive_file.close()
        if os.path.exists(archive_path):
            os.unlink(archive_path)
        if was_autocommit:
            conn.autocommit = True
        cur.close()

    return MaterializeResult(
        metadata={
            "record_count": MetadataValue.int(total_staged),
            "raw_feature_count": MetadataValue.int(raw_feature_count),
            "inserted": MetadataValue.int(inserted),
            "expired": MetadataValue.int(expired),
            "unchanged": MetadataValue.int(total_staged - inserted),
        }
    )


structures_record_count_nonzero = make_row_count_check(
    structures_arcgis, table="structures"
)


@asset_check(asset=structures_arcgis)
def structures_schema_drift(database: DatabaseResource) -> AssetCheckResult:
    authorize_source(
        database,
        source_key=county_open_data_source_key(),
        acquisition_method="arcgis_rest",
        asset_key="structures_schema_drift",
    )
    county = get_county_config()
    try:
        resp = requests.get(f"{county.arcgis_structures_url}?f=json", timeout=30)
        resp.raise_for_status()
        actual_fields = {f["name"] for f in resp.json().get("fields", [])}
        missing = EXPECTED_FIELDS - actual_fields
        return AssetCheckResult(
            passed=len(missing) == 0,
            severity=AssetCheckSeverity.WARN,
            metadata={
                "missing_fields": MetadataValue.text(
                    str(missing) if missing else "none"
                )
            },
        )
    except requests.exceptions.RequestException as e:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.WARN,
            metadata={"error": MetadataValue.text(f"Network error: {e}")},
        )
