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
