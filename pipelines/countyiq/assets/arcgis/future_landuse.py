"""Future land use designations from ArcGIS REST API -> staging.future_landuse.

Records: ~1,659 polygons
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

KEY_COLUMNS = ["globalid"]
VALUE_COLUMNS = ["district", "future_lu", "general_lu", "adopt_date", "source_url"]


@asset(
    group_name="radar",
    description="Future land use designations from ArcGIS -> staging.future_landuse",
    kinds={"postgres", "arcgis"},
)
def future_landuse_arcgis(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Fetch future land use polygons, archive to S3, SCD2 upsert with geometry."""

    county = get_county_config()
    authorization = authorize_source(
        database,
        source_key=county_open_data_source_key(),
        acquisition_method="arcgis_rest",
        asset_key="future_landuse_arcgis",
        dagster_run_id=context.run_id,
    )
    require_source_use(authorization, "derived_product")
    require_source_use(authorization, "raw_retention")
    context.log.info(
        f"Querying ArcGIS future land use for {county.name}: {county.arcgis_future_landuse_url}"
    )

    raw_features = query_all_features(
        url=county.arcgis_future_landuse_url,
        where="1=1",
        out_fields="*",
        out_sr=4326,
        batch_size=2000,
    )
    context.log.info(f"Fetched {len(raw_features)} raw features")

    s3.archive(f"{county.s3_prefix}/arcgis/future_landuse", raw_features)

    records = _parse(raw_features)
    for rec in records:
        rec["source_url"] = county.arcgis_future_landuse_url
    context.log.info(f"Parsed {len(records)} future land use records")

    if not records:
        context.log.warning("No records parsed -- skipping upsert")
        return MaterializeResult(metadata={"record_count": MetadataValue.int(0)})

    geom_lookup = _build_geom_lookup(raw_features)

    cur = database.cursor()
    try:
        stats = scd2_upsert_geom(
            cursor=cur,
            schema="staging",
            table="future_landuse",
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
        globalid = a.get("GlobalID")
        if not globalid:
            continue
        adopt_raw = a.get("ADOPT_DATE")
        records.append(
            {
                "globalid": str(globalid).strip(),
                "district": a.get("DISTRICT"),
                "future_lu": a.get("FUTURE_LU"),
                "general_lu": a.get("GENERAL_LU"),
                "adopt_date": datetime.fromtimestamp(adopt_raw / 1000, tz=timezone.utc)
                if adopt_raw
                else None,
            }
        )
    return records


def _build_geom_lookup(raw_features: list[dict]) -> dict:
    """Build globalid -> JSON-encoded GeoJSON MultiPolygon lookup."""
    lookup: dict = {}
    for feat in raw_features:
        attrs = feat.get("attributes", {})
        globalid = attrs.get("GlobalID")
        geom = feat.get("geometry")
        if globalid is None or not geom:
            continue
        geojson = rings_to_multipolygon_geojson(geom.get("rings"))
        if geojson:
            lookup[str(globalid).strip()] = json.dumps(geojson)
    return lookup


future_landuse_record_count_nonzero = make_row_count_check(
    future_landuse_arcgis, table="future_landuse"
)
