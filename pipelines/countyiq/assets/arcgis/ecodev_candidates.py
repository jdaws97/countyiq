"""Economic development candidate parcels from ArcGIS REST API -> staging.ecodev_candidates.

Records: ~70 polygons
Schedule: Weekly (Sunday 02:00)
"""

import json

from dagster import (
    asset,
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
)

from countyiq.lib.arcgis_client import query_all_features
from countyiq.lib.checks import make_row_count_check
from countyiq.lib.county_config import get_county_config
from countyiq.lib.geometry import rings_to_multipolygon_geojson
from countyiq.lib.scd import scd2_upsert_geom
from countyiq.lib.source_rights import authorize_source, require_source_use
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
    group_name="paused_sources",
    description="PAUSED pending reuse approval: economic development candidate parcels",
    kinds={"postgres", "arcgis"},
)
def ecodev_candidates_arcgis(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Fetch ecodev candidate polygons, archive to S3, SCD2 upsert with geometry."""

    county = get_county_config()
    authorization = authorize_source(
        database,
        source_key="ecodev_candidates",
        acquisition_method="arcgis_rest",
        asset_key="ecodev_candidates_arcgis",
        dagster_run_id=context.run_id,
    )
    require_source_use(authorization, "derived_product")
    require_source_use(authorization, "raw_retention")
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

    geom_lookup = _build_geom_lookup(raw_features)

    cur = database.cursor()
    try:
        stats = scd2_upsert_geom(
            cursor=cur,
            schema="staging",
            table="ecodev_candidates",
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


ecodev_candidates_record_count_nonzero = make_row_count_check(
    ecodev_candidates_arcgis, table="ecodev_candidates"
)
