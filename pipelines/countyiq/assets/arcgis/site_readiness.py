"""Lawful York OPEN_DATA inputs for parcel site-readiness intelligence."""

import json
from datetime import datetime, timezone
from typing import Callable

from dagster import AssetExecutionContext, MaterializeResult, MetadataValue, asset

from countyiq.lib.arcgis_client import query_all_features
from countyiq.lib.checks import make_row_count_check
from countyiq.lib.county_config import county_open_data_source_key, get_county_config
from countyiq.lib.geometry import point_to_geojson, rings_to_multipolygon_geojson
from countyiq.lib.scd import scd2_upsert_geom
from countyiq.lib.source_rights import authorize_source, require_source_use
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource


def _arcgis_date(value):
    if value in (None, ""):
        return None
    return datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc)


def _authorize(
    context: AssetExecutionContext,
    database: DatabaseResource,
    asset_key: str,
) -> None:
    authorization = authorize_source(
        database,
        source_key=county_open_data_source_key(),
        acquisition_method="arcgis_rest",
        asset_key=asset_key,
        dagster_run_id=context.run_id,
    )
    require_source_use(authorization, "derived_product")
    require_source_use(authorization, "raw_retention")


def _polygon_geometries(features: list[dict], key_fn: Callable[[dict], object]) -> dict:
    result = {}
    for feature in features:
        key = key_fn(feature.get("attributes", {}))
        geometry = feature.get("geometry") or {}
        geojson = rings_to_multipolygon_geojson(geometry.get("rings"))
        if key is not None and geojson:
            result[key] = json.dumps(geojson)
    return result


def _point_geometries(features: list[dict], key_fn: Callable[[dict], object]) -> dict:
    result = {}
    for feature in features:
        key = key_fn(feature.get("attributes", {}))
        geometry = feature.get("geometry") or {}
        geojson = point_to_geojson(geometry.get("x"), geometry.get("y"))
        if key is not None and geojson:
            result[key] = json.dumps(geojson)
    return result


def _fetch_archive(
    context: AssetExecutionContext,
    s3: S3StorageResource,
    *,
    url: str,
    archive_path: str,
    minimum_records: int,
) -> list[dict]:
    if not url:
        raise RuntimeError("Source is not configured for the active county")
    features = query_all_features(
        url=url,
        where="1=1",
        out_fields="*",
        out_sr=4326,
        batch_size=2000,
    )
    context.log.info("Fetched %d features from %s", len(features), url)
    if len(features) < minimum_records:
        raise RuntimeError(
            f"Source returned {len(features):,} rows; minimum is "
            f"{minimum_records:,}. Refusing to alter staging data."
        )
    s3.archive(archive_path, features)
    return features


def _result(records: list[dict], stats: dict) -> MaterializeResult:
    return MaterializeResult(
        metadata={
            "record_count": MetadataValue.int(len(records)),
            "inserted": MetadataValue.int(stats["inserted"]),
            "expired": MetadataValue.int(stats["expired"]),
            "unchanged": MetadataValue.int(stats["unchanged"]),
        }
    )


def _require_usable_records(records: list[dict], minimum_records: int, label: str) -> None:
    if len(records) < minimum_records:
        raise RuntimeError(
            f"{label} parsed {len(records):,} usable rows; minimum is "
            f"{minimum_records:,}. Refusing to alter staging data."
        )


def parse_zoning_overlays(features: list[dict], source_url: str) -> list[dict]:
    records = []
    for feature in features:
        attrs = feature.get("attributes", {})
        globalid = attrs.get("GlobalID")
        if not globalid:
            continue
        records.append(
            {
                "globalid": str(globalid).strip(),
                "objectid": attrs.get("OBJECTID"),
                "municipality": attrs.get("MUNI_NAME"),
                "overlay_type": attrs.get("ZN_OV_TYPE"),
                "overlay_name": attrs.get("ZN_OV_NAME"),
                "description": attrs.get("DESCRIPTION"),
                "project_number": attrs.get("PRJ_NUM"),
                "create_date": _arcgis_date(attrs.get("CREATE_DATE")),
                "modify_date": _arcgis_date(attrs.get("MODIFY_DATE")),
                "source_url": source_url,
            }
        )
    return records


