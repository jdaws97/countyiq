"""FEMA NFHL flood hazard zones → staging.flood_zones.

Source: FEMA National Flood Hazard Layer (NFHL) MapServer
Layer 28: S_Fld_Haz_Ar (Flood Hazard Zones)
Records: ~5,238 polygons for York County (DFIRM_ID=42133C)
Schedule: Weekly (Sunday 04:00)
"""

import json
import time

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

from countyiq.lib.county_config import get_county_config
from countyiq.lib.parsers.fema import parse_fema_geojson
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

PAGE_SIZE = 1000  # FEMA MapServer returns 500 at 2000 with geometry; 1000 is reliable
REQUEST_TIMEOUT = 120
MAX_RETRIES = 3
RETRY_BACKOFF = 5  # seconds, multiplied by attempt number

# Only request the fields we need (reduces server load vs outFields=*)
OUT_FIELDS = ",".join([
    "DFIRM_ID", "FLD_AR_ID", "FLD_ZONE", "ZONE_SUBTY", "SFHA_TF",
    "STATIC_BFE", "V_DATUM", "DEPTH", "STUDY_TYP", "SOURCE_CIT",
])

KEY_COLUMNS = ["fld_ar_id"]
VALUE_COLUMNS = [
    "dfirm_id",
    "fld_zone",
    "zone_subty",
    "sfha_tf",
    "static_bfe",
    "v_datum",
    "depth",
    "study_typ",
    "source_cit",
]

# Expected fields from FEMA MapServer layer metadata (for schema drift check)
EXPECTED_FIELDS = {
    "DFIRM_ID", "FLD_AR_ID", "FLD_ZONE", "ZONE_SUBTY", "SFHA_TF",
    "STATIC_BFE", "V_DATUM", "DEPTH", "STUDY_TYP", "SOURCE_CIT",
}


def _fetch_page(url: str, attempt: int = 1) -> dict:
    """Fetch a single page with retry on 5xx errors."""
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        if attempt < MAX_RETRIES and e.response is not None and e.response.status_code >= 500:
            wait = RETRY_BACKOFF * attempt
            time.sleep(wait)
            return _fetch_page(url, attempt + 1)
        raise


def _fetch_all_pages(base_url: str, layer_id: int, dfirm_id: str, context) -> dict:
    """Paginate through FEMA MapServer and return merged ArcGIS JSON features.

    Uses f=json (not f=geojson) because FEMA's GeoJSON endpoint returns 500
    errors at higher offsets with geometry. The parser handles both formats.
    """
    all_features = []
    offset = 0
    while True:
        url = (
            f"{base_url}/{layer_id}/query"
            f"?where=DFIRM_ID%3D%27{dfirm_id}%27"
            f"&outFields={OUT_FIELDS}"
            f"&outSR=4326"
            f"&resultRecordCount={PAGE_SIZE}"
            f"&resultOffset={offset}"
            f"&f=json"
        )
        context.log.info(f"Fetching page at offset {offset}")
        page = _fetch_page(url)
        features = page.get("features", [])
        all_features.extend(features)
        context.log.info(f"  Got {len(features)} features (total: {len(all_features)})")

        if not page.get("exceededTransferLimit"):
            break
        offset += PAGE_SIZE

    return {"type": "FeatureCollection", "features": all_features}


