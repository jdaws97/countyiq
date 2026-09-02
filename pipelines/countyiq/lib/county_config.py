"""County-specific configuration for multi-county pipeline support.

Each county has its own config with source URLs, filter strings, and thresholds.
The active county is selected by the COUNTY env var (default: "york").

To add a new county, copy ``countyiq/counties/county.toml.example`` to a
``<county-key>.toml`` manifest, validate it with the test suite, and set
``COUNTY=<county-key>``.  No Python registry edit is required.
"""

import os
import re
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class CountyConfig:
    """Configuration for a single county's data sources."""

    # Identity
    name: str                       # e.g. "York County"
    state: str = "PA"
    open_data_source_key: str = ""  # key in meta.source_rights for county GIS

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
    arcgis_parcels_min_records: int = 10000
    arcgis_zoning_min_records: int = 100
    arcgis_roads_min_records: int = 1000
    arcgis_structures_min_records: int = 10000
    arcgis_municipalities_min_records: int = 10
    arcgis_address_pts_min_records: int = 10000

    # Assessment portal and Tyler recorder scrapers were removed 2026-08-05
    # (scrape-free source policy — see docs/decisions.md). Assessment facts
    # come from the GIS parcel layer; transfer detection comes from
    # public.parcel_events derived off staging.parcels SCD2 diffs.

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

    # PA DEP public environmental-diligence layers. The services are
    # statewide; each county supplies a conservative WGS84 query envelope.
    pa_dep_storage_tanks_url: str = (
        "https://gis.dep.pa.gov/depgisprd/rest/services/emappa/"
        "eMapPA_External/FeatureServer/171"
    )
    pa_dep_cleanup_sites_url: str = (
        "https://gis.dep.pa.gov/depgisprd/rest/services/Assessments/"
        "AssessmentLayers/MapServer/5"
    )
    pa_dep_query_bbox: tuple[float, float, float, float] = ()
    pa_dep_storage_tanks_min_records: int = 50
    pa_dep_cleanup_sites_min_records: int = 50

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
    arcgis_zoning_overlays_url: str = ""
    arcgis_business_parks_url: str = ""
    arcgis_industrial_parks_url: str = ""
    arcgis_soils_url: str = ""
    arcgis_local_traffic_counts_url: str = ""
    arcgis_zoning_overlays_min_records: int = 10
    arcgis_business_parks_min_records: int = 50
    arcgis_industrial_parks_min_records: int = 100
    arcgis_soils_min_records: int = 1000
    arcgis_local_traffic_counts_min_records: int = 500

    # PA DOS Corporate Entities
    # Statewide registered-business dataset on data.pa.gov, queried per
    # parcel-owner name (replaced the file.dos.pa.gov Playwright scrape
    # 2026-08-05 — scrape-free source policy).
    pa_dos_soda_dataset: str = "xvd7-5r2c"
    pa_dos_min_records: int = 100

    # Public Proceedings - tuple of (body_name, minutes_url, proceeding_type) tuples
    municipality_websites: tuple[tuple[str, str, str], ...] = ()

    # Development signal thresholds (see assets/enrichment/development_signals.py)
    signal_subdivision_radius_m: int = 250      # corridor radius for nearby_subdivision
    signal_subdivision_on_parcel_m: int = 30    # plan point inside/at the parcel = active_subdivision
    signal_infrastructure_radius_m: int = 800   # proximity for PennDOT / CDBG
    signal_local_traffic_radius_m: int = 400    # nearest recent local traffic observation
    signal_environmental_radius_m: int = 500   # nearby PA DEP diligence record
    signal_nominal_sale_max: int = 1000         # sales at/below this are nominal transfers
    signal_vacancy_apr_max: int = 50000         # residential assessed-value ceiling for vacancy
    signal_vacancy_price_max: int = 100000      # recent-sale-price ceiling for vacancy
    signal_assemblage_min_neighbors: int = 6    # differently-owned neighbors to emit assemblage
    signal_assemblage_strong_neighbors: int = 8 # neighbors for the higher assemblage weight

    # S3 archive prefix (raw data goes to s3://york-county-raw/<prefix>/...)
    s3_prefix: str = ""