@asset(
    group_name="radar",
    description="York zoning overlays -> staging.zoning_overlays",
    kinds={"postgres", "arcgis"},
)
def zoning_overlays_arcgis(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    county = get_county_config()
    _authorize(context, database, "zoning_overlays_arcgis")
    features = _fetch_archive(
        context,
        s3,
        url=county.arcgis_zoning_overlays_url,
        archive_path=f"{county.s3_prefix}/arcgis/zoning_overlays",
        minimum_records=county.arcgis_zoning_overlays_min_records,
    )
    records = parse_zoning_overlays(features, county.arcgis_zoning_overlays_url)
    _require_usable_records(
        records, county.arcgis_zoning_overlays_min_records, "zoning overlays"
    )
    geometries = _polygon_geometries(
        features, lambda attrs: str(attrs["GlobalID"]).strip() if attrs.get("GlobalID") else None
    )
    with database.transaction() as cursor:
        stats = scd2_upsert_geom(
            cursor=cursor,
            schema="staging",
            table="zoning_overlays",
            records=records,
            key_columns=["globalid"],
            value_columns=[
                "objectid", "municipality", "overlay_type", "overlay_name",
                "description", "project_number", "create_date", "modify_date",
                "source_url",
            ],
            geom_lookup=geometries,
        )
    return _result(records, stats)


def parse_economic_parks(
    features: list[dict], source_url: str, park_type: str
) -> list[dict]:
    records = []
    for feature in features:
        attrs = feature.get("attributes", {})
        pidn = attrs.get("PIDN")
        objectid = attrs.get("OBJECTID")
        if not pidn or objectid is None:
            continue
        records.append(
            {
                "park_type": park_type,
                "pidn": str(pidn).strip(),
                "source_objectid": objectid,
                "name": attrs.get("NAME"),
                "website_url": attrs.get("URL"),
                "create_date": _arcgis_date(attrs.get("CREATE_DATE")),
                "modify_date": _arcgis_date(attrs.get("MODIFY_DATE")),
                "source_url": source_url,
            }
        )
    return records


def _economic_parks_asset(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
    *,
    park_type: str,
    url: str,
    asset_key: str,
    minimum_records: int,
) -> MaterializeResult:
    county = get_county_config()
    _authorize(context, database, asset_key)
    features = _fetch_archive(
        context,
        s3,
        url=url,
        archive_path=f"{county.s3_prefix}/arcgis/{park_type}_parks",
        minimum_records=minimum_records,
    )
    records = parse_economic_parks(features, url, park_type)
    _require_usable_records(records, minimum_records, f"{park_type} parks")
    geometries = _polygon_geometries(
        features, lambda attrs: attrs.get("OBJECTID")
    )
    with database.transaction() as cursor:
        stats = scd2_upsert_geom(
            cursor=cursor,
            schema="staging",
            table="economic_development_parks",
            records=records,
            key_columns=["park_type", "source_objectid"],
            value_columns=[
                "pidn", "name", "website_url", "create_date",
                "modify_date", "source_url",
            ],
            geom_lookup=geometries,
            geom_key="source_objectid",
            scope_column="park_type",
            scope_value=park_type,
        )
    return _result(records, stats)


@asset(
    group_name="radar",
    description="York business parks -> staging.economic_development_parks",
    kinds={"postgres", "arcgis"},
)
def business_parks_arcgis(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    county = get_county_config()
    return _economic_parks_asset(
        context,
        database,
        s3,
        park_type="business",
        url=county.arcgis_business_parks_url,
        asset_key="business_parks_arcgis",
        minimum_records=county.arcgis_business_parks_min_records,
    )


@asset(
    group_name="radar",
    description="York industrial parks -> staging.economic_development_parks",
    kinds={"postgres", "arcgis"},
)
def industrial_parks_arcgis(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    county = get_county_config()
    return _economic_parks_asset(
        context,
        database,
        s3,
        park_type="industrial",
        url=county.arcgis_industrial_parks_url,
        asset_key="industrial_parks_arcgis",
        minimum_records=county.arcgis_industrial_parks_min_records,
    )


def parse_soils(features: list[dict], source_url: str) -> list[dict]:
    records = []
    for feature in features:
        attrs = feature.get("attributes", {})
        objectid = attrs.get("OBJECTID_1")
        if objectid is None:
            continue
        records.append(
            {
                "objectid": objectid,
                "map_unit_symbol": attrs.get("MUSYM"),
                "map_unit_name": attrs.get("MUNAME"),
                "map_unit_key": attrs.get("MU_KEY"),
                "calculated_acres": attrs.get("CALCACRES"),
                "drainage": attrs.get("DRAINAGE"),
                "capability_class": attrs.get("CLASS"),
                "permeability": attrs.get("PERMIABILI"),
                "septic_rating": attrs.get("SEPTIC"),
                "slope_low": attrs.get("SLOPEL"),
                "slope_high": attrs.get("SLOPEH"),
                "representative_slope": attrs.get("REP_SLOPE"),
                "hydric_rating": attrs.get("HYDRCRATNG"),
                "hydrologic_group": attrs.get("HYR_GRP"),
                "relative_value": attrs.get("RELATIVE_V"),
                "source_url": source_url,
            }
        )
    return records


@asset(
    group_name="radar",
    description="York soil suitability polygons -> staging.soils",
    kinds={"postgres", "arcgis"},
)
def soils_arcgis(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    county = get_county_config()
    _authorize(context, database, "soils_arcgis")
    features = _fetch_archive(
        context,
        s3,
        url=county.arcgis_soils_url,
        archive_path=f"{county.s3_prefix}/arcgis/soils",
        minimum_records=county.arcgis_soils_min_records,
    )
    records = parse_soils(features, county.arcgis_soils_url)
    _require_usable_records(records, county.arcgis_soils_min_records, "soils")
    geometries = _polygon_geometries(features, lambda attrs: attrs.get("OBJECTID_1"))
    with database.transaction() as cursor:
        stats = scd2_upsert_geom(
            cursor=cursor,
            schema="staging",
            table="soils",
            records=records,
            key_columns=["objectid"],
            value_columns=[
                "map_unit_symbol", "map_unit_name", "map_unit_key",
                "calculated_acres", "drainage", "capability_class",
                "permeability", "septic_rating", "slope_low", "slope_high",
                "representative_slope", "hydric_rating", "hydrologic_group",
                "relative_value", "source_url",
            ],
            geom_lookup=geometries,
        )
    return _result(records, stats)


def _traffic_key(attrs: dict) -> str | None:
    globalid = attrs.get("GlobalID")
    if globalid:
        return str(globalid).strip()
    objectid = attrs.get("OBJECTID")
    return f"objectid:{objectid}" if objectid is not None else None


def parse_local_traffic_counts(features: list[dict], source_url: str) -> list[dict]:
    records = []
    for feature in features:
        attrs = feature.get("attributes", {})
        globalid = _traffic_key(attrs)
        if globalid is None:
            continue
        records.append(
            {
                "globalid": globalid,
                "objectid": attrs.get("OBJECTID"),
                "counter_id": attrs.get("COUNTER_ID"),
                "count_type": attrs.get("COUNT_TYPE"),
                "bridge_id": attrs.get("BRIDGE_ID1"),
                "bridge_key": attrs.get("BRKEY"),
                "purpose": attrs.get("PURPOSE"),
                "volume": attrs.get("VOLUME"),
                "am_volume": attrs.get("AM_VOLUME"),
                "am_percent": attrs.get("AM_PERCENT"),
                "am_peak": attrs.get("AM_PEAK"),
                "pm_volume": attrs.get("PM_VOLUME"),
                "pm_percent": attrs.get("PM_PERCENT"),
                "pm_peak": attrs.get("PM_PEAK"),
                "planning_region": attrs.get("PLN_REGION"),
                "count_year": attrs.get("YEAR"),
                "other_mode": attrs.get("OTHER_MODE"),
                "comment": attrs.get("COMMENT"),
                "create_date": _arcgis_date(attrs.get("CREATE_DATE")),
                "modify_date": _arcgis_date(attrs.get("MODIFY_DATE")),
                "source_url": source_url,
            }
        )
    return records


@asset(
    group_name="radar",
    description="York local traffic observations -> staging.local_traffic_counts",
    kinds={"postgres", "arcgis"},
)
def local_traffic_counts_arcgis(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    county = get_county_config()
    _authorize(context, database, "local_traffic_counts_arcgis")
    features = _fetch_archive(
        context,
        s3,
        url=county.arcgis_local_traffic_counts_url,
        archive_path=f"{county.s3_prefix}/arcgis/local_traffic_counts",
        minimum_records=county.arcgis_local_traffic_counts_min_records,
    )
    records = parse_local_traffic_counts(features, county.arcgis_local_traffic_counts_url)
    _require_usable_records(
        records, county.arcgis_local_traffic_counts_min_records, "local traffic counts"
    )
    geometries = _point_geometries(features, _traffic_key)
    with database.transaction() as cursor:
        stats = scd2_upsert_geom(
            cursor=cursor,
            schema="staging",
            table="local_traffic_counts",
            records=records,
            key_columns=["globalid"],
            value_columns=[
                "objectid", "counter_id", "count_type", "bridge_id",
                "bridge_key", "purpose", "volume", "am_volume", "am_percent",
                "am_peak", "pm_volume", "pm_percent", "pm_peak",
                "planning_region", "count_year", "other_mode", "comment",
                "create_date", "modify_date", "source_url",
            ],
            geom_lookup=geometries,
            geom_kind="point",
        )
    return _result(records, stats)


zoning_overlays_record_count = make_row_count_check(
    zoning_overlays_arcgis,
    table="zoning_overlays",
    threshold_fn=lambda: get_county_config().arcgis_zoning_overlays_min_records,
)
business_parks_record_count = make_row_count_check(
    business_parks_arcgis,
    table="economic_development_parks",
    name="business_parks_record_count",
    where="valid_to IS NULL AND park_type = 'business'",
    threshold_fn=lambda: get_county_config().arcgis_business_parks_min_records,
)
industrial_parks_record_count = make_row_count_check(
    industrial_parks_arcgis,
    table="economic_development_parks",
    name="industrial_parks_record_count",
    where="valid_to IS NULL AND park_type = 'industrial'",
    threshold_fn=lambda: get_county_config().arcgis_industrial_parks_min_records,
)
soils_record_count = make_row_count_check(
    soils_arcgis,
    table="soils",
    threshold_fn=lambda: get_county_config().arcgis_soils_min_records,
)
local_traffic_counts_record_count = make_row_count_check(
    local_traffic_counts_arcgis,
    table="local_traffic_counts",
    threshold_fn=lambda: get_county_config().arcgis_local_traffic_counts_min_records,
)