@asset(
    group_name="bulk",
    description="FEMA NFHL flood hazard zones → staging.flood_zones",
    kinds={"postgres", "geojson"},
)
def fema_flood_zones(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Fetch FEMA flood zone polygons, parse, and SCD2 upsert."""

    county = get_county_config()

    # 1. Fetch all pages from FEMA MapServer
    geojson = _fetch_all_pages(
        county.fema_nfhl_url,
        county.fema_flood_layer,
        county.fema_dfirm_id,
        context,
    )
    context.log.info(f"Total features fetched: {len(geojson['features'])}")

    # 2. Archive raw GeoJSON to S3
    s3.archive(
        f"{county.s3_prefix}/bulk/fema_flood",
        geojson,
        filename="flood_zones.geojson",
    )

    # 3. Parse features
    records = parse_fema_geojson(geojson)
    context.log.info(f"Parsed {len(records)} flood zone records")

    if not records:
        context.log.warning("No flood zone records parsed — skipping upsert")
        return MaterializeResult(metadata={"record_count": MetadataValue.int(0)})

    # 3b. Truncation guard
    if len(records) < county.fema_min_records:
        raise RuntimeError(
            f"Only {len(records)} flood zone records parsed "
            f"(expected >= {county.fema_min_records}). "
            f"Possible truncated response — aborting."
        )

    # 4. Upsert with PostGIS geometry handling (scoped to this county's DFIRM)
    cur = database.cursor()
    try:
        stats = _geom_scd2_upsert(cur, records, dfirm_id=county.fema_dfirm_id)
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


def _geom_scd2_upsert(cursor, records: list[dict], dfirm_id: str) -> dict:
    """SCD2 upsert with PostGIS geometry support, scoped by DFIRM ID.

    Uses the same expire/insert pattern as lib/scd.py but handles
    geometry via ST_SetSRID(ST_Multi(ST_GeomFromGeoJSON()), 4326).
    Uses execute_batch for performance with 5K+ geometry rows.

    The expire query is scoped to dfirm_id so that running for one county
    does not expire another county's records in the same table.
    """
    conn = cursor.connection
    was_autocommit = conn.autocommit
    if was_autocommit:
        conn.autocommit = False

    try:
        all_cols = KEY_COLUMNS + VALUE_COLUMNS
        fqn = "staging.flood_zones"

        # Create temp table
        cursor.execute("DROP TABLE IF EXISTS _tmp_flood_zones")
        cursor.execute(f"CREATE TEMP TABLE _tmp_flood_zones (LIKE {fqn} INCLUDING DEFAULTS)")

        # Bulk insert into temp table with geometry — execute_batch for performance
        insert_sql = f"""
            INSERT INTO _tmp_flood_zones ({', '.join(all_cols)}, geom)
            VALUES ({', '.join(['%s'] * len(all_cols))},
                    ST_SetSRID(ST_Multi(ST_GeomFromGeoJSON(%s)), 4326))
        """
        rows = []
        for rec in records:
            row = [rec.get(c) for c in all_cols]
            geom = rec.get("geojson")
            row.append(json.dumps(geom) if geom else None)
            rows.append(row)
        execute_batch(cursor, insert_sql, rows, page_size=500)

        # Expire changed/deleted — scoped to this county's DFIRM ID
        key_join = "c.fld_ar_id = t.fld_ar_id"
        value_diff = " OR ".join(
            f"c.{v}::text IS DISTINCT FROM t.{v}::text" for v in VALUE_COLUMNS
        )
        cursor.execute(f"""
            UPDATE {fqn} c SET valid_to = NOW()
            WHERE c.valid_to IS NULL
            AND c.dfirm_id = %s
            AND (
                EXISTS (
                    SELECT 1 FROM _tmp_flood_zones t
                    WHERE {key_join} AND ({value_diff})
                )
                OR NOT EXISTS (
                    SELECT 1 FROM _tmp_flood_zones t WHERE {key_join}
                )
            )
        """, (dfirm_id,))
        expired = cursor.rowcount

        # Insert new/changed
        col_list = ', '.join(all_cols)
        cursor.execute(f"""
            INSERT INTO {fqn} ({col_list}, geom, valid_from)
            SELECT {', '.join(f't.{c}' for c in all_cols)}, t.geom, NOW()
            FROM _tmp_flood_zones t
            WHERE NOT EXISTS (
                SELECT 1 FROM {fqn} c
                WHERE c.valid_to IS NULL AND {key_join}
            )
        """)
        inserted = cursor.rowcount

        cursor.execute("DROP TABLE IF EXISTS _tmp_flood_zones")
        conn.commit()

        if was_autocommit:
            conn.autocommit = True

        unchanged = len(records) - inserted
        return {"inserted": inserted, "expired": expired, "unchanged": unchanged}
    except Exception:
        conn.rollback()
        if was_autocommit:
            conn.autocommit = True
        raise


@asset_check(asset=fema_flood_zones)
def fema_record_count_nonzero(database: DatabaseResource) -> AssetCheckResult:
    """Verify staging.flood_zones has at least one current record."""
    result = database.execute(
        "SELECT COUNT(*) FROM staging.flood_zones WHERE valid_to IS NULL"
    )
    count = result[0][0] if result else 0
    return AssetCheckResult(
        passed=count > 0,
        severity=AssetCheckSeverity.ERROR,
        metadata={"current_record_count": MetadataValue.int(count)},
    )


@asset_check(asset=fema_flood_zones)
def fema_schema_drift() -> AssetCheckResult:
    """Verify FEMA MapServer still has the expected fields."""
    county = get_county_config()
    try:
        url = f"{county.fema_nfhl_url}/{county.fema_flood_layer}?f=json"
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        layer_meta = resp.json()
        actual_fields = {f["name"] for f in layer_meta.get("fields", [])}
        missing = EXPECTED_FIELDS - actual_fields
        extra = actual_fields - EXPECTED_FIELDS
        return AssetCheckResult(
            passed=len(missing) == 0,
            severity=AssetCheckSeverity.WARN,
            metadata={
                "missing_fields": MetadataValue.text(str(missing) if missing else "none"),
                "extra_fields": MetadataValue.text(str(extra) if extra else "none"),
            },
        )
    except requests.exceptions.RequestException as e:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.WARN,
            metadata={"error": MetadataValue.text(f"Network error: {e}")},
        )
