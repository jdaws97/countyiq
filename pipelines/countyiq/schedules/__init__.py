"""Schedule definitions for MVP pipeline jobs.

All 6 MVP sources run on weekly schedules. Monthly bulk schedule for
lower-frequency sources. Enrichment runs via sensor (see sensors/),
not cron.
"""

from dagster import ScheduleDefinition

from countyiq.jobs import (
    arcgis_refresh,
    bulk_refresh,
    enrichment_refresh,
    fema_refresh,
    scout_discovery_refresh,
    scout_monitor_refresh,
    scraper_refresh,
)

all_schedules = [
    ScheduleDefinition(
        job=arcgis_refresh,
        cron_schedule="0 2 * * 0",  # Sunday 02:00
        name="weekly_arcgis",
    ),
    ScheduleDefinition(
        job=scraper_refresh,
        cron_schedule="0 3 * * 1",  # Monday 03:00
        name="weekly_scrapers",
    ),
    ScheduleDefinition(
        job=bulk_refresh,
        cron_schedule="0 5 1 * *",  # 1st of month 05:00
        name="monthly_bulk",
    ),
    ScheduleDefinition(
        job=fema_refresh,
        cron_schedule="0 4 * * 0",  # Sunday 04:00
        name="weekly_fema",
    ),
    ScheduleDefinition(
        job=scout_discovery_refresh,
        cron_schedule="30 1 * * 3",  # Wednesday 01:30
        name="weekly_scout_discovery",
    ),
    ScheduleDefinition(
        job=scout_monitor_refresh,
        cron_schedule="30 6 * * *",  # Daily 06:30
        name="daily_scout_monitor",
    ),
    ScheduleDefinition(
        job=enrichment_refresh,
        cron_schedule="0 8 * * 0",  # Sunday 08:00 (after source pipelines)
        name="weekly_enrichment",
    ),
]
