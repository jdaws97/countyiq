# Phase 4.1: API Foundation + Basic Map — Design Spec

**Scope:** Sub-project 1 of Phase 4. Builds the API route layer and React frontend shell with map visualization using data available now (everything except GIS Parcels, which is blocked by a server outage).

**Date:** 2026-03-29

---

## Purpose

Stand up the full local development stack — FastAPI on localhost:8000, React+MapLibre on localhost:5173, both querying Docker Postgres on localhost:5433. This is the moment CountyIQ becomes a visible product instead of a collection of pipelines.

**Sub-project 2** (after GIS Parcels service is restored) will add: parcel rendering on the map, property report card side panel, comparables, adjacent parcels, owner profiles, and change feed.

---

## What We Have (Data Available Now)

| Source | Records | Geometry |
|---|---|---|
| Building Structures | 213,041 | Polygons — **too large for GeoJSON, needs vector tiles (sub-project 2)** |
| Address Points | 189,920 | Points — too large for GeoJSON at full zoom |
| PA Open Data (Businesses) | 89,237 | No geometry |
| Tax Claims | 36,831 | No geometry (join to address_points for geocoding) |
| Roads | 33,748 | Lines — too large for full GeoJSON, but can serve by bbox |
| FEMA Flood Zones | 4,000 | Polygons — fine for GeoJSON |
| PennDOT Roads | 2,271 | Lines — fine for GeoJSON |
| Zoning | 1,694 | Polygons — fine for GeoJSON |
| PLCB Licenses | 1,346 | No geometry |
| PennDOT Projects | 81 | Points/Lines — fine for GeoJSON |
| Municipalities | 72 | Polygons — fine for GeoJSON |
| **Parcels** | **0** | **Blocked — GIS server down** |

**GeoJSON strategy:** Layers under ~5K features are served as GeoJSON via API endpoints. Layers over ~50K features (structures, address points, parcels) require vector tiles — deferred to sub-project 2. This is a temporary approach; all layers will eventually use vector tiles for consistent performance.

---

## API Routes

All routes use the existing `api/lib/database.py` pattern (`get_cursor()` context manager with `RealDictCursor`). New routes are added as separate files in `api/routes/` and mounted in `api/main.py`.

### New Routes (this sub-project)

| Method | Path | Purpose | Data Source |
|---|---|---|---|
| GET | `/api/stats` | Homepage stats cards | Aggregation across staging tables |
| GET | `/api/municipalities` | List all 72 with summary stats | `staging.municipalities` |
| GET | `/api/municipalities/{code}` | Single municipality profile | `staging.municipalities` + `staging.tax_claims` |
| GET | `/api/search?q=...` | Fuzzy search on addresses | `staging.address_points` via pg_trgm |
| GET | `/api/layers/municipalities` | GeoJSON for map | `staging.municipalities` (with geometry) |
| GET | `/api/layers/flood_zones` | GeoJSON for map | `staging.flood_zones` (with geometry) |
| GET | `/api/layers/zoning` | GeoJSON for map | `staging.zoning` (with geometry) |
| GET | `/api/layers/penndot_projects` | GeoJSON for map | `staging.penndot_projects` (with geometry) |
| GET | `/api/ops/health` | System health data | `meta.pipeline_status` |

### Existing Routes (keep as-is)

| Path | Purpose |
|---|---|
| GET `/api/health` | Lambda smoke test |
| GET `/api/scout/*` | County Scout endpoints |

### Route Details

**`GET /api/stats`**
```sql
SELECT
  (SELECT COUNT(*) FROM staging.municipalities WHERE valid_to IS NULL) as municipality_count,
  (SELECT COUNT(DISTINCT pidn) FROM staging.tax_claims WHERE valid_to IS NULL) as delinquent_parcels,
  (SELECT SUM(total) FROM staging.tax_claims WHERE valid_to IS NULL AND total > 0) as total_delinquent,
  (SELECT COUNT(*) FROM staging.flood_zones WHERE valid_to IS NULL) as flood_zone_count,
  (SELECT COUNT(*) FROM staging.plcb_licenses WHERE valid_to IS NULL) as liquor_license_count;
```
Returns counts that populate the homepage stats cards. When parcels load, add `parcel_count` and `total_assessed`.

