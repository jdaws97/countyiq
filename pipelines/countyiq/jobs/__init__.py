"""Job definitions for grouping assets by source type."""

from dagster import define_asset_job, AssetSelection

arcgis_refresh = define_asset_job(
    name="arcgis_refresh",
    selection=AssetSelection.groups("arcgis"),
    description="Refresh all ArcGIS REST API data sources",
)

scraper_refresh = define_asset_job(
    name="scraper_refresh",
    selection=AssetSelection.groups("scrapers"),
    description="Refresh all Playwright/BeautifulSoup scraper sources",
)

bulk_refresh = define_asset_job(
    name="bulk_refresh",
    selection=AssetSelection.groups("bulk"),
    description="Refresh all bulk download / API sources",
)

enrichment_refresh = define_asset_job(
    name="enrichment_refresh",
    selection=AssetSelection.groups("enrichment"),
    description="Run entity resolution and enrichment assets",
)

fema_refresh = define_asset_job(
    name="fema_refresh",
    selection=AssetSelection.assets("fema_flood_zones"),
    description="Refresh FEMA flood hazard zone data",
)

scout_discovery_refresh = define_asset_job(
    name="scout_discovery_refresh",
    selection=AssetSelection.assets("county_scout_discovery"),
    description="Discover and classify new County Scout source candidates",
)

scout_monitor_refresh = define_asset_job(
    name="scout_monitor_refresh",
    selection=AssetSelection.assets("county_scout_monitor"),
    description="Monitor promoted County Scout sources for changes and outages",
)
