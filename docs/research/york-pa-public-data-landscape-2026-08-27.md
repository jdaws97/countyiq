# York County, Pennsylvania public-data landscape and commercial-use review

**Research date:** 2026-08-27
**Product:** CountyIQ
**Decision scope:** data discovery, Pennsylvania county commonality, lawful collection and maintenance, and commercial product use

> This is an engineering and product-risk assessment based on public primary sources, not a legal opinion. It records the evidence supporting a derived-analytics product, the narrower residual risks, and questions that should be reviewed by Pennsylvania counsel and the relevant data owners.

## Executive decision

CountyIQ has a defensible evidence-based path to ingest York's current official `OPEN_DATA` services privately and sell **CountyIQ-derived analytics and intelligence**. Backend-only use matters: it avoids transferring the county's raw compilation, operating a substitute source API, or republishing the county's viewer. It does not make source terms irrelevant, because ingestion and storage are still uses that require an authorized source.

The current evidence is materially stronger than “anyone can see it”:

- The [current official parcel service](https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/Parcels/FeatureServer) identifies itself as the parcel service for the GIS Open Data Portal, exposes a public query API, and reports weekly updates.
- [YCPC's current parcel metadata](https://www.ycpc.org/DocumentCenter/View/6301/Parcels-PDF-) was generated June 5, 2025 and states `Access_Constraints: None` and `Use_Constraints: None`. It expressly describes proximity, overlay, buffering, and cross-analysis with zoning, infrastructure, and demographic data for transparency and data-driven decisions.
- A 2026-08-27 audit found all 59 logical `OPEN_DATA` items public, all 59 with an empty `termsOfUse`, and the only ten nonempty `licenseInfo` values equal to `public`. Current YCPC metadata PDFs were found for 52 of the 59 services; every one says access constraints none and use constraints none. The other seven remain public `OPEN_DATA` items with no posted item terms.
- [PASDA's live status layer](https://apps.pasda.psu.edu/arcgis/rest/services/CountyDataShare/MapServer/0) marks York “Share with PASDA, Data Sharing Agreement Signed” as of November 2018. The [Commonwealth geospatial data-sharing agreement](https://www.pa.gov/content/dam/copapwp-pagov/en/oa/documents/programs/information-technology/documents/geospatial-data-sharing-agreement.pdf) permits a party to aggregate or incorporate received data into its materials, products, and services and says it does not restrict public use; it restricts sale/licensing/commercialization of the unaggregated received data by agreement parties. The agreement is strong policy evidence, not a standalone end-user license or third-party-beneficiary grant.
- PASDA defines open data as allowing use, reuse, and redistribution without a commercial/noncommercial distinction and documents businesses building internal and client-facing applications. See the [2022 PA GIS Data Sharing Report](https://www.pasda.psu.edu/2022_Data_Sharing_Report.pdf), pages 4–5.

There is a narrower conflicting surface: the [York County Property Tax Viewer disclaimer](https://arcweb1.ycpc.org/Disclaimer/Disclaimer.pdf) restricts data “from the York County Property Tax Viewer (‘Tool’),” including third-party provision, sale, solicitation/financial-gain uses, screenshots, maps, and resale. CountyIQ should not scrape, reproduce, or source data from that viewer. A legacy PASDA parcel metadata page also carries older restrictive/as-is wording. Those conflicts should remain in the evidence ledger, but they do not turn the separately published, current `OPEN_DATA` service and no-constraint metadata into mere view-only access.

The product boundary is therefore:

| Status | Decision |
|---|---|
| **GREEN — supported** | Private backend ingestion of the current York `OPEN_DATA` services; normalized facts; joins; change detection; trends; alerts; scores; maps rendered by CountyIQ; and narrative intelligence. Preserve provenance, source dates, current terms/metadata captures, and privacy controls. |
| **YELLOW — source-specific review** | Display or export of source-identical attributes, long-lived historical snapshots, unusually large extracts, or features that let a customer reconstruct a substantial source dataset. Minimize owner/address fields and obtain written clarification for ambiguous cases. |
| **RED — excluded without a separate grant** | Property Tax Viewer scraping/reproduction, raw county-data resale, bulk source-equivalent downloads, a source-proxy API, customer redistribution of the raw compilation, or screenshots/recreated viewer products. |

Written YCPC confirmation is still prudent residual-risk cleanup, especially for source-identical exports and indefinite historical retention. It should identify the exact service/layers and cover automated bulk access, storage, history, derivatives, joins, authenticated display, export thresholds, archival retention, corrections, attribution, and paid subscriptions. It is no longer recorded as a categorical blocker to a backend-derived analytics product.

## What “all available datasets” means here

There is no finite, authoritative catalog of every public record held by York County, its 72 municipalities, every authority, every school district, every court office, every Commonwealth agency, and every federal agency. Pennsylvania's Right-to-Know Law also does not require an agency to create, compile, or reformat a dataset that does not already exist.

This review uses a reproducible definition:

1. Enumerate every logical service in York's public ArcGIS `OPEN_DATA` folder.
2. Enumerate publicly reachable York ArcGIS folders outside `OPEN_DATA`, but do not treat reachability as a license.
3. Enumerate every York County record currently returned by PASDA's provider search.
4. Review York County/YCPC public report, archive, meeting, property, court, election, procurement, and planning source families.
5. Review municipality-level proceedings and permit availability as a source family because delivery varies by municipality and vendor.
6. Review statewide and federal source families that can be filtered to York and therefore offer the strongest 67-county commonality.
7. Record important paid, request-only, restricted, sensitive, or unavailable sources rather than omitting them.

The companion [source register](./york-pa-dataset-register-2026-08-27.csv) is the machine-readable inventory. It records access, reuse status, commonality, product value, disposition, and source URLs. Counts are observations as of the research date and will change.

## Current CountyIQ source posture

The repository is intentionally moving to a scrape-free policy. Current configuration and assets show these source families:

- York ArcGIS: parcels, zoning, roads, building footprints, municipal boundaries, address points, ZIP codes, planning subdivisions, economic-development candidate parcels, growth areas, future land use, conservation easements, agricultural-security areas, and CDBG housing locations.
- Pennsylvania/federal ArcGIS: PennDOT roadway segments, roadway traffic, transportation projects, and FEMA flood data.
- Public documents/pages: York delinquent tax-claim PDF, sheriff-sale listing, and municipal meeting proceedings.
- Explicit state open data: Pennsylvania Department of State corporate entities and PLCB licenses.
- Derived products: parcel events, owner/entity resolution, development signals, briefs, and county narratives.

That direction removes several high-risk browser scrapers. “Scrape-free” is not the same as “licensed for raw commercial redistribution,” but the current York `OPEN_DATA` evidence supports private ingestion and derived use. Remaining risks concern raw/source-equivalent delivery, privacy and product purpose, source-specific non-`OPEN_DATA` surfaces, and retention rights for raw source documents.

### Current-source legal/product disposition

| Current source | Access basis | Commercial/product disposition |
|---|---|---|
| York `OPEN_DATA/Parcels` | Current official open-data API; public item with empty terms; 2025 YCPC metadata says access none/use none; viewer is a separate restricted surface | **Use for private backend and derived analytics.** No viewer scraping, raw resale, source-proxy API, or reconstructive bulk export. Minimize owner/mailing-address display and preserve provenance. |
| Other York `OPEN_DATA` layers | 59/59 public items; no posted `termsOfUse`; 52 current agency metadata documents say access none/use none; remaining seven are still official open-data items | **Use for derived product features.** Capture item JSON/metadata per refresh. Apply privacy controls and source-identical export review by layer. |
| York `Projects/EcoDev_Candidates_Parcels` | Publicly reachable but outside `OPEN_DATA` | **Do not ingest for commercial product without owner confirmation.** A public REST endpoint is not an open-data grant. |
| York `CDBG/CDBG_Housing_Locations` | Publicly reachable but outside `OPEN_DATA`; housing-related | **Hold.** Confirm publication intent and field sensitivity; do not expose household/recipient information. |
| York tax-claim PDF | Official public document; no express downstream license found | Conditional/high privacy. Use property-level fact verification, not people-search or solicitation lists. Restrict exports and apply retention/correction controls. |
| York sheriff-sale site | Official public listing; no express downstream license found | Conditional/high privacy and FCRA risk. Avoid consumer eligibility, tenant/employment screening, people profiles, and claims beyond the source. |
| Municipal agendas/minutes | Official public proceedings; heterogeneous sites and vendors | Conditional. Facts and dates are valuable; store source copies privately for evidence, expose concise factual derivations, and respect robots/terms. Do not republish whole copyrighted packets by default. |
| PA Department of State data.pa dataset | Commonwealth open-data policy | Strong candidate. Preserve attribution/provenance and metadata; do not imply state endorsement. |
| PLCB open-data export | Commonwealth open-data policy when served through data.pa | Strong candidate, subject to dataset metadata. |
| PennDOT open data | Official statewide open-data services | Strong candidate. Preserve service/item metadata and attribution; validate 67-county coverage per layer. |
| FEMA NFHL | Federal public source | Strong candidate. Preserve effective-date, layer, and map-quality caveats; do not represent CountyIQ as an official flood determination. |

The municipal family has now been reviewed at body level rather than accepted
as one county-wide source. The [municipal proceedings review](./york-pa-municipal-proceedings-review-2026-08-27.md)
records 110 configured source entries across 65 municipalities, 107 listing
URLs, and 12 explicit paused body policies so absence is never silently treated
as no activity. All 122 body policies remain recorded across all 72
municipalities. Active entries are conditional pending periodic evidence
review; runtime policy, exact-origin, redirect, robots, method, content,
attribution, retention, and health checks enforce that decision.

## York County dataset universe

### 1. York ArcGIS `OPEN_DATA`: 59 logical services

The live server returned 59 unique logical services. FeatureServer and MapServer representations of the same named service are counted once.

The accompanying rights audit resolved each logical service to its current York enterprise item. All 59 items were public and had empty `termsOfUse`; ten had `licenseInfo` equal to `public`, while 49 had an empty `licenseInfo`. A scan of current YCPC Document Center metadata IDs 6260–6340 found 57 metadata PDFs, 52 of which map to the 59 current services after four documented name aliases. Every mapped PDF states `Access_Constraints: None` and `Use_Constraints: None`. No matching current PDF was found in that block for `Contours`, `DIST_House`, `DIST_Planning_Regions_Appointments`, `DIST_Senate`, `HYDRO_Streams_Impaired`, `PUB_FACIL_Nursing_Homes`, or `Traffic_Counts`; that absence is recorded rather than inferred away.

| Theme | Services |
|---|---|
| Core property and addressing | `Parcels`, `AddressPts`, `BLDG_Footprint`, `Land_Joins`, `Zipcodes` |
| Land use and development | `Zoning`, `ZONING_OVERLAYS`, `LANDUSE_Future_Landuse`, `LANDUSE_Landcover_2024`, `Growth_Areas`, `PLANNING_Subdivisions`, `PLANNING_Heritage_Sites`, `Ag_Security`, `Conservation_Easements` |
| Economic development | `ECONDEV_Business_Parks`, `ECONDEV_Industrial_Parks` |
| Transportation | `Roads`, `Traffic_Counts`, `Transit_Routes`, `Bicycle_Corridors`, `RECREATION_Trails`, `TRANSP_Airports`, `TRANSP_Bicycle_Parking`, `TRANSP_Park_and_Rides`, `TRANSP_Railroads`, `TRANSP_Sidewalks`, `TRANSP_Transit_Stops` |
| Political/administrative boundaries | `Municipal_Boundary`, `DIST_County_Boundary`, `DIST_House`, `DIST_Magisterial`, `DIST_Planning_Regions_Appointments`, `DIST_Precinct`, `DIST_School`, `DIST_Senate` |
| Hydrography/environment | `HYDRO_Floodplains`, `HYDRO_Lakes_Ponds`, `HYDRO_Streams`, `HYDRO_Streams_Impaired`, `HYDRO_Subwatersheds`, `HYDRO_Watersheds`, `HYDRO_Wetlands`, `ENVIR_Important_Birding_Areas`, `ENVIR_Natural_Areas_Inventory`, `ENVIR_Unique_Features`, `Geology`, `Soils`, `Contours` |
| Public facilities and recreation | `Parks`, `PUB_FACIL_College_Campuses`, `PUB_FACIL_Govt_Offices`, `PUB_FACIL_Libraries`, `PUB_FACIL_Medical`, `PUB_FACIL_Nursing_Homes`, `PUB_FACIL_Polling_Place`, `PUB_FACIL_Schools` |
| Emergency facilities | `DES_EMS_Stations`, `DES_Fire_Stations`, `DES_Police_Stations` |

Product value is highest for parcels/addresses/buildings, zoning/overlays/future land use, subdivisions, growth/economic-development areas, roads/traffic/transit, flood/wetland/environmental constraints, easements/agricultural areas, and nearby public facilities. Address points and owner fields require minimization; emergency-facility locations are normally low sensitivity when officially published but should not be enriched with operational/security data.

### 2. PASDA York provider catalog: 47 records

PASDA currently returns 44 York County feature/theme records and three 2015 orthoimagery records:

`Address Points`; `Agricultural Security Area`; `Airports`; `Bicycle Corridors`; `Buildings`; `College Campuses`; `Conservation Easements`; `Contours - 2FT`; `County Boundary`; `DES EMS Stations`; `DES Fire Stations`; `DES Police Stations`; `Government Offices`; `Growth Areas`; `Impaired Streams`; `Lakes and Ponds`; `Land Joins`; `Landcover`; `Libraries`; `Magisterial`; `Medical Facilities`; `Municipal Boundary`; `Natural Areas Inventory`; `Nursing Homes`; `Parcels`; `Park and Rides`; `Parks`; `Planning Subdivisions`; `Polling Locations`; `Railroads`; `Recreation Trails`; `Roads`; `School District Boundaries`; `School Locations points`; `Senate District Boundaries`; `Soils`; `Streams`; `Transit Routes`; `Transit Stops`; `Unique Features`; `Voting`; `Zipcodes`; `Zoning`; `Zoning Overlays`; `YCPC 2015 Digital Orthoimagery`; `YCPC 2015 County Mosaics`; and `YCPC 2015 Tile Index`.

PASDA is valuable because it is an independent download/archive surface and explicitly frames shared data as open. It is not a freshness or schema guarantee. Several records are older than York's live services (for example, legacy buildings/landcover/imagery), and provider/item metadata must still be retained. CountyIQ should acquire current York data from the county's `OPEN_DATA` service and retain PASDA as corroboration/archive. The older PASDA parcel metadata restriction remains recorded as conflicting legacy evidence; it is not the selected acquisition surface.

### 3. Public York ArcGIS services outside `OPEN_DATA`

These endpoints were discoverable without credentials. They are recorded so absence is not mistaken for oversight, but they should not be ingested merely because the server answers a query.

| Folder | Discoverable services | Disposition |
|---|---|---|
| CDBG | `CDBG_Housing_Locations`, `Project_Edits` | Hold for written publication/reuse approval; inspect for recipient/household data. |
| Emergency Services | `MagDist`, `PoliceDept`, `YCDES_Map_Service` | Use only layers intentionally published for public reuse; exclude operational/security data. |
| Geocodes | Four locator services, including owner/PIDN-capable locators | Do not automate owner/person lookup without explicit approval and privacy review. |
| Geoprocessing | Five processing tools | Utilities, not source datasets; do not depend on them without permission/SLA. |
| Planning | `LandDevAppLayers`, `Subdiv_All`, `Subdivisions_NEW` | High product value, but hold until YCPC confirms publication, fields, and reuse. |
| Projects | `2020_Census_Data`, `CDBG_Repository_2017`, `EcoDev_Candidates_Parcels`, `Flooded_Roadway`, `HazMit_Parcels_BaseMap6`, `HazMit_Parcels_New_2025`, `MTP_2024_CENSUS_YAMPO_Urbanized_Areas`, `MTP_2024_Congestion`, `MTP_2024_ECONDEV_Businesses`, `MTP_2024_Freight`, `MTP_2024_Safety`, `MTP_2024_TRANSP_Transit_Hopper_Zones`, `MTP_2024_Vehicle_Access`, `Parcel_Tax_Finder_BaseMap_Cached`, `Probation_Web_App`, `Proposed_Floodplain_Information`, `SR_Housing_StoryMap_data` | Treat as project/application internals. Seek approval for useful planning layers. **Exclude `Probation_Web_App`** and person-level justice data. |
| Stormwater | `MS4_Sewershed` | Useful constraint/infrastructure layer; confirm owner and reuse. |
| Transportation | `Roads_Tyler` | Likely application/vendor integration; do not ingest without confirmation. |

### 4. County/YCPC reports, files, and official public pages

These sources are public and product-relevant, but many are documents rather than stable bulk datasets:

- [YCPC Data & Analyses](https://www.ycpc.org/410/Data-Analyses): annual building-permit reports, population-projection workbooks, subdivision activity, GIS portal, and traffic counts. YCPC expressly warns that municipal building-permit submissions are voluntary and may not be county-complete.
- [Subdivision Activity Reports](https://www.ycpc.org/233/Subdivision-Activity-Reports): plan-level monthly reports, recent annual plan files, municipal/year totals, and historical county totals back to 1976. This is one of the highest-value development-signal sources.
- [Reports & Documents](https://www.ycpc.org/198/Reports-Documents): comprehensive, economic-development, hazard-mitigation, housing, land-use, open-space, water, agricultural, and transportation plans; CDBG/HOME/CAPER material; municipal plan status; building permits; and subdivision reports.
- [County archives](https://yorkcountypa.gov/Archive.aspx): budgets, annual financial reports, audits, millage, cost allocation, retirement/OPEB, row-office reports, prison/coroner reports, DCED reports, court calendars, recovery-fund reports, and related historical documents.
- Commissioner, authority, planning, and other board agendas/minutes: factual development and policy signals, but document form, vendor, retention, and completeness vary.
- Delinquent tax-claim list and sheriff-sale listing: property distress signals with significant privacy, reputational, accuracy, and prohibited-use controls.
- Tax assessment/property viewer: rich parcel/assessment facts but the explicit commercial/reuse conflict described above.
- Recorder of Deeds through Landex: deeds, mortgages, plans, and parcel identifiers; search/viewing may be paid and is governed by Landex/county contract terms. Do not scrape or redistribute without a contract that authorizes CountyIQ's use.
- Prothonotary, Clerk of Courts, Register of Wills, and Archives: common public-record offices, but electronic access, bulk availability, fees, court-record policy, and sensitivity differ. Do not build person dossiers from these sources.
- Elections: current and historical election results, candidate/precinct material, campaign reports filed locally, and meeting information. Prefer statewide aggregated/bulk results where available; do not collect individual voter files.
- Procurement/bids/contracts, budget, payroll/compensation, audits, and open-record responses: strong government-intelligence value, typically document/page delivery rather than a stable API.
- York City OpenGov permitting/licensing portal and other municipal permit portals: public interactive access does not establish bulk/API or commercial redistribution rights. Seek vendor/municipality approval or use official reports.

### 5. Sources intentionally excluded or deferred

| Source/type | Why it is recorded but not recommended |
|---|---|
| Tyler assessment and recorder browser scraping | Repository decision removed it; contractual/access and reliability risk. Use licensed bulk delivery or official open source instead. |
| PA DOS Playwright scraping | Replaced by an explicit data.pa dataset governed by the Commonwealth open-data policy. |
| eCode360 scraping | Vendor/terms and unstable document access. Link to ordinances or obtain licensed access; zoning geometries and official municipal PDFs are safer inputs. |
| Probation, inmate, criminal docket, Crimewatch, and person-level police data | High sensitivity, CHRIA/court-policy/privacy/accuracy risk, weak fit for parcel intelligence, and material misuse potential. |
| Individual voter file | Separate statutory access/use rules and unnecessary personal data. Aggregated registration and election results are sufficient. |
| 911 operational layers | Counties must maintain standardized NG911 data, but operational aggregation is not a public open-data license. Public address/road/boundary layers may be used only from an authorized public source. |
| PA-SHARE archaeology detail | Access restrictions protect sensitive archaeological resources; do not ingest restricted locations. Public historic-resource data may be considered under PA-SHARE terms. |
| RTKL as a default ingestion channel | Legally available for existing public records, but variable timing, possible market-value fees for GIS/assessment data, no duty to compile, and source-specific downstream rights. Use only for targeted gaps after product/legal approval. |

## Commonality across Pennsylvania's 67 counties

### Measured county sharing status

PASDA's live County Data Sharing Status layer was queried on 2026-08-27. Its per-county status labels have differing observation/update dates, so this is a discovery indicator, not a current license or field-parity guarantee.

- **46 counties marked “Share with PASDA, agreement signed”:** Adams, Allegheny, Bedford, Berks, Blair, Bradford, Bucks, Butler, Cambria, Carbon, Centre, Chester, Clearfield, Columbia, Crawford, Cumberland, Dauphin, Delaware, Erie, Fayette, Forest, Franklin, Fulton, Huntingdon, Indiana, Juniata, Lancaster, Lehigh, Luzerne, Lycoming, Mercer, Mifflin, Monroe, Montgomery, Montour, Perry, Philadelphia, Snyder, Somerset, Union, Venango, Warren, Washington, Wayne, Wyoming, and York.
- **14 marked agreement signed but without a PASDA share/download link:** Armstrong, Cameron, Elk, Greene, Jefferson, Lebanon, McKean, Northampton, Northumberland, Potter, Schuylkill, Sullivan, Susquehanna, and Tioga.
- **7 marked not signed:** Beaver, Clarion, Clinton, Lackawanna, Lawrence, Pike, and Westmoreland.

This means 46/67 counties (68.7%) have a general PASDA sharing indicator, not that all 46 publish parcels, zoning, permits, or equivalent fields. Pennsylvania's [GIS data-access guidance](https://www.pa.gov/agencies/oa/programs/information-technology2/state-geospatial-coordinating-board/gis-data-access) says each county is autonomous and access methods vary. PASDA's 2022 report aptly describes Pennsylvania as having “67 different methods and timeframes.”

The government-provider search returned 726 dataset titles, 620 of which could be attributed to a county-name prefix. The following counts measure **other counties with a title-equivalent PASDA dataset**, excluding York. They are a conservative public-catalog measure, not proof that a county lacks a dataset elsewhere.

| York dataset family | Other PA counties with PASDA title-equivalent | Commonality finding |
|---|---:|---|
| Parcels | 38 | Most common high-value county layer, but not uniform statewide. |
| Roads | 37 | High county commonality; PennDOT is the stronger statewide fallback. |
| Address points | 24 | Moderate sharing; no uniform public 67-county unit-level source. |
| Municipal boundaries | 20 | County copies vary; statewide authoritative alternatives exist. |
| Voting/precinct | 12 | Partial county sharing; statewide election files improve portability. |
| School districts | 9 | County copies vary; PDE/Census alternatives exist. |
| Building footprints/buildings | 8 | Material gap; schemas and vintages differ. |
| Zoning | 7 | Highly fragmented and frequently municipal. |
| Floodplains | 4 | Weak county commonality; FEMA provides the portable baseline. |
| Agricultural-security areas | 3 | Rare, locally valuable planning signal. |
| Conservation easements | 2 | Rare at county-publisher level; statewide/program sources may supplement. |
| Wetlands | 2 | Weak county commonality; USFWS NWI provides the portable baseline. |
| Planning subdivisions | 1 | York is a major differentiator; only Delaware matched by title. |
| Future land use | 1 | Very rare county-published layer. |
| Growth areas; zoning overlays; impaired streams; traffic counts; transit routes/stops; business parks; industrial parks; land joins; unique features | 0 each | No other county title-equivalent found in PASDA. Record as noncommon, then use state/federal substitutes where available. |

### Dataset commonality matrix

| Dataset family | Exists conceptually in all counties? | Uniform public bulk/API? | CountyIQ conclusion |
|---|---:|---:|---|
| County/municipal boundaries and statewide reference geography | Yes | **Yes**, through Commonwealth/federal sources | Use statewide authoritative layers; strongest portability. |
| Parcels/assessment rolls | Yes | **No** | Common business concept, noncommon schema, identifiers, fields, cadence, fees, and license. PASDA sharing is partial. |
| DEP statewide parcel service | No, not complete | **No** | Live service contained 43 normalized counties; York was present with about 170,810 records. Useful for validation/fallback, not a 67-county parcel product or a substitute for an express license. |
| Roads/traffic/projects/bridges/transit reference layers | Yes | Mostly, through PennDOT | Strong statewide commonality; local road/sidewalk/transit detail varies. |
| Flood, wetlands, water, environmental facilities, mining, oil/gas | Yes spatially | Mostly, through FEMA/DEP/USGS/EPA | Strong statewide/national product layer; coverage represents relevant features, not a record in every county. |
| Addresses/buildings | Maintained broadly; NG911 standards apply | No public 67-county bulk source | County open data varies. Do not infer public availability from NG911 maintenance duties. |
| Zoning and overlays | Often municipal, sometimes county-hosted | **No** | One of the least standardized, highest-value gaps. Requires municipality/county source mapping and license review. |
| Subdivision/land-development applications | Usually municipal/county planning records | **No** | York is unusually useful. Definitions, review authority, documents, and availability vary materially. |
| Building permits | Yes as local records | **No** unit-record source | Census BPS gives comparable aggregates; local permit detail is fragmented and may be incomplete, as YCPC warns for York. |
| Agendas/minutes/ordinances | Yes in concept | **No** | Sunshine/public-record duties do not create uniform URLs, formats, retention, or APIs. Maintain per-body configs and coverage evidence. |
| Budgets, audits, financial reports | Yes in concept | Partly | DCED Municipal Statistics and Auditor General/state transparency sources improve comparability; local documents remain useful. |
| Tax delinquency and sheriff sales | Yes in concept | **No** | Fragmented office/vendor delivery; high privacy/reputation risk. Not a default expansion source. |
| Deeds/mortgages/recorded documents | Yes | **No** | Often paid/vendor-hosted; document access and downstream reuse are contract-specific. |
| Court dockets | Yes | Centralized public search, constrained bulk access | AOPC policy controls electronic case records; avoid person-oriented product expansion. |
| Elections/registration aggregates | Yes | **Yes** for many statewide files | Strong 67-county/precinct commonality. Avoid individual voter data. |
| Business entities/professional/liquor licenses | Statewide | **Yes** or broadly searchable | Strong common layer; local-only licenses and campaign filings remain fragmented. |
| Health, labor, education, human-services aggregates | Yes at county/district/facility levels | Mostly | Valuable context; avoid individual-level sensitive records and communicate suppression/lag. |

## High-value statewide and federal sources

These are the best route to portability because the source and schema span York and other counties. “67-county” means the source has statewide geography or records, not that every metric is non-null in every county.

| Priority | Source family | Useful content | Commonality / legal posture |
|---:|---|---|---|
| 1 | [PA Open Data Portal](https://data.pa.gov/) | Corporate entities, licenses, grants, inspections, agency datasets, downloadable tables/APIs | The [data policy](https://data.pa.gov/data-policy) states datasets are free and without restriction; attribution is requested, no warranty/endorsement. Check dataset metadata for third-party exceptions. |
| 1 | [PennDOT Open Data](https://gis.penndot.pa.gov/gis/rest/services/opendata) | Road segments/admin, traffic, bridges, projects, rail, intersections, shoulders, park-and-rides, EV registrations, boundaries | Statewide and highly portable. Validate layer-specific coverage/cadence. |
| 1 | [PA DEP GIS](https://www.pa.gov/agencies/dep/data-and-tools/gis) | 300+ non-sensitive layers: permits/facilities, water, mines, oil/gas, waste, tanks, stormwater, impaired streams, hazards | Statewide; direct download/services; excellent property due-diligence and development constraints. |
| 1 | [DCED Municipal Statistics](https://apps.dced.pa.gov/Munstats-public/) | Municipal/county taxes, annual financials, officials, police/fire, authorities, planning, demographics, local tax registers | Statewide structured municipal/government context; mandatory/self-reported fields still need quality checks. |
| 1 | [U.S. Census APIs](https://www.census.gov/data/developers/guidance/api-user-guide.Available_Data.html) | ACS, decennial, population estimates, County Business Patterns, nonemployer, economic data | Federal, nationwide, standard geography. Strong market/demographic context. |
| 1 | [Census Building Permits Survey](https://www.census.gov/construction/bps/index.html) | Monthly/annual residential permit units and valuation by county/place/permit office | Best comparable development aggregate; does not replace local parcel-level permits and may reflect reporting limitations. |
| 1 | FEMA NFHL, National Risk Index, and disaster data | Flood hazards, risk components, declarations, mitigation context | Federal/nationwide. Preserve effective dates and “not an official determination” caveats. |
| 1 | EPA ECHO/Envirofacts/EnviroAtlas | Regulated facilities, compliance/enforcement, releases, environmental indicators | Federal/nationwide; strong site-risk and nearby-facility intelligence. [EnviroAtlas data](https://www.epa.gov/enviroatlas/data-download) is downloadable. |
| 2 | [DCNR open/geologic data](https://www.pa.gov/agencies/dcnr/conservation/geology/publications-and-data) | Parks, forests, trails, geology, sinkholes, wells, quarries, natural resources | Statewide physical/amenity/hazard context; PennDOT's source guide reports 140+ published GIS datasets. |
| 2 | PASDA imagery, lidar, elevation, hydrography and county data | Base mapping, historical imagery, county shares | Open portal and archive; retain provider/item terms and vintage. |
| 2 | PA Department of Education data | Enrollment, finance, assessment, graduation, school/district attributes, facilities | Statewide district/school context; avoid student-level data. |
| 2 | PA DHS/DOH facility and aggregate reports | Licensed facilities, Medicaid/SNAP/TANF aggregates, nursing/personal-care/health facility data | Statewide context; only aggregated/public facility data. No PHI or case-level records. |
| 2 | PA DLI/BLS/BEA/QCEW | Employment, wages, labor force, industry, GDP/income | Standard county/workforce geography; strong market context. |
| 2 | PA Department of State elections and campaign data | County/precinct returns, registration aggregates, state campaign finance, lobbying | Statewide for elections; local campaign filings may remain county-specific. |
| 2 | PA Agriculture | Food inspections, facility/license lists, agricultural and conservation data | Statewide but some inspections are local-department dependent. Use data.pa export where available. |
| 2 | Pennsylvania Treasury/DGS transparency | State contracts, awards, spending, procurement opportunities | Statewide public-sector and vendor signals; record document/update limitations. |
| 2 | PA Auditor General and local-government audits | Municipal, authority, pension, school-district audits | Statewide government-risk/context signals, mostly documents. |
| 2 | PA-SHARE public historic resources | Historic places, surveys, tax-credit/project context | Useful constraint/opportunity data only under [PA-SHARE](https://www.pa.gov/agencies/phmc/pa-share) terms; exclude restricted archaeology. |
| 2 | FCC Broadband Data Collection | Fixed/mobile service coverage and availability | Nationwide; useful site/community infrastructure context. Respect license/terms attached to downloadable files. |
| 2 | USDA NRCS/NASS/FSA public data | Soils, land cover, agricultural census/aggregates, conservation context | Nationwide/state/county; avoid restricted producer/farm records. |
| 2 | USGS/NWI/NOAA | Elevation, hydrography, geology, earthquakes, wetlands, climate and hazards | Federal/nationwide; strong base and hazard layers. |
| 3 | HUD open data | Subsidized properties, fair-market rents, CHAS, housing programs and market indicators | Nationwide; valuable housing context, but keep eligibility/protected-class use outside product decisioning. |
| 3 | CMS/CDC PLACES public aggregates | Providers/facilities and community health indicators | Nationwide aggregate/facility context; not person-level health intelligence. |
| 3 | USAspending/SBA | Federal awards, contracts, assistance and disclosed loans | Nationwide economic-development signals; entity/address matching needs confidence and correction controls. |
| 3 | IRS exempt-organization data | Nonprofit entities/filings | Nationwide entity context; respect source lag and avoid unsupported operational claims. |

## Legal analysis

### Public access, open publication, and backend use are different questions

Pennsylvania's [Right-to-Know Law](https://www.legis.state.pa.us/WU01/LI/LI/US/HTM/2008/0/0003..HTM) generally prevents Commonwealth and local agencies from denying an otherwise public record because of intended use (§§ 301(b), 302(b), 703), but:

- exceptions, other statutes, privilege, and court policies still apply;
- agencies need only provide an existing record and need not create, compile, or reformat data (§ 705);
- complex or extensive datasets, including GIS and integrated property-assessment data, may carry reasonable market-value fees (§ 1307(b)(4)); and
- disclosure rights do not automatically grant copyright, trademark, contractual, database, privacy, or downstream redistribution rights.

For CountyIQ, RTKL can establish access to a record, but it should not be recorded as the product's reuse license unless the response or another authority resolves reuse. A bare public webpage likewise proves access, not necessarily bulk automation or redistribution.

York's current GIS evidence goes beyond bare access: the county placed the services in an official `OPEN_DATA` folder, publishes public query endpoints, posts no item terms, and issued current metadata with no access or use constraints. The parcel metadata affirmatively contemplates spatial and cross-dataset analysis. That combination supports copying the data into a private analytical backend and selling CountyIQ's own derived output. It is not an unlimited promise for every downstream act.

Keeping the source only on the backend is legally and commercially meaningful because customers do not receive the raw compilation and cannot use CountyIQ as a substitute download service. It does **not** make the ingestion invisible or exempt from source conditions: CountyIQ still copies, stores, updates, and transforms the data. Therefore the source-rights ledger must distinguish four separate permissions:

1. automated acquisition and refresh;
2. private storage, normalization, history, and joins;
3. customer display of facts and CountyIQ-derived intelligence; and
4. raw, bulk, or reconstructive export/redistribution.

The current evidence supports the first three for York `OPEN_DATA` when personal-data safeguards are applied. It does not support treating the fourth as unrestricted.

### Evidence that public GIS is intended for reuse and commercial analysis

- YCPC's parcel metadata describes overlay, proximity, buffering, cross-analysis, transparency, and data-driven decisions—not citizen lookup alone.
- PASDA's 2022 report defines open data to include use, reuse, and redistribution without distinguishing commercial and noncommercial users. It reports use by businesses, engineering and technology firms, and organizations building internal and client-facing applications.
- The Commonwealth's [PASDA participation page](https://www.pasda.psu.edu/participate.html) says the Pennsylvania Base Map supports the private sector and avoids duplicated collection costs.
- The Commonwealth geospatial agreement expressly anticipates aggregation and incorporation into products and services while drawing a line around commercialization of raw, unaggregated data received under the agreement.
- [Regrid](https://app.regrid.com/store/us/pa/york) markets a York County parcel product, and [CountyGISMaps](https://countygismaps.com/pa/york) markets York parcel access under a license that permits derived/internal/client uses while restricting raw redistribution. These show a functioning commercial market and a familiar derived-use/no-raw-resale boundary. They do not disclose sufficient upstream rights to serve as CountyIQ's legal safe harbor.
- In [*Zillow, Inc. v. Luzerne County*](https://www.pacourts.us/assets/opinions/Commonwealth/out/194CD25_6-9-26.pdf?cb=1) (Pa. Cmwlth. 2026), Zillow sought CAMA property data under RTKL; the court upheld a reasonable-market-value fee, noting comparable per-parcel fees charged by other counties. The case is evidence of commercial requesters lawfully obtaining public assessment data, but it decides access/fees rather than a downstream reuse license.

### Copyright and source-document handling

- Facts are not protected by copyright, but expressive reports, photographs, maps, selection/arrangement, and vendor interfaces may be.
- Federal works are generally excluded from U.S. copyright under [17 U.S.C. § 105](https://www.law.cornell.edu/uscode/text/17/105), but a federal dataset may contain third-party material or separate terms.
- State/local works are **not automatically public domain**. The Supreme Court's [Georgia v. Public.Resource.Org](https://www.supremecourt.gov/opinions/19pdf/590us1r30_3f14.pdf) government-edicts rule is narrower than a blanket rule for all government-created works.

Recommended architecture: archive source documents privately as evidence only when access/retention is authorized; expose normalized facts, citations, small necessary excerpts, and CountyIQ's own analysis; do not mirror full meeting packets, maps, imagery, photos, or vendor documents to customers by default.

### Automated access and CFAA/terms risk

The [Computer Fraud and Abuse Act](https://www.law.cornell.edu/uscode/text/18/1030) is not a general public-web scraping license. [Van Buren v. United States](https://www.supremecourt.gov/opinions/20pdf/19-783_k53l.pdf) narrowed “exceeds authorized access,” and the Ninth Circuit's public-site analysis in [hiQ v. LinkedIn](https://cdn.ca9.uscourts.gov/datastore/opinions/2022/04/18/17-16783.pdf) is not controlling precedent in Pennsylvania's Third Circuit. Contract/terms, copyright, trespass/load, circumvention, privacy, and misrepresentation risks remain.

CountyIQ should only automate sources that are intentionally public, permit the method used, and can be accessed without bypassing authentication, CAPTCHAs, technical blocks, or access controls. Keep current robots checks, conservative rate limits, conditional requests, identifiable contact information, source-level kill switches, and evidence of terms checked. A Playwright fallback does not create permission.

### Court/criminal data

The [Unified Judicial System Electronic Case Record Public Access Policy](https://www.pacourts.us/Storage/media/pdfs/20211119/145411-amendedecrpolicyeffective1.1.22.pdf) excludes categories such as Social Security and account numbers, victim/informant/juror data, certain addresses, sealed/restricted material, and other identifiers. Bulk access is subject to AOPC capability, referral, fees, and conditions; excluded data may be released only in deidentified form for limited purposes with certifications.

Pennsylvania CHRIA, including [18 Pa.C.S. § 9121](https://www.legis.state.pa.us/WU01/LI/LI/CT/HTM/18/00.091..HTM), restricts dissemination of criminal-history information, including limited-access charge information. CountyIQ should not ingest probation, inmate, person-level police, or criminal docket data into a commercial people/property intelligence product without a separate legal program.

### Consumer reports and prohibited customer uses

If CountyIQ supplies information about a natural person for credit, insurance, employment, tenant/housing, or similar eligibility decisions, it can become a consumer reporting agency or furnish consumer reports under the Fair Credit Reporting Act. The FTC's [tenant-screening guidance](https://www.ftc.gov/business-guidance/resources/what-tenant-background-screening-companies-need-know-about-fair-credit-reporting-act) describes duties including permissible purpose, maximum possible accuracy, consumer access, and disputes.

Unless CountyIQ deliberately builds a separate compliant program, customer terms and product design should prohibit:

- credit, insurance, employment, tenant, or housing eligibility screening;
- adverse action against a person;
- locating, harassing, intimidating, or threatening people;
- debt collection or targeted solicitation based on delinquency, foreclosure, sheriff sale, probate, or vulnerability;
- protected-class targeting or housing decisions using protected traits/proxies; and
- redistributing raw person/owner lists.

These prohibitions need enforcement: no unrestricted person-name lookup, no bulk distress-owner export, role-based access, query/export logging, anomaly detection, account suspension, and contractual audit/termination rights.

### Privacy, security, and evolving Pennsylvania law

Aggregation can create new exposure even when each input was public. Searchability, permanent history, cross-source linkage, scoring, and subscriber distribution materially change practical privacy and reputational risk.

Current Pennsylvania requirements and watch items include:

- The [Breach of Personal Information Notification Act](https://www.legis.state.pa.us/WU01/LI/LI/US/HTM/2005/0/0094..HTM), as amended, applies to covered personal information held by a business; CountyIQ account/authentication/payment data is covered even where a public government record is excluded from the statute's definition.
- [18 Pa.C.S. § 2719](https://www.legis.state.pa.us/WU01/LI/LI/CT/HTM/18/00.027..HTM) addresses publication of restricted personal information of a public-safety official with threatening/harassing intent. It is not a complete data-removal law; separate RTKL address exclusions and safety controls still matter.
- [HB 78 (2025–2026)](https://www.palegis.us/legislation/bills/2025/hb78), a broad consumer-data bill, was at Senate second consideration on 2026-06-25 and was **not enacted as of this review**. It should be monitored because final obligations could affect access, deletion/correction, sensitive data, contracts, and assessments.
- FTC Act risk remains if privacy/security representations are inaccurate or material product practices are unfair or deceptive.

CountyIQ should offer correction and safety-suppression channels even when not strictly required, while preserving a nonpublic audit record of the source and correction.

## Mandatory controls before a paid launch

1. **Pin York ingestion to the current `OPEN_DATA` service.** Do not source from the Property Tax Viewer or legacy application items. Capture the service definition, enterprise item JSON, metadata PDF, terms fields, timestamps, and content hashes before first paid use and at every detected terms change. Written YCPC confirmation remains recommended for source-identical exports and indefinite historical retention, not a categorical blocker for derived analytics.
2. **Create a source-rights registry enforced by the pipeline.** Required fields: source owner, exact endpoint/item ID, access method, license/terms URL and captured text/hash, checked date, allowed purposes, redistribution/export rules, attribution, retention, personal-data class, counsel/owner approval, and kill-switch status.
3. **Default unknown rights to hold.** “Public,” “no login,” “downloadable,” and “in an ArcGIS REST directory” are not sufficient commercial rights states.
4. **Separate raw evidence from customer data.** Private object storage, least-privilege access, encryption, retention limits, and no customer raw-document URL unless independently authorized.
5. **Minimize person data.** Prefer entity/property IDs; suppress owner mailing address from broad search/export; do not expose phone/email, household, probate, criminal, voter, recipient, or public-safety home-address data.
6. **Add accuracy and correction controls.** Source/effective dates, confidence, “not official determination” labels, correction intake, investigation SLA, versioned corrections, and immediate suppression for credible safety claims.
7. **Enforce prohibited uses.** Terms, onboarding attestations, query/export limits, monitoring, and termination—not a disclaimer alone.
8. **Validate licenses per county before expansion.** County onboarding is a legal/data contract, not just a URL/config exercise. Preserve the absence of commonality in the coverage matrix.
9. **Perform vendor review.** Landex, CivicPlus, OpenGov, eCode360, Esri-hosted items, and other vendor systems require contract/terms analysis even when a government customer operates them.
10. **Prepare security governance.** Data inventory/classification, vendor DPAs, secrets/access review, tested backups, incident response, breach-notification workflow, and deletion/retention schedules.
11. **Have counsel review the final customer experience.** Especially owner profiles, distressed-property pages, entity resolution, predictive scores, alerts, exports, advertising/solicitation positioning, and FCRA/FHA boundaries.

## Recommended product/data roadmap

### Build first — high value and portable

1. PennDOT roads, traffic, bridges, projects, rail, and transportation context.
2. DEP environmental permits/facilities, impaired waters, tanks, mines, oil/gas, stormwater, and waste layers.
3. FEMA/USGS/DCNR flood, terrain, geology, sinkhole, wetland, and natural-resource constraints.
4. Census ACS/CBP/BPS, DCED municipal finance/tax, DLI/BLS/BEA economic context.
5. State business entities, PLCB and professional licenses, public food inspections, and public procurement/awards.
6. York `OPEN_DATA` parcels, planning subdivisions, zoning/overlays, future land use, growth areas, buildings, roads, traffic, environmental constraints, easements, and agricultural-security areas as a private derived-analytics foundation. These are strong differentiators; minimize person-linked fields and do not provide source-equivalent bulk exports.

### Build after permission and controls

1. Source-identical York parcel/assessment exports, very large customer downloads, and indefinite reconstruction-ready parcel history; obtain explicit written terms and counsel approval.
2. York non-`OPEN_DATA` planning/project layers, including economic-development candidate parcels.
3. Tax claims and sheriff sales, with strict property-purpose, accuracy, retention, and anti-misuse controls.
4. Municipal proceedings-derived development events, with source-level terms and document-retention rules.
5. Paid deed/mortgage data under an explicit commercial license.

### Do not make part of the general product

Probation/inmate/criminal-history profiles, individual voter records, restricted archaeology, operational 911 data, household assistance/health records, or person-targeting lists based on financial/legal distress.

## Counsel/data-owner questions that must be answered

1. Can YCPC confirm that the current `OPEN_DATA/Parcels/FeatureServer` and its no-use-constraints metadata—not the Property Tax Viewer terms—govern automated backend acquisition and CountyIQ-derived commercial analytics?
2. What threshold separates permissible attribute display/export from prohibited raw or source-equivalent redistribution, and may CountyIQ expose small authenticated exports?
3. May CountyIQ retain historical snapshots after a source record changes or is removed, and may it expose derived change events without exposing the old raw record?
4. What attribution, disclaimer, correction, and update obligations apply?
5. Are tax-claim and sheriff-sale lists authorized for commercial property analytics, and what use/redistribution restrictions apply?
6. Do owner profiles, distress flags, briefs, alerts, and proposed customer workflows trigger FCRA, FHA, debt-collection, privacy, or professional-licensing obligations?

## Maintenance cadence

This register should be rechecked quarterly and before every new county/source launch. Recheck immediately when an endpoint, robots policy, terms page, ArcGIS item owner/license, vendor, authentication requirement, schema, or data classification changes. Record a negative result—missing API, unsigned PASDA status, request-only delivery, unavailable field, or commercial-rights uncertainty—as data, not as an empty cell.

## Primary sources

- [York County GIS/Maps](https://yorkcountypa.gov/1042/GISMaps)
- [York `OPEN_DATA/Parcels` FeatureServer](https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/Parcels/FeatureServer)
- [YCPC 2025 parcel metadata](https://www.ycpc.org/DocumentCenter/View/6301/Parcels-PDF-)
- [York County Property Tax Viewer disclaimer](https://arcweb1.ycpc.org/Disclaimer/Disclaimer.pdf)
- [York County Open Records Policy](https://yorkcountypa.gov/698/Open-Records-Policy)
- [YCPC Data & Analyses](https://www.ycpc.org/410/Data-Analyses)
- [YCPC Subdivision Activity Reports](https://www.ycpc.org/233/Subdivision-Activity-Reports)
- [PASDA About](https://www.pasda.psu.edu/about.html)
- [PASDA 2022 PA GIS Data Sharing Report](https://www.pasda.psu.edu/2022_Data_Sharing_Report.pdf)
- [PASDA participation/private-sector purpose](https://www.pasda.psu.edu/participate.html)
- [PASDA County Data Sharing Status service](https://apps.pasda.psu.edu/arcgis/rest/services/CountyDataShare/MapServer/0)
- [Commonwealth geospatial data-sharing agreement](https://www.pa.gov/content/dam/copapwp-pagov/en/oa/documents/programs/information-technology/documents/geospatial-data-sharing-agreement.pdf)
- [Commonwealth GIS Data Access](https://www.pa.gov/agencies/oa/programs/information-technology2/state-geospatial-coordinating-board/gis-data-access)
- [Commonwealth Open Data Policy](https://data.pa.gov/data-policy)
- [Pennsylvania Right-to-Know Law](https://www.legis.state.pa.us/WU01/LI/LI/US/HTM/2008/0/0003..HTM)
- [UJS Electronic Case Record Public Access Policy](https://www.pacourts.us/Storage/media/pdfs/20211119/145411-amendedecrpolicyeffective1.1.22.pdf)
- [Pennsylvania breach-notification law](https://www.legis.state.pa.us/WU01/LI/LI/US/HTM/2005/0/0094..HTM)
- [Pennsylvania HB 78 status](https://www.palegis.us/legislation/bills/2025/hb78)
- [FTC tenant-screening/FCRA guidance](https://www.ftc.gov/business-guidance/resources/what-tenant-background-screening-companies-need-know-about-fair-credit-reporting-act)
- [17 U.S.C. § 105](https://www.law.cornell.edu/uscode/text/17/105)
- [Georgia v. Public.Resource.Org](https://www.supremecourt.gov/opinions/19pdf/590us1r30_3f14.pdf)
- [18 U.S.C. § 1030](https://www.law.cornell.edu/uscode/text/18/1030)
- [Van Buren v. United States](https://www.supremecourt.gov/opinions/20pdf/19-783_k53l.pdf)
- [hiQ Labs v. LinkedIn](https://cdn.ca9.uscourts.gov/datastore/opinions/2022/04/18/17-16783.pdf)
- [Zillow, Inc. v. Luzerne County](https://www.pacourts.us/assets/opinions/Commonwealth/out/194CD25_6-9-26.pdf?cb=1)
- [Regrid York County parcel store](https://app.regrid.com/store/us/pa/york)
- [CountyGISMaps York County listing](https://countygismaps.com/pa/york) and [license](https://countygismaps.com/licensing)
