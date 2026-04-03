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

    # Recorder of Deeds (Tyler Records Public Access)
    recorder_base_url: str = ""              # Tyler self-service base URL
    recorder_parcel_search_id: str = ""      # Search ID for parcel/UPI search
    recorder_document_search_id: str = ""    # Search ID for date/name/doc search
    recorder_min_documents: int = 1
    recorder_max_parcels_per_run: int = 500
    recorder_throttle_seconds: float = 0.25
    recorder_session_refresh: int = 500

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

    # Tax Claim Bureau (Delinquent Tax Listing PDF)
    tax_claims_pdf_url: str = ""       # DocumentCenter PDF URL
    tax_claims_min_records: int = 5000  # Truncation guard (unique parcels)

    # Zip codes (GIS layer)
    arcgis_zipcodes_url: str = ""      # FeatureServer URL for zip code polygons

    # Traffic counts (PennDOT)
    traffic_counts_url: str = ""       # MapServer URL for traffic segments
    traffic_counts_cty_code: str = ""  # County code filter
    traffic_counts_min_records: int = 500

    # Sheriff sales
    sheriff_sales_url: str = ""        # Sheriff sale listing URL
    sheriff_sales_min_records: int = 10

    # Development radar ArcGIS layers
    arcgis_planning_subdivisions_url: str = ""
    arcgis_planning_subdivisions_min_records: int = 1000
    arcgis_ecodev_candidates_url: str = ""
    arcgis_growth_areas_url: str = ""
    arcgis_future_landuse_url: str = ""
    arcgis_conservation_easements_url: str = ""
    arcgis_ag_security_url: str = ""
    arcgis_cdbg_housing_url: str = ""

    # PA DOS Corporate Entities
    pa_dos_search_url: str = ""
    pa_dos_min_records: int = 100

    # Public Proceedings - tuple of (body_name, minutes_url, proceeding_type) tuples
    municipality_websites: tuple = ()

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
        recorder_base_url="https://webrecorders.yorkcountypa.gov/web/",
        recorder_parcel_search_id="DOCSEARCH41S1",
        recorder_document_search_id="DOCSEARCH138S1",
        recorder_min_documents=1,
        recorder_max_parcels_per_run=500,
        recorder_throttle_seconds=0.25,
        recorder_session_refresh=500,
        soda_datasets=(
            # (dataset_id, county_filter_field, county_filter_value, record_id_field)
            ("xvd7-5r2c", "shortcountyname", "York", ":id"),  # Registered Businesses in PA Current by County
        ),
        soda_min_records=10000,
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
        tax_claims_pdf_url="https://yorkcountypa.gov/DocumentCenter/View/1911/Delinquent-Tax-Claim-Listing-PDF",
        tax_claims_min_records=5000,
        arcgis_zipcodes_url="https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/Zipcodes/FeatureServer/0",
        traffic_counts_url="https://gis.penndot.gov/arcgis/rest/services/opendata/roadwaytraffic/MapServer/0",
        traffic_counts_cty_code="67",
        traffic_counts_min_records=1000,
        sheriff_sales_url="https://attorneyportal.yorkcountypa.gov/sheriff.salelisting/",
        sheriff_sales_min_records=10,
        arcgis_planning_subdivisions_url="https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/PLANNING_Subdivisions/FeatureServer/0",
        arcgis_planning_subdivisions_min_records=5000,
        arcgis_ecodev_candidates_url="https://arcweb1.ycpc.org/server/rest/services/Projects/EcoDev_Candidates_Parcels/FeatureServer/0",
        arcgis_growth_areas_url="https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/Growth_Areas/FeatureServer/0",
        arcgis_future_landuse_url="https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/LANDUSE_Future_Landuse/FeatureServer/0",
        arcgis_conservation_easements_url="https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/Conservation_Easements/FeatureServer/0",
        arcgis_ag_security_url="https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/Ag_Security/FeatureServer/0",
        arcgis_cdbg_housing_url="https://arcweb1.ycpc.org/server/rest/services/CDBG/CDBG_Housing_Locations/FeatureServer/0",
        pa_dos_search_url="https://file.dos.pa.gov/search/business",
        pa_dos_min_records=100,
        municipality_websites=(
            # Seed with a few known municipalities to prove the pipeline works
            # Full list will be populated by researching each municipality's website
        ),
        s3_prefix="york",
    ),
}


def get_county_config(county_key: str | None = None) -> CountyConfig:
    """Get the config for a county. Defaults to COUNTY env var, then 'york'."""
    if county_key is None:
        county_key = os.environ.get("COUNTY", "york")
    return COUNTY_CONFIGS[county_key]
