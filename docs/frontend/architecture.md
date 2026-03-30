# Frontend Architecture

## Who Uses This

CountyIQ serves five distinct audiences. Each arrives with different questions, but all share the same pain: getting answers about York County property currently requires searching 3-5 disconnected county systems manually.

| Audience | What they need | How they arrive |
|----------|---------------|-----------------|
| **County & municipal staff** | Total assessed value, delinquency rates, ownership changes in their jurisdiction. Exportable reports for meetings. | Search their township name, bookmark municipality pages |
| **Title companies & RE attorneys** | Owner, deed reference, delinquent taxes, other properties owned by same entity. Fast lookups, not browsing. | Search by address or PIDN, need the property report card |
| **Developers & investors** | Vacant land with specific zoning/size/location, adjacent parcel ownership for assemblage, recent sale prices for market validation. | Filtered map views, vacancy finder |
| **Journalists & civic watchdogs** | Top property owners, suspicious transfers ($1 sales), delinquency patterns, institutional buying trends. | Top owners dashboard, change feed |
| **General taxpayers** | "What's my property assessed at vs my neighbors?" "Who owns that vacant lot?" "Am I in a flood zone?" | Search their own address |

## Stack

| Component | Technology | Purpose |
|---|---|---|
| UI framework | React 18+ (TypeScript) | Component-based UI, hooks for state management |
| Map rendering | MapLibre GL JS (via `react-map-gl`) | Free, open-source vector tile map rendering with WebGL |
| Data visualization | Deck.gl | GPU-accelerated rendering of 220K+ parcel polygons with interactive tooltips |
| Build tool | Vite | Fast builds, hot reload for development |
| API backend | FastAPI + Uvicorn (Docker) | Async REST API for data queries |
| Hosting | Cloudflare Pages | Static site hosting with CDN and HTTPS |

### Why MapLibre + Deck.gl

MapLibre GL JS renders the base map (streets, labels, terrain) as vector tiles in the browser using WebGL. It handles zoom, pan, rotation, and 3D tilt natively. `react-map-gl` wraps it in React components so it integrates cleanly with the rest of the UI.

Deck.gl sits on top of the map as a data visualization layer. The key advantage: it renders large datasets using the GPU instead of the CPU. Your 220,000 parcel polygons, color-coded by zoning or assessed value, with hover tooltips and click interactions — Deck.gl handles that at 60fps where raw MapLibre would start struggling past ~50K features. It's built by the same team that maintains `react-map-gl` (Vis.gl, originally from Uber), so the integration is seamless.

Both are free and open source with no usage limits. Unlike Mapbox, there's no per-map-load pricing.

---

## Product: What the User Sees

### Homepage (search-first dashboard)

The landing page is a search bar + at-a-glance intelligence — not a blank map. Every audience starts by looking for something specific.

```
+------------------------------------------------------------------+
|  CountyIQ - York County Civic Intelligence                        |
|                                                                   |
|  +------------------------------------------------------------+  |
|  |  Search any address, owner, parcel ID...                    |  |
|  +------------------------------------------------------------+  |
|                                                                   |
|  +---------------+  +---------------+  +----------------+        |
|  |  176,059      |  |  423          |  |  $14.2B        |        |
|  |  Parcels      |  |  Changed      |  |  Total         |        |
|  |  Tracked      |  |  This Week    |  |  Assessed      |        |
|  +---------------+  +---------------+  +----------------+        |
|                                                                   |
|  QUICK ACCESS                                                     |
|  +-------------+ +-------------+ +-------------+ +-------------+ |
|  | Explore Map | | Vacant Land | | Top Owners  | | Recent Sales| |
|  +-------------+ +-------------+ +-------------+ +-------------+ |
|  +-------------+ +-------------+ +-------------+                 |
|  | Flood Risk  | | Delinquent  | | Municipalities|                |
|  +-------------+ +-------------+ +-------------+                 |
|                                                                   |
|  RECENT CHANGES                                                   |
|  - 12 parcels transferred: YORK DEV LLC -> KEYSTONE REALTY       |
|  - 3 new delinquencies in West Manchester Twp                     |
|  - Largest sale: 125 MAIN ST, $420,000 (Mar 18)                  |
|                                                                   |
|  TOP OWNERS                                                       |
|  1. YORK COUNTY INDUSTRIAL DEV    | 847 parcels | $142M         |
|  2. DALLMEYER PROPERTIES LLC      | 234 parcels | $38M          |
|  3. FIRST NATIONAL COMMUNITY BANK | 189 parcels | $31M          |
|  [See all ->]                                                     |
+------------------------------------------------------------------+
```

