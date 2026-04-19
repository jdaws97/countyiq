"""Agricultural security areas from ArcGIS REST API -> staging.ag_security.

Records: ~4,581 polygons
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
from countyiq.lib.county_config import get_county_config
from countyiq.lib.geometry import rings_to_multipolygon_geojson
from countyiq.lib.scd import scd2_upsert_geom
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

KEY_COLUMNS = ["pidn"]
VALUE_COLUMNS = [
    "resolution", "res_date", "res_acres", "book", "page",
    "instrument", "last_review", "flag", "district", "source_url",
]


@asset(
    group_name="radar",
    description="Agricultural security areas from ArcGIS -> staging.ag_security",
    kinds={"postgres", "arcgis"},
)
def ag_security_arcgis(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Fetch ag security area polygons, archive to S3, SCD2 upsert with geometry."""

    county = get_county_config()
    context.log.info(f"Querying ArcGIS ag security areas for {county.name}: {county.arcgis_ag_security_url}")

    raw_features = query_all_features(
        url=county.arcgis_ag_security_url,
        where="1=1",
        out_fields="*",
        out_sr=4326,
        batch_size=2000,
    )
    context.log.info(f"Fetched {len(raw_features)} raw features")

    s3.archive(f"{county.s3_prefix}/arcgis/ag_security", raw_features)

    records = _parse(raw_features)
    for rec in records:
        rec["source_url"] = county.arcgis_ag_security_url
    context.log.info(f"Parsed {len(records)} ag security records")

    if not records:
        context.log.warning("No records parsed -- skipping upsert")
        return MaterializeResult(metadata={"record_count": MetadataValue.int(0)})

    geom_lookup = _build_geom_lookup(raw_features)

    cur = database.cursor()
    try:
        stats = scd2_upsert_geom(
            cursor=cur,
            schema="staging",
            table="ag_security",
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
        res_date_raw = a.get("RES_DATE")
        last_review_raw = a.get("LAST_REVIEW")
        records.append({
            "pidn": str(pidn).strip(),
            "resolution": a.get("RESOLUTION"),
            "res_date": datetime.fromtimestamp(res_date_raw / 1000, tz=timezone.utc) if res_date_raw else None,
            "res_acres": a.get("RES_ACRES"),
            "book": a.get("BOOK"),
            "page": a.get("PAGE"),
            "instrument": a.get("INSTRUMENT"),
            "last_review": datetime.fromtimestamp(last_review_raw / 1000, tz=timezone.utc) if last_review_raw else None,
            "flag": a.get("FLAG"),
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


ag_security_record_count_nonzero = make_row_count_check(
    ag_security_arcgis, table="ag_security"
)
