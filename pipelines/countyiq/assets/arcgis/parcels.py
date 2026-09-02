"""Parcel boundaries from ArcGIS REST API → staging.parcels.

Records: ~176,000 parcels with geometry + 40+ attribute fields
Schedule: Weekly (Sunday 02:00)

Memory-optimized: streams ArcGIS pages directly into the DB temp table
instead of materializing all 176K features in Python memory.
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

from countyiq.lib.arcgis_client import iterate_feature_pages_parallel
from countyiq.lib.checks import make_row_count_check
from countyiq.lib.county_config import county_open_data_source_key, get_county_config
from countyiq.lib.geometry import rings_to_multipolygon_geojson
from countyiq.lib.parsers.arcgis_parcels import parse_parcels_features
from countyiq.lib.source_rights import authorize_source, require_source_use
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

KEY_COLUMNS = ["pidn"]

# Every parsed field is persisted and SCD2-diffed. The deed reference, previous
# owner, mailing address, and land/building value splits are what parcel_events
# derives transfer/value/structure events from — dropping a column here silently
# blinds that derivation (test_parcels_asset_columns guards the mapping).
# Widening this list mass-expires/reinserts all current rows on its first run:
# a one-time SCD2 version bump, not data loss.
VALUE_COLUMNS = [
    "owner_full", "propadr", "aprtotal", "saledt", "price",
    "municipality", "school_dis", "acres", "class", "source_url",
    "district", "block", "map", "parcel", "deed_bk", "deed_pg",
    "own_name1", "own_name2", "mail_addr_full", "prev_owner", "luc",
    "style", "num_stories", "res_living_area", "yrblt", "clean_green",
    "heatsys", "fuel", "aprland", "aprbldg", "prev_price",
    "comm_struc", "comm_year_built", "comm_building_sq_ft", "grade", "cdu",
]

ALL_COLUMNS = KEY_COLUMNS + VALUE_COLUMNS

# Treat a non-null geometry change as an SCD2 change, but preserve the current
# shape when a source response transiently omits geometry.
PARCEL_GEOMETRY_DIFF_SQL = (
    "t.geom IS NOT NULL AND "
    "(c.geom IS NULL OR NOT ST_Equals(c.geom, t.geom))"
)
PARCEL_GEOMETRY_SELECT_SQL = "COALESCE(t.geom, prev.geom)"

# MUNICIPALITY was removed from the live layer (drift detected 2026-08-02 by
# the parcels_schema_drift check on its first registered run). The parser
# tolerates its absence and municipality_join backfills spatially — the SCD2
# diff deliberately ignores source-NULL municipality for exactly this reason.
EXPECTED_FIELDS = {
    "PIDN", "OWNER_FULL", "PROPADR", "APRTOTAL", "SALEDT", "PRICE",
    "SCHOOL_DIS", "ACRES", "CLASS", "DISTRICT", "BLOCK",
    "MAP", "PARCEL", "DEED_BK", "DEED_PG", "OWN_NAME1", "OWN_NAME2",
    "MAIL_ADDR_FULL", "PREV_OWNER", "LUC", "STYLE", "NUM_STORIE",
    "RES_LIVING_AREA", "YRBLT", "APRLAND", "APRBLDG", "PREV_PRICE",
    "CLEAN_GREEN", "HEATSYS", "FUEL", "COMM_STRUC", "COMM_YEAR_BUILT",
    "COMM_BUILDING_SQ_FT", "GRADE", "CDU",
}


@asset(
    group_name="arcgis",
    description=f"{get_county_config().name} parcel boundaries from ArcGIS REST API → staging.parcels",
    kinds={"postgres", "arcgis"},
)
def parcels_arcgis(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Stream parcel pages from ArcGIS directly into DB. Memory-efficient."""
    county = get_county_config()
    authorization = authorize_source(database, source_key=county_open_data_source_key(), acquisition_method="arcgis_rest", asset_key="parcels_arcgis", dagster_run_id=context.run_id)
    require_source_use(authorization, "derived_product")
    require_source_use(authorization, "raw_retention")
    context.log.info(f"Querying ArcGIS parcels for {county.name}: {county.arcgis_parcels_url}")

    cur = database.cursor()
    conn = cur.connection
    was_autocommit = conn.autocommit
    archive_file = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".ndjson",
        prefix="parcels_",
        delete=False,
        encoding="utf-8",
    )
    archive_path = archive_file.name
    if was_autocommit:
        conn.autocommit = False

    try:
        # Create temp table
        cur.execute("DROP TABLE IF EXISTS _tmp_parcels")
        cur.execute("CREATE TEMP TABLE _tmp_parcels (LIKE staging.parcels INCLUDING DEFAULTS)")
        # Geometry batches update staged rows by pidn while pages are still
        # arriving. Build the lookup index before those updates; creating it
        # after the fetch makes each batch scan an ever-growing temp table.
        cur.execute("CREATE INDEX idx_tmp_parcels_pidn ON _tmp_parcels (pidn)")

        # Fetch at most four pages concurrently and release each page after it
        # is staged. The previous all-pages buffer peaked around 1.27 GiB for
        # York parcels before parsing or PostgreSQL work began.
        context.log.info("Streaming parcel pages in parallel (4-page window)...")
        feature_pages = iterate_feature_pages_parallel(
            url=county.arcgis_parcels_url,
            where="1=1",
            out_fields="*",
            out_sr=4326,
            batch_size=2000,
            max_workers=4,
        )

        # Parse and insert each page before requesting the next one.
        total_staged = 0
        insert_sql = f"INSERT INTO _tmp_parcels ({', '.join(ALL_COLUMNS)}) VALUES ({', '.join(['%s'] * len(ALL_COLUMNS))})"
        geom_updates = []

        CHUNK = 5000
        for page_features in feature_pages:
            for feature in page_features:
                archive_file.write(json.dumps(feature, default=str))
                archive_file.write("\n")

            for i in range(0, len(page_features), CHUNK):
                chunk_features = page_features[i:i + CHUNK]
                records = parse_parcels_features(chunk_features)

                rows = []
                for rec in records:
                    rec["source_url"] = county.arcgis_parcels_url
                    row = [rec.get(col) for col in ALL_COLUMNS]
                    rows.append(row)
                execute_batch(cur, insert_sql, rows, page_size=1000)
                total_staged += len(rows)

                for feat in chunk_features:
                    geom = feat.get("geometry")
                    attrs = feat.get("attributes", {})
                    pidn = attrs.get("PIDN")
                    if geom and pidn:
                        geojson = rings_to_multipolygon_geojson(geom.get("rings"))
                        if geojson:
                            geom_updates.append((json.dumps(geojson), pidn))

                if len(geom_updates) >= 5000:
                    _flush_geometries(cur, geom_updates)
                    geom_updates = []

                context.log.info(f"  Staged {total_staged:,} records")

        if geom_updates:
            _flush_geometries(cur, geom_updates)

        context.log.info(f"Total staged: {total_staged:,}")

        # Refresh planner statistics after the full source has been staged.
        cur.execute("ANALYZE _tmp_parcels")
        context.log.info("Temp table analyzed")

        if total_staged == 0:
            cur.execute("DROP TABLE IF EXISTS _tmp_parcels")
            conn.commit()
            context.log.warning("Zero features fetched — aborting to protect existing data")
            return MaterializeResult(metadata={"record_count": MetadataValue.int(0)})

        # ── DATA LOSS GUARD ──────────────────────────────────────────
        # If the fetch returned significantly fewer records than what's
        # already in the table, something went wrong (network error,
        # rate limiting, partial fetch). Abort WITHOUT running SCD2
        # expire — otherwise the "missing" records get wiped.
        cur.execute("SELECT COUNT(*) FROM staging.parcels WHERE valid_to IS NULL")
        existing_count = cur.fetchone()[0]

        if existing_count > 0 and total_staged < existing_count * 0.5:
            cur.execute("DROP TABLE IF EXISTS _tmp_parcels")
            conn.commit()
            msg = (
                f"DATA LOSS GUARD: fetched {total_staged:,} but {existing_count:,} "
                f"exist ({total_staged / existing_count * 100:.0f}% of current). "
                f"Aborting SCD2 to prevent mass expire. Check ArcGIS connectivity."
            )
            context.log.error(msg)
            raise RuntimeError(msg)

        min_records = county.arcgis_parcels_min_records
        if total_staged < min_records:
            cur.execute("DROP TABLE IF EXISTS _tmp_parcels")
            conn.commit()
            msg = (
                f"DATA LOSS GUARD: fetched {total_staged:,} but minimum is "
                f"{min_records:,}. Aborting. Possible truncation or API error."
            )
            context.log.error(msg)
            raise RuntimeError(msg)

        archive_file.flush()
        os.fsync(archive_file.fileno())
        archive_file.close()
        s3.archive_file(
            f"{county.s3_prefix}/arcgis/parcels",
            archive_path,
            filename="response.ndjson",
        )

        context.log.info(
            f"Data loss guard passed: {total_staged:,} staged vs "
            f"{existing_count:,} existing ({total_staged / max(existing_count, 1) * 100:.0f}%)"
        )

        # SCD2 expire + insert (using temp table directly)
        key_join = "c.pidn = t.pidn"
        # municipality is enriched after load by municipality_join (spatial
        # centroid match) because the GIS source often ships it NULL. A NULL
        # source value must not count as a change, or every enriched parcel
        # expires + reinserts on every weekly run and the join is destroyed.
        diff_terms = []
        for v in VALUE_COLUMNS:
            if v == "municipality":
                diff_terms.append(
                    "(t.municipality IS NOT NULL "
                    "AND c.municipality::text IS DISTINCT FROM t.municipality::text)"
                )
            else:
                diff_terms.append(f"c.{v}::text IS DISTINCT FROM t.{v}::text")
        diff_terms.append(PARCEL_GEOMETRY_DIFF_SQL)
        value_diff = " OR ".join(diff_terms)

        # Expire changed/deleted
        cur.execute(f"""
            UPDATE staging.parcels c SET valid_to = NOW()
            WHERE c.valid_to IS NULL
            AND (
                EXISTS (SELECT 1 FROM _tmp_parcels t WHERE {key_join} AND ({value_diff}))
                OR NOT EXISTS (SELECT 1 FROM _tmp_parcels t WHERE {key_join})
            )
        """)
        expired = cur.rowcount
        context.log.info(f"Expired {expired} records")

        # Insert new/changed. Carry the enriched municipality forward from the
        # most recent (possibly just-expired) version when the source is NULL,
        # so a reinsert doesn't lose the spatial-join enrichment until the next
        # weekly municipality_join run.
        col_list = ", ".join([*ALL_COLUMNS, "geom"])
        if existing_count == 0:
            # The first load has no prior enrichment or geometry to preserve.
            # Avoid a pointless lateral lookup for every county parcel.
            select_exprs = [*(f"t.{c}" for c in ALL_COLUMNS), "t.geom"]
            prior_join = ""
        else:
            select_exprs = [
                "COALESCE(t.municipality, prev.municipality)" if c == "municipality" else f"t.{c}"
                for c in ALL_COLUMNS
            ]
            select_exprs.append(PARCEL_GEOMETRY_SELECT_SQL)
            prior_join = """
            LEFT JOIN LATERAL (
                SELECT p_prev.municipality, p_prev.geom
                FROM staging.parcels p_prev
                WHERE p_prev.pidn = t.pidn
                ORDER BY p_prev.valid_from DESC
                LIMIT 1
            ) prev ON TRUE
            """
        cur.execute(f"""
            INSERT INTO staging.parcels ({col_list}, valid_from)
            SELECT {', '.join(select_exprs)}, NOW()
            FROM _tmp_parcels t
            {prior_join}
            WHERE NOT EXISTS (
                SELECT 1 FROM staging.parcels c WHERE c.valid_to IS NULL AND {key_join}
            )
        """)
        inserted = cur.rowcount
        context.log.info(f"Inserted {inserted} records")

        cur.execute("DROP TABLE IF EXISTS _tmp_parcels")
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
            "inserted": MetadataValue.int(inserted),
            "expired": MetadataValue.int(expired),
            "unchanged": MetadataValue.int(total_staged - inserted),
        }
    )


