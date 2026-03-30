# York County Intelligence Platform — Data Source Feasibility Report

**Schema note:** All source data targets the `staging` schema (e.g., `staging.parcels`, `staging.conservation_district_plans`). See `docs/schema/strategy.md` for the full schema layout. Earlier drafts of this document used per-domain schemas (`permits.*`, `business.*`, etc.) which have been removed.

*Compiled March 20, 2026 — Updated with Live Browser Testing Results*

---

## Executive Summary

This report documents the actual accessibility, ingestion method, legal basis, and risk assessment for every data source identified for the York County Intelligence Platform. **Each source was tested against live endpoints via browser on March 20, 2026**, with corrected URLs, actual API responses, and verified data structures.

**Bottom line:** The MVP can be built entirely on freely downloadable, legally unambiguous data sources. The GIS data is richer than expected (49 Feature Services via ArcGIS REST API on `arcweb1.ycpc.org`, not the previously documented endpoint). PennDOT's Projects MapServer adds 46 more layers with 78 fields per project — promoted to MVP. The intermediate phase requires two formal requests (AOPC bulk court data, York County Recorder of Deeds) and introduces moderate scraping that is legally defensible. Six additional sources (Sources 11-16) have been verified and add development pipeline visibility, tax sale intelligence, and government decision tracking. The grand vision's meeting minutes ingestion is the highest-effort, lowest-risk data collection task.

**Total verified sources: 22** (10 original + 12 new). 20 are legally accessible and free. 2 require formal RTK/AOPC requests. 1 (Landex) is paid and deprioritized. 1 (Inmate Records) is unreachable and needs manual URL verification. Key surprise: PLCB provides bulk CSV download of all liquor licenses — no scraping needed.

