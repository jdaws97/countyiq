"""PennDOT transportation projects from PA Projects MapServer -> staging.penndot_projects.

Records: ~20-80 points across 4 layers (Underway, Four Year Plan, Under Development, Under Construction)
Schedule: Weekly (Sunday 02:00)
"""

import json

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

from countyiq.lib.arcgis_client import query_all_features
from countyiq.lib.checks import make_row_count_check
from countyiq.lib.county_config import get_county_config
from countyiq.lib.geometry import point_to_geojson
from countyiq.lib.parsers.penndot_projects import parse_penndot_projects_features
from countyiq.lib.scd import scd2_upsert_geom
from countyiq.lib.source_rights import authorize_source, require_source_use
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

KEY_COLUMNS = ["project_id"]
VALUE_COLUMNS = [
    "project_name", "description", "status", "project_type",
    "start_date", "end_date", "cost", "municipality", "county", "data", "source_url",
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
    authorization = authorize_source(database, source_key="penndot_open_data", acquisition_method="arcgis_rest", asset_key="penndot_projects_arcgis", dagster_run_id=context.run_id)
    require_source_use(authorization, "derived_product")
    require_source_use(authorization, "raw_retention")
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
    for rec in records:
        rec["source_url"] = county.penndot_projects_url
    context.log.info(f"Parsed {len(records)} project records (deduplicated)")

    if not records:
        context.log.warning("No records parsed — skipping upsert")
        return MaterializeResult(metadata={"record_count": MetadataValue.int(0)})

    if len(records) < county.penndot_projects_min_records:
        raise RuntimeError(
            f"Only {len(records)} project records (expected >= {county.penndot_projects_min_records}). "
            f"Possible truncated response — aborting."
        )

    geom_lookup = _build_geom_lookup(all_features)

    cur = database.cursor()
    try:
        # `data` is a jsonb column; scd2_upsert_geom JSON-encodes dict/list
        # values automatically and psycopg2 + JSONB accept the resulting text.
        stats = scd2_upsert_geom(
            cursor=cur,
            schema="staging",
            table="penndot_projects",
            records=records,
            key_columns=KEY_COLUMNS,
            value_columns=VALUE_COLUMNS,
            geom_lookup=geom_lookup,
            geom_kind="point",
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


def _build_geom_lookup(raw_features: list[dict]) -> dict:
    """Build project_id -> JSON-encoded GeoJSON Point lookup."""
    lookup: dict = {}
    for feat in raw_features:
        attrs = feat.get("attributes", {})
        proj_id = attrs.get("PROJ_ID")
        geom = feat.get("geometry") or {}
        if proj_id is None:
            continue
        geojson = point_to_geojson(geom.get("x"), geom.get("y"))
        if geojson:
            lookup[str(proj_id)] = json.dumps(geojson)
    return lookup


penndot_projects_record_count_nonzero = make_row_count_check(
    penndot_projects_arcgis, table="penndot_projects"
)


@asset_check(asset=penndot_projects_arcgis)
def penndot_projects_schema_drift(database: DatabaseResource) -> AssetCheckResult:
    """Verify PennDOT Projects MapServer layer 1 still has expected fields."""
    authorize_source(
        database,
        source_key="penndot_open_data",
        acquisition_method="arcgis_rest",
        asset_key="penndot_projects_schema_drift",
    )
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