**Stats bar** — live counts from the database. Updates weekly with pipeline runs.

**Quick access cards** — each opens a pre-filtered view. "Vacant Land" opens the map filtered to parcels without building footprints. "Top Owners" opens the ownership dashboard. "Flood Risk" opens the map with FEMA overlay. These are the zero-learning-curve entry points.

**Recent changes** — derived from SCD2 history. Ownership transfers, new delinquencies, large sales. Queries `/api/changes?limit=5`.

**Top owners** — the "who owns York County" hook. Queries `/api/owners/top?limit=3`.

### Map view

Full-screen interactive map — the core exploration tool. Reached via "Explore Map" or any filtered quick-access card.

```
+------------------------------------------------------------------+
|  [<- Home] [Search...                    ] [Layer v] [Filter v]   |
+----------------------------------------------+-------------------+
|                                              |                    |
|                                              |  PROPERTY REPORT   |
|              MAP VIEW                        |                    |
|                                              |  JOHN A SMITH      |
|         (MapLibre + Deck.gl)                 |  123 Main St       |
|                                              |  Conewago Twp      |
|   Layers:                                    |                    |
|   - Parcels (color-coded)                    |  Assessed: $185K   |
|   - Building footprints                      |  Last sale: $240K  |
|   - Municipal boundaries                     |  Ratio: 77%        |
|   - Flood zones                              |  1.24 acres | R    |
|   - Delinquent tax overlay                   |  Year built: 1955  |
|                                              |  Not in flood zone |
|   Click parcel -> report card                |                    |
|   in side panel                              |  Also owns 3 other |
|                                              |  parcels ($450K)   |
|                                              |                    |
|                                              |  [Full Profile ->] |
|                                              |  [Compare]         |
|                                              |  [Export PDF]       |
+----------------------------------------------+-------------------+
```

**Map layers:**
- **Parcels** — polygons at zoom 13+, colored by active filter (assessed value, zoning, owner, recent sale, delinquency). Click opens property report card in side panel.
- **Building footprints** — polygon outlines at zoom 15+, on by default. Makes the map look like a real place. Parcels without footprints are visually distinct (likely vacant).
- **Municipal boundaries** — toggleable polygon overlay with labels.
- **Flood zones** — toggleable FEMA flood hazard overlay (AE/A zones highlighted).
- **Delinquent tax overlay** — toggleable, highlights delinquent properties in red.
- **Roads** — reference layer.

**Filter bar** — pre-built filters that don't require GIS knowledge:
- Vacant land (no building footprint)
- Recently sold (last 90/180/365 days)
- Flood risk (in FEMA SFHA zone)
- Delinquent taxes
- By municipality, school district, class (R/C/I)
- By assessed value range, acreage range

### Property report card (side panel)

When you click a parcel or search an address, the side panel shows a human-readable summary — not a raw data dump. Template-rendered from structured data, no LLM needed.

**What it shows:**
- Owner name (linked to full profile if entity-resolved)
- Address, municipality, school district
- Assessed value with assessment-to-sale ratio ("Assessed at $185K, last sold for $240K — 77% ratio")
- Comparable percentile ("Assessed higher than 68% of residential parcels in Conewago Twp")
- Flood zone status (spatial join against FEMA data)
- Sale history (current sale date/price, previous sale date/price)
- Acres, class, year built, living area
- Building footprint: present/absent (vacancy indicator)
- Other properties owned by same entity (count + total value, from entity resolution)
- Deed reference (DEED_BK/DEED_PG)

**Actions:**
- **Full Profile** — opens owner entity page showing all properties they own
- **Compare** — add to comparison tray (select 2-3 parcels for side-by-side)
- **Export PDF** — downloadable property summary for meetings/reports
- **View on county site** — direct link to the source record on the county GIS viewer

### Owner profile page

Full-page view of a resolved owner entity. The question it answers: "What does this person or company own?"

- Owner name, entity type (individual/LLC/trust/government)
- Total parcels owned, total assessed value, total acreage
- Map showing all owned parcels highlighted
- Table of all properties with address, municipality, assessed value, class, year acquired
- Assessment data for each (when assessment pipeline is built)
- Sortable by any column

### Parcel comparison

Select 2-3 parcels → side-by-side comparison table. Useful for title companies comparing properties, taxpayers checking if their assessment is fair, developers evaluating adjacent lots.

