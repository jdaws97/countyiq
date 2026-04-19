"""CDBG housing development locations from ArcGIS REST API -> staging.cdbg_housing.

Records: ~63 points
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
from countyiq.lib.geometry import point_to_geojson
from countyiq.lib.scd import scd2_upsert_geom
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

KEY_COLUMNS = ["housingdevid"]
VALUE_COLUMNS = [
    "prj_id", "address", "constructi", "units",
    "date_of_oc", "affordabil", "name", "source_url",
]


@asset(
    group_name="radar",
    description="CDBG housing development locations from ArcGIS -> staging.cdbg_housing",
    kinds={"postgres", "arcgis"},
)
def cdbg_housing_arcgis(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Fetch CDBG housing points, archive to S3, SCD2 upsert with geometry."""

    county = get_county_config()
    context.log.info(f"Querying ArcGIS CDBG housing for {county.name}: {county.arcgis_cdbg_housing_url}")

    raw_features = query_all_features(
        url=county.arcgis_cdbg_housing_url,
        where="1=1",
        out_fields="*",
        out_sr=4326,
        batch_size=2000,
    )
    context.log.info(f"Fetched {len(raw_features)} raw features")

    s3.archive(f"{county.s3_prefix}/arcgis/cdbg_housing", raw_features)

    records = _parse(raw_features)
    for rec in records:
        rec["source_url"] = county.arcgis_cdbg_housing_url
    context.log.info(f"Parsed {len(records)} CDBG housing records")

    if not records:
        context.log.warning("No records parsed -- skipping upsert")
        return MaterializeResult(metadata={"record_count": MetadataValue.int(0)})

    geom_lookup = _build_geom_lookup(raw_features)

    cur = database.cursor()
    try:
        stats = scd2_upsert_geom(
            cursor=cur,
            schema="staging",
            table="cdbg_housing",
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


def _parse(raw_features: list[dict]) -> list[dict]:
    """Parse ArcGIS attributes into staging column names."""
    records = []
    for feat in raw_features:
        a = feat.get("attributes", {})
        housingdevid = a.get("HousingDevID")
        if not housingdevid:
            continue
        records.append({
            "housingdevid": str(housingdevid).strip(),
            "prj_id": a.get("PRJ_ID"),
            "address": a.get("Address"),
            "constructi": a.get("Constructi"),
            "units": a.get("Units"),
            "date_of_oc": a.get("Date_of_OC"),
            "affordabil": a.get("Affordabil"),
            "name": a.get("Name"),
        })
    return records


def _build_geom_lookup(raw_features: list[dict]) -> dict:
    """Build housingdevid -> JSON-encoded GeoJSON Point lookup."""
    lookup: dict = {}
    for feat in raw_features:
        attrs = feat.get("attributes", {})
        housingdevid = attrs.get("HousingDevID")
        geom = feat.get("geometry") or {}
        if housingdevid is None:
            continue
        geojson = point_to_geojson(geom.get("x"), geom.get("y"))
        if geojson:
            lookup[str(housingdevid).strip()] = json.dumps(geojson)
    return lookup


cdbg_housing_record_count_nonzero = make_row_count_check(
    cdbg_housing_arcgis, table="cdbg_housing"
)
