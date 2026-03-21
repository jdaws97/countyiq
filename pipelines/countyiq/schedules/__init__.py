"""Schedule definitions for MVP pipeline jobs.

All 6 MVP sources run on weekly schedules. Monthly bulk schedule for
lower-frequency sources. Enrichment runs via sensor (see sensors/),
not cron.
"""

from dagster import ScheduleDefinition

from countyiq.jobs import arcgis_refresh, scraper_refresh, bulk_refresh, fema_refresh

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
]
