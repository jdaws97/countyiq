"""Dagster asset jobs.

Two categories:

1. **Scheduled jobs** — cost-isolated jobs wired to cron in
   ``schedules/__init__.py``. These cover source refreshes and deterministic
   enrichment only. Paid LLM passes are never selected by a schedule.

2. **Manual-trigger jobs** — single-asset or composite jobs that target a specific
   pass or source. They are redundant with the scheduled group jobs and exist
   only so an operator can re-run one pass (e.g. after a prompt change) without
   rematerializing the full enrichment chain. Launch from the Dagster UI.
"""

from dagster import AssetSelection, define_asset_job

from countyiq.lib.county_config import get_county_config

_county = get_county_config()

plan_review_pilot = define_asset_job(
    name="plan_review_pilot",
    selection=AssetSelection.assets("plan_review_snapshot"),
    description="Manually retain the newest official review snapshot for private evaluation",
)


def _configured_assets(pairs: tuple[tuple[str, object], ...]) -> AssetSelection:
    """Select only assets backed by a configured county capability."""

    return AssetSelection.assets(*(asset_name for asset_name, value in pairs if value))


# -----------------------------------------------------------------------------
# Scheduled jobs (production refresh path)
# -----------------------------------------------------------------------------

arcgis_refresh = define_asset_job(
    name="arcgis_refresh",
    selection=_configured_assets(
        (
            ("parcels_arcgis", _county.arcgis_parcels_url),
            ("zoning_arcgis", _county.arcgis_zoning_url),
            ("roads_arcgis", _county.arcgis_roads_url),
            ("structures_arcgis", _county.arcgis_structures_url),
            ("municipalities_arcgis", _county.arcgis_municipalities_url),
            ("address_points_arcgis", _county.arcgis_address_pts_url),
            ("zipcodes_arcgis", _county.arcgis_zipcodes_url),
            ("traffic_counts_arcgis", _county.traffic_counts_url),
            ("penndot_roads_arcgis", _county.penndot_roads_url),
            ("penndot_projects_arcgis", _county.penndot_projects_url),
        )
    ),
    description="Refresh all ArcGIS REST API data sources",
)

radar_refresh = define_asset_job(
    name="radar_refresh",
    selection=_configured_assets(
        (
            ("planning_subdivisions_arcgis", _county.arcgis_planning_subdivisions_url),
            ("growth_areas_arcgis", _county.arcgis_growth_areas_url),
            ("future_landuse_arcgis", _county.arcgis_future_landuse_url),
            (
                "conservation_easements_arcgis",
                _county.arcgis_conservation_easements_url,
            ),
            ("ag_security_arcgis", _county.arcgis_ag_security_url),
            ("zoning_overlays_arcgis", _county.arcgis_zoning_overlays_url),
            ("business_parks_arcgis", _county.arcgis_business_parks_url),
            ("industrial_parks_arcgis", _county.arcgis_industrial_parks_url),
            ("soils_arcgis", _county.arcgis_soils_url),
            ("local_traffic_counts_arcgis", _county.arcgis_local_traffic_counts_url),
            ("pa_dep_environmental_diligence", _county.pa_dep_query_bbox),
        )
    ),
    description="Refresh development-radar ArcGIS layers (upstream of development_signals)",
)

scraper_refresh = define_asset_job(
    name="scraper_refresh",
    selection=_configured_assets(
        (
            ("public_proceedings_scrape", _county.municipality_websites),
            ("sheriff_sales_scrape", _county.sheriff_sales_url),
        )
    ),
    description="Refresh bounded municipal proceedings and sheriff-sale sources",
)

bulk_refresh = define_asset_job(
    name="bulk_refresh",
    selection=_configured_assets(
        (
            ("plcb_licenses", _county.plcb_filter),
            ("tax_claims", _county.tax_claims_pdf_url),
        )
    ),
    description="Refresh all bulk download / API sources",
)

fema_refresh = define_asset_job(
    name="fema_refresh",
    selection=AssetSelection.groups("fema"),
    description="Refresh FEMA flood hazard zone data",
)

enrichment_refresh = define_asset_job(
    name="enrichment_refresh",
    selection=AssetSelection.groups("enrichment"),
    description="Run entity resolution, signal validation, and intelligence passes",
)

