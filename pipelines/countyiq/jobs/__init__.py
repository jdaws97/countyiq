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

radar_refresh = define_asset_job(
    name="radar_refresh",
    selection=AssetSelection.groups("radar"),
    description="Refresh all development radar ArcGIS layers",
)

pa_dos_refresh = define_asset_job(
    name="pa_dos_refresh",
    selection=AssetSelection.assets("pa_dos_entities"),
    description="Refresh PA DOS corporate entity lookups",
)

proceedings_refresh = define_asset_job(
    name="proceedings_refresh",
    selection=AssetSelection.assets("public_proceedings_scrape"),
    description="Scrape meeting minutes from all York County municipalities",
)

proceedings_extraction_refresh = define_asset_job(
    name="proceedings_extraction_refresh",
    selection=AssetSelection.assets("proceeding_extraction"),
    description="Run Pass 0: extract structured records from meeting minute PDFs",
)

intelligence_data_refresh = define_asset_job(
    name="intelligence_data_refresh",
    selection=AssetSelection.assets("pa_dos_entities", "public_proceedings_scrape", "proceeding_extraction"),
    description="Full intelligence data pipeline: PA DOS + proceedings + extraction",
)