COUNTY_CONFIGS: dict[str, CountyConfig] = {
    "york": CountyConfig(
        name="York County",
        open_data_source_key="york_open_data",
        plcb_filter="York County",
        plcb_min_records=500,
        arcgis_parcels_url="https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/Parcels/FeatureServer/0",
        arcgis_base_url="https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA",
        arcgis_zoning_url="https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/Zoning/FeatureServer/0",
        arcgis_roads_url="https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/Roads/FeatureServer/0",
        arcgis_structures_url="https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/BLDG_Footprint/FeatureServer/0",
        arcgis_municipalities_url="https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/Municipal_Boundary/FeatureServer/0",
        arcgis_address_pts_url="https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/AddressPts/FeatureServer/0",
        arcgis_parcels_min_records=150000,
        arcgis_zoning_min_records=500,
        arcgis_roads_min_records=10000,
        arcgis_structures_min_records=100000,
        arcgis_municipalities_min_records=50,
        arcgis_address_pts_min_records=100000,
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
        pa_dep_query_bbox=(-77.20, 39.65, -76.15, 40.25),
        pa_dep_storage_tanks_min_records=300,
        pa_dep_cleanup_sites_min_records=900,
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
        arcgis_zoning_overlays_url="https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/ZONING_OVERLAYS/FeatureServer/0",
        arcgis_business_parks_url="https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/ECONDEV_Business_Parks/FeatureServer/0",
        arcgis_industrial_parks_url="https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/ECONDEV_Industrial_Parks/FeatureServer/0",
        arcgis_soils_url="https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/Soils/FeatureServer/0",
        arcgis_local_traffic_counts_url="https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/Traffic_Counts/FeatureServer/0",
        arcgis_zoning_overlays_min_records=50,
        arcgis_business_parks_min_records=100,
        arcgis_industrial_parks_min_records=250,
        arcgis_soils_min_records=10000,
        arcgis_local_traffic_counts_min_records=2500,
        pa_dos_min_records=100,
        municipality_websites=(
            # Format: (body_name, minutes_page_url, proceeding_type)
            # Surveyed 2026-04-08 via Playwright. 90 entries across 40+ municipalities.
            # ZHB: 22 dedicated pages. PC: 24 dedicated pages.
            # Re-audited 2026-08-02: all 72 municipalities cross-referenced against
            # the YCPC Directory of Public Officials (ycpc.org DocumentCenter #5089,
            # refreshed annually — use it to re-verify websites/contacts each year).
            # Confirmed NO web presence (contact-only, do not re-survey blindly):
            #   - Cross Roads Borough (all domains dead, zero Wayback captures)
            #   - Railroad Borough (YCPC directory: "Website: None"; 717-235-5042)

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
            # Dover Twp's combined archive now delegates document delivery to
            # Rep'd. Paused 2026-08-27 because Rep'd's terms restrict site
            # content to personal, non-commercial use; see migration 033.
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
            (
                "Hellam Twp Board of Supervisors",
                "https://www.hellamtownship.gov/board-of-supervisors-meetings/",
                "board_of_supervisors",
            ),
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
            # Shrewsbury Twp moved BOS/PC minutes to eCode360 in 2026 and the
            # township site carries no per-meeting documents (verified
            # 2026-08-02). The eCode360 entry was REMOVED 2026-08-05 under the
            # scrape-free source policy (eCode's commercial-use restrictions;
            # see docs/decisions.md) — Shrewsbury Twp BOS/PC minutes are a
            # KNOWN COVERAGE GAP until the township posts originals again.
            ("Spring Garden Twp Board of Supervisors", "https://www.springgardentwp.org/meeting-minutes/", "board_of_supervisors"),
            ("Spring Grove Borough Council", "https://www.springgrovepa.gov/meeting-minutes", "borough_council"),
            ("Springfield Twp Board of Supervisors", "https://springfieldyork.org/meeting-minutes/", "board_of_supervisors"),
            ("Springettsbury Twp Board of Supervisors", "https://springettsbury.com/township-document-archives/", "board_of_supervisors"),
            ("Wellsville Borough Council", "https://wellsvilleborough.com/boards-commissions/borough-council-agenda-budget/", "borough_council"),
            ("West Manchester Twp Board of Supervisors", "https://www.westmanchestertownship.com/boards-committees/board-of-supervisors/", "board_of_supervisors"),
            # West Manheim BOS/PC/ZHB paths are paused: the official robots.txt
            # explicitly disallowed them in the 2026-08-27 retained audit.
            ("Windsor Twp Board of Supervisors", "https://windsortownship.com/events-minutes/board-of-trustees/", "board_of_supervisors"),
            ("Wrightsville Borough Council", "https://wrightsvilleborough.com/meeting-minutes/", "borough_council"),
            ("Yoe Borough Council", "https://yoeborough.org/information/minutes/", "borough_council"),
            # Yorkana site is dead as of 2026-08-02 (TLS cert expired; HTTP serves
            # the cPanel default page). Kept for retry if hosting is restored.
            ("Yorkana Borough Council", "https://yorkanaborough.com/meeting-minutes/", "borough_council"),
            ("York City Council", "https://www.yorkcity.org/government/city-council/meetings/", "city_council"),
            (
                "York Twp Board of Commissioners",
                "https://yorktownshippa.gov/boards-4/boc/",
                "board_of_commissioners",
            ),

            # --- Added 2026-04-08 deep survey ---
            ("Chanceford Twp Board of Supervisors", "https://www.chancefordtwp.com/Minutes.html", "board_of_supervisors"),
            ("Delta Borough Council", "https://www.deltaborough.us/current-meeting-minutes", "borough_council"),
            ("Dillsburg Borough Council", "https://dillsburg.com/minutes/", "borough_council"),
            ("Dover Borough Council", "https://www.doverboroughpa.com/minutes.html", "borough_council"),
            # GoDaddy CDN delivery is an explicitly recorded product-owner risk
            # acceptance in migration 042; raw archives remain private/export-disabled.
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
            # York County's Warrington Twp is warringtontwp.org — warringtontownship.org
            # is Warrington Twp, BUCKS County (wrong-county trap, fixed 2026-08-02).
            # Year-specific URL; update annually (per-year archives back to 2016).
            ("Warrington Twp Board of Supervisors", "https://warringtontwp.org/index.php/board-of-supervisors-minutes-2026/", "board_of_supervisors"),
            ("Windsor Borough Council", "https://www.windsorboropa.com/agenda-minutes.html", "borough_council"),

            # --- Added 2026-08-02 audit (previously-missing municipalities) ---
            # Heidelberg: one combined page for BOS/PC/ZHB docs; classifier routes
            # by filename. NOT heidelbergtownship.org — that's Heidelberg Twp,
            # BERKS County (wrong-county trap).
            ("Heidelberg Twp Board of Supervisors", "https://www.heidelbergtwpmunicipal.com/meeting-agendas-monthly-minutes/", "board_of_supervisors"),
            ("Washington Twp Board of Supervisors", "https://washingtontownshipyc.net/meeting-minutes", "board_of_supervisors"),
            # West York's hub delegates document delivery to public Google Drive.
            # Paused until the Drive origin has written commercial permission or
            # the borough publishes direct originals; see migration 033.
            # Winterstown: 104 doc links, but mostly .docx (8 PDFs ingest today;
            # .docx extraction pending). April survey's "no minutes pages" was wrong.
            ("Winterstown Borough Council", "https://www.winterstownborough.com/documents", "borough_council"),
            # North Hopewell: site back online (April "DNS failure" stale). Agendas
            # only, as .doc on the homepage — no minutes posted; .doc support pending
            ("North Hopewell Twp Board of Supervisors", "https://www.northhopewelltwp.com/", "board_of_supervisors"),

            # --- County ---
            ("York County Commissioners", "https://yorkcountypa.gov/817/Meeting-Agendas-and-Minutes", "county_commissioners"),

            # ================================================================
            # ZONING HEARING BOARDS (ZHB)
            # ================================================================
            ("Carroll Twp Zoning Hearing Board", "https://www.carrolltownship.com/zoning-hearing-board/", "zoning_hearing"),
            # Year-specific URL; update annually
            ("Conewago Twp Zoning Hearing Board", "https://www.conewagotwp.com/2026-zoning-agendas-minutes/", "zoning_hearing"),
            # Dover ZHB shares the paused Rep'd-backed combined archive (above).
            ("East Manchester Twp Zoning Hearing Board", "https://emanchestertwp.com/boards-and-committees/zoning-hearing-board/", "zoning_hearing"),
            ("Fairview Twp Zoning Hearing Board", "https://twp.fairview.pa.us/zoning-hearing-board/", "zoning_hearing"),
            ("Goldsboro Boro Zoning Hearing Board", "https://goldsboropa.com/zoning-hearing-board/", "zoning_hearing"),
            ("Hanover Boro Zoning Hearing Board", "https://hanoverboroughpa.gov/AgendaCenter/Zoning-Hearing-Board-11", "zoning_hearing"),
            ("Heidelberg Twp Zoning Hearing Board", "https://www.heidelbergtwpmunicipal.com/meeting-agendas-monthly-minutes/", "zoning_hearing"),
            (
                "Hellam Twp Zoning Hearing Board",
                "https://www.hellamtownship.gov/zoning-hearing-board-meetings/",
                "zoning_hearing",
            ),
            ("Hopewell Twp Zoning Hearing Board", "https://www.hopewelltownship.com/public-meetings/zoning-hearing-board/", "zoning_hearing"),
            ("North Codorus Twp Zoning Hearing Board", "https://northcodorustwp.org/zoning-hearing-board-2/", "zoning_hearing"),
            ("Paradise Twp Zoning Hearing Board", "https://paradisetownship.org/documents/zoning-hearing-board-notices/", "zoning_hearing"),
            ("Peach Bottom Twp Zoning Hearing Board", "https://www.peachbottomtownship.org/zoning-hearing-board", "zoning_hearing"),
            ("Penn Twp Zoning Hearing Board", "https://penntownship.org/zoning-hearing-board/", "zoning_hearing"),
            ("Red Lion Boro Zoning Hearing Board", "https://redlionpa.org/government/agendas-minutes/zoning-hearing-board-agendas/", "zoning_hearing"),
            # Site restructured 2026 (old /government/zoning-hearing-board/ is 404);
            # hearing notices page — ZHB minutes live only in eCode360, which is
            # not collected (scrape-free policy; see BOS note above)
            ("Shrewsbury Twp Zoning Hearing Board", "https://www.shrewsburytownship.org/government/zoning_hearing_board/hearing_notices.php", "zoning_hearing"),
            ("Spring Garden Twp Zoning Hearing Board", "https://www.springgardentwp.org/zoning-hearing-board/", "zoning_hearing"),
            ("Spring Grove Boro Zoning Hearing Board", "https://www.springgrovepa.gov/zoning-hearing", "zoning_hearing"),
            # Fixed 2026-08-02: previous URL was Warrington Twp BUCKS County (returned
            # 200, silent wrong-county contamination risk — purge any ingested docs
            # with source_url on warringtontownship.org)
            ("Warrington Twp Zoning Hearing Board", "https://warringtontwp.org/index.php/past-zoning-minutes/", "zoning_hearing"),
            ("West Manchester Twp Zoning Hearing Board", "https://www.westmanchestertownship.com/boards-committees/zoning-hearing-board/", "zoning_hearing"),
            # West Manheim ZHB is part of the robots-paused group above.
            ("York City Zoning Hearing Board", "https://www.yorkcity.org/government/authorities-boards-and-commissions/zoning-hearing-board/", "zoning_hearing"),
            ("York Twp Zoning Hearing Board", "https://yorktownshippa.gov/ZHB", "zoning_hearing"),
            ("Lower Windsor Twp Zoning Hearing Board", "https://www.lowerwindsor.com/zoning-hearing-board/", "zoning_hearing"),

            # ================================================================
            # PLANNING COMMISSIONS (PC)
            # ================================================================
            ("Carroll Twp Planning Commission", "https://www.carrolltownship.com/planning-commission/", "planning_commission"),
            # Year-specific URL; update annually
            ("Conewago Twp Planning Commission", "https://www.conewagotwp.com/2026-planning-agendas-minutes/", "planning_commission"),
            ("Dover Twp Planning Commission", "https://www.dovertownship.org/home/government/boards-commissions/planning-commission/", "planning_commission"),
            ("East Hopewell Twp Planning Commission", "https://www.easthopewelltownshippa.gov/planning-commission", "planning_commission"),
            ("East Manchester Twp Planning Commission", "https://emanchestertwp.com/boards-and-committees/planning-commission/", "planning_commission"),
            ("Fairview Twp Planning Commission", "https://twp.fairview.pa.us/planning-commission/", "planning_commission"),
            ("Franklin Twp Planning Commission", "https://franklintownship.org/planning-commission-meeting-minutesagendas/", "planning_commission"),
            ("Goldsboro Boro Planning Commission", "https://goldsboropa.com/planning-commission/", "planning_commission"),
            ("Heidelberg Twp Planning Commission", "https://www.heidelbergtwpmunicipal.com/meeting-agendas-monthly-minutes/", "planning_commission"),
            ("Hanover Boro Planning Commission", "https://hanoverboroughpa.gov/AgendaCenter/Planning-Commission-8", "planning_commission"),
            (
                "Hellam Twp Planning Commission",
                "https://www.hellamtownship.gov/planning-commission-meetings/",
                "planning_commission",
            ),
            ("Hopewell Twp Planning Commission", "https://www.hopewelltownship.com/public-meetings/planning-commission-board/", "planning_commission"),
            ("North Codorus Twp Planning Commission", "https://northcodorustwp.org/planning-commission-2/", "planning_commission"),
            ("Paradise Twp Planning Commission", "https://paradisetownship.org/documents/planning-commission-agendas-minutes/", "planning_commission"),
            # Penn Twp's /documents/ page holds both BOS and PC documents; classifier routes by filename
            ("Penn Twp Planning Commission", "https://penntownship.org/documents/", "planning_commission"),
            ("Red Lion Boro Planning Commission", "https://redlionpa.org/government/agendas-minutes/2023-planning-commission-agendas-minutes/", "planning_commission"),
            # Shrewsbury Twp PC minutes live only in eCode360, which is not
            # collected (scrape-free policy — see the BOS-section note).
            # Township-site PC pages carry no per-meeting documents
            # (verified 2026-08-02).
            ("Spring Garden Twp Planning Commission", "https://www.springgardentwp.org/planning-commission/", "planning_commission"),
            ("Spring Grove Boro Planning Commission", "https://www.springgrovepa.gov/planning-commissions", "planning_commission"),
            # Fixed 2026-08-02: previous URL was BUCKS County (see Warrington ZHB
            # note). Year-specific URL; update annually.
            ("Warrington Twp Planning Commission", "https://warringtontwp.org/index.php/planning-commission-minutes-2026/", "planning_commission"),
            ("West Manchester Twp Planning Commission", "https://www.westmanchestertownship.com/boards-committees/planning-commission/", "planning_commission"),
            # West Manheim PC is part of the robots-paused group above.
            ("Windsor Twp Planning Commission", "https://windsortownship.com/events-minutes/planning-commission/", "planning_commission"),
            ("York City Planning Commission", "https://www.yorkcity.org/government/authorities-boards-and-commissions/planning-commission-board/", "planning_commission"),
            ("York Twp Planning Commission", "https://yorktownshippa.gov/PC", "planning_commission"),
            ("Lower Windsor Twp Planning Commission", "https://www.lowerwindsor.com/planning-commission/", "planning_commission"),
        ),
        s3_prefix="york",
    ),
}


