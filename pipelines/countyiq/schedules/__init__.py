"""Schedule definitions for the planned hosted pipeline jobs.

Weekly cadence for source refreshes (ArcGIS, bounded scrapers, PA DOS, FEMA,
radar), monthly for low-frequency bulk downloads. Only deterministic
enrichment runs Sunday 08:00 after upstream sources complete; paid LLM passes
are manual and opt-in.

Per-pass jobs are registered in ``definitions.py`` without schedules for
targeted, budget-reviewed runs.
"""

from dagster import ScheduleDefinition

from countyiq.jobs import (
    arcgis_refresh,
    bulk_refresh,
    deterministic_enrichment_refresh,
    fema_refresh,
    pa_dos_refresh,
    radar_refresh,
    scraper_refresh,
)
from countyiq.lib.county_config import CountyConfig, get_county_config

TIMEZONE = "America/New_York"


def _has_radar_sources(county: CountyConfig) -> bool:
    """Return whether the county configured any optional screening layer."""

    return any(
        (
            county.arcgis_planning_subdivisions_url,
            county.arcgis_growth_areas_url,
            county.arcgis_future_landuse_url,
            county.arcgis_conservation_easements_url,
            county.arcgis_ag_security_url,
            county.arcgis_zoning_overlays_url,
            county.arcgis_business_parks_url,
            county.arcgis_industrial_parks_url,
            county.arcgis_soils_url,
            county.arcgis_local_traffic_counts_url,
            county.pa_dep_query_bbox,
        )
    )


_county = get_county_config()

all_schedules = [
    ScheduleDefinition(
        job=arcgis_refresh,
        cron_schedule="0 2 * * 0",  # Sunday 02:00
        name="weekly_arcgis",
        execution_timezone=TIMEZONE,
    ),
    ScheduleDefinition(
        job=deterministic_enrichment_refresh,
        cron_schedule="0 8 * * 0",  # Sunday 08:00 (after source pipelines)
        name="weekly_deterministic_enrichment",
        execution_timezone=TIMEZONE,
    ),
]

if any((_county.municipality_websites, _county.sheriff_sales_url)):
    all_schedules.append(
        ScheduleDefinition(
            job=scraper_refresh,
            cron_schedule="0 3 * * 0",  # Sunday 03:00
            name="weekly_scrapers",
            execution_timezone=TIMEZONE,
        )
    )

if _county.pa_dos_soda_dataset:
    all_schedules.append(
        ScheduleDefinition(
            job=pa_dos_refresh,
            cron_schedule="30 3 * * 0",  # Sunday 03:30, bounded batch
            name="weekly_pa_dos",
            execution_timezone=TIMEZONE,
        )
    )

if any((_county.plcb_filter, _county.tax_claims_pdf_url)):
    all_schedules.append(
        ScheduleDefinition(
            job=bulk_refresh,
            cron_schedule="0 5 1 * *",  # 1st of month 05:00
            name="monthly_bulk",
            execution_timezone=TIMEZONE,
        )
    )

if _county.fema_nfhl_url and _county.fema_dfirm_id:
    all_schedules.append(
        ScheduleDefinition(
            job=fema_refresh,
            cron_schedule="0 4 * * 0",  # Sunday 04:00
            name="weekly_fema",
            execution_timezone=TIMEZONE,
        )
    )

if _has_radar_sources(_county):
    all_schedules.append(
        ScheduleDefinition(
            job=radar_refresh,
            cron_schedule="30 2 * * 0",  # Sunday 02:30 (after arcgis, before enrichment)
            name="weekly_radar",
            execution_timezone=TIMEZONE,
        )
    )
