"""FEMA NFHL flood hazard zones → staging.flood_zones.

Source: FEMA National Flood Hazard Layer (NFHL) MapServer
Layer 28: S_Fld_Haz_Ar (Flood Hazard Zones)
Records: ~5,238 polygons for York County (DFIRM_ID=42133C)
Schedule: Weekly (Sunday 04:00)
"""

import json
import time

import requests
from dagster import (
    asset,
    asset_check,
    AssetCheckResult,
    AssetCheckSeverity,
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
)

from countyiq.lib.checks import make_row_count_check
from countyiq.lib.county_config import get_county_config
from countyiq.lib.parsers.fema import parse_fema_geojson
from countyiq.lib.scd import scd2_upsert_geom
from countyiq.lib.source_rights import authorize_source, require_source_use
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

PAGE_SIZE = 1000  # FEMA MapServer returns 500 at 2000 with geometry; 1000 is reliable
REQUEST_TIMEOUT = 120
MAX_RETRIES = 3
RETRY_BACKOFF = 5  # seconds, multiplied by attempt number

# Only request the fields we need (reduces server load vs outFields=*)
OUT_FIELDS = ",".join(
    [
        "DFIRM_ID",
        "FLD_AR_ID",
        "FLD_ZONE",
        "ZONE_SUBTY",
        "SFHA_TF",
        "STATIC_BFE",
        "V_DATUM",
        "DEPTH",
        "STUDY_TYP",
        "SOURCE_CIT",
    ]
)

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
    "source_url",
]

# Expected fields from FEMA MapServer layer metadata (for schema drift check)
EXPECTED_FIELDS = {
    "DFIRM_ID",
    "FLD_AR_ID",
    "FLD_ZONE",
    "ZONE_SUBTY",
    "SFHA_TF",
    "STATIC_BFE",
    "V_DATUM",
    "DEPTH",
    "STUDY_TYP",
    "SOURCE_CIT",
}


def _fetch_page(url: str, attempt: int = 1) -> dict:
    """Fetch one page with bounded retries for transient provider failures."""
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        status_code = e.response.status_code if e.response is not None else None
        retryable = not isinstance(e, requests.exceptions.HTTPError) or (
            status_code in {408, 429}
            or (status_code is not None and status_code >= 500)
        )
        if attempt < MAX_RETRIES and retryable:
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

        # Some ArcGIS services incorrectly retain exceededTransferLimit=true
        # after the final offset. An empty page is always terminal.
        if not features or not page.get("exceededTransferLimit"):
            break
        offset += PAGE_SIZE

    return {"type": "FeatureCollection", "features": all_features}


@asset(
    group_name="fema",
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
    authorization = authorize_source(
        database,
        source_key="fema_nfhl",
        acquisition_method="arcgis_rest",
        asset_key="fema_flood_zones",
        dagster_run_id=context.run_id,
    )
    require_source_use(authorization, "derived_product")
    require_source_use(authorization, "raw_retention")

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

    # 3. Parse features. Each record carries a "geojson" key holding the
    # raw Polygon coords; pop it out into geom_lookup and let scd2_upsert_geom
    # wrap with ST_Multi() so the column type (MultiPolygon) is satisfied.
    records = parse_fema_geojson(geojson)
    geom_lookup: dict[str, str] = {}
    for rec in records:
        rec["source_url"] = county.fema_nfhl_url
        if "geojson" in rec:
            geom = rec.pop("geojson")
            if geom and rec.get("fld_ar_id"):
                geom_lookup[rec["fld_ar_id"]] = json.dumps(geom)
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

    # 4. Upsert with PostGIS geometry, scoped by dfirm_id so running for
    # one county does not expire another county's records in the same table.
    cur = database.cursor()
    try:
        stats = scd2_upsert_geom(
            cursor=cur,
            schema="staging",
            table="flood_zones",
            records=records,
            key_columns=KEY_COLUMNS,
            value_columns=VALUE_COLUMNS,
            geom_lookup=geom_lookup,
            geom_kind="multipolygon",
            scope_column="dfirm_id",
            scope_value=county.fema_dfirm_id,
        )
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


fema_record_count_nonzero = make_row_count_check(
    fema_flood_zones, table="flood_zones", name="fema_record_count_nonzero"
)


@asset_check(asset=fema_flood_zones)
def fema_schema_drift(database: DatabaseResource) -> AssetCheckResult:
    """Verify FEMA MapServer still has the expected fields."""
    authorize_source(
        database,
        source_key="fema_nfhl",
        acquisition_method="arcgis_rest",
        asset_key="fema_schema_drift",
    )
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
                "missing_fields": MetadataValue.text(
                    str(missing) if missing else "none"
                ),
                "extra_fields": MetadataValue.text(str(extra) if extra else "none"),
            },
        )
    except requests.exceptions.RequestException as e:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.WARN,
            metadata={"error": MetadataValue.text(f"Network error: {e}")},
        )
