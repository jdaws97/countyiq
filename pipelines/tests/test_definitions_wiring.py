"""Dagster asset selections and registered quality checks for local jobs."""

from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def defs():
    from countyiq.definitions import defs as _defs

    return _defs


@pytest.fixture(scope="module")
def asset_graph(defs):
    return defs.resolve_asset_graph()


def _resolve(job, graph):
    return sorted(k.to_user_string() for k in job.selection.resolve(graph))


def test_definitions_load(defs):
    assert defs.jobs, "no jobs registered"


def test_fema_refresh_only_covers_fema(asset_graph):
    from countyiq.jobs import bulk_refresh, fema_refresh

    fema_assets = _resolve(fema_refresh, asset_graph)
    bulk_assets = _resolve(bulk_refresh, asset_graph)

    assert fema_assets == ["fema_flood_zones"], fema_assets
    assert "fema_flood_zones" not in bulk_assets, (
        "FEMA has a dedicated refresh job and must not run with bulk sources"
    )


def test_radar_refresh_covers_all_radar_deps(asset_graph):
    """radar_refresh must cover every asset that `development_signals` depends on
    within the radar group; otherwise enrichment consumes stale layers."""
    from countyiq.jobs import radar_refresh

    radar_assets = set(_resolve(radar_refresh, asset_graph))
    expected = {
        "growth_areas_arcgis",
        "future_landuse_arcgis",
        "planning_subdivisions_arcgis",
        "conservation_easements_arcgis",
        "ag_security_arcgis",
        "zoning_overlays_arcgis",
        "business_parks_arcgis",
        "industrial_parks_arcgis",
        "soils_arcgis",
        "local_traffic_counts_arcgis",
        "pa_dep_environmental_diligence",
    }
    missing = expected - radar_assets
    assert not missing, f"radar_refresh is missing radar assets: {missing}"


def test_bulk_refresh_has_expected_sources(asset_graph):
    from countyiq.jobs import bulk_refresh

    assert set(_resolve(bulk_refresh, asset_graph)) == {
        "plcb_licenses",
        "tax_claims",
    }


def test_arcgis_and_radar_are_disjoint(asset_graph):
    """An asset belongs to exactly one of arcgis / radar so group-level jobs
    don't double-materialize."""
    from countyiq.jobs import arcgis_refresh, radar_refresh

    arcgis = set(_resolve(arcgis_refresh, asset_graph))
    radar = set(_resolve(radar_refresh, asset_graph))
    assert not (arcgis & radar), f"overlap: {arcgis & radar}"


def test_deterministic_enrichment_job_excludes_paid_passes(asset_graph):
    from countyiq.jobs import deterministic_enrichment_refresh

    assert set(_resolve(deterministic_enrichment_refresh, asset_graph)) == {
        "municipal_evidence_linking",
        "municipality_join",
        "entity_candidate_pairs_refresh",
        "development_signals",
        "owner_resolution",
        "parcel_events",
        "intelligence_events",
        "development_momentum",
    }


def test_scraper_job_excludes_pa_dos(asset_graph):
    from countyiq.jobs import scraper_refresh

    assets = set(_resolve(scraper_refresh, asset_graph))
    assert assets == {"public_proceedings_scrape", "sheriff_sales_scrape"}
    assert "pa_dos_entities" not in assets


def test_pass1_manual_job_refreshes_candidate_inputs(asset_graph):
    from countyiq.jobs import entity_verification_refresh

    assert set(_resolve(entity_verification_refresh, asset_graph)) == {
        "municipal_evidence_linking",
        "municipality_join",
        "entity_candidate_pairs_refresh",
        "entity_verification",
        "development_signals",
        "owner_resolution",
    }


def test_pass3_manual_jobs_keep_parcel_and_owner_budgets_separate(asset_graph):
    from countyiq.jobs import brief_generation_refresh, owner_briefs_refresh

    assert set(_resolve(brief_generation_refresh, asset_graph)) == {"brief_generation"}
    assert set(_resolve(owner_briefs_refresh, asset_graph)) == {"owner_briefs"}


def test_paused_assets_are_absent_from_refresh_jobs(asset_graph):
    from countyiq.jobs import (
        arcgis_refresh,
        bulk_refresh,
        enrichment_refresh,
        fema_refresh,
        radar_refresh,
        scraper_refresh,
    )

    refresh_assets = set()
    for job in (
        arcgis_refresh,
        bulk_refresh,
        enrichment_refresh,
        fema_refresh,
        radar_refresh,
        scraper_refresh,
    ):
        refresh_assets.update(_resolve(job, asset_graph))

    assert not refresh_assets.intersection(
        {
            "cdbg_housing_arcgis",
            "ecodev_candidates_arcgis",
        }
    )


def test_asset_checks_are_registered():
    """load_assets_from_package_module does NOT collect AssetChecksDefinition
    objects — every check in the repo was silently unregistered until
    Definitions gained asset_checks= (2026-08-02). Pin it."""
    from countyiq.definitions import defs

    names = {k.name for k in defs.get_repository_def().asset_graph.asset_check_keys}
    assert len(names) >= 40, f"expected the full check suite, got {len(names)}"
    # One from each family: source row counts, schema drift, enrichment outputs.
    assert "parcels_record_count" in names
    assert "parcels_schema_drift" in names
    assert "development_signals_nonempty" in names
    assert "owner_briefs_nonempty" in names
