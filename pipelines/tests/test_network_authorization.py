"""External reads must remain behind the source-rights decision point."""

import inspect
from pathlib import Path

import pytest
from countyiq.assets.arcgis import (
    address_points,
    ag_security,
    cdbg_housing,
    conservation_easements,
    ecodev_candidates,
    future_landuse,
    growth_areas,
    municipalities,
    parcels,
    penndot_projects,
    penndot_roads,
    planning_subdivisions,
    roads,
    site_readiness,
    structures,
    traffic_counts,
    zipcodes,
    zoning,
)
from countyiq.assets.bulk import fema_flood, pa_open_data, plcb, tax_claims
from countyiq.assets.enrichment import proceeding_extraction
from countyiq.assets.scrapers import pa_dos_entities, public_proceedings, sheriff_sales

GOVERNED_INGESTION_FUNCTIONS = [
    address_points.address_points_arcgis,
    ag_security.ag_security_arcgis,
    cdbg_housing.cdbg_housing_arcgis,
    conservation_easements.conservation_easements_arcgis,
    ecodev_candidates.ecodev_candidates_arcgis,
    future_landuse.future_landuse_arcgis,
    growth_areas.growth_areas_arcgis,
    municipalities.municipalities_arcgis,
    parcels.parcels_arcgis,
    penndot_projects.penndot_projects_arcgis,
    penndot_roads.penndot_roads_arcgis,
    planning_subdivisions.planning_subdivisions_arcgis,
    roads.roads_arcgis,
    site_readiness._authorize,
    structures.structures_arcgis,
    traffic_counts.traffic_counts_arcgis,
    zipcodes.zipcodes_arcgis,
    zoning.zoning_arcgis,
    fema_flood.fema_flood_zones,
    pa_open_data.pa_open_data,
    plcb.plcb_licenses,
    tax_claims.tax_claims,
    pa_dos_entities.pa_dos_entities,
    public_proceedings.public_proceedings_scrape,
    sheriff_sales.sheriff_sales_scrape,
    proceeding_extraction.proceeding_extraction,
]


def _decorated_source(function) -> str:
    decorated = getattr(
        getattr(getattr(function, "node_def", None), "compute_fn", None),
        "decorated_fn",
        function,
    )
    return inspect.getsource(decorated)


@pytest.mark.parametrize(
    "function",
    [
        address_points.address_points_schema_drift,
        municipalities.municipalities_schema_drift,
        parcels.parcels_schema_drift,
        penndot_projects.penndot_projects_schema_drift,
        penndot_roads.penndot_roads_schema_drift,
        roads.roads_schema_drift,
        structures.structures_schema_drift,
        zoning.zoning_schema_drift,
        fema_flood.fema_schema_drift,
        pa_open_data.pa_open_data_schema_drift,
        plcb.plcb_no_schema_drift,
        proceeding_extraction.proceeding_extraction,
    ],
)
def test_network_function_authorizes_before_request(function):
    source = _decorated_source(function)
    request_offsets = [
        offset
        for token in ("requests.get(", "get_with_retry(", "source_snapshots.metadata(")
        if (offset := source.find(token)) >= 0
    ]
    assert request_offsets, function
    assert 0 <= source.find("authorize_source(") < min(request_offsets)


@pytest.mark.parametrize("function", GOVERNED_INGESTION_FUNCTIONS)
def test_ingestion_requires_derived_product_permission(function):
    source = _decorated_source(function)
    authorization_offset = source.find("authorize_source(")
    if authorization_offset < 0:
        authorization_offset = source.find("authorize_municipality_sources(")
    derived_offset = source.find('"derived_product"')

    assert authorization_offset >= 0, function
    assert derived_offset > authorization_offset, function


def test_every_governed_raw_archive_checks_retention_policy():
    assets_root = Path(__file__).parents[1] / "countyiq" / "assets"
    missing: list[str] = []
    for path in assets_root.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if "s3.archive" not in source:
            continue
        if "require_source_use" not in source:
            missing.append(str(path))

    assert not missing, f"raw archives without retention enforcement: {missing}"


def test_sheriff_listing_fetch_is_robots_gated():
    source = _decorated_source(sheriff_sales.sheriff_sales_scrape)

    assert source.find("authorize_source(") < source.find("get_with_robots(")
    assert "get_with_retry(" not in source
