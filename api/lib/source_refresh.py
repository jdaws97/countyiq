"""Source-level refresh receipts, separate from grouped job outcomes."""

from datetime import datetime
from typing import TypedDict


class RefreshRun(TypedDict):
    job_name: str
    status: str
    started_at: datetime | None
    finished_at: datetime
    last_success_at: datetime | None


SOURCE_REFRESH_ASSETS: dict[str, tuple[str, ...]] = {
    "parcels": ("parcels_arcgis",),
    "municipalities": ("municipalities_arcgis",),
    "address_points": ("address_points_arcgis",),
    "structures": ("structures_arcgis",),
    "roads": ("roads_arcgis",),
    "zoning": ("zoning_arcgis",),
    "flood_zones": ("fema_flood_zones",),
    "plcb_licenses": ("plcb_licenses",),
    "penndot_roads": ("penndot_roads_arcgis",),
    "penndot_projects": ("penndot_projects_arcgis",),
    "tax_claims": ("tax_claims",),
    "sheriff_sales": ("sheriff_sales_scrape",),
    "traffic_counts": ("traffic_counts_arcgis",),
    "zipcodes": ("zipcodes_arcgis",),
    "zoning_overlays": ("zoning_overlays_arcgis",),
    "planning_subdivisions": ("planning_subdivisions_arcgis",),
    "growth_areas": ("growth_areas_arcgis",),
    "future_landuse": ("future_landuse_arcgis",),
    "conservation_easements": ("conservation_easements_arcgis",),
    "ag_security": ("ag_security_arcgis",),
    "economic_development_parks": (
        "business_parks_arcgis",
        "industrial_parks_arcgis",
    ),
    "soils": ("soils_arcgis",),
    "local_traffic_counts": ("local_traffic_counts_arcgis",),
    "environmental_diligence": ("pa_dep_environmental_diligence",),
}


def source_refresh_run(
    source_key: str,
    asset_runs: dict[str, RefreshRun],
) -> RefreshRun | None:
    """A composite source requires every contributing asset to be observed."""
    asset_keys = SOURCE_REFRESH_ASSETS[source_key]
    if any(key not in asset_runs for key in asset_keys):
        return None
    runs = [asset_runs[key] for key in asset_keys]
    latest = max(runs, key=lambda run: run["finished_at"])
    successes = [run["last_success_at"] for run in runs]
    last_success = None
    if all(value is not None for value in successes):
        last_success = min(value for value in successes if value is not None)
    return {
        "job_name": latest["job_name"],
        "status": (
            "success" if all(run["status"] == "success" for run in runs) else "failure"
        ),
        "started_at": None,
        "finished_at": latest["finished_at"],
        "last_success_at": last_success,
    }