# Safe first-load/rebuild path. This selection intentionally names only assets
# that make no provider calls; paid passes remain available through the full
# enrichment job and pass-specific manual jobs after an estimate and review.
deterministic_enrichment_refresh = define_asset_job(
    name="deterministic_enrichment_refresh",
    selection=AssetSelection.assets(
        "municipality_join",
        "entity_candidate_pairs_refresh",
        "municipal_evidence_linking",
        "development_signals",
        "owner_resolution",
        "parcel_events",
        "intelligence_events",
        "development_momentum",
    ),
    description="Rebuild deterministic joins, signals, identities, events, and momentum without LLM calls",
)

# -----------------------------------------------------------------------------
# Manual-trigger jobs (operator re-runs for individual sources / passes)
#
# These do NOT have schedules. They exist so you can re-run one piece of the
# pipeline without rematerializing its whole group. Example: tweaking the
# Pass 2 validation prompt and wanting to re-score without re-running Pass 1.
# -----------------------------------------------------------------------------

pa_dos_refresh = define_asset_job(
    name="pa_dos_refresh",
    selection=AssetSelection.assets("pa_dos_entities"),
    description="Run one bounded, resumable PA DOS statewide open-data lookup batch",
)

proceedings_refresh = define_asset_job(
    name="proceedings_refresh",
    selection=AssetSelection.assets("public_proceedings_scrape"),
    description="[Manual] Re-scrape meeting minutes for all municipalities",
)

proceedings_extraction_refresh = define_asset_job(
    name="proceedings_extraction_refresh",
    selection=AssetSelection.assets(
        "proceeding_extraction",
        "municipal_evidence_linking",
        "development_signals",
        "intelligence_events",
        "development_momentum",
    ),
    description="[Manual] Read municipal sources, link property references, and refresh watched events",
)

entity_verification_refresh = define_asset_job(
    name="entity_verification_refresh",
    selection=AssetSelection.assets(
        "municipality_join",
        "entity_candidate_pairs_refresh",
        "municipal_evidence_linking",
        "entity_verification",
        "development_signals",
        "owner_resolution",
    ),
    description=(
        "[Manual] Refresh candidate pairs, run Pass 1, then rebuild the "
        "Pass 0-derived signals and Pass 1-derived owner projection"
    ),
)

signal_validation_refresh = define_asset_job(
    name="signal_validation_refresh",
    selection=AssetSelection.assets("signal_validation_batched"),
    description="[Manual] Re-run Pass 2: batched signal validation per parcel",
)

brief_generation_refresh = define_asset_job(
    name="brief_generation_refresh",
    selection=AssetSelection.assets("brief_generation"),
    description="[Manual] Re-run Pass 3: generate intelligence briefs",
)

record_intelligence_refresh = define_asset_job(
    name="record_intelligence_refresh",
    selection=AssetSelection.assets(
        "municipal_record_explanations",
        "municipal_matter_explanations",
        "property_record_explanations",
        "intelligence_events",
    ),
    description="[Manual] Explain current records and case histories, then refresh municipal activity",
)

owner_briefs_refresh = define_asset_job(
    name="owner_briefs_refresh",
    selection=AssetSelection.assets("owner_briefs"),
    description="[Manual] Re-run Pass 3b: generate owner portfolio briefs",
)

county_narratives_refresh = define_asset_job(
    name="county_narratives_refresh",
    selection=AssetSelection.assets("county_narratives"),
    description="[Manual] Re-run Pass 4: cross-parcel patterns and county narratives",
)

emerging_intelligence_refresh = define_asset_job(
    name="emerging_intelligence_refresh",
    selection=AssetSelection.assets("emerging_intelligence_drafts"),
    description="[Manual] Assess explicit evidence scopes; drafts require a separate publication review",
)

intelligence_data_refresh = define_asset_job(
    name="intelligence_data_refresh",
    selection=AssetSelection.assets(
        "pa_dos_entities",
        "public_proceedings_scrape",
        "proceeding_extraction",
        "municipal_evidence_linking",
        "development_signals",
        "intelligence_events",
        "development_momentum",
    ),
    description="[Manual] Re-pull all intelligence source data (PA DOS + proceedings + Pass 0)",
)

intelligence_full_pipeline = define_asset_job(
    name="intelligence_full_pipeline",
    selection=AssetSelection.assets(
        "entity_verification",
        "signal_validation_batched",
        "development_momentum",
        "brief_generation",
        "municipal_record_explanations",
        "municipal_matter_explanations",
        "property_record_explanations",
        "county_narratives",
        "intelligence_events",
    ),
    description="[Manual] Re-run Passes 1–4 end-to-end (skips source scrapes and Pass 0)",
)