_COUNTY_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_TUPLE_FIELDS = {
    "soda_datasets",
    "penndot_projects_layers",
    "municipality_websites",
    "pa_dep_query_bbox",
}
_REQUIRED_MANIFEST_FIELDS = {
    "name",
    "open_data_source_key",
    "plcb_filter",
    "arcgis_parcels_url",
    "s3_prefix",
}


def _tuple_value(field_name: str, value: object) -> object:
    if field_name not in _TUPLE_FIELDS:
        return value
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a TOML array")
    if field_name in {"soda_datasets", "municipality_websites"}:
        return tuple(tuple(item) if isinstance(item, list) else item for item in value)
    return tuple(value)


def _validate_manifest(key: str, values: dict[str, object], source: Path) -> CountyConfig:
    if not _COUNTY_KEY_PATTERN.fullmatch(key):
        raise ValueError(f"{source}: invalid county key {key!r}")

    valid_fields = {field.name for field in fields(CountyConfig)}
    unknown = sorted(set(values) - valid_fields)
    if unknown:
        raise ValueError(f"{source}: unknown CountyConfig field(s): {', '.join(unknown)}")

    missing = sorted(
        name for name in _REQUIRED_MANIFEST_FIELDS
        if not isinstance(values.get(name), str) or not str(values[name]).strip()
    )
    if missing:
        raise ValueError(f"{source}: missing required field(s): {', '.join(missing)}")

    normalized = {name: _tuple_value(name, value) for name, value in values.items()}
    config = CountyConfig(**normalized)

    if len(config.state) != 2:
        raise ValueError(f"{source}: state must be a two-letter abbreviation")
    for field in fields(CountyConfig):
        value = getattr(config, field.name)
        if field.name.endswith("_url") and value and not str(value).startswith("https://"):
            raise ValueError(f"{source}: {field.name} must use https://")
        if "min_records" in field.name and isinstance(value, int) and value < 0:
            raise ValueError(f"{source}: {field.name} cannot be negative")

    for index, source_row in enumerate(config.municipality_websites):
        if not isinstance(source_row, tuple) or len(source_row) != 3:
            raise ValueError(
                f"{source}: municipality_websites[{index}] must be "
                "[body_name, minutes_url, proceeding_type]"
            )
        if not str(source_row[1]).startswith("https://"):
            raise ValueError(
                f"{source}: municipality_websites[{index}] URL must use https://"
            )
    return config


