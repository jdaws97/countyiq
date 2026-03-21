"""County-specific configuration for multi-county pipeline support.

Each county has its own config with source URLs, filter strings, and thresholds.
The active county is selected by the COUNTY env var (default: "york").

To add a new county:
  1. Add a CountyConfig entry to COUNTY_CONFIGS
  2. Fill in the source URLs and thresholds for that county
  3. Set COUNTY=<key> when running pipelines
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class CountyConfig:
    """Configuration for a single county's data sources."""

    # Identity
    name: str                       # e.g. "York County"
    state: str = "PA"

    # PLCB liquor licenses (statewide CSV, filtered by county name)
    plcb_filter: str = ""           # Value in the "County" CSV column
    plcb_min_records: int = 100     # Minimum expected records (truncation guard)

    # ArcGIS GIS Portal
    arcgis_parcels_url: str = ""    # FeatureServer/0 URL for parcels layer
    arcgis_base_url: str = ""       # Base REST services URL
    arcgis_zoning_url: str = ""     # FeatureServer/0 URL for zoning layer
    arcgis_roads_url: str = ""      # FeatureServer/0 URL for roads layer
    arcgis_structures_url: str = "" # FeatureServer/0 URL for building footprints
    arcgis_municipalities_url: str = ""  # FeatureServer/0 URL for municipal boundaries
    arcgis_address_pts_url: str = ""     # FeatureServer/0 URL for address points
    arcgis_zoning_min_records: int = 100
    arcgis_roads_min_records: int = 1000
    arcgis_structures_min_records: int = 10000
    arcgis_municipalities_min_records: int = 10
    arcgis_address_pts_min_records: int = 10000

    # Assessment portal
    assessment_url: str = ""        # Assessment portal base URL
    assessment_min_records: int = 1000
    assessment_max_per_run: int = 500         # Tier 2 properties per execution
    assessment_throttle_seconds: float = 5.0  # Delay between all requests
    assessment_session_refresh: int = 200     # Re-establish session after N detail pages

    # PA Open Data Portal (SODA API)
    soda_base_url: str = "https://data.pa.gov/resource"
    soda_datasets: tuple = ()        # Tuple of (dataset_id, county_filter_field, county_filter_value, record_id_field) tuples
    soda_min_records: int = 50       # Minimum expected records per dataset (truncation guard)

    # PennDOT Open Data (state road segments — MapServer)
    penndot_roads_url: str = ""      # MapServer/0 URL for roadway segments
    penndot_roads_cty_code: str = "" # CTY_CODE filter value
    penndot_roads_min_records: int = 500

    # PennDOT Projects (PA Projects MapServer)
    penndot_projects_url: str = ""   # MapServer base URL
    penndot_projects_layers: tuple = (1, 2, 4, 5)  # Underway, 4yr plan, under dev, under construction
    penndot_projects_county_filter: str = ""  # COUNTY_NAME filter value
    penndot_projects_min_records: int = 10

    # FEMA National Flood Hazard Layer
    fema_nfhl_url: str = ""          # MapServer base URL
    fema_flood_layer: int = 28       # S_Fld_Haz_Ar layer ID
    fema_dfirm_id: str = ""          # County DFIRM ID for filtering
    fema_min_records: int = 100      # Minimum expected records (truncation guard)

    # S3 archive prefix (raw data goes to s3://york-county-raw/<prefix>/...)
    s3_prefix: str = ""


COUNTY_CONFIGS: dict[str, CountyConfig] = {
    "york": CountyConfig(
        name="York County",
        plcb_filter="York County",
        plcb_min_records=500,
        arcgis_parcels_url="https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/Parcels/FeatureServer/0",
        arcgis_base_url="https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA",
        arcgis_zoning_url="https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/Zoning/FeatureServer/0",
        arcgis_roads_url="https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/Roads/FeatureServer/0",
        arcgis_structures_url="https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/BLDG_Footprint/FeatureServer/0",
        arcgis_municipalities_url="https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/Municipal_Boundary/FeatureServer/0",
        arcgis_address_pts_url="https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/AddressPts/FeatureServer/0",
        arcgis_zoning_min_records=500,
        arcgis_roads_min_records=10000,
        arcgis_structures_min_records=100000,
        arcgis_municipalities_min_records=50,
        arcgis_address_pts_min_records=100000,
        assessment_url="https://assessmentpublic.yorkcountypa.gov/",
        assessment_min_records=150000,
        soda_datasets=(
            # (dataset_id, county_filter_field, county_filter_value, record_id_field)
            ("xvd7-5r2c", "county", "YORK", ":id"),  # Registered Businesses in PA Current by County
        ),
        soda_min_records=100,
        penndot_roads_url="https://gis.penndot.gov/arcgis/rest/services/opendata/roadwaysegments/MapServer/0",
        penndot_roads_cty_code="67",
        penndot_roads_min_records=1000,
        penndot_projects_url="https://gis.penndot.gov/arcgis/rest/services/paprojects/paprojects/MapServer",
        penndot_projects_layers=(1, 2, 4, 5),
        penndot_projects_county_filter="YORK",
        penndot_projects_min_records=5,
        fema_nfhl_url="https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer",
        fema_flood_layer=28,
        fema_dfirm_id="42133C",
        fema_min_records=3000,
        s3_prefix="york",
    ),
}


def get_county_config(county_key: str | None = None) -> CountyConfig:
    """Get the config for a county. Defaults to COUNTY env var, then 'york'."""
    if county_key is None:
        county_key = os.environ.get("COUNTY", "york")
    return COUNTY_CONFIGS[county_key]