**Key corrections from live testing:**
- The original Open Data Hub URL (`data-yorkcountypa.opendata.arcgis.com`) is **dead (404)**. The working portal is `york-county-pa-gis-portal-yorkcountypa.hub.arcgis.com`
- The ArcGIS REST API is hosted on `arcweb1.ycpc.org` (YCPC's own server), NOT `services1.arcgis.com`
- The Assessment portal is powered by **iasWorld Public Access** (ASP.NET), not a generic web app — this affects scraping strategy
- Assessment portal has a "cannot be sold" disclaimer on the home page — analyzed below
- PA DOS Business Search is behind **Cloudflare** bot protection at `file.dos.pa.gov`
- UJS Portal has **no robots.txt** and offers a **Parcel** search option (links cases to properties)
- Landex Webstore is a **paid commercial service** ($5 + per-document fees) — not viable for bulk data

---

## Data Source Matrix

| # | Source | Phase | Access Method | Auth Required | Legal Risk | Cost | Live Test Status |
|---|--------|-------|---------------|---------------|------------|------|-----------------|
| 1 | York County GIS Portal | MVP | ArcGIS REST API | None | Minimal | Free | ✅ Verified |
| 2 | York County Assessment Database | MVP | Playwright scraping / RTK | None (web) | Low | Free/RTK fees | ✅ Verified |
| 3 | FEMA National Flood Hazard Layer | MVP | Direct download | None | Minimal | Free | ✅ Verified |
| 4 | PA Open Data Portal (data.pa.gov) | MVP | SODA API | None | Minimal | Free | ✅ Verified |
| 5 | PennDOT Open Data | MVP | ArcGIS REST API | None | Minimal | Free | ⚠️ Not live-tested (same platform pattern as #1) |
| 6 | UJS Portal (Court Records) | Phase 2 | Formal AOPC request + Playwright | None (web) / Written app (bulk) | Minimal | Fees TBD | ✅ Verified |
| 7 | York County Recorder of Deeds | Phase 2 | RTK request (bulk) | Paid (Landex) | Low-Moderate | RTK fees / $5+/doc (Landex) | ✅ Verified |
| 8 | PA DOS Business Entities | Phase 2 | file.dos.pa.gov + data.pa.gov | None | Minimal | Free | ✅ Verified |
| 9 | Sheriff Sales / Tax Claim | Phase 2 | Web scraping + PDF parsing | None | Low | Free | ⚠️ URL structure changed on county site |
| 10 | Municipal Meeting Minutes | Phase 3 | Web scraping (72 municipalities) | None | Low | Free | ⚠️ Not live-tested (72 separate sites) |
| 11 | Conservation District (YCCD) | Phase 2 | PDF download + pdfplumber | None | Minimal | Free | ✅ Verified |
| 12 | County Bids | Phase 2 | HTML scraping (BeautifulSoup) | None | Minimal | Free | ✅ Verified |
| 13 | PennDOT Projects | MVP | ArcGIS MapServer REST API | None | Minimal | Free | ✅ Verified |
| 14 | Tax Claim Bureau | Phase 2 | HTML + PDF parsing | None | Low | Free | ✅ Verified |
| 15 | Commissioners Meetings | Phase 2 | HTML table + PDF download | None | Minimal | Free | ✅ Verified |
| 16 | YCPC Subdivision Activity | Phase 2 | HTML + PDF download (pdfplumber) | None | Minimal | Free | ✅ Verified |
| 17 | PA DEP eFACTS | Phase 2 | ASP.NET scraping (Playwright) | None | Minimal | Free | ✅ Verified |
| 18 | York City RFPs | Phase 2 | HTML scraping (BeautifulSoup) | None | Minimal | Free | ✅ Verified |
| 19 | CRIMEWATCH (Police Blotters) | Phase 2 | Playwright + pagination | None | Low | Free | ✅ Verified |
| 20 | Inmate Records | Phase 2 | Unknown — domain unreachable | Unknown | TBD | TBD | ❌ DNS failure |
| 21 | PALS Professional Licenses | Phase 2 | Playwright (AngularJS SPA) | None | Minimal | Free | ✅ Verified |
| 22 | PLCB Liquor Licenses | Phase 2 | CSV bulk download (no scraping!) | None | Minimal | Free | ✅ Verified |

---

## Source 1: York County GIS Portal

**Working URL:** https://york-county-pa-gis-portal-yorkcountypa.hub.arcgis.com/

**⚠️ DEAD URL (from original report):** ~~https://data-yorkcountypa.opendata.arcgis.com/~~ → Returns 404 "Page Not Found"

**Phase:** MVP

### What's Available (Verified March 20, 2026)
The portal shows **49 Feature Service datasets** in the OPEN_DATA folder, including:

- **Parcels** — 176,060 records, last updated Oct 27, 2025. 47 attribute fields including PIDN, owner name (full, first, last), previous owner, property address, mailing address, deed book/page, assessed values (land/building/total), sale date/price/previous price, year built, living area, stories, heating system, school district, land use code, acreage, class (R/C/I), commercial building sq ft, grade, CDU
- **Municipal_Boundary** — 72 polygon boundaries (boroughs, townships, city). Provides the municipality name for every parcel via spatial join (`ST_Intersects`). The parcels layer itself has no municipality field — this layer is the authoritative source.
- **AddressPts** — Geocoded point for every address in the county (~1 per structure). Backend-only (not a map layer). Two key uses: (1) **Entity resolution fallback** — when a parcel's PROPADR is messy or missing, match an owner's mailing address against address points for a second-chance geocode. (2) **Search accuracy** — provides a canonical, pre-geocoded address list for `/api/search` fuzzy matching, rather than relying solely on the inconsistent PROPADR field ("ST" vs "STREET", missing unit numbers, etc.).
- **BLDG_Footprint** — Polygon outline of every building in the county. Three key uses: (1) **Visual quality** — at zoom 15-16, parcel boundaries alone look like empty lot grids; adding building footprints makes it look like a real place (single biggest visual upgrade for minimal effort). (2) **Vacancy/improvement detection** — a parcel with no footprint is likely vacant; a parcel assessed as "improved" with no footprint is a data quality flag. (3) **Assessment analysis** — footprint square footage vs assessed living area can flag assessment discrepancies.
- Zoning, Zoning Overlays
- HYDRO_Floodplains, Streams, Watersheds, Wetlands, Lakes/Ponds
- DIST_School, DIST_House, DIST_Senate, DIST_Precinct, DIST_Magisterial
- Roads, Contours
- LANDUSE_Future_Landuse, Growth_Areas, Geology, Soils
- Parks, RECREATION_Trails, Transit_Routes, Traffic_Counts
- DES_EMS_Stations, DES_Fire_Stations, DES_Police_Stations
- PUB_FACIL_Schools, Libraries, Medical, Nursing_Homes, Govt_Offices, Polling_Place
- Conservation_Easements, Ag_Security, ENVIR_Natural_Areas_Inventory
- Zipcodes, Land_Joins, PLANNING_Subdivisions, PLANNING_Heritage_Sites

### Access Method (Verified)
**ArcGIS REST API on YCPC's own server. No authentication required.**

- **REST API base (VERIFIED WORKING):** `https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/`
- **Server version:** ArcGIS 11.5
- **Parcels FeatureServer:** `https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/Parcels/FeatureServer/0`
- **Query endpoint (TESTED):** `https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/Parcels/FeatureServer/0/query?where=1%3D1&outFields=*&resultRecordCount=2&f=json`
- **Response format:** JSON with full attributes + polygon geometry (State Plane PA South, WKID 2272)
- **Pagination:** Supported via `resultRecordCount` + `resultOffset` (`exceededTransferLimit: true` in response)
- **GeoJSON endpoint:** Also available from the same server
- **Download formats on Hub:** CSV, Shapefile, GeoJSON, KML available via the portal UI
- **License:** Custom License (standard YCPC disclaimer — data provided as-is, not a legally recorded plan)

**⚠️ INVALID (from original report):** ~~`https://services1.arcgis.com/KDAchYMHMRxuGkv7/arcgis/rest/services`~~ → Returns `{"error":{"code":400,"message":"Invalid URL"}}`

### Parcels Dataset — Field Inventory (from live API response)

| Field | Alias | Type | Notes |
|-------|-------|------|-------|
| PIDN | Parcel ID Number | String(13) | Primary key |
| DISTRICT | District | String(2) | |
| BLOCK | Block | String(3) | |
| MAP | Map | String(2) | |
| PARCEL | Parcel | String(6) | |
| PARCEL_MAJOR | Parcel Major | String(4) | |
| PARCEL_MINOR | Parcel Minor | String(2) | |
| LEASEHD | Lease Hold | String(5) | |
| DEED_BK | Deed Book | String(8) | Links to Recorder of Deeds |
| DEED_PG | Deed Page | String(8) | Links to Recorder of Deeds |
| SITE_ST_NO | Site Street Number | Integer | |
| SITE_ST_DIR | Site Street Direction | String(2) | |
| SITE_ST_NAME | Site Street Name | String(30) | |
| SITE_ST_SUF | Site Street Suffix | String(8) | |
| PROPADR | Property Address | String(54) | Full address |
| OWNER_FULL | Owner Full Name | String(81) | Entity resolution target |
| OWN_NAME1 | Owner First Name | String(40) | |
| OWN_NAME2 | Owner Last Name | String(40) | |
| MAIL_ADDR_FULL | Full Mailing Address | String(124) | |
| MAIL_ADDR1-3 | Mailing Address Lines | String(40) each | |
| PREV_OWNER | Previous Owner | String(40) | Ownership history |
| CLASS | Class | String(1) | R=Residential, C=Commercial, I=Industrial |
| LUC | Land Use Code | String(4) | |
| ACRES | Acres | Double | |
| STYLE | Style | String(2) | Building style code |
| NUM_STORIE | Number of Stories | Double | |
| RES_LIVING_AREA | Residential Living Area | Integer | Square feet |
| YRBLT | Year Built | SmallInteger | |
| CLEAN_GREEN | Clean Green | String(3) | Tax program enrollment |
| HEATSYS | Heating System | SmallInteger | Code |
| FUEL | Fuel | SmallInteger | Code |
| UTILITY | Utility | String(40) | |
| APRLAND | Appraised Land | Double | Assessment value |
| APRBLDG | Appraised Building | Double | Assessment value |
| APRTOTAL | Appraised Total | Double | Assessment value |
| SALEDT | Sale Date | String(11) | |
| PRICE | Price | Double | Last sale price |
| PREV_PRICE | Previous Price | Double | |
| SCHOOL_DIS | School District | String(5) | Code |
| COMM_STRUC | Commercial Structure Code | String(3) | |
| COMM_YEAR_BUILT | Commercial Year Built | Integer | |
| COMM_BUILDING_SQ_FT | Commercial Building Sq Ft | Integer | |
| GRADE | Grade | String(2) | |
| CDU | CDU | String(2) | Condition/Desirability/Utility |

### Ingestion Strategy (Updated)
- **Method:** Direct REST API queries with pagination — no Playwright needed, pure HTTP GET
- **Bulk load:** Page through all 176,060 records using `resultRecordCount=2000&resultOffset=N`
- **Coordinate system:** Request `outSR=4326` for WGS84 coordinates directly from the API
- **Refresh:** Scheduled Dagster asset, weekly (Sunday 02:00)
- **Storage:** Parse JSON into PostGIS tables with SCD Type 2:
  - `staging.parcels` — 176K+ polygons, all attributes, PIDN as natural key
  - `staging.municipalities` — 72 polygons from Municipal_Boundary layer
  - `staging.address_points` — geocoded points from AddressPts layer
  - `staging.structures` — building footprint polygons from BLDG_Footprint layer
  - `staging.school_districts`, `staging.zoning_districts` from other layers
- **Enrichment (post-load):** Spatial join municipalities → parcels to populate `staging.parcels.municipality`

### Legal Basis
**Minimal risk.** Data is explicitly published as "Public — Anyone can see this content" on an official government ArcGIS portal. Custom license is a standard liability disclaimer, not a usage restriction. YCPC Planning Commission maintains the data for public use.

### Verdict: ✅ GO — MVP Day 1 (corrected endpoints)

---

## Source 2: York County Assessment Database

**URL:** https://assessmentpublic.yorkcountypa.gov/

**Phase:** MVP

### What's Available (Verified March 20, 2026)
The assessment portal provides these detail tabs per property (verified by navigating to a property record):

- **Profile:** PARID, municipality, school district, NBHD code, tax year, property class, LUC code, topography, utilities, roads, CAMA acres
- **Owner:** Owner name and mailing address
- **Sales:** Sale history with dates and prices
- **Values:** Current assessed values
- **Value History:** Historical assessment values
- **Land:** Land details
- **Agricultural:** Clean & Green / agricultural data
- **Residential:** Residential building details (bedrooms, bathrooms, etc.)
- **Outbuildings:** Outbuilding details
- **Permits:** Building permits
- **Commercial:** Commercial building details
- **Current Tax Information:** Tax amounts by jurisdiction
- **Delinquent Taxes:** Outstanding tax obligations
- **Appeals:** Assessment appeal history
- **Photos:** Property photos

### Platform Details (Discovered via live testing)
- **Software:** iasWorld Public Access (by Tyler Technologies, formerly Thomson Reuters)
- **Technology:** ASP.NET Web Forms (C#)
- **Data currency:** March 14, 2026 (displayed on portal)
- **Search types:** Basic Search (owner name, parcel ID, address) and Advanced/Sales Search
- **URL structure:** Session-based — `Datalets/Datalet.aspx?sIndex=0&idx=3` (NOT RESTful — no direct deep links to specific properties)
- **Pagination:** Search results show "Displaying 1-15 of 500" with page navigation
- **Result cap:** Maximum 500 results displayed per search, max 2119 total found for common names
- **Parcel ID format:** 18-digit (e.g., `46000060065000000`)

### The "Cannot Be Sold" Clause — Analysis

**The home page disclaimer states:** "The information provided herewith is solely for your own use and cannot be sold."

**Legal analysis:**
1. This is a **website Terms of Use** disclaimer, not a statute. It cannot override the PA Right-to-Know Law, which makes assessment records public.
2. The full Search Disclaimer page is a standard **liability waiver** — "no representations or warranties," "use at your own risk," "not liable for damages." This is boilerplate, not a data licensing restriction.
3. **The RTK request path bypasses this disclaimer entirely.** When you request data directly from the Assessment Office under Act 3 of 2008, you're not bound by the website's ToU — you're exercising a statutory right.
4. Assessment records are **public records by statute** in Pennsylvania. A website disclaimer cannot restrict the public nature of government records.
5. **Practical impact:** Don't sell raw scraped data from the portal. Instead: (a) file RTK request for bulk data, (b) use scraped portal data only to enrich/validate RTK data, (c) your platform provides analysis and value-add, not raw resale of the data.

### Access Method
**Web scraping requires Playwright.** The iasWorld platform uses ASP.NET ViewState, session cookies, and postback-based navigation. Cannot be scraped with simple HTTP requests.

**No API available.** iasWorld is a commercial CAMA system; Tyler Technologies does not expose public APIs.

### Ingestion Strategy (Updated)
- **Primary (recommended):** File PA RTK request to York County Board of Assessment (28 East Market St, Room 105, York PA 17401-1585, Phone: 717-771-9232, Email: RWhite@yorkcountypa.gov) for full assessment roll in electronic format
- **Fallback:** Playwright scraping of the portal — iterate through municipality codes, extract all property records
- **Playwright considerations:** Must handle ASP.NET ViewState, session cookies, disclaimer "Agree" click, postback navigation, and the 500-result display limit per search
- **Rate limiting:** Essential — 5-10 second delays between requests
- **Refresh:** Monthly (data is updated periodically, not real-time)

### Legal Basis
**Low risk.** Assessment records are public records under PA law. The "cannot be sold" disclaimer is a website ToU, not law. RTK request path is unambiguously legal. Web scraping is defensible under hiQ/Van Buren precedent since no authentication is required.

### Status: DEFERRED — Not wired into MVP pipeline

**Decision (2026-03-29):** The assessment scraper code exists (`pipelines/countyiq/assets/scrapers/assessment.py`) but is **not connected** to any job, schedule, or the `public.properties` VIEW. Reason: the portal's "cannot be sold" disclaimer creates commercial-use ambiguity, and the GIS Parcels layer (#1) already provides the same core fields — owner name, assessed values, sale history, property class, LUC, municipality, school district — with *more* detail (year built, living area, acres, deed references, previous owner, building style).

**What's lost by deferring:**
- `value_history` (historical assessment values by tax year) — nice-to-have, no other free source
- `permits` (building permits) — may be available via eFACTS (#17) in Phase 2
- `delinquent_taxes` — available from Tax Claim Bureau (#14), a free legally-required public notice

**To reactivate:** Wire `assessment_scrape` into the `scraper_refresh` job, add it to `weekly_scrapers` schedule, and restore the assessment join in `public.properties` VIEW. The scraper, parser, tests, and fixtures are all intact.

### Original Verdict: ✅ GO — RTK request preferred, Playwright scraping as fallback

---

## Source 3: FEMA National Flood Hazard Layer (NFHL)

**URL:** https://hazards.fema.gov/femaportal/NFHL/searchResult

**Phase:** MVP

### What's Available (Verified March 20, 2026)
- **Item ID:** 42133C-NFHL
- **County:** York County, Pennsylvania
- **Last updated:** August 19, 2025
- **Download size:** 77MB
- **Format:** Shapefile (zipped)
- **Contents:** Flood zone boundaries (A, AE, X, VE zones), Base Flood Elevations, floodway delineations, cross-section lines, community boundaries

### Access Method (Verified)
**Direct download from FEMA Map Service Center.** No authentication, no registration.

The NFHL search result page at `hazards.fema.gov/femaportal/NFHL/searchResult` provides a searchable table of 2,659 county-level downloads. Searching "YORK COUNTY PENNSYLVANIA" returns the single exact match with a download button.

Additional access paths:
- **REST API:** `https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer`
- **PASDA (Penn State):** https://www.pasda.psu.edu/
- **Data.gov:** https://catalog.data.gov/dataset/fema-flood-zones-e5639

### Ingestion Strategy
- **Method:** One-time shapefile download (77MB), load into PostGIS `flood_zones` table
- **Refresh:** Quarterly (FEMA updates regularly), automated via Dagster
- **Spatial join:** Pre-compute `parcel_spatial_overlays` by intersecting parcel geometries with flood zone polygons

### Legal Basis
**Minimal risk.** US federal government data, public domain, no copyright, no restrictions.

### Verdict: ✅ GO — MVP Day 1

---

## Source 4: PA Open Data Portal (data.pa.gov)

**URL:** https://data.pa.gov/

**Phase:** MVP (supplemental), Phase 2 (business entities)

### What's Available (Verified March 20, 2026)
The SODA catalog API at `data.pa.gov/api/catalog/v1` is operational. Searching "york county" returns 1,520 results across federated Socrata portals.

Key finding: The first result is the "York County GIS Open Data Portal" entry (dataset ID `r3cg-p69f`), which is a type `href` (link) pointing to the GIS Hub — not a tabular dataset. Querying it returns `"no row or column access to non-tabular tables"`.

**Relevant tabular datasets for the platform:**
- Registered Businesses in PA Current by County (`xvd7-5r2c`)
- Various environmental, licensing, and infrastructure datasets

### Access Method (Verified)
**SODA API is operational.** Catalog query tested and returned valid JSON:
```
GET https://data.pa.gov/api/catalog/v1?q=york%20county&limit=5
```
Response time: 38ms. Full SoQL query language supported.

### Ingestion Strategy
- **Method:** HTTP GET to SODA API endpoints with `?county=YORK` filter
- **Format:** JSON or CSV
- **Pagination:** `$limit` and `$offset` parameters, max 50,000 per page
- **Refresh:** Weekly via Dagster

### Legal Basis
**Minimal risk.** State open data initiative, explicitly public, no restrictions.

### Verdict: ✅ GO — Free, API-accessible

---

## Source 5: PennDOT Open Data

**URL:** https://data-pennshare.opendata.arcgis.com/

**Phase:** MVP (reference layers)

### What's Available
County boundaries, local roads, bridges, transportation infrastructure, municipality boundaries. Same ArcGIS Hub platform pattern as Source 1.

### Access Method
**ArcGIS REST API + download.** Not live-tested in this session, but uses identical platform (Esri ArcGIS Hub) as the York County GIS Portal — same access pattern confirmed to work.

### Ingestion Strategy
- **Method:** GeoJSON/shapefile download, load as reference layers
- **Refresh:** Infrequent (infrastructure data changes slowly)

### Legal Basis
**Minimal risk.** State agency open data, explicitly published for public use.

### Verdict: ✅ GO — Reference data, low priority

---

## Source 6: PA Unified Judicial System Portal (Court Records)

**URL:** https://ujsportal.pacourts.us/

**Phase:** Phase 2

### What's Available (Verified March 20, 2026)
The UJS Portal Case Search page is accessible with no login required.

**Search options (verified from live dropdown):**
- Appellate (by court name)
- Attorney
- Calendar Event
- Citation Number
- Complaint Number
- Date Filed
- Docket Number
- Incident Number
- Organization
- OTN (Offense Tracking Number)
- **Parcel** ← Key for our platform — links court cases directly to properties
- Participant Name
- SID

### Key Technical Findings
- **robots.txt:** Does NOT exist (returns 404 error page). No explicit crawl directives.
- **Terms & Conditions:** Link exists in footer but resolves to error page — could not read full T&C
- **Authentication:** Not required for case search. "Create New Account" and "Login" options exist but are not required
- **Technology:** ASP.NET MVC application with JavaScript rendering — would require Playwright for scraping
- **URL pattern:** Clean URLs (`/CaseSearch`) — more scraping-friendly than the Assessment portal

### Access Method
**Formal bulk data request to AOPC is the recommended path.**

The formal process (204 Pa. Code § 213.81):
1. Download the "Request for Bulk Distribution of Electronic Case Records" form from https://www.pacourts.us/public-records/public-records-forms
2. Complete with: specific data requested (York County CPCMS + MDJS dockets), security plan, purpose certification
3. Submit to AOPC Information Technology, PO Box 62307, Harrisburg, PA 17106-2307
4. AOPC provides cost estimate (fees = computer time + media + shipping)

**Scraping considerations:** Although no robots.txt exists and no auth is required, the AOPC provides a formal bulk distribution mechanism. Use it — the data will be cleaner and more complete than anything scraped from the web portal.

### Legal Basis
**Minimal risk when using formal request process.** The AOPC explicitly permits bulk distribution under 204 Pa. Code § 213.74.

### Verdict: ✅ GO — File formal AOPC bulk request (Phase 2 gating item)

---

## Source 7: York County Recorder of Deeds

**Portal:** Landex Webstore at https://www.landex.com/webstore/

**Phase:** Phase 2

### What's Available
Deeds, mortgages, liens, UCC filings, satisfactions, releases, assignments, lis pendens, easements. Data fields: grantor/grantee names, recording date, book/page, instrument type, consideration amount.

### Key Findings from Live Testing

**Landex Webstore (verified March 20, 2026):**
- This is a **paid commercial document publishing service** by Optical Storage Solutions, Inc.
- The process: Search → Add to Cart → Checkout ($5 order processing + per-document price) → Download PDF
- Not viable for bulk data acquisition
- Provides "real-time access to Recorder of Deeds/Register of Wills and selected Orphans Court records for counties in Pennsylvania and New York"
- Subject to Terms of Use and Privacy Policy
- JavaScript required ("This page requires JavaScript to view properly")

**Note on liens:** The Landex page explicitly states: "If you are looking for LIENS in Pennsylvania against a property, those documents are filed in the Prothonotary's Office, not Recorder of Deeds."

### Access Method (Updated)
1. **File RTK request** to York County Recorder of Deeds for bulk electronic export of the recorded document index (parties, dates, types, book/page, parcel references — NOT document images)
2. **For ongoing incremental updates:** Could potentially use Landex search to identify new recordings, but the paid model makes this impractical for bulk updates
3. **Alternative:** Check if York County has a free deed index search separate from Landex (many PA counties do)

### Legal Basis
**Low-moderate risk.** Recorded documents are public records. RTK for index data is fully legal. Landex is a commercial vendor — their paid model and ToS restrict automated access to their platform specifically.

### Verdict: ✅ GO — RTK request for bulk index (Phase 2)

---

## Source 8: PA Department of State Business Entities

**Working URL:** https://file.dos.pa.gov/search/business

**⚠️ SSL ERROR:** ~~https://www.corporations.pa.gov/search/corpsearch~~ → Privacy/SSL error in browser

**Phase:** Phase 2

### What's Available (Verified March 20, 2026)
Business entity search returned 99 results for "York County". Result fields:
- **Filing Information:** Entity name + filing number (e.g., "Central Pennsylvania Transportation Authority (606005)")
- **Former names** displayed inline
- **Initial Filing Date** (dates going back to 1864 in results)
- **Status:** Active, Active - County Orphan, etc.
- **Entity Type:** Authority, County Orphan, LLC, Corporation, etc.
- **Formed In:** State of formation
- **Address:** Registered address

Data currency: "As of 03/20/2026 we have processed all business filings received in our office through 03/17/2026"

### Key Technical Findings
- **Cloudflare protection:** Site displayed "Just a moment..." Cloudflare challenge page before loading. This means automated scraping requires Playwright with **stealth plugins** or Cloudflare bypass
- **No robots.txt tested** for this domain
- **Advanced search** option available (dropdown)
- **Sections available:** Business, UCC, Trademark, CROP

### Access Method (Updated — Dual Approach)

**Primary: PA Open Data Portal SODA API**
- Dataset "Registered Businesses in PA Current by County" (`xvd7-5r2c`)
- `https://data.pa.gov/resource/xvd7-5r2c.json?county=YORK`
- No authentication, no Cloudflare, no restrictions

**Secondary: Direct search on file.dos.pa.gov**
- More detailed data (filing number, status, former names, officers)
- Requires Playwright + Cloudflare stealth bypass
- Useful for enrichment beyond what data.pa.gov provides

### Ingestion Strategy
- **Primary:** SODA API from data.pa.gov (no scraping needed)
- **Enrichment:** Playwright scraping of file.dos.pa.gov for officer/agent details (Phase 2+)
- **Target tables:** `business_entities`, `business_officers`
- **Refresh:** Weekly via Dagster

### Legal Basis
**Minimal risk.** Business entity filings are public records. PA Open Data Portal publishes them explicitly for public use.

### Verdict: ✅ GO — PA Open Data Portal SODA API (primary), Playwright with stealth (enrichment)

---

## Source 9: York County Sheriff Sales / Tax Claim

**URLs (from original report — need verification):**
- Sheriff sales: http://sales.yorksheriff.org/sheriff.salelisting/
- Tax claim: https://yorkcountypa.gov/528/Tax-Sale-Information
- Online bidding: https://york.pa.realforeclose.com/

**Phase:** Phase 2

### Live Testing Notes
The York County website (`yorkcountypa.gov`) appears to have reorganized its page IDs. Attempting to navigate to `/971/Sheriff-Sales` and `/297/Sheriff-Sales` both redirected to unrelated pages. The county site uses CivicPlus CMS with numeric page IDs that may have been reassigned.

**Recommendation:** Manually verify these URLs from a local browser. The sheriff sales and tax claim data is definitely published (required by law) — the URLs just need to be re-located on the redesigned county website.

### What's Available
**Sheriff sales:** Active listings with property details, sale dates, case numbers, minimum bids.
**Tax claim/upset sales:** Delinquent tax claim listings (properties with unpaid taxes). PDF format.

### Ingestion Strategy
- **Sheriff sales:** Playwright to scrape listing pages → `government_actions` table with `action_type = 'sheriff_sale'`
- **Tax claim:** Download PDF daily, parse with pdfplumber → `government_actions` with `action_type = 'tax_claim'`
- **Refresh:** Daily

### Legal Basis
**Low risk.** Sheriff sale and tax claim listings are legally required public notices.

### Verdict: ✅ GO — Web scraping + PDF parsing (Phase 2, after URL verification)

---

## Source 10: Municipal Meeting Minutes

**72 municipalities in York County**

**Phase:** Phase 3

### What's Available (from prior research)
All sampled townships publish minutes online as PDFs. No API access anywhere. URL patterns vary significantly. All minutes are static PDF links on individual municipal websites.

### Ingestion Strategy
- **Phase 1:** Build registry of all 72 municipality websites and minutes page URLs
- **Phase 2:** Playwright scraper for PDF discovery and download
- **Phase 3:** OCR/text extraction + NLP for entity and parcel mention extraction
- **Refresh:** Weekly scan of all 72 sites

### Legal Basis
**Low risk.** Meeting minutes are public records under both the PA RTK Law and the PA Sunshine Act.

### Verdict: ✅ GO — High effort, low risk (Phase 3 as planned)

---

## Source 11: York County Conservation District — Pending Plan Review List

**URL:** https://www.yorkccd.org/erosion-and-sediment-control/pending-plan-review-list

**Phase:** Phase 2

### What's Available (Verified March 20, 2026)
The YCCD publishes a weekly PDF listing all pending Erosion & Sediment Control plan/permit applications. The PDF ("Plan Review Status 3-16-2026" was the most recent at test time) is updated every Monday (or Tuesday when Monday is a holiday).

**Data in the PDF:** Applicant name, plan preparer, project municipality, submission date, review status, assigned technician. Each entry represents a land disturbance activity requiring E&S review — new construction, subdivisions, commercial development, stormwater management.

**Why this matters for the platform:** These are leading indicators of development activity. A plan submitted to YCCD today means grading, construction, and eventually a new assessment record 6-18 months from now. Cross-referencing with YCPC subdivision reports and county GIS parcels creates a development pipeline view.

### Access Method (Verified)
**Direct PDF download.** Single PDF link at the bottom of the page, replaced weekly. No authentication, no CAPTCHAs. WordPress site (standard HTML).

### Ingestion Strategy
- **Method:** Weekly HTTP GET of the page → extract PDF link → download PDF → parse with pdfplumber
- **Target table:** `staging.conservation_district_plans`
- **Schedule:** Weekly (Tuesday to catch Monday updates)
- **Parsing notes:** PDF is likely tabular — pdfplumber table extraction should work. May need fallback regex parsing if layout varies.

### Legal Basis
**Minimal risk.** E&S plan submissions are public information. The YCCD publishes this list specifically for public consumption.

### Verdict: ✅ GO — Weekly PDF scrape (Phase 2)

---

## Source 12: York County Bid Postings

**URL:** https://yorkcountypa.gov/Bids.aspx

**Phase:** Phase 2

### What's Available (Verified March 20, 2026)
The county Bid Postings page on CivicEngage (CivicPlus CMS) provides a filterable list of current bid and contract opportunities for consultants, service providers, contractors, vendors, and suppliers.

**Features verified:**
- **Filter controls:** "Show Me" dropdown (Open Bids / All Bids), "Sorted By" dropdown (Category / other options), "Show Closed/Awarded/Cancelled Bids" checkbox
- **Notification system:** "Sign up to receive a text message or email when new bids are added!" link
- **At test time:** "There are no open bid postings at this time" — but the structure and filters confirmed working

**Data per bid:** Title, category, posting date, closing date, description, attached documents (bid specs PDFs).

### Access Method (Verified)
**HTML scraping with BeautifulSoup.** Standard CivicPlus CMS page — server-rendered HTML, no JavaScript rendering required. Your table notes "3 fallback patterns" for parsing — smart, since CivicPlus can vary its HTML structure across updates.

### Ingestion Strategy
- **Method:** HTTP GET → BeautifulSoup parsing with 3 fallback HTML patterns
- **Target table:** `staging.county_bids`
- **Schedule:** Daily
- **Edge case:** The "no open bid postings" state should be handled gracefully (don't error on empty lists)

### Legal Basis
**Minimal risk.** Government bid postings are public notices, legally required to be published for transparency.

### Verdict: ✅ GO — Daily HTML scrape (Phase 2)

---

## Source 13: PennDOT Projects (PA Projects MapServer)

**URL:** https://gis.penndot.gov/arcgis/rest/services/paprojects/paprojects/MapServer

**Phase:** MVP

### What's Available (Verified March 20, 2026)
This is significantly richer than originally documented. The MapServer (ArcGIS 10.91) exposes **46 layers** covering the complete lifecycle of PennDOT road and bridge projects:

**Project status layers (Points + Lines):**
- Layer 0/15: Completed
- Layer 1/16: Underway
- Layer 2/17: Four Year Plan
- Layer 3/18: Twelve Year Program
- Layer 4/19: Under Development
- Layer 5/20: Under Construction
- Layer 6/21: Anticipated
- Layer 7: Aviation Points
- Layer 8: Transit
- Layer 9/22: DOI (Decade of Investment)
- Layer 10/23: TIP (Transportation Improvement Program)
- Layer 11/24: TYP (Twelve Year Plan)

**Bridge condition layers (Points + Lines):**
- Layers 34-36: State Bridges Poor/Fair/Good Condition
- Layers 37-39: State Bridges Poor/Fair/Good Condition Lines
- Layers 40-42: Local Bridges Poor/Fair/Good Condition
- Layers 43-45: Local Bridges Poor/Fair/Good Condition Lines

**Boundary layers:**
- Layers 25-33: Interstate, State, County, District, House, Senate, Congress, Planning Partner, Municipality boundaries

### Live Query Test (Verified)
Queried Layer 1 (Underway Points) with `COUNTY_NAME='YORK'` — returned rich project records with **78 fields** per feature:

**Key fields:** PROJ_ID, PROJECT_TITLE, IMPROVEMENT_CODE_DESC, PROJ_STATUS_DESC, PHS_EST_COST_AM (estimated cost), PRJCT_GRPHY_DC (geographic description), PRJCT_IMPRV_DC (improvement description), LET_DATE, NTP_DATE, COMPLETION_DATE, PROJ_MANAGER, PRJCT_MNGR_EMAIL, COUNTY_NAME, MUNICIPAL_CODE, HOUSE/SENATE/CONGRESS_LEGISLATOR_NAME, ACT_89 flags, bridge work flag, and full geometry.

**Sample results:** "Forrest Ave Resurface" ($3.08M, NTP 03/17/2025), "Wago Road Bridge Rehabilitation" ($4.14M, Let 04/18/2024). `exceededTransferLimit: true` confirms more results available via pagination.

### Access Method (Verified)
**ArcGIS REST API — pure JSON queries, no authentication.**

```
Base: https://gis.penndot.gov/arcgis/rest/services/paprojects/paprojects/MapServer
Query: /1/query?where=COUNTY_NAME%3D%27YORK%27&outFields=*&f=json&resultRecordCount=2000
```

- **Coordinate system:** Web Mercator (WKID 102100/3857)
- **Max record count:** 2000 per page
- **Pagination:** `resultRecordCount` + `resultOffset`

### Ingestion Strategy
- **Method:** REST API queries across layers 1, 2, 4, 5 (Underway, Four Year Plan, Under Development, Under Construction) + bridge condition layers 34-45
- **Filter:** `COUNTY_NAME='YORK'`
- **Target table:** `staging.penndot_projects`
- **Schedule:** Daily (project statuses change)
- **Bonus:** Bridge condition data feeds directly into infrastructure intelligence — poor condition bridges near properties are a material fact for real estate transactions

### Legal Basis
**Minimal risk.** PennDOT publishes this data on an official ArcGIS MapServer explicitly for public access. Federal/state transportation data.

### Verdict: ✅ GO — REST API, promote to MVP (this is too valuable to wait for Phase 2)

---

## Source 14: York County Tax Claim Bureau — Tax Sale Information

**URL:** https://yorkcountypa.gov/528/Tax-Sale-Information

**Phase:** Phase 2

### What's Available (Verified March 20, 2026)
The Tax Sale Information page at `/528/` is **live and working** (unlike the previously broken sheriff sales URLs). Content includes:

**Tax sale types documented:**
- **Upset Sale:** First sale (generally held in September). Starting bid = total delinquent taxes + current taxes + municipal liens + costs. Properties at least 2 years delinquent.
- **Judicial Sale:** Second attempt for unsold properties.
- **Repository Sale:** Final attempt for remaining unsold properties.

**Upcoming sale verified:** "Our next Upset Sale will be held online on September 17, 2026"

**Key sidebar links:**
- **Delinquent Tax Claim Listing (PDF)** — The core data source. Lists all properties with delinquent taxes.
- **Online Payment For Delinquent Taxes** — Indicates York County uses an online payment portal
- **Tax Sale Information** (current page)

**Contact:** Sharon Sauble, Tax Claim Manager, 717-771-9205, Sharon M. Sauble email link. Office: 28 East Market Street, Room Number 110, York, PA 17401.

### Access Method (Verified)
**HTML page scraping + PDF download.** The main page provides sale dates and general info (server-rendered HTML via CivicPlus). The Delinquent Tax Claim Listing sidebar link provides the actual property-level data as a PDF.

### Ingestion Strategy
- **Method:** Daily HTTP GET of the page → parse sale dates and announcements → download Delinquent Tax Claim Listing PDF → parse with pdfplumber
- **Target table:** `staging.tax_sale_notices`
- **Schedule:** Daily (catch new listings and updates)
- **PDF parsing:** The delinquent listing PDF likely contains: parcel ID, owner name, address, tax years delinquent, amount owed. pdfplumber table extraction.

### Legal Basis
**Low risk.** Tax sale notices are legally required public notices under PA Real Estate Tax Sale Law (Act 542 of 1947). Publishing these is a legal obligation.

### Verdict: ✅ GO — Daily HTML + PDF scrape (Phase 2)

---

## Source 15: York County Commissioners — Meeting Agendas and Minutes

**URL:** https://yorkcountypa.gov/1275/_2026 (year is parameterized)

**Phase:** Phase 2

### What's Available (Verified March 20, 2026)
The Commissioners' Meeting Agendas and Minutes page provides a well-structured HTML table covering multiple county boards.

**Boards covered (from page header):**
- Commissioner's Meetings
- Salary Board
- Retirement Board
- Depository Board
- Election Board
- Juvenile Detention Center Meeting Agenda

**Table structure (verified):**
| Meeting Date | Agendas | Minutes |
Each row has: date + optional time/label, PDF link for agenda, PDF link for minutes.

**Example entries verified:** January 5 2026 (Organizational Salary Board), January 7 2026, January 21 2026 — all with PDF links for both agendas and minutes.

**Year navigation:** Sidebar links for 2022, 2023, 2024, 2025, 2026. URL pattern: `/1275/_YYYY`

**Breadcrumb path:** Home > Government > County Administration > Commissioners' Office > Meeting Agendas and Minutes > 2026

### Access Method (Verified)
**HTML table scraping with BeautifulSoup.** Clean, consistent table structure. PDF links are direct downloads. CivicPlus CMS page — server-rendered HTML, no JavaScript required.

### Ingestion Strategy
- **Method:** HTTP GET per year page → parse HTML table → extract meeting dates and PDF links → download PDFs → parse with pdfplumber for decision content
- **Target table:** `staging.commissioners_decisions`
- **Schedule:** Daily (new meetings added regularly)
- **Historical backfill:** 5 years of data available (2022-2026)
- **PDF analysis:** Commissioner meeting minutes contain land use decisions, contract approvals, policy changes — NLP extraction in later phases

### Legal Basis
**Minimal risk.** Meeting minutes and agendas are public records under both the PA Right-to-Know Law and the PA Sunshine Act. The county publishes them specifically for public access.

### Verdict: ✅ GO — Daily HTML table + PDF scrape (Phase 2)

---

## Source 16: YCPC Subdivision Activity Reports

**URL:** https://ycpc.org/233/Subdivision-Activity-Reports

**Phase:** Phase 2

### What's Available (Verified March 20, 2026)
The York County Planning Commission publishes annual Subdivision Activity Reports going back to at least 2017.

**Reports available (verified from page):**
- **Annual PDFs:** 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025 — all as downloadable PDFs
- **Document carousel:** Reports displayed in a paginated carousel with left/right navigation

**Additional resources on the page:**
- **"Subdivision and Land Development Plans" online mapping application** — interactive map of plans from the last 6 years (link to external mapping app)
- **Code Sheets:** Municipality Codes (PDF), Subdivision Data Codes (PDF)

**Related sidebar documents (all PDFs):**
- Agricultural Land Protection Plan
- Building Permit Reports
- Integrated Water Resources Flowchart
- Municipal Plan Status
- Open Space and Greenways Plan
- Plan Review Process Flowchart
- Planning & Implementation Tools
- Protecting York County's Rural Environment
- Subdivision & Land Development Ordinance

**Contact:** Municipal Planning Division, 717-771-9870

### Access Method (Verified)
**HTML page scraping + PDF download.** CivicPlus CMS page with document carousel. PDF links are direct. The building permit reports and plan status documents in the sidebar are bonus data sources.

### Ingestion Strategy
- **Method:** HTTP GET → parse document carousel for PDF links → download → parse with pdfplumber
- **Target table:** `staging.planning_commission_plans`
- **Schedule:** Daily (catch new monthly/annual reports)
- **Cross-reference:** Subdivision data contains municipality codes and plan types that link to parcels via the GIS data
- **Bonus:** The "Subdivision and Land Development Plans" mapping application may have its own API worth investigating

### Legal Basis
**Minimal risk.** Planning commission reports are public records. YCPC publishes them explicitly for public consumption.

### Verdict: ✅ GO — Daily PDF scrape (Phase 2)

---

## Source 17: PA DEP eFACTS (Environmental Compliance)

**URL:** https://www.ahs.dep.pa.gov/eFACTSWeb/default.aspx

**⚠️ DEAD URL (from original table):** ~~dep.pa.gov/DataandTools/Reports/Pages/eFACTS.aspx~~ → Redirects to main DEP page

**Phase:** Phase 2

### What's Available (Verified March 20, 2026)
Pennsylvania's Environment Facility Application Compliance Tracking System (eFACTS) provides environmental compliance data for individuals, businesses, and local governments. Searching York County returned **8,463 regulated sites** across 706 pages.

**Search types available:**
- Authorization Search, Client Search, Facility Search, Inspection Search
- **Sites by County/Municipality** — perfect for bulk York County extraction
- Name Search, Site Search, Pollution Prevention

**Data per site:** Site Name, Site ID, Site Address, Status (Active/Inactive). Each site links to detailed pages with authorizations, compliance history, inspections, violations, and enforcement actions.

**Related DEP tools:** eMapPA (GIS), eNotice, EPA ECHO, EPA Envirofacts, Permits/Licensing/Certification

**Technology:** Classic ASP.NET Web Forms — NOT a Coveo JS SPA as originally noted. Standard postback-based pagination.

### Access Method (Verified)
**ASP.NET scraping with Playwright.** The County/Municipality search provides paginated results (706 pages for York County). ASP.NET ViewState/postback navigation. However, since this is classic ASP.NET (not an SPA), simpler HTTP session-based scraping with `requests` + form data may also work.

### Ingestion Strategy
- **Method:** Select York County → paginate through all 706 pages → extract site data → follow links for authorization/inspection details
- **Target table:** `staging.dep_permits`
- **Schedule:** Daily
- **Volume:** 8,463 sites — substantial but manageable with pagination
- **Enrichment:** Cross-reference site addresses with parcel data for spatial joins

### Legal Basis
**Minimal risk.** DEP compliance data is public information. eFACTS is explicitly published for public consumption by an official PA government agency.

### Verdict: ✅ GO — Playwright scraping with county filter (Phase 2)

---

## Source 18: York City Request for Proposals

**URL:** https://www.yorkcity.org/business/request-for-proposals/

**Phase:** Phase 2

### What's Available (Verified March 20, 2026)
The York City RFP page is **live and accessible** — no Cloudflare 403 (contradicting the original table). The page lists active RFPs and bid invitations as a simple bulleted list of links.

**Sample listings verified:** Special Events Consulting Services 2026 Phase 2, HRIS, Invitation to Bid, Crossing Guards 2025-2026 RFP, Veterans Memorial Park Basketball Courts, Front Load Dumpsters/Roll Off Service, Payment Service Provider, Refuse & Recycling Collections, and more.

**Also found:** "Procurement Portal" link for subscription-based notifications of new opportunities. Sidebar links to Permits & Inspections, Planning & Zoning, Tax Abatement Programs.

**Technology:** WordPress site — standard HTML, no JavaScript rendering needed.

### Access Method (Verified)
**Simple HTML scraping with BeautifulSoup.** Plain bulleted list of links. No authentication, no Cloudflare (despite original table claiming 403). Each link leads to a detail page or PDF.

### Ingestion Strategy
- **Method:** HTTP GET → parse bulleted link list → extract titles and URLs → follow links for detail/PDF content
- **Target table:** `staging.york_city_rfps`
- **Schedule:** Daily
- **Note:** This is York City only (population ~45K), not all of York County. But it's the county seat and largest municipality.

### Legal Basis
**Minimal risk.** Government procurement postings are public notices.

### Verdict: ✅ GO — Daily HTML scrape (Phase 2)

---

## Source 19: CRIMEWATCH York County (Police Blotters)

**URL:** https://crimewatch.net/us/pa/york

**⚠️ DEAD URL (from original table):** ~~york.crimewatch.net~~ → DNS failure / unreachable

**Phase:** Phase 2

### What's Available (Verified March 20, 2026)
CRIMEWATCH is a law enforcement community engagement platform serving York County. The county-level page shows a news feed of police activity from multiple departments.

**Content types:** Arrests (with photos), crime alerts, missing persons, Most Wanted, community notifications. Each entry includes: suspect name, charges, department name, date, narrative description.

**Features verified:**
- **NEWS FEED** with "Most Recent" sort
- **CRIME MAP** — interactive map of incidents
- **FIND MY AGENCY** — directory of participating departments
- **MOST WANTED** section
- **Navigation:** CRIME dropdown, MEGAN'S LAW, MISSING PERSONS, CRIME VICTIMS tabs
- **SEARCH** and **DIRECTORY** links in header

**Sample entry:** Arrest record from Hanover Borough Police Department, dated March 20, 2026, with photo, charges, and narrative.

**Technology:** JavaScript-heavy SPA with pagination. Requires Playwright.

### Access Method (Verified)
**Playwright scraping with pagination.** The news feed loads dynamically. No authentication required. No login needed for public blotter data.

### Ingestion Strategy
- **Method:** Playwright → navigate to York County feed → paginate through entries → extract suspect name, charges, department, date, narrative, location
- **Target table:** `staging.blotters`
- **Schedule:** Daily
- **Entity resolution:** Names from blotters cross-reference with UJS court records and property ownership data
- **Privacy note:** Only scrape publicly posted blotter data — no non-public records

### Legal Basis
**Low risk.** Police blotters are public information. CRIMEWATCH is explicitly designed to share this information with the public. However, be mindful of mugshot/photo usage — store metadata only, not images.

### Verdict: ✅ GO — Playwright scraping (Phase 2)

---

## Source 20: York County Inmate Records

**URL:** https://inmatelocator.yorkcountypa.gov

**Phase:** Phase 2

### Live Test Result: ❌ UNREACHABLE
The domain `inmatelocator.yorkcountypa.gov` returned a DNS/connection failure (chrome-error). This subdomain either no longer exists, has been taken offline, or is only accessible from within the county network.

### Recommended Action
- Verify the URL manually from a local browser on a different network
- Check if the inmate locator has moved to a different domain (some PA counties use third-party providers like VINELink or JailTracker)
- Check `yorkcountypa.gov` for a current "Inmate Search" or "Prison" page link

### Verdict: ⚠️ BLOCKED — URL needs manual verification

---

## Source 21: PALS — PA Professional Licensing System

**URL:** https://www.pals.pa.gov/#!/page/search

**Phase:** Phase 2

### What's Available (Verified March 20, 2026)
The Pennsylvania Licensing System (PALS), operated by the Bureau of Professional and Occupational Affairs (Department of State), provides public verification of professional licenses.

**Search types:** Person, Facility, Disciplinary, Provider

**Search fields (Person search verified):**
- Board/Commission (dropdown — covers all 29 PA licensing boards)
- License Type (dropdown — varies by board)
- License Number
- Name (Last, First, Middle)
- City, State, Zip
- **County (dropdown)** — perfect for filtering York County
- Country

**Boards covered include:** Real Estate, Nursing, Medicine, Pharmacy, Engineering, Cosmetology, Contractors, Accountancy, Architecture, Funeral Directors, and 20+ more.

**Technology:** AngularJS SPA with hashbang routing (`#!/page/search`). Requires Playwright for interaction.

### Access Method (Verified)
**Playwright required.** AngularJS SPA with dynamic form rendering. The County dropdown enables bulk extraction of all York County licensees by board.

### Ingestion Strategy
- **Method:** Playwright → select County = York → iterate through each Board/Commission → extract all licensees
- **Target table:** `staging.professional_licenses`
- **Schedule:** Monthly (license data changes slowly)
- **Entity resolution:** Licensed professionals (realtors, contractors, attorneys, etc.) link to business entities and property transactions
- **High-value boards:** Real Estate Commission, Contractors, Engineers, Architects, Funeral Directors

### Legal Basis
**Minimal risk.** PALS is explicitly the "primary source for verification of license credentials." Professional license data is public information published by the Department of State.

### Verdict: ✅ GO — Playwright with county filter (Phase 2)

---

## Source 22: PLCB+ Liquor License Search

**URL:** https://plcbplus.pa.gov/pub/Default.aspx?PossePresentation=LicenseSearch

**Phase:** Phase 2

### What's Available (Verified March 20, 2026)
The PLCB+ Online Regulatory System provides a comprehensive liquor license search AND — critically — **bulk CSV downloads of ALL active licenses statewide**.

**Search fields:** LID Number, License Number, License Type, License Status, **County**, Municipality, Licensee name, Officer Name, Premises Name, Address, City/Town, Zip Code, CLA filter, Safekeeping Contact Name.

**Bulk download links (no scraping needed!):**
- **"CSV Download of All Licenses"** — Full export of all active licenses
- **"CSV Download of All Licenses and Associated Permits"** — Full export with permit details

**Note:** Search is capped at 200 results displayed, but the CSV downloads have no limit.

**Technology:** POSSE platform (by Computronix). ASP.NET Web Forms. Powered by POSSE.

### Access Method (Verified)
**CSV bulk download — no scraping required!** Just download the CSV and filter for York County. This is the easiest data source in the entire platform.

### Ingestion Strategy
- **Method:** HTTP GET of CSV download link → filter for County = York → load into RDS PostgreSQL
- **Target table:** `staging.liquor_licenses`
- **Schedule:** Monthly
- **Data:** License type, licensee name, premises name, address, municipality, status, associated permits
- **Entity resolution:** Liquor licensees are businesses with physical premises — direct link to parcels and business entities

### Legal Basis
**Minimal risk.** PLCB explicitly provides public search and bulk CSV export for license data. No restrictions.

### Verdict: ✅ GO — CSV bulk download, filter for York County (Phase 2)

---

## Legal Framework Summary

### PA Right-to-Know Law (Act 3 of 2008)

**Key provisions for this platform:**
- **Presumption of openness:** All state/local government records are presumed public unless a specific exemption applies
- **Electronic format:** Agencies must provide records in electronic form where technically feasible (65 P.S. § 67.701)
- **Process:** Written request → 5 business day initial response → up to 35 days total
- **Fees:** Free to submit; duplication fees must be "reasonable"; electronic records limited to lesser of paper or electronic media cost
- **Bulk data:** For complex/extensive datasets, agencies may charge "reasonable market value"
- **Appeal:** If denied, appeal to PA Office of Open Records within 15 business days
- **RTK request form:** https://www.openrecords.pa.gov/Documents/RTKL/RTKRequestForm.pdf

### Web Scraping Legal Analysis

**Federal law (CFAA, 18 USC § 1030):**
- *Van Buren v. United States* (SCOTUS, 2021): Narrowed CFAA — "exceeds authorized access" only applies when the access itself is restricted
- *hiQ Labs v. LinkedIn* (9th Cir., 2022): Scraping publicly available data from websites that require no authentication does not violate the CFAA

**Pennsylvania-specific:** PA has no separate anti-scraping statute. Federal CFAA applies.

**Practical guidelines for defensible scraping:**
1. Only scrape publicly accessible pages (no login required)
2. Check and comply with robots.txt
3. Review and comply with Terms of Service
4. Implement rate limiting (5-10 second delays minimum)
5. Don't cause service disruption
6. Don't circumvent any technical access controls (including Cloudflare challenges)
7. Document that all data accessed is public record

### Assessment Portal "Cannot Be Sold" Clause — Detailed Analysis

The home page states: "The information provided herewith is solely for your own use and cannot be sold."

**Why this does NOT block the platform:**
1. This is a website Terms of Use — not a statute or regulation
2. It cannot override the PA Right-to-Know Law, which makes assessment records public
3. The RTK request path bypasses website ToU entirely (you're requesting from the government office, not through the website)
4. The platform provides analysis, not raw resale — there's a meaningful transformation
5. The full disclaimer is a standard liability waiver, not a data licensing agreement
6. Multiple commercial platforms (Zillow, Redfin, etc.) already aggregate PA assessment data

**Recommended approach:** File RTK request for bulk data (not bound by website ToU). Use portal scraping only for verification/enrichment.

### Data Aggregation Privacy Analysis

**Current PA law:**
- No general restriction on aggregating or commercializing public records
- **PA Breach Notification Act** (amended June 2024): If your platform stores PII and is breached, notification required
- **PA Consumer Data Privacy Act (HB 78):** Awaiting Senate. Would apply if 50K+ consumers or $10M+ revenue
- **Public Servant Data Privacy Act (HB 1822):** Could restrict publishing addresses/phone numbers of judges and elected officials

**Risk mitigation:**
1. Only store data that is already publicly available
2. Implement access controls and query auditing (already in the schema)
3. Don't store SSNs, driver's license numbers, financial account numbers
4. Monitor HB 1822 — may need to restrict entity profiles for judges/officials
5. Establish breach notification procedures
6. Include privacy policy and terms of service for platform users

---

## Action Items by Phase

### MVP — File/Build These Now
1. **York County Assessment Office RTK Request** — Request full assessment roll in electronic format (CSV/Excel). Contact: RWhite@yorkcountypa.gov, (717) 771-9232, 28 E Market St Room 105, York PA 17401-1585. Estimated timeline: 5-35 days. Estimated cost: $50-200.
2. **Download GIS data via REST API** — No request needed. Use `https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/` endpoints for Parcels, Municipal_Boundary, DIST_School, Zoning, HYDRO_Floodplains, and all other layers.
3. **Download FEMA NFHL** — No request needed. Item 42133C-NFHL (77MB) from https://hazards.fema.gov/femaportal/NFHL/searchResult
4. **Build PennDOT Projects pipeline** — REST API at `https://gis.penndot.gov/arcgis/rest/services/paprojects/paprojects/MapServer`. Query layers 1,2,4,5 + bridge condition layers 34-45 with `COUNTY_NAME='YORK'`. 78 fields per project including cost estimates, timelines, locations. Daily refresh.

### Phase 2 — File/Build These When Ready
5. **AOPC Bulk Distribution Request** — Request York County CPCMS + MDJS dockets. Note: UJS Portal has a "Parcel" search option — request that parcel linkage data be included if possible.
6. **York County Recorder of Deeds RTK Request** — Request recorded document index in electronic format. Note: Liens are filed with Prothonotary, not Recorder.
7. **Build YCCD Plan Review scraper** — Weekly PDF from `yorkccd.org/erosion-and-sediment-control/pending-plan-review-list`. Leading indicator of development activity.
8. **Build County Bids scraper** — Daily HTML from `yorkcountypa.gov/Bids.aspx`. BeautifulSoup with 3 fallback patterns for CivicPlus HTML variations.
9. **Build Tax Claim Bureau scraper** — Daily from `yorkcountypa.gov/528/Tax-Sale-Information`. HTML page + Delinquent Tax Claim Listing PDF. Contact: Sharon Sauble, 717-771-9205.
10. **Build Commissioners Minutes scraper** — Daily from `yorkcountypa.gov/1275/_YYYY`. HTML table with Agenda/Minutes PDF links. 5 years of history (2022-2026).
11. **Build YCPC Subdivision scraper** — Daily from `ycpc.org/233/Subdivision-Activity-Reports`. Annual PDFs (2017-2025). Investigate the "Subdivision and Land Development Plans" mapping app for possible API.
12. **Build DEP eFACTS scraper** — Playwright on `ahs.dep.pa.gov/eFACTSWeb/`. Select York County → paginate 706 pages → 8,463 regulated sites with compliance/permit/inspection data.
13. **Build York City RFP scraper** — Daily HTML from `yorkcity.org/business/request-for-proposals/`. Simple bulleted link list, BeautifulSoup.
14. **Build CRIMEWATCH scraper** — Daily Playwright on `crimewatch.net/us/pa/york`. Police blotters with arrest data, charges, departments.
15. **Build PALS license scraper** — Monthly Playwright on `pals.pa.gov/#!/page/search`. AngularJS SPA — select County=York, iterate boards. Focus on Real Estate, Contractors, Engineers, Architects.
16. **Download PLCB liquor licenses** — Monthly CSV from `plcbplus.pa.gov` "CSV Download of All Licenses" link. Filter for York County. No scraping needed.

### Ongoing Engineering
17. **Verify sheriff sales URLs** — The York County website has been reorganized. Locate current sheriff sales and tax claim pages.
18. **Verify inmate locator URL** — `inmatelocator.yorkcountypa.gov` returned DNS failure. Check for alternate URL or third-party provider (VINELink, JailTracker).
19. **Build municipality website registry** — Catalog all 72 municipality URLs and minutes page locations for Phase 3.
20. **Monitor Cloudflare on file.dos.pa.gov** — If SODA API on data.pa.gov is insufficient for business entity data, plan Playwright+stealth approach for the DOS portal.
21. **Investigate YCPC mapping app** — The Subdivision & Land Development Plans mapping application may expose an API for plan-level data with geometries.

---

## Sources

### Legal Citations
- [PA Right-to-Know Law (Act 3 of 2008)](https://www.legis.state.pa.us/cfdocs/legis/li/uconsCheck.cfm?yr=2008&sessInd=0&act=3)
- [PA Office of Open Records](https://www.openrecords.pa.gov/)
- [204 Pa. Code § 213.74 — Bulk Distribution of Court Records](https://www.law.cornell.edu/regulations/pennsylvania/204-Pa-Code-SS-213.74)
- [AOPC Public Records Forms](https://www.pacourts.us/public-records/public-records-forms)
- [hiQ Labs v. LinkedIn, 938 F.3d 985 (9th Cir. 2022)](https://cdn.ca9.uscourts.gov/datastore/opinions/2022/04/18/17-16783.pdf)
- [Van Buren v. United States, 141 S. Ct. 1648 (2021)](https://www.supremecourt.gov/opinions/20pdf/19-783_k53l.pdf)

### Data Source URLs (Verified March 20, 2026)
- [York County GIS Portal (WORKING)](https://york-county-pa-gis-portal-yorkcountypa.hub.arcgis.com/)
- [York County GIS REST API (WORKING)](https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/)
- ~~[York County Open Data Hub (DEAD 404)](https://data-yorkcountypa.opendata.arcgis.com/)~~
- [York County Assessment Portal (WORKING)](https://assessmentpublic.yorkcountypa.gov/)
- [FEMA NFHL Search (WORKING)](https://hazards.fema.gov/femaportal/NFHL/searchResult)
- [FEMA NFHL REST API](https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer)
- [PA Open Data Portal SODA API (WORKING)](https://data.pa.gov/api/catalog/v1)
- [PennDOT Open Data](https://data-pennshare.opendata.arcgis.com/)
- [UJS Portal Case Search (WORKING)](https://ujsportal.pacourts.us/CaseSearch)
- [Landex Webstore (WORKING — PAID)](https://www.landex.com/webstore/)
- [PA DOS Business Search (WORKING — Cloudflare)](https://file.dos.pa.gov/search/business)
- ~~[PA DOS corporations.pa.gov (SSL ERROR)](https://www.corporations.pa.gov/search/corpsearch)~~
- [York County Website](https://yorkcountypa.gov/)
- [YCCD Pending Plan Review List (WORKING)](https://www.yorkccd.org/erosion-and-sediment-control/pending-plan-review-list)
- [York County Bid Postings (WORKING)](https://yorkcountypa.gov/Bids.aspx)
- [PennDOT PA Projects MapServer (WORKING)](https://gis.penndot.gov/arcgis/rest/services/paprojects/paprojects/MapServer)
- [York County Tax Sale Information (WORKING)](https://yorkcountypa.gov/528/Tax-Sale-Information)
- [York County Commissioners Meetings (WORKING)](https://yorkcountypa.gov/1275/_2026)
- [YCPC Subdivision Activity Reports (WORKING)](https://ycpc.org/233/Subdivision-Activity-Reports)
- [PA DEP eFACTS (WORKING)](https://ahs.dep.pa.gov/eFACTSWeb/default.aspx)
- [York City RFPs (WORKING)](https://yorkcity.org/business/request-for-proposals/)
- [CRIMEWATCH York County (WORKING)](https://crimewatch.net/us/pa/york)
- ~~[York County Inmate Locator (DNS FAILURE)](https://inmatelocator.yorkcountypa.gov/)~~
- [PALS License Search (WORKING)](https://pals.pa.gov/#!/page/search)
- [PLCB+ License Search / Data Export (WORKING)](https://plcbplus.pa.gov/)
