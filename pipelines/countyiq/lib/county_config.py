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
    soda_datasets: tuple[tuple[str, str, str, str], ...] = ()
    soda_min_records: int = 50       # Minimum expected records per dataset (truncation guard)

    # PennDOT Open Data (state road segments — MapServer)
    penndot_roads_url: str = ""      # MapServer/0 URL for roadway segments
    penndot_roads_cty_code: str = "" # CTY_CODE filter value
    penndot_roads_min_records: int = 500

    # PennDOT Projects (PA Projects MapServer)
    penndot_projects_url: str = ""   # MapServer base URL
    penndot_projects_layers: tuple[int, ...] = (1, 2, 4, 5)
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
    municipality_websites: tuple[tuple[str, str, str], ...] = ()

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
            # Format: (body_name, minutes_page_url, proceeding_type)
            # Surveyed 2026-04-08 via Playwright. 90 entries across 40+ municipalities.
            # ZHB: 22 dedicated pages. PC: 24 dedicated pages.

            # ================================================================
            # BOARD OF SUPERVISORS / BOROUGH COUNCIL / CITY COUNCIL
            # ================================================================

            # --- CivicEngage AgendaCenter sites ---
            ("Hanover Borough Council", "https://hanoverboroughpa.gov/AgendaCenter", "borough_council"),
            ("Monaghan Twp Board of Supervisors", "https://monaghantownship.com/AgendaCenter", "board_of_supervisors"),

            # --- CourseVector / PA Boroughs template sites ---
            ("Hallam Borough Council", "https://hallamborough.com/library/agendas-minutes", "borough_council"),
            ("Lewisberry Borough Council", "https://lewisberryborough.org/residents/meeting-agendas-and-minutes/", "borough_council"),
            ("Manchester Borough Council", "https://manchesterborough.gov/documents/meeting-minutes-agendas/", "borough_council"),
            ("New Salem Borough Council", "https://newsalemborough.org/government/agendas-minutes/", "borough_council"),
            ("York Haven Borough Council", "https://yorkhavenborough.org/administration/borough-council-meeting-agendas-minutes/", "borough_council"),

            # --- WordPress / custom CMS sites ---
            ("Carroll Twp Board of Supervisors", "https://www.carrolltownship.com/bos-agenda-2024/", "board_of_supervisors"),
            ("Codorus Twp Board of Supervisors", "https://codorustownship.org/meeting-minutes/", "board_of_supervisors"),
            # York County's Conewago Twp is conewagotwp.com (conewagotownship.com is Dauphin County)
            ("Conewago Twp Board of Supervisors", "https://www.conewagotwp.com/board-of-supervisors/", "board_of_supervisors"),
            ("Dallastown Borough Council", "https://dallastownboro.com/meetings-agendas-minutes/", "borough_council"),
            ("Dover Twp Board of Supervisors", "https://www.dovertownship.org/minutes/", "board_of_supervisors"),
            # East Hopewell is a Wix site; minutes live under /board-of-supervisors
            ("East Hopewell Twp Board of Supervisors", "https://www.easthopewelltownshippa.gov/board-of-supervisors", "board_of_supervisors"),
            ("East Manchester Twp Board of Supervisors", "https://emanchestertwp.com/boards-and-committees/meetings-archive/", "board_of_supervisors"),
            ("East Prospect Borough Council", "https://www.eastprospectborough.com/minutes", "borough_council"),
            # Fairview Twp actual site is twp.fairview.pa.us (not fairviewtownship.com)
            ("Fairview Twp Board of Supervisors", "https://twp.fairview.pa.us/board-of-supervisors/", "board_of_supervisors"),
            ("Fawn Grove Borough Council", "https://fawngroveborough.org/documents/council-meeting-minutes/", "borough_council"),
            # Fawn Twp actual site is fawntwp.org (not fawntownship.com which has WordPress error)
            ("Fawn Twp Board of Supervisors", "https://fawntwp.org/monthly-meeting-minutes/", "board_of_supervisors"),
            ("Felton Borough Council", "https://feltonboroughpa.com/documents/minutes/", "borough_council"),
            ("Franklin Twp Board of Supervisors", "https://franklintownship.org/meeting-minutes-agendas/", "board_of_supervisors"),
            ("Goldsboro Borough Council", "https://goldsboropa.com/document-library-2/", "borough_council"),
            ("Hellam Twp Board of Supervisors", "https://www.hellamtownship.gov/departments/public-meetings/", "board_of_supervisors"),
            ("Hopewell Twp Board of Supervisors", "https://www.hopewelltownship.com/public-meetings/board-of-supervisors/", "board_of_supervisors"),
            ("Jackson Twp Board of Supervisors", "https://jackson-township.org/meeting-agendas/", "board_of_supervisors"),
            ("Manchester Twp Board of Supervisors", "https://www.mantwp.com/meetings-agendas/", "board_of_supervisors"),
            ("Manheim Twp Board of Supervisors", "https://www.manheimtwpyorkpa.org/index.php/government/minutes-agendas", "board_of_supervisors"),
            ("North Codorus Twp Board of Supervisors", "https://northcodorustwp.org/board-of-supervisors-3/", "board_of_supervisors"),
            ("North York Borough Council", "https://northyorkborough.com/borough-council-meeting-minutes/", "borough_council"),
            ("Paradise Twp Board of Supervisors", "https://paradisetownship.org/documents/board-of-supervisor-agenda-notices/", "board_of_supervisors"),
            ("Peach Bottom Twp Board of Supervisors", "https://www.peachbottomtownship.org/meeting-minutes", "board_of_supervisors"),
            # Penn Twp /meeting-minutes/ page is empty; all 238 PDFs live at /documents/
            ("Penn Twp Board of Supervisors", "https://penntownship.org/documents/", "board_of_supervisors"),
            ("Red Lion Borough Council", "https://redlionpa.org/government/agendas-minutes/borough-council-agendas-minutes/", "borough_council"),
            ("Seven Valleys Borough Council", "https://sevenvalleysborough.com/minutes/", "borough_council"),
            ("Shrewsbury Borough Council", "https://shrewsburyborough.org/minutes/", "borough_council"),
            ("Shrewsbury Twp Board of Supervisors", "https://www.shrewsburytownship.org/minutes/", "board_of_supervisors"),
            ("Spring Garden Twp Board of Supervisors", "https://www.springgardentwp.org/meeting-minutes/", "board_of_supervisors"),
            ("Spring Grove Borough Council", "https://www.springgrovepa.gov/meeting-minutes", "borough_council"),
            ("Springfield Twp Board of Supervisors", "https://springfieldyork.org/meeting-minutes/", "board_of_supervisors"),
            ("Springettsbury Twp Board of Supervisors", "https://springettsbury.com/township-document-archives/", "board_of_supervisors"),
            ("Wellsville Borough Council", "https://wellsvilleborough.com/boards-commissions/borough-council-agenda-budget/", "borough_council"),
            ("West Manchester Twp Board of Supervisors", "https://www.westmanchestertownship.com/boards-committees/board-of-supervisors/", "board_of_supervisors"),
            ("West Manheim Twp Board of Supervisors", "https://westmanheimtwp.com/boards-comissions/board-of-supervisors/minutes/", "board_of_supervisors"),
            ("Windsor Twp Board of Supervisors", "https://windsortownship.com/events-minutes/board-of-trustees/", "board_of_supervisors"),
            ("Wrightsville Borough Council", "https://wrightsvilleborough.com/meeting-minutes/", "borough_council"),
            ("Yoe Borough Council", "https://yoeborough.org/information/minutes/", "borough_council"),
            ("Yorkana Borough Council", "https://yorkanaborough.com/meeting-minutes/", "borough_council"),
            ("York City Council", "https://www.yorkcity.org/government/city-council/meetings/", "city_council"),
            ("York Twp Board of Commissioners", "https://yorktownshippa.gov/boards/boc/", "board_of_commissioners"),

            # --- Added 2026-04-08 deep survey ---
            ("Chanceford Twp Board of Supervisors", "https://www.chancefordtwp.com/Minutes.html", "board_of_supervisors"),
            ("Delta Borough Council", "https://www.deltaborough.us/current-meeting-minutes", "borough_council"),
            ("Dillsburg Borough Council", "https://dillsburg.com/minutes/", "borough_council"),
            ("Dover Borough Council", "https://www.doverboroughpa.com/minutes.html", "borough_council"),
            ("Franklintown Borough Council", "https://franklintownborough.net/notices%2Fagendas%2Fminutes", "borough_council"),
            ("Glen Rock Borough Council", "https://www.glenrockpa.org/borough-government/council-meeting-minutes-agendas/", "borough_council"),
            ("Jacobus Borough Council", "https://jacobuspa.com/council-meeting/council-meeting-minutes/", "borough_council"),
            ("Jefferson Borough Council", "https://jeffersonboro.net/council-minutes-agendas", "borough_council"),
            ("Loganville Borough Council", "https://loganvilleborough.com/loganville_borough_council", "borough_council"),
            ("Lower Chanceford Twp Board of Supervisors", "https://lowerchancefordtwppa.gov/meetings.php", "board_of_supervisors"),
            ("Lower Windsor Twp Board of Supervisors", "https://www.lowerwindsor.com/board-of-supervisors/", "board_of_supervisors"),
            ("Mount Wolf Borough Council", "https://mtwolfpa.gov/agenda-minutes/", "borough_council"),
            ("Newberry Twp Board of Supervisors", "https://newberrytwp.com/board-of-supervisors-info", "board_of_supervisors"),
            ("New Freedom Borough Council", "https://newfreedomboro.org/meeting-information/", "borough_council"),
            ("Stewartstown Borough Council", "https://www.stewartstown.org/borough-government/", "borough_council"),
            ("Warrington Twp Board of Supervisors", "https://warringtontownship.org/local_government/board_meetings.php", "board_of_supervisors"),
            ("Windsor Borough Council", "https://www.windsorboropa.com/agenda-minutes.html", "borough_council"),

            # --- County ---
            ("York County Commissioners", "https://yorkcountypa.gov/817/Meeting-Agendas-and-Minutes", "county_commissioners"),

            # ================================================================
            # ZONING HEARING BOARDS (ZHB)
            # ================================================================
            ("Carroll Twp Zoning Hearing Board", "https://www.carrolltownship.com/zoning-hearing-board/", "zoning_hearing"),
            # Year-specific URL; update annually
            ("Conewago Twp Zoning Hearing Board", "https://www.conewagotwp.com/2026-zoning-agendas-minutes/", "zoning_hearing"),
            ("Dover Twp Zoning Hearing Board", "https://www.dovertownship.org/boards/zoning-hearing-board/", "zoning_hearing"),
            ("East Manchester Twp Zoning Hearing Board", "https://emanchestertwp.com/boards-and-committees/zoning-hearing-board/", "zoning_hearing"),
            ("Fairview Twp Zoning Hearing Board", "https://twp.fairview.pa.us/zoning-hearing-board/", "zoning_hearing"),
            ("Goldsboro Boro Zoning Hearing Board", "https://goldsboropa.com/zoning-hearing-board/", "zoning_hearing"),
            ("Hanover Boro Zoning Hearing Board", "https://hanoverboroughpa.gov/AgendaCenter/Zoning-Hearing-Board-11", "zoning_hearing"),
            ("Hellam Twp Zoning Hearing Board", "https://www.hellamtownship.gov/government/zoning-hearing-board/", "zoning_hearing"),
            ("Hopewell Twp Zoning Hearing Board", "https://www.hopewelltownship.com/public-meetings/zoning-hearing-board/", "zoning_hearing"),
            ("North Codorus Twp Zoning Hearing Board", "https://northcodorustwp.org/zoning-hearing-board-2/", "zoning_hearing"),
            ("Paradise Twp Zoning Hearing Board", "https://paradisetownship.org/documents/zoning-hearing-board-notices/", "zoning_hearing"),
            ("Peach Bottom Twp Zoning Hearing Board", "https://www.peachbottomtownship.org/zoning-hearing-board", "zoning_hearing"),
            ("Penn Twp Zoning Hearing Board", "https://penntownship.org/zoning-hearing-board/", "zoning_hearing"),
            ("Red Lion Boro Zoning Hearing Board", "https://redlionpa.org/government/agendas-minutes/zoning-hearing-board-agendas/", "zoning_hearing"),
            ("Shrewsbury Twp Zoning Hearing Board", "https://www.shrewsburytownship.org/government/zoning-hearing-board/", "zoning_hearing"),
            ("Spring Garden Twp Zoning Hearing Board", "https://www.springgardentwp.org/zoning-hearing-board/", "zoning_hearing"),
            ("Spring Grove Boro Zoning Hearing Board", "https://www.springgrovepa.gov/zoning-hearing", "zoning_hearing"),
            ("Warrington Twp Zoning Hearing Board", "https://warringtontownship.org/local_government/advisory_boards/zoning_hearing_board.php", "zoning_hearing"),
            ("West Manchester Twp Zoning Hearing Board", "https://www.westmanchestertownship.com/boards-committees/zoning-hearing-board/", "zoning_hearing"),
            ("West Manheim Twp Zoning Hearing Board", "https://westmanheimtwp.com/boards-comissions/zoning-hearing-board/", "zoning_hearing"),
            ("York City Zoning Hearing Board", "https://www.yorkcity.org/government/authorities-boards-and-commissions/zoning-hearing-board/", "zoning_hearing"),
            ("York Twp Zoning Hearing Board", "https://yorktownshippa.gov/ZHB", "zoning_hearing"),
            ("Lower Windsor Twp Zoning Hearing Board", "https://www.lowerwindsor.com/zoning-hearing-board/", "zoning_hearing"),

            # ================================================================
            # PLANNING COMMISSIONS (PC)
            # ================================================================
            ("Carroll Twp Planning Commission", "https://www.carrolltownship.com/planning-commission/", "planning_commission"),
            # Year-specific URL; update annually
            ("Conewago Twp Planning Commission", "https://www.conewagotwp.com/2026-planning-agendas-minutes/", "planning_commission"),
            ("Dover Twp Planning Commission", "https://www.dovertownship.org/boards/planning-commission/", "planning_commission"),
            ("East Hopewell Twp Planning Commission", "https://www.easthopewelltownshippa.gov/planning-commission", "planning_commission"),
            ("East Manchester Twp Planning Commission", "https://emanchestertwp.com/boards-and-committees/planning-commission/", "planning_commission"),
            ("Fairview Twp Planning Commission", "https://twp.fairview.pa.us/planning-commission/", "planning_commission"),
            ("Franklin Twp Planning Commission", "https://franklintownship.org/planning-commission-meeting-minutesagendas/", "planning_commission"),
            ("Goldsboro Boro Planning Commission", "https://goldsboropa.com/planning-commission/", "planning_commission"),
            ("Hanover Boro Planning Commission", "https://hanoverboroughpa.gov/AgendaCenter/Planning-Commission-8", "planning_commission"),
            ("Hellam Twp Planning Commission", "https://www.hellamtownship.gov/planning-commission/", "planning_commission"),
            ("Hopewell Twp Planning Commission", "https://www.hopewelltownship.com/public-meetings/planning-commission-board/", "planning_commission"),
            ("North Codorus Twp Planning Commission", "https://northcodorustwp.org/planning-commission-2/", "planning_commission"),
            ("Paradise Twp Planning Commission", "https://paradisetownship.org/documents/planning-commission-agendas-minutes/", "planning_commission"),
            # Penn Twp's /documents/ page holds both BOS and PC documents; classifier routes by filename
            ("Penn Twp Planning Commission", "https://penntownship.org/documents/", "planning_commission"),
            ("Red Lion Boro Planning Commission", "https://redlionpa.org/government/agendas-minutes/2023-planning-commission-agendas-minutes/", "planning_commission"),
            ("Shrewsbury Twp Planning Commission", "https://www.shrewsburytownship.org/government/planning-commission/", "planning_commission"),
            ("Spring Garden Twp Planning Commission", "https://www.springgardentwp.org/planning-commission/", "planning_commission"),
            ("Spring Grove Boro Planning Commission", "https://www.springgrovepa.gov/planning-commissions", "planning_commission"),
            ("Warrington Twp Planning Commission", "https://warringtontownship.org/departments/planning_development_zoning/planning_commission.php", "planning_commission"),
            ("West Manchester Twp Planning Commission", "https://www.westmanchestertownship.com/boards-committees/planning-commission/", "planning_commission"),
            ("West Manheim Twp Planning Commission", "https://westmanheimtwp.com/boards-comissions/planning-commision/", "planning_commission"),
            ("Windsor Twp Planning Commission", "https://windsortownship.com/events-minutes/planning-commission/", "planning_commission"),
            ("York City Planning Commission", "https://www.yorkcity.org/government/authorities-boards-and-commissions/planning-commission-board/", "planning_commission"),
            ("York Twp Planning Commission", "https://yorktownshippa.gov/PC", "planning_commission"),
            ("Lower Windsor Twp Planning Commission", "https://www.lowerwindsor.com/planning-commission/", "planning_commission"),
        ),
        s3_prefix="york",
    ),
}


def get_county_config(county_key: str | None = None) -> CountyConfig:
    """Get the config for a county. Defaults to COUNTY env var, then 'york'."""
    if county_key is None:
        county_key = os.environ.get("COUNTY", "york")
    return COUNTY_CONFIGS[county_key]
