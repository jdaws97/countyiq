"""Portable PA DEP evidence for parcel-level environmental screening.

These are deterministic proximity facts. They are not contamination findings,
regulatory conclusions, or inputs that require an LLM.
"""

import json
from datetime import datetime

from dagster import AssetExecutionContext, MaterializeResult, MetadataValue, asset

from countyiq.lib.county_config import get_county_config
from countyiq.lib.geometry import point_to_geojson
from countyiq.lib.scd import scd2_upsert_geom
from countyiq.lib.source_rights import authorize_source, require_source_use
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource
from countyiq.resources.source_snapshots import SourceSnapshotsResource


def _point(feature: dict) -> str | None:
    geometry = feature.get("geometry") or {}
    geojson = point_to_geojson(geometry.get("x"), geometry.get("y"))
    return json.dumps(geojson) if geojson else None


def parse_storage_tanks(features: list[dict], source_url: str) -> list[dict]:
    records = []
    for feature in features:
        attrs = feature.get("attributes") or {}
        source_id = attrs.get("OBJECTID")
        if source_id is None or _point(feature) is None:
            continue
        address = (
            " ".join(
                str(value).strip()
                for value in (
                    attrs.get("FACILITY_ADDRESS1"),
                    attrs.get("FACILITY_ADDRESS2"),
                )
                if value
            )
            or None
        )
        records.append(
            {
                "source_layer": "active_storage_tank",
                "source_id": str(source_id),
                "site_name": attrs.get("FACILITY_NAME"),
                "facility_type": "Active regulated storage tank facility",
                "facility_status": "active",
                "address": address,
                "municipality": attrs.get("FACILITY_MUNICIPALITY"),
                "county_name": attrs.get("FACILITY_COUNTY"),
                "detail_url": attrs.get("TANK_INFORMATION"),
                "source_url": source_url,
                "_geom": _point(feature),
            }
        )
    return records


def parse_cleanup_sites(features: list[dict], source_url: str) -> list[dict]:
    records = []
    for feature in features:
        attrs = feature.get("attributes") or {}
        source_id = attrs.get("SHAPE_FID") or attrs.get("SUB_FACILITY_ID")
        if source_id is None or _point(feature) is None:
            continue
        records.append(
            {
                "source_layer": "land_recycling_cleanup",
                "source_id": str(source_id),
                "site_name": attrs.get("SITE_NAME")
                or attrs.get("PRIMARY_FACILITY_NAME"),
                "facility_type": attrs.get("SUB_FACILITY_TYPE")
                or attrs.get("PRIMARY_FACILITY_KIND"),
                "facility_status": attrs.get("SUB_FACILITY_STATUS")
                or attrs.get("PRIMARY_FACILITY_STATUS"),
                "address": None,
                "municipality": None,
                "county_name": None,
                "detail_url": None,
                "source_url": source_url,
                "_geom": _point(feature),
            }
        )
    return records


def _upsert_layer(
    database: DatabaseResource,
    *,
    records: list[dict],
    layer: str,
    acquired_at: datetime,
    snapshot_id: str,
) -> dict:
    geometries = {record["source_id"]: record.pop("_geom") for record in records}
    with database.transaction() as cursor:
        return scd2_upsert_geom(
            cursor=cursor,
            schema="staging",
            table="environmental_diligence_sites",
            records=records,
            key_columns=["source_layer", "source_id"],
            value_columns=[
                "site_name",
                "facility_type",
                "facility_status",
                "address",
                "municipality",
                "county_name",
                "detail_url",
                "source_url",
            ],
            geom_lookup=geometries,
            geom_kind="point",
            geom_key="source_id",
            scope_column="source_layer",
            scope_value=layer,
            snapshot_started_at=acquired_at,
            snapshot_id=snapshot_id,
        )


@asset(
    group_name="radar",
    description="PA DEP storage-tank and cleanup locations for parcel diligence screening",
    kinds={"postgres", "arcgis"},
)
def pa_dep_environmental_diligence(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
    source_snapshots: SourceSnapshotsResource,
) -> MaterializeResult:
    county = get_county_config()
    if not county.pa_dep_query_bbox:
        return MaterializeResult(
            metadata={"status": MetadataValue.text("not_configured")}
        )

    authorization = authorize_source(
        database,
        source_key="pa_dep_open_data",
        acquisition_method="arcgis_rest",
        asset_key="pa_dep_environmental_diligence",
        dagster_run_id=context.run_id,
    )
    require_source_use(authorization, "raw_retention")
    require_source_use(authorization, "derived_product")

    storage_features = source_snapshots.arcgis("storage_tanks", context)
    cleanup_features = source_snapshots.arcgis("cleanup_sites", context)

    storage_records = parse_storage_tanks(
        storage_features, county.pa_dep_storage_tanks_url
    )
    cleanup_records = parse_cleanup_sites(
        cleanup_features, county.pa_dep_cleanup_sites_url
    )
    minimums = {
        "active_storage_tank": county.pa_dep_storage_tanks_min_records,
        "land_recycling_cleanup": county.pa_dep_cleanup_sites_min_records,
    }
    for layer, records in (
        ("active_storage_tank", storage_records),
        ("land_recycling_cleanup", cleanup_records),
    ):
        if len(records) < minimums[layer]:
            raise RuntimeError(
                f"PA DEP {layer} returned {len(records):,} usable rows; "
                f"minimum is {minimums[layer]:,}. Refusing to alter staging data."
            )

    source_snapshots.archive_receipt(s3, context)
    s3.archive(f"{county.s3_prefix}/pa_dep/active_storage_tanks", storage_features)
    s3.archive(f"{county.s3_prefix}/pa_dep/land_recycling_cleanup", cleanup_features)
    storage_stats = _upsert_layer(
        database,
        records=storage_records,
        layer="active_storage_tank",
        acquired_at=source_snapshots.acquisition_time(),
        snapshot_id=source_snapshots.snapshot_identity(),
    )
    cleanup_stats = _upsert_layer(
        database,
        records=cleanup_records,
        layer="land_recycling_cleanup",
        acquired_at=source_snapshots.acquisition_time(),
        snapshot_id=source_snapshots.snapshot_identity(),
    )
    return MaterializeResult(
        metadata={
            "storage_tank_count": MetadataValue.int(len(storage_records)),
            "cleanup_site_count": MetadataValue.int(len(cleanup_records)),
            "inserted": MetadataValue.int(
                storage_stats["inserted"] + cleanup_stats["inserted"]
            ),
            "expired": MetadataValue.int(
                storage_stats["expired"] + cleanup_stats["expired"]
            ),
        }
    )
