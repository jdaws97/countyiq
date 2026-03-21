"""Dagster entry point — registers all assets, jobs, schedules, sensors, and resources."""

from dagster import Definitions, load_assets_from_package_module

from countyiq import assets
from countyiq.jobs import arcgis_refresh, scraper_refresh, bulk_refresh, enrichment_refresh
from countyiq.schedules import all_schedules
from countyiq.sensors.alerting import success_reporter, failure_alerter
from countyiq.resources.database import make_database_resource
from countyiq.resources.storage import make_s3_resource

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