**`GET /api/layers/{layer_name}`**
Returns GeoJSON FeatureCollection. Each row becomes a Feature with `geometry` from PostGIS `ST_AsGeoJSON()` and `properties` from the non-geometry columns. Supported layers: `municipalities`, `flood_zones`, `zoning`, `penndot_projects`.

```sql
SELECT jsonb_build_object(
  'type', 'FeatureCollection',
  'features', COALESCE(jsonb_agg(
    jsonb_build_object(
      'type', 'Feature',
      'geometry', ST_AsGeoJSON(geom)::jsonb,
      'properties', to_jsonb(t) - 'geom' - 'valid_from' - 'valid_to'
    )
  ), '[]'::jsonb)
) FROM staging.{layer} t WHERE valid_to IS NULL;
```

**`GET /api/search?q=...`**
Fuzzy search using pg_trgm on `staging.address_points.full_address` (or equivalent column). Returns top 20 matches with similarity score. Falls back gracefully if pg_trgm extension isn't installed.

**`GET /api/municipalities`**
Lists all 72 municipalities with tax delinquency stats:
```sql
SELECT m.name, m.muni_type,
  COUNT(DISTINCT tc.pidn) as delinquent_parcels,
  COALESCE(SUM(tc.total), 0) as total_delinquent
FROM staging.municipalities m
LEFT JOIN staging.tax_claims tc ON tc.tax_district_name ILIKE m.name || '%' AND tc.valid_to IS NULL
WHERE m.valid_to IS NULL
GROUP BY m.name, m.muni_type
ORDER BY m.name;
```

**`GET /api/ops/health`**
Queries `meta.pipeline_status` for source statuses. Returns green/yellow/red per source. If `meta.pipeline_status` is empty (no pipeline runs yet), returns status based on record counts in staging tables.

---

## Frontend

### Stack

| Package | Purpose |
|---|---|
| React 18 (TypeScript) | UI framework |
| Vite | Build tool + dev server |
| react-router-dom | Client-side routing |
| maplibre-gl | Vector tile map rendering |
| react-map-gl | React wrapper for MapLibre |
| deck.gl + @deck.gl/mapbox | GPU-accelerated data layers |

### Routes

| Route | Component | Description |
|---|---|---|
| `/` | `HomePage` | Search bar, stats cards, quick-access tiles, intel panels |
| `/map` | `MapView` | Full-screen MapLibre + Deck.gl with layer toggle |
| `/map?layer=flood` | `MapView` | Map with flood zones pre-activated |
| `/map?layer=delinquent` | `MapView` | Map with delinquent tax overlay pre-activated |
| `/municipalities` | `MunicipalityList` | All 72 municipalities with stats |
| `/ops/health` | `OpsHealth` | System health dashboard |

### Design System