def load_county_manifests(
    directory: Path,
    *,
    existing: Mapping[str, CountyConfig] | None = None,
) -> dict[str, CountyConfig]:
    """Load and validate every ``*.toml`` county manifest in a directory.

    The filename is the county key.  Built-in keys cannot be shadowed, which
    prevents a local manifest from silently changing York's production source
    contract.
    """
    loaded: dict[str, CountyConfig] = {}
    if not directory.exists():
        return loaded
    for path in sorted(directory.glob("*.toml")):
        key = path.stem
        if key in loaded or (existing and key in existing):
            raise ValueError(f"{path}: duplicate county key {key!r}")
        try:
            values = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ValueError(f"{path}: unable to read county manifest: {exc}") from exc
        loaded[key] = _validate_manifest(key, values, path)
    return loaded


_manifest_directory = Path(
    os.environ.get(
        "COUNTYIQ_COUNTY_CONFIG_DIR",
        str(Path(__file__).resolve().parents[1] / "counties"),
    )
)
COUNTY_CONFIGS.update(load_county_manifests(_manifest_directory, existing=COUNTY_CONFIGS))


def get_county_config(county_key: str | None = None) -> CountyConfig:
    """Get the config for a county. Defaults to COUNTY env var, then 'york'."""
    if county_key is None:
        county_key = os.environ.get("COUNTY", "york")
    return COUNTY_CONFIGS[county_key]


