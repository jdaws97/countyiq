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

entity_verification_refresh = define_asset_job(
    name="entity_verification_refresh",
    selection=AssetSelection.assets("entity_verification"),
    description="Pass 1: entity verification across all sources",
)

signal_validation_refresh = define_asset_job(
    name="signal_validation_refresh",
    selection=AssetSelection.assets("signal_validation_batched"),
    description="Pass 2: validate all signals per parcel via batched LLM call",
)

brief_generation_refresh = define_asset_job(
    name="brief_generation_refresh",
    selection=AssetSelection.assets("brief_generation"),
    description="Pass 3: generate intelligence briefs from validated signals",
)

county_narratives_refresh = define_asset_job(
    name="county_narratives_refresh",
    selection=AssetSelection.assets("county_narratives"),
    description="Pass 4: detect cross-parcel patterns and generate county narratives",
)

intelligence_full_pipeline = define_asset_job(
    name="intelligence_full_pipeline",
    selection=AssetSelection.assets(
        "entity_verification", "signal_validation_batched",
        "development_momentum", "brief_generation", "county_narratives",
    ),
    description="Full intelligence pipeline: validated signals, product scoring, and Passes 1-4",
)