**Aesthetic:** Command-center intelligence platform. Dark navy background (#0a0e1a), subtle grid overlay, amber/gold accent (#d4a843) for alerts and emphasis, blue (#4a7fff) for primary actions, red (#e05252) for delinquency/alerts.

**Typography:**
- Data/labels: JetBrains Mono (monospace)
- Body text: DM Sans (clean sans-serif)
- Search prompt: Instrument Serif italic (editorial contrast)

**Key components:**
- `Nav` — sticky top bar with CIQ logo, title, status indicator
- `SearchBar` — prominent search with keyboard hint
- `StatCard` — monospace value + label with colored top accent bar
- `QuickAccessTile` — icon + name + description, left accent bar, disabled state
- `IntelPanel` — header with badge + data rows
- `LayerToggle` — map sidebar with checkbox per layer

**Homepage layout (approved mockup):** Search-first dashboard with stats grid (3 cards), quick-access tiles (4x2 grid, 4 active + 4 disabled), and intelligence briefing (tax delinquency breakdown + data source status). See `homepage-v2.html` in `.superpowers/brainstorm/` for the approved HTML mockup.

### Map View

**Base map:** MapLibre GL JS with a dark style (e.g., `https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json` — free, no API key).

**Initial viewport:** York County center (~39.92, -76.73), zoom 10.

**Layers (toggleable):**
| Layer | Type | Source | Default |
|---|---|---|---|
| Municipal Boundaries | GeoJSONLayer (polygon fill + outline) | `/api/layers/municipalities` | ON |
| FEMA Flood Zones | GeoJSONLayer (blue semi-transparent fill) | `/api/layers/flood_zones` | OFF |
| Zoning | GeoJSONLayer (color-coded by zone type) | `/api/layers/zoning` | OFF |
| PennDOT Projects | GeoJSONLayer (orange points/lines) | `/api/layers/penndot_projects` | OFF |

**Deferred to sub-project 2:**
- Parcels layer (vector tiles — 176K polygons)
- Structures layer (vector tiles — 213K polygons)
- Property report card side panel (click interaction)
- Delinquent tax point overlay (needs parcel geometry for positioning)

### Vite Dev Proxy

Vite proxies `/api/*` to the FastAPI server to avoid CORS issues during local dev:

```typescript
// vite.config.ts
export default defineConfig({
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
});
```

---

## File Map

### API (modify/create)

| File | Action | Purpose |
|---|---|---|
| `api/main.py` | Modify | Mount new routers (stats, municipalities, search, layers, ops) |
| `api/routes/stats.py` | Create | Homepage stats endpoint |
| `api/routes/municipalities.py` | Create | Municipality list + profile |
| `api/routes/search.py` | Create | Fuzzy address search |
| `api/routes/layers.py` | Create | GeoJSON layer endpoints for map |
| `api/routes/ops.py` | Create | Health dashboard endpoint |
| `api/lib/database.py` | Keep | Existing connection helper (change port default to 5433 for local dev) |

### Frontend (create)

| File | Action | Purpose |
|---|---|---|
| `frontend/package.json` | Rewrite | Dependencies and scripts |
| `frontend/vite.config.ts` | Create | Vite config with API proxy |
| `frontend/tsconfig.json` | Create | TypeScript config |
| `frontend/index.html` | Create | HTML entry point |
| `frontend/src/main.tsx` | Create | React entry point |
| `frontend/src/App.tsx` | Create | Router setup |
| `frontend/src/pages/HomePage.tsx` | Create | Search + stats + tiles + intel panels |
| `frontend/src/pages/MapView.tsx` | Create | MapLibre + Deck.gl + layer toggle |
| `frontend/src/pages/MunicipalityList.tsx` | Create | Municipality listing |
| `frontend/src/pages/OpsHealth.tsx` | Create | System health dashboard |
| `frontend/src/components/Nav.tsx` | Create | Top navigation bar |
| `frontend/src/components/SearchBar.tsx` | Create | Search input with hints |
| `frontend/src/components/StatCard.tsx` | Create | Stats card component |
| `frontend/src/components/LayerToggle.tsx` | Create | Map layer checkbox panel |
| `frontend/src/styles/theme.css` | Create | CSS variables, grid background, global styles |

---

## Testing

### API

- Test each route with `curl` against localhost:8000 + Docker Postgres
- Verify GeoJSON responses are valid (parseable by MapLibre)
- Verify stats return non-zero values from backfilled data

### Frontend

- `npm run dev` on localhost:5173
- Verify homepage renders with live stats from API
- Verify map loads with base tiles
- Verify each layer toggle fetches and renders GeoJSON
- Use Playwright MCP to take screenshots of each page

---

## Local Development Workflow

```bash
# Terminal 1: Docker Postgres (already running)
cd pipelines && docker compose up -d postgres-test

# Terminal 2: API server
cd api && DATABASE_PORT=5433 uvicorn main:app --reload --port 8000

# Terminal 3: Frontend dev server
cd frontend && npm run dev
```

Browser: `http://localhost:5173` — React app, proxied API calls to localhost:8000.

---

## Notes for Sub-Project 2

- **Vector tiles needed for:** parcels (176K), structures (213K), address points (190K). GeoJSON is too slow for these sizes — browser freezes rendering 200K+ polygons as raw GeoJSON. Vector tiles use MapLibre's native tile renderer which handles millions of features via spatial indexing and zoom-level simplification.
- **Parcel-dependent features:** property report card, comparables, adjacent parcels, owner profiles, change feed, bbox endpoint, delinquent overlay
- **Entity resolution** should be built before owner profiles
- The homepage design has 4 grayed-out tiles that activate when parcels load
