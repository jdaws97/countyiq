"""Local Dagster execution: assets, checks, jobs and resources."""

from dagster import (
    Definitions,
    load_asset_checks_from_package_module,
    load_assets_from_package_module,
    multiprocess_executor,
)

from countyiq import assets
from countyiq.jobs import (
    arcgis_refresh,
    brief_generation_refresh,
    bulk_refresh,
    county_narratives_refresh,
    deterministic_enrichment_refresh,
    enrichment_refresh,
    emerging_intelligence_refresh,
    entity_verification_refresh,
    fema_refresh,
    intelligence_data_refresh,
    intelligence_full_pipeline,
    owner_briefs_refresh,
    pa_dos_refresh,
    plan_review_pilot,
    proceedings_extraction_refresh,
    proceedings_refresh,
    radar_refresh,
    record_intelligence_refresh,
    scraper_refresh,
    signal_validation_refresh,
)
from countyiq.resources.database import make_database_resource
from countyiq.resources.storage import make_s3_resource

# Keep subprocess isolation while bounding each local run's memory use.
# The local runner separately locks the VPS against concurrent runs/deployments.
bounded_multiprocess_executor = multiprocess_executor.configured(
    {"max_concurrent": 1},
    name="bounded_multiprocess_executor",
)

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
        radar_refresh,
        pa_dos_refresh,
        proceedings_refresh,
        proceedings_extraction_refresh,
        intelligence_data_refresh,
        entity_verification_refresh,
        signal_validation_refresh,
        brief_generation_refresh,
        record_intelligence_refresh,
        owner_briefs_refresh,
        county_narratives_refresh,
        emerging_intelligence_refresh,
        plan_review_pilot,
        deterministic_enrichment_refresh,
        intelligence_full_pipeline,
    ],
    resources={
        # Defer credentials until execution so local job snapshots contain only
        # environment references, never the borrowed production secrets.
        "database": make_database_resource(defer_secrets=True),
        "s3": make_s3_resource(defer_secrets=True),
    },
    executor=bounded_multiprocess_executor,
)