| Field | 123 Main St | 125 Main St | 200 Oak Ave |
|-------|------------|------------|-------------|
| Assessed | $185,000 | $160,000 | $195,000 |
| Last sale | $240,000 | $210,000 | $225,000 |
| Ratio | 77% | 76% | 87% |
| Acres | 1.24 | 0.50 | 1.10 |
| Year built | 1955 | 1970 | 1985 |
| Flood zone | No | No | AE |

### Municipality profile pages

`/municipality/{name}` — a dashboard for each of the 72 municipalities. Municipal staff would bookmark their township's page.

- Total parcels, total assessed value, total acreage
- Top 10 owners in this municipality
- Delinquency rate (count and total value of delinquent properties)
- Recent ownership changes
- Vacant land count and acreage
- Class breakdown (residential / commercial / industrial)
- School district(s) serving this municipality

### Top owners dashboard

The "who owns York County" view. Leaderboard of property owners ranked by parcel count, assessed value, or acreage. Filterable by municipality.

- Click an owner → highlights all their parcels on the map
- Filter: municipality, class, minimum parcel count
- Columns: rank, owner name, entity type, parcel count, total assessed, total acres
- Export to CSV

### Change detection feed

`/changes` — "What changed this week." All derived from SCD2 history.

- **Ownership transfers** — records where `owner_full` changed (old value → new value)
- **New delinquencies** — records entering delinquent status
- **Assessment changes** — records where `aprtotal` changed
- **New parcels** — records with recent `valid_from` and no prior history
- **Suspicious transfers** — sales at $1 or $0 (gift/transfer/foreclosure signals)

Filterable by change type and municipality. Queries `/api/changes`.

### Ops health page

`/ops/health` — internal monitoring page. Shows pipeline status (green/yellow/red), last run times, record counts, infrastructure metrics. Queries `/api/ops/health`. See `docs/operations/health-dashboard.md`.

---

### Export strategy

All exports are **client-side** — no server-side export endpoints needed.

- **CSV export** (top owners, municipality profiles, search results): Frontend converts JSON API response to CSV using a library like `papaparse`. Download as `.csv` file.
- **PDF export** (property report card): Frontend uses `html2pdf.js` or `jspdf` to render the report card panel to PDF. No server-side PDF generation needed.
- **Municipality report export**: CSV of municipality profile data for township meeting handouts.

### Dependencies and graceful degradation

Some features depend on pipelines that may not yet be operational:

| Feature | Depends on | If not available |
|---------|-----------|------------------|
| Owner profile, "Also owns X parcels" | Entity resolution pipeline (`public.owners`) | Hide the section; show owner name from `staging.parcels.owner_full` only |
| Flood zone status in report card | `staging.flood_zones` loaded | Show "Flood data unavailable" |
| Vacancy indicator | `staging.structures` loaded | Hide vacancy indicator |
| Municipality filter | `staging.municipalities` spatial join | Municipality field is NULL; hide municipality-based features |
| "Recently sold" filter | `saledt` is a `String(11)`, not a date | Parse with `CAST(saledt AS DATE)` at query time; consider adding a `sale_date DATE` column in a future migration for index-friendly filtering |
| Address-based search accuracy | `staging.address_points` loaded | Fall back to fuzzy matching on `staging.parcels.propadr` only |

The frontend should check for null/empty responses and hide sections rather than showing "0" or broken UI.

---

## What it does NOT include (MVP)

- **No user accounts or login** — fully public, read-only
- **No editing or data entry** — read-only intelligence platform
- **No real-time updates** — data refreshes weekly; frontend serves cached responses
- **No LLM/AI features** — all summaries are template-rendered from structured data. Natural language search and AI-generated narratives are Phase 2 (see `docs/implementation/expansion-roadmap.md`).

---

## API Endpoints (FastAPI on Docker)

