"""Conservation easements from ArcGIS REST API -> staging.conservation_easements.

Records: ~960 polygons
Schedule: Weekly (Sunday 02:00)
"""

import json
from datetime import datetime, timezone

from dagster import (
    asset,
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
)

from countyiq.lib.arcgis_client import query_all_features
from countyiq.lib.checks import make_row_count_check
from countyiq.lib.county_config import county_open_data_source_key, get_county_config
from countyiq.lib.geometry import rings_to_multipolygon_geojson
from countyiq.lib.scd import scd2_upsert_geom
from countyiq.lib.source_rights import authorize_source, require_source_use
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

KEY_COLUMNS = ["pidn"]
VALUE_COLUMNS = [
    "ease_id", "ease_code", "exclusion", "federal", "ease_acres",
    "grantor", "curr_owner", "pres_date", "district", "source_url",
]


@asset(
    group_name="radar",
    description="Conservation easements from ArcGIS -> staging.conservation_easements",
    kinds={"postgres", "arcgis"},
)
def conservation_easements_arcgis(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Fetch conservation easement polygons, archive to S3, SCD2 upsert with geometry."""

    county = get_county_config()
    authorization = authorize_source(database, source_key=county_open_data_source_key(), acquisition_method="arcgis_rest", asset_key="conservation_easements_arcgis", dagster_run_id=context.run_id)
    require_source_use(authorization, "derived_product")
    require_source_use(authorization, "raw_retention")
    context.log.info(f"Querying ArcGIS conservation easements for {county.name}: {county.arcgis_conservation_easements_url}")

    raw_features = query_all_features(
        url=county.arcgis_conservation_easements_url,
        where="1=1",
        out_fields="*",
        out_sr=4326,
        batch_size=2000,
    )
    context.log.info(f"Fetched {len(raw_features)} raw features")

    s3.archive(f"{county.s3_prefix}/arcgis/conservation_easements", raw_features)

    records = _parse(raw_features)
    for rec in records:
        rec["source_url"] = county.arcgis_conservation_easements_url
    context.log.info(f"Parsed {len(records)} conservation easement records")

    if not records:
        context.log.warning("No records parsed -- skipping upsert")
        return MaterializeResult(metadata={"record_count": MetadataValue.int(0)})

    geom_lookup = _build_geom_lookup(raw_features)

    cur = database.cursor()
    try:
        stats = scd2_upsert_geom(
            cursor=cur,
            schema="staging",
            table="conservation_easements",
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


def _parse(raw_features: list[dict]) -> list[dict]:
    """Parse ArcGIS attributes into staging column names."""
    records = []
    for feat in raw_features:
        a = feat.get("attributes", {})
        pidn = a.get("PIDN")
        if not pidn:
            continue
        pres_raw = a.get("PRES_DATE")
        records.append({
            "pidn": str(pidn).strip(),
            "ease_id": a.get("EASE_ID"),
            "ease_code": a.get("EASE_CODE"),
            "exclusion": a.get("EXCLUSION"),
            "federal": a.get("FEDERAL"),
            "ease_acres": a.get("EASE_ACRES"),
            "grantor": a.get("GRANTOR"),
            "curr_owner": a.get("CURR_OWNER"),
            "pres_date": datetime.fromtimestamp(pres_raw / 1000, tz=timezone.utc) if pres_raw else None,
            "district": a.get("DISTRICT"),
        })
    return records


def _build_geom_lookup(raw_features: list[dict]) -> dict:
    """Build pidn -> JSON-encoded GeoJSON MultiPolygon lookup."""
    lookup: dict = {}
    for feat in raw_features:
        attrs = feat.get("attributes", {})
        pidn = attrs.get("PIDN")
        geom = feat.get("geometry")
        if pidn is None or not geom:
            continue
        geojson = rings_to_multipolygon_geojson(geom.get("rings"))
        if geojson:
            lookup[str(pidn).strip()] = json.dumps(geojson)
    return lookup


conservation_easements_record_count_nonzero = make_row_count_check(
    conservation_easements_arcgis, table="conservation_easements"
)