def _flush_geometries(cursor, geom_updates: list[tuple]):
    """Batch-update geometries on temp table rows."""
    update_sql = """
        UPDATE _tmp_parcels
        SET geom = ST_SetSRID(ST_Multi(ST_GeomFromGeoJSON(%s)), 4326)
        WHERE pidn = %s
    """
    execute_batch(cursor, update_sql, geom_updates, page_size=500)


parcels_record_count = make_row_count_check(
    parcels_arcgis,
    table="parcels",
    threshold_fn=lambda: get_county_config().arcgis_parcels_min_records,
    name="parcels_record_count",
)


@asset_check(asset=parcels_arcgis)
def parcels_schema_drift(database: DatabaseResource) -> AssetCheckResult:
    authorize_source(
        database,
        source_key=county_open_data_source_key(),
        acquisition_method="arcgis_rest",
        asset_key="parcels_schema_drift",
    )
    county = get_county_config()
    try:
        resp = requests.get(f"{county.arcgis_parcels_url}?f=json", timeout=30)
        resp.raise_for_status()
        layer_meta = resp.json()
        actual_fields = {f["name"] for f in layer_meta.get("fields", [])}
        missing = EXPECTED_FIELDS - actual_fields
        return AssetCheckResult(
            passed=len(missing) == 0,
            severity=AssetCheckSeverity.WARN,
            metadata={
                "missing_fields": MetadataValue.text(str(missing) if missing else "none"),
                "total_fields": MetadataValue.int(len(actual_fields)),
            },
        )
    except requests.exceptions.RequestException as e:
        return AssetCheckResult(
            passed=False, severity=AssetCheckSeverity.WARN,
            metadata={"error": MetadataValue.text(f"Network error: {e}")},
        )