def get_county_key() -> str:
    """Return the normalized key for the active isolated county stack."""

    return os.environ.get("COUNTY", "york").strip().lower() or "york"


def county_prompt_context(config: CountyConfig | None = None) -> str:
    """Return the human county/state context used in cached LLM instructions."""
    selected = config or get_county_config()
    return f"{selected.name}, {selected.state}"


def county_open_data_source_key(config: CountyConfig | None = None) -> str:
    """Return the governed source key for the active county's GIS/open data."""
    selected = config or get_county_config()
    if not selected.open_data_source_key:
        raise ValueError(f"{selected.name} has no open_data_source_key")
    return selected.open_data_source_key


_MUNICIPAL_BODY_SUFFIX = re.compile(
    r"\s+(?:Board of Supervisors|Board of Commissioners|"
    r"Zoning Hearing Board|Planning Commission)$",
    re.IGNORECASE,
)


def municipality_name_from_body(
    body_name: str,
    *,
    county: CountyConfig | None = None,
) -> str | None:
    """Return a canonical municipality name for a configured board label.

    County-level bodies deliberately return ``None`` so coverage metrics never
    inflate the municipality denominator with the active county itself.
    """

    county_name = (county or get_county_config()).name.strip().lower()
    if body_name.strip().lower().startswith(f"{county_name} "):
        return None
    base = body_name.strip()
    if re.search(r"\s+(?:Borough|Boro) Council$", base, re.IGNORECASE):
        base = re.sub(
            r"\s+(?:Borough|Boro) Council$", " BORO", base, flags=re.IGNORECASE
        )
    elif re.search(r"\s+City Council$", base, re.IGNORECASE):
        base = re.sub(r"\s+City Council$", " CITY", base, flags=re.IGNORECASE)
    else:
        base = _MUNICIPAL_BODY_SUFFIX.sub("", base)
    base = re.sub(r"\s+Borough$", " BORO", base, flags=re.IGNORECASE)
    base = re.sub(r"\s+Boro$", " BORO", base, flags=re.IGNORECASE)
    base = re.sub(r"\s+Township$", " TWP", base, flags=re.IGNORECASE)
    base = re.sub(r"\s+Twp$", " TWP", base, flags=re.IGNORECASE)
    base = re.sub(r"\s+City$", " CITY", base, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", base).upper()


def municipality_source_key(body_name: str, county_key: str | None = None) -> str:
    """Stable, county-safe database key for one municipal body source.

    York keeps its original keys so existing audit receipts remain valid.
    Every new county is namespaced, preventing common names such as
    ``Washington Township`` from colliding with York's reviewed policies.
    """

    slug = re.sub(r"[^a-z0-9]+", "_", body_name.lower()).strip("_")
    selected_key = (county_key or get_county_key()).strip().lower()
    return slug if selected_key == "york" else f"{selected_key}:{slug}"
