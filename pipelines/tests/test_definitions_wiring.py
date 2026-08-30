"""Guardrails on Dagster job/schedule wiring.

These tests lock in invariants that are easy to silently break:

* Every asset group a schedule targets has the right set of assets.
* `fema_flood_zones` is in its own group, not `bulk` (otherwise it would
  materialize twice per month under `bulk_refresh`).
* Every radar asset is reachable from `radar_refresh` so the weekly schedule
  keeps `development_signals` inputs fresh.
* Every scheduled job is actually registered in `Definitions`.

Run with: ``pytest tests/test_definitions_wiring.py -v``.
"""

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
    assert defs.schedules, "no schedules registered"
    assert defs.sensors, "no sensors registered"


def test_every_scheduled_job_is_registered(defs):
    registered_job_names = {j.name for j in defs.jobs}
    for schedule in defs.schedules:
        assert schedule.job_name in registered_job_names, (
            f"schedule {schedule.name} targets unregistered job {schedule.job_name}"
        )


def test_fema_refresh_only_covers_fema(asset_graph):
    from countyiq.jobs import fema_refresh, bulk_refresh

    fema_assets = _resolve(fema_refresh, asset_graph)
    bulk_assets = _resolve(bulk_refresh, asset_graph)

    assert fema_assets == ["fema_flood_zones"], fema_assets
    assert "fema_flood_zones" not in bulk_assets, (
        "fema_flood_zones must not be in bulk_refresh or it runs twice "
        "(monthly via bulk_refresh + weekly via fema_refresh)"
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


def test_no_schedule_selects_paid_llm_assets(defs, asset_graph):
    paid_assets = {
        "proceeding_extraction",
        "entity_verification",
        "signal_validation_batched",
        "brief_generation",
        "owner_briefs",
        "county_narratives",
    }
    for schedule in defs.schedules:
        selected = set(_resolve(schedule.job, asset_graph))
        assert not selected.intersection(paid_assets), (
            f"schedule {schedule.name} crosses the paid LLM boundary: "
            f"{selected.intersection(paid_assets)}"
        )


def test_pass1_manual_job_refreshes_candidate_inputs(asset_graph):
    from countyiq.jobs import entity_verification_refresh

    assert set(_resolve(entity_verification_refresh, asset_graph)) == {
        "municipality_join",
        "entity_candidate_pairs_refresh",
        "entity_verification",
    }


def test_paused_and_scout_assets_are_absent_from_every_schedule(asset_graph):
    from countyiq.jobs import (
        arcgis_refresh,
        bulk_refresh,
        enrichment_refresh,
        fema_refresh,
        radar_refresh,
        scraper_refresh,
    )

    scheduled_assets = set()
    for job in (
        arcgis_refresh,
        bulk_refresh,
        enrichment_refresh,
        fema_refresh,
        radar_refresh,
        scraper_refresh,
    ):
        scheduled_assets.update(_resolve(job, asset_graph))

    assert not scheduled_assets.intersection(
        {
            "cdbg_housing_arcgis",
            "ecodev_candidates_arcgis",
            "county_scout_discovery",
            "county_scout_monitor",
        }
    )


def test_schedule_names_are_stable(defs):
    """Production cron names are referenced in ops docs and runbook — keep
    them stable. Add new entries here when new schedules land."""
    expected = {
        "weekly_arcgis",
        "weekly_radar",
        "weekly_scrapers",
        "monthly_bulk",
        "weekly_fema",
        "weekly_deterministic_enrichment",
        "weekly_pa_dos",
    }
    actual = {s.name for s in defs.schedules}
    assert actual == expected, f"schedule set drifted: +{actual - expected} / -{expected - actual}"


def test_optional_radar_schedule_requires_a_configured_layer():
    """A parcel-only county must not launch an empty weekly radar run."""
    from countyiq.lib.county_config import CountyConfig
    from countyiq.schedules import _has_radar_sources

    assert not _has_radar_sources(CountyConfig(name="Example"))
    assert _has_radar_sources(CountyConfig(
        name="Example",
        pa_dep_query_bbox=(-77.0, 39.0, -76.0, 40.0),
    ))


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
