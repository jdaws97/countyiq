"""Parcel boundaries from ArcGIS REST API → staging.parcels.

Records: ~176,000 parcels with geometry + 40+ attribute fields
Schedule: Weekly (Monday 02:00)

Memory-optimized: streams ArcGIS pages directly into the DB temp table
instead of materializing all 176K features in Python memory.
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

from countyiq.lib.arcgis_client import fetch_all_features_parallel
from countyiq.lib.checks import make_row_count_check
from countyiq.lib.county_config import get_county_config
from countyiq.lib.geometry import rings_to_multipolygon_geojson
from countyiq.lib.parsers.arcgis_parcels import parse_parcels_features
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

KEY_COLUMNS = ["pidn"]

VALUE_COLUMNS = [
    "owner_full", "propadr", "aprtotal", "saledt", "price",
    "municipality", "school_dis", "acres", "class", "source_url",
]

ALL_COLUMNS = KEY_COLUMNS + VALUE_COLUMNS

EXPECTED_FIELDS = {
    "PIDN", "OWNER_FULL", "PROPADR", "APRTOTAL", "SALEDT", "PRICE",
    "MUNICIPALITY", "SCHOOL_DIS", "ACRES", "CLASS", "DISTRICT", "BLOCK",
    "MAP", "PARCEL", "DEED_BK", "DEED_PG", "OWN_NAME1", "OWN_NAME2",
    "MAIL_ADDR_FULL", "PREV_OWNER", "LUC", "STYLE", "NUM_STORIE",
    "RES_LIVING_AREA", "YRBLT", "APRLAND", "APRBLDG", "PREV_PRICE",
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
    context.log.info(f"Querying ArcGIS parcels for {county.name}: {county.arcgis_parcels_url}")

    cur = database.cursor()
    conn = cur.connection
    was_autocommit = conn.autocommit
    if was_autocommit:
        conn.autocommit = False

    try:
        # Create temp table
        cur.execute("DROP TABLE IF EXISTS _tmp_parcels")
        cur.execute("CREATE TEMP TABLE _tmp_parcels (LIKE staging.parcels INCLUDING DEFAULTS)")

        # Fetch ALL pages in parallel (8 concurrent HTTP requests)
        # ~5-8x faster than sequential for 176K parcels
        context.log.info("Fetching all parcel pages in parallel (4 workers)...")
        all_features = fetch_all_features_parallel(
            url=county.arcgis_parcels_url,
            where="1=1",
            out_fields="*",
            out_sr=4326,
            batch_size=2000,
            max_workers=4,  # 4 workers to avoid ArcGIS rate limiting
        )
        context.log.info(f"Fetched {len(all_features):,} features total")

        # Parse and insert in batches
        total_staged = 0
        insert_sql = f"INSERT INTO _tmp_parcels ({', '.join(ALL_COLUMNS)}) VALUES ({', '.join(['%s'] * len(ALL_COLUMNS))})"
        geom_updates = []

        CHUNK = 5000
        for i in range(0, len(all_features), CHUNK):
            chunk_features = all_features[i:i + CHUNK]
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

        # Index temp table for fast SCD2 expire query
        cur.execute("CREATE INDEX ON _tmp_parcels (pidn)")
        context.log.info("Temp table indexed")

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

        min_records = county.arcgis_parcels_min_records or 150000
        if total_staged < min_records:
            cur.execute("DROP TABLE IF EXISTS _tmp_parcels")
            conn.commit()
            msg = (
                f"DATA LOSS GUARD: fetched {total_staged:,} but minimum is "
                f"{min_records:,}. Aborting. Possible truncation or API error."
            )
            context.log.error(msg)
            raise RuntimeError(msg)

        context.log.info(
            f"Data loss guard passed: {total_staged:,} staged vs "
            f"{existing_count:,} existing ({total_staged / max(existing_count, 1) * 100:.0f}%)"
        )

        # SCD2 expire + insert (using temp table directly)
        key_join = "c.pidn = t.pidn"
        value_diff = " OR ".join(f"c.{v}::text IS DISTINCT FROM t.{v}::text" for v in VALUE_COLUMNS)

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

        # Insert new/changed
        col_list = ", ".join(ALL_COLUMNS)
        cur.execute(f"""
            INSERT INTO staging.parcels ({col_list}, valid_from)
            SELECT {', '.join(f't.{c}' for c in ALL_COLUMNS)}, NOW()
            FROM _tmp_parcels t
            WHERE NOT EXISTS (
                SELECT 1 FROM staging.parcels c WHERE c.valid_to IS NULL AND {key_join}
            )
        """)
        inserted = cur.rowcount
        context.log.info(f"Inserted {inserted} records")

        # Update geometry on newly inserted records
        cur.execute("""
            UPDATE staging.parcels p SET geom = t.geom
            FROM _tmp_parcels t
            WHERE p.pidn = t.pidn AND p.valid_to IS NULL AND p.geom IS NULL AND t.geom IS NOT NULL
        """)
        geom_updated = cur.rowcount
        context.log.info(f"Updated {geom_updated} geometries")

        cur.execute("DROP TABLE IF EXISTS _tmp_parcels")
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


def _flush_geometries(cursor, geom_updates: list[tuple]):
    """Batch-update geometries on temp table rows."""
    update_sql = """
        UPDATE _tmp_parcels
        SET geom = ST_SetSRID(ST_Multi(ST_GeomFromGeoJSON(%s)), 4326)
        WHERE pidn = %s
    """
    execute_batch(cursor, update_sql, geom_updates, page_size=500)


parcels_record_count = make_row_count_check(
    parcels_arcgis, table="parcels", min_count=150001, name="parcels_record_count"
)


@asset_check(asset=parcels_arcgis)
def parcels_schema_drift() -> AssetCheckResult:
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
