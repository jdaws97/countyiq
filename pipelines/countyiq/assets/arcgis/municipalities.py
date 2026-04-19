"""Municipal boundaries from ArcGIS REST API → staging.municipalities.

Records: ~72 polygons
Schedule: Weekly (Sunday 02:00) via arcgis_refresh
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
from countyiq.lib.geometry import rings_to_multipolygon_geojson
from countyiq.lib.parsers.municipalities import parse_municipalities_features
from countyiq.lib.scd import scd2_upsert_geom
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

KEY_COLUMNS = ["name"]
VALUE_COLUMNS = ["muni_type", "county", "source_url"]

EXPECTED_FIELDS = {"MUNI_NAME", "TYPE"}


@asset(
    group_name="arcgis",
    description=f"{get_county_config().name} municipal boundaries from ArcGIS REST API → staging.municipalities",
    kinds={"postgres", "arcgis"},
)
def municipalities_arcgis(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Fetch municipal boundaries, archive to S3, SCD2 upsert with geometry."""

    county = get_county_config()
    context.log.info(f"Querying ArcGIS municipalities for {county.name}: {county.arcgis_municipalities_url}")

    raw_features = query_all_features(
        url=county.arcgis_municipalities_url,
        where="1=1",
        out_fields="*",
        out_sr=4326,
        batch_size=2000,
    )
    context.log.info(f"Fetched {len(raw_features)} raw features")

    s3.archive(f"{county.s3_prefix}/arcgis/municipalities", raw_features)

    records = parse_municipalities_features(raw_features)
    for rec in records:
        rec["source_url"] = county.arcgis_municipalities_url
    context.log.info(f"Parsed {len(records)} municipality records")

    if not records:
        context.log.warning("No records parsed — skipping upsert")
        return MaterializeResult(metadata={"record_count": MetadataValue.int(0)})

    if len(records) < county.arcgis_municipalities_min_records:
        raise RuntimeError(
            f"Only {len(records)} municipality records (expected >= {county.arcgis_municipalities_min_records}). "
            f"Possible truncated response — aborting."
        )

    geom_lookup = _build_geom_lookup(raw_features)

    cur = database.cursor()
    try:
        stats = scd2_upsert_geom(
            cursor=cur,
            schema="staging",
            table="municipalities",
            records=records,
            key_columns=KEY_COLUMNS,
            value_columns=VALUE_COLUMNS,
            geom_lookup=geom_lookup,
            geom_kind="multipolygon",
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
    """Build muni_name -> JSON-encoded GeoJSON MultiPolygon lookup."""
    lookup: dict = {}
    for feat in raw_features:
        attrs = feat.get("attributes", {})
        name = attrs.get("MUNI_NAME")
        geom = feat.get("geometry")
        if not (name and geom):
            continue
        geojson = rings_to_multipolygon_geojson(geom.get("rings"))
        if geojson:
            lookup[str(name)] = json.dumps(geojson)
    return lookup


municipalities_record_count_nonzero = make_row_count_check(
    municipalities_arcgis, table="municipalities"
)


@asset_check(asset=municipalities_arcgis)
def municipalities_schema_drift() -> AssetCheckResult:
    """Verify ArcGIS Municipal_Boundary layer still has expected fields."""
    county = get_county_config()
    try:
        resp = requests.get(f"{county.arcgis_municipalities_url}?f=json", timeout=30)
        resp.raise_for_status()
        actual_fields = {f["name"] for f in resp.json().get("fields", [])}
        missing = EXPECTED_FIELDS - actual_fields
        return AssetCheckResult(
            passed=len(missing) == 0,
            severity=AssetCheckSeverity.WARN,
            metadata={"missing_fields": MetadataValue.text(str(missing) if missing else "none")},
        )
    except requests.exceptions.RequestException as e:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.WARN,
            metadata={"error": MetadataValue.text(f"Network error: {e}")},
        )
