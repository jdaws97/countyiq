"""Dagster entry point — registers all assets, jobs, schedules, sensors, and resources."""

from dagster import Definitions, load_asset_checks_from_package_module, load_assets_from_package_module

from countyiq import assets
from countyiq.jobs import (
    arcgis_refresh,
    bulk_refresh,
    enrichment_refresh,
    fema_refresh,
    radar_refresh,
    scout_discovery_refresh,
    scout_monitor_refresh,
    scraper_refresh,
    pa_dos_refresh,
    proceedings_refresh,
    proceedings_extraction_refresh,
    intelligence_data_refresh,
    entity_verification_refresh,
    signal_validation_refresh,
    brief_generation_refresh,
    county_narratives_refresh,
    deterministic_enrichment_refresh,
    intelligence_full_pipeline,
)
from countyiq.schedules import all_schedules
from countyiq.sensors.alerting import success_reporter, failure_alerter
from countyiq.resources.database import make_database_resource
from countyiq.resources.storage import make_s3_resource

defs = Definitions(
    assets=load_assets_from_package_module(assets),
    # load_assets_from_package_module does NOT collect AssetChecksDefinition
    # objects — without this line every make_row_count_check/schema-drift
    # check in the codebase silently never ran (found 2026-08-02).
    asset_checks=load_asset_checks_from_package_module(assets),
    jobs=[
        arcgis_refresh,
        scraper_refresh,
        bulk_refresh,
        enrichment_refresh,
        fema_refresh,
        scout_discovery_refresh,
        scout_monitor_refresh,
        radar_refresh,
        pa_dos_refresh,
        proceedings_refresh,
        proceedings_extraction_refresh,
        intelligence_data_refresh,
        entity_verification_refresh,
        signal_validation_refresh,
        brief_generation_refresh,
        county_narratives_refresh,
        deterministic_enrichment_refresh,
        intelligence_full_pipeline,
    ],
    schedules=all_schedules,
    sensors=[success_reporter, failure_alerter],
    resources={
        "database": make_database_resource(),
        "s3": make_s3_resource(),
    },
)
