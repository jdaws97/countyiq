"""Dagster entry point — registers all assets, jobs, schedules, sensors, and resources."""

from dagster import Definitions, load_assets_from_package_module

from york_county import assets
from york_county.jobs import arcgis_refresh, scraper_refresh, bulk_refresh, enrichment_refresh
from york_county.schedules import all_schedules
from york_county.sensors.alerting import success_reporter, failure_alerter
from york_county.resources.database import make_database_resource
from york_county.resources.storage import make_s3_resource

defs = Definitions(
    assets=load_assets_from_package_module(assets),
    jobs=[arcgis_refresh, scraper_refresh, bulk_refresh, enrichment_refresh],
    schedules=all_schedules,
    sensors=[success_reporter, failure_alerter],
    resources={
        "database": make_database_resource(),
        "s3": make_s3_resource(),
    },
)