| Endpoint | Method | Purpose | Example |
|---|---|---|---|
| `/api/parcels/bbox` | GET | Parcels within a map bounding box | `?west=-76.8&south=39.8&east=-76.6&north=40.0&layer=delinquent` |
| `/api/parcels/{pidn}` | GET | Property report card (full details + computed fields) | `/api/parcels/4300006006500` |
| `/api/parcels/{pidn}/comparables` | GET | Similar properties nearby with percentile ranking | `/api/parcels/4300006006500/comparables?radius=5` |
| `/api/parcels/{pidn}/adjacent` | GET | Neighboring parcel owners (for assemblage) | `/api/parcels/4300006006500/adjacent` |
| `/api/owners/top` | GET | Ownership concentration leaderboard | `?by=parcel_count&municipality=Conewago&limit=50` |
| `/api/owners/{owner_id}` | GET | Owner profile with all properties | `/api/owners/12345` |
| `/api/search` | GET | Fuzzy search across owners, addresses, parcels | `?q=smith+main+st&municipality=Conewago` |
| `/api/changes` | GET | Recent data changes across all sources | `?since=7d&type=ownership_transfer,new_delinquency` |
| `/api/municipalities` | GET | List all municipalities with summary stats | — |
| `/api/municipalities/{name}` | GET | Municipality profile data | `/api/municipalities/conewago-twp` |
| `/api/stats` | GET | Homepage stats (total parcels, changes this week, total assessed) | — |
| `/api/ops/health` | GET | System health dashboard data | See `docs/operations/health-dashboard.md` |

### Computed fields (calculated at query time, not stored)

These fields are derived from existing data and returned by the API, not stored in staging tables:

- **Assessment-to-sale ratio:** `aprtotal / price` (when both non-null)
- **Comparable percentile:** SQL window function over same-class parcels in same municipality
- **Flood zone status:** Spatial join `staging.parcels` against `staging.flood_zones` via `ST_Intersects`
- **Vacancy indicator:** LEFT JOIN `staging.structures` — null means no building footprint
- **Adjacent owners:** Spatial query using `ST_Touches` or `ST_DWithin` on parcel geometries
- **Owner portfolio summary:** Aggregate from entity resolution (parcel count, total assessed, for the same `owner_id`)

---

## Vector Tiles

Tiles are **not served by the API**. They are pre-generated by the Dagster tile pipeline, uploaded to R2 (`countyiq-tiles`), and served via Cloudflare CDN at `/tiles/{layer}/{z}/{x}/{y}.pbf` (7-day cache via `Cache-Control` header). The API has no tile routes. MapLibre loads tiles directly from the Cloudflare URL.

**Tile layers generated at MVP:**

| Layer | Source table | Geometry | Zoom range | Notes |
|-------|-------------|----------|------------|-------|
| `parcels` | `staging.parcels` | MultiPolygon | 13-18 | Color-coded by value/zoning/owner |
| `footprints` | `staging.structures` | Polygon | 15-18 | Building outlines, on by default |
| `flood_zones` | `staging.flood_zones` | MultiPolygon | 10-18 | FEMA hazard areas, toggleable |
| `municipalities` | `staging.municipalities` | MultiPolygon | 8-14 | Boundary outlines + labels |

**Not a map layer:** `staging.address_points` is backend-only — used by `/api/search` for canonical address matching and by entity resolution as a geocoding fallback when PROPADR is messy. No vector tiles generated.

**See `docs/api/api.md` for FastAPI app code, Docker configuration, and CORS setup.**

---

## Infrastructure

### Cloudflare routing

Cloudflare sits in front of everything and routes requests:

| Path | Served by | Cache |
|---|---|---|
| `/*` (default) | Cloudflare Pages (React SPA) | Cloudflare edge cache |
| `/tiles/*` | Cloudflare R2 | 7-day cache (Cache-Control header) |
| `/api/*` | Hetzner VPS via Cloudflare proxy | No cache (dynamic) |

This means a single domain serves both the React app and the API. No CORS issues between frontend and backend since they share the same domain.

### SPA routing

Cloudflare Pages handles SPA routing natively (no config needed). React Router uses client-side URLs like `/ops/health` or `/search?q=smith` that don't correspond to real files — Cloudflare Pages automatically serves `index.html` for these paths, letting React Router handle them client-side.

### Storage

| Storage | Purpose | Access |
|---|---|---|
| Cloudflare Pages | React build output | Via Cloudflare CDN |
| R2: `countyiq-tiles` | Pre-generated vector tiles | Via Cloudflare CDN |
| R2: `countyiq-raw` | Raw scrape archives | Private (pipeline only) |

### Frontend deployment workflow

```bash
# Local development
cd frontend
npm install
npm run dev          # Vite dev server on localhost:5173
                     # API calls proxied to local FastAPI
```

**Production deployment:** Push to `main` → Cloudflare Pages auto-builds and deploys. No manual steps.

### Custom domain (future)

Not needed for MVP. The Cloudflare Pages URL (`countyiq.pages.dev`) works fine. When you want a custom domain:

Add domain in Cloudflare Dashboard → Pages → Custom domains. Cloudflare handles DNS + TLS automatically.
