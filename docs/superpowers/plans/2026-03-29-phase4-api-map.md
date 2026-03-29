# Phase 4.1: API Foundation + Basic Map — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working local stack — FastAPI API routes on localhost:8000 and a React + MapLibre frontend on localhost:5173 — both querying Docker Postgres with real backfilled data.

**Architecture:** API routes in `api/routes/` serve JSON and GeoJSON from staging tables. React frontend uses MapLibre GL JS for the map, Deck.gl for data layers, and fetches from `/api/*` via Vite proxy. Dark command-center aesthetic with JetBrains Mono, DM Sans, and Instrument Serif typography.

**Tech Stack:** FastAPI, psycopg2, React 18 (TypeScript), Vite, MapLibre GL JS, react-map-gl, Deck.gl, react-router-dom

**Spec:** `docs/superpowers/specs/2026-03-29-phase4-api-map-design.md`
**Homepage Mockup:** `.superpowers/brainstorm/26435-1774815587/content/homepage-v2.html`

**Prerequisites:**
- Docker Postgres running: `cd pipelines && docker compose up -d postgres-test`
- Data backfilled (572K+ records across 11 sources)
- Node.js installed (for frontend)

---

## File Map

### API (all paths relative to repo root)

| File | Action | Purpose |
|---|---|---|
| `api/routes/stats.py` | Create | `/api/stats` — homepage stats |
| `api/routes/layers.py` | Create | `/api/layers/{name}` — GeoJSON for map |
| `api/routes/municipalities.py` | Create | `/api/municipalities` — list + profile |
| `api/routes/search.py` | Create | `/api/search?q=...` — fuzzy address search |
| `api/routes/ops.py` | Create | `/api/ops/health` — system health |
| `api/main.py` | Modify | Mount new routers |
| `api/requirements.txt` | Keep | Already has fastapi, mangum, psycopg2-binary |

### Frontend (all paths relative to `frontend/`)

| File | Action | Purpose |
|---|---|---|
| `package.json` | Rewrite | Dependencies + scripts |
| `tsconfig.json` | Create | TypeScript config |
| `vite.config.ts` | Create | Vite + API proxy |
| `index.html` | Create | HTML entry point |
| `src/main.tsx` | Create | React entry point |
| `src/App.tsx` | Create | Router setup |
| `src/styles/theme.css` | Create | CSS variables + global styles |
| `src/components/Nav.tsx` | Create | Top navigation bar |
| `src/components/SearchBar.tsx` | Create | Search input component |
| `src/components/StatCard.tsx` | Create | Stats card component |
| `src/components/LayerToggle.tsx` | Create | Map layer toggle panel |
| `src/pages/HomePage.tsx` | Create | Dashboard with stats, tiles, intel |
| `src/pages/MapView.tsx` | Create | Full-screen map with layers |
| `src/pages/MunicipalityList.tsx` | Create | Municipality listing |
| `src/pages/OpsHealth.tsx` | Create | System health page |

---

### Task 1: API Route — `/api/stats`

**Files:**
- Create: `api/routes/stats.py`

- [ ] **Step 1: Create the stats route**

Create `api/routes/stats.py`:

```python
"""Homepage stats endpoint."""

from fastapi import APIRouter

from api.lib.database import get_cursor

router = APIRouter(tags=["stats"])


@router.get("")
def get_stats() -> dict:
    """Aggregate stats for homepage cards."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT
                (SELECT COUNT(*) FROM staging.municipalities WHERE valid_to IS NULL) AS municipality_count,
                (SELECT COUNT(DISTINCT pidn) FROM staging.tax_claims WHERE valid_to IS NULL) AS delinquent_parcels,
                (SELECT COALESCE(SUM(total), 0) FROM staging.tax_claims WHERE valid_to IS NULL AND total > 0) AS total_delinquent,
                (SELECT COUNT(*) FROM staging.flood_zones WHERE valid_to IS NULL) AS flood_zone_count,
                (SELECT COUNT(*) FROM staging.plcb_licenses WHERE valid_to IS NULL) AS liquor_license_count,
                (SELECT COUNT(*) FROM staging.address_points WHERE valid_to IS NULL) AS address_point_count,
                (SELECT COUNT(*) FROM staging.structures WHERE valid_to IS NULL) AS structure_count,
                (SELECT COUNT(*) FROM staging.parcels WHERE valid_to IS NULL) AS parcel_count
        """)
        row = cur.fetchone()

    total_records = sum(v for v in row.values() if isinstance(v, int))

    return {
        "total_records": total_records,
        "parcel_count": row["parcel_count"],
        "municipality_count": row["municipality_count"],
        "delinquent_parcels": row["delinquent_parcels"],
        "total_delinquent": float(row["total_delinquent"]),
        "flood_zone_count": row["flood_zone_count"],
        "liquor_license_count": row["liquor_license_count"],
        "address_point_count": row["address_point_count"],
        "structure_count": row["structure_count"],
    }
```

- [ ] **Step 2: Test it**

```bash
cd api && DATABASE_PORT=5433 uvicorn main:app --reload --port 8000 &
sleep 2
curl -s http://localhost:8000/api/stats | python3 -m json.tool
kill %1
```

Expected: JSON with non-zero counts. `delinquent_parcels` should be 9025, `municipality_count` should be 72.

Note: This will fail until main.py mounts the router. We'll mount all routers together in Task 5.

- [ ] **Step 3: Commit**

```bash
git add api/routes/stats.py
git commit -m "feat(api): add /api/stats endpoint for homepage cards"
```

---

### Task 2: API Route — `/api/layers/{name}` (GeoJSON)

**Files:**
- Create: `api/routes/layers.py`

- [ ] **Step 1: Create the layers route**

Create `api/routes/layers.py`:

```python
"""GeoJSON layer endpoints for map rendering."""

from fastapi import APIRouter, HTTPException

from api.lib.database import get_cursor

router = APIRouter(tags=["layers"])

# Allowed layers and their staging table names
LAYER_CONFIG = {
    "municipalities": {
        "table": "staging.municipalities",
        "properties": ["name", "muni_type", "county"],
    },
    "flood_zones": {
        "table": "staging.flood_zones",
        "properties": ["fld_zone", "zone_subty", "sfha_tf", "fld_ar_id"],
    },
    "zoning": {
        "table": "staging.zoning",
        "properties": ["muni_name", "zcode", "zname", "ztype", "gen_zcode", "gen_zname"],
    },
    "penndot_projects": {
        "table": "staging.penndot_projects",
        "properties": ["project_id", "project_name", "description", "status", "municipality"],
    },
}


@router.get("/{layer_name}")
def get_layer(layer_name: str) -> dict:
    """Return a GeoJSON FeatureCollection for the requested layer."""
    config = LAYER_CONFIG.get(layer_name)
    if not config:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown layer: {layer_name}. Available: {list(LAYER_CONFIG.keys())}",
        )

    table = config["table"]
    props = config["properties"]
    prop_select = ", ".join(f"t.{p}" for p in props)

    with get_cursor() as cur:
        cur.execute(f"""
            SELECT
                ST_AsGeoJSON(t.geom)::json AS geometry,
                {prop_select}
            FROM {table} t
            WHERE t.valid_to IS NULL
              AND t.geom IS NOT NULL
        """)
        rows = cur.fetchall()

    features = []
    for row in rows:
        geom = row.pop("geometry")
        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": dict(row),
        })

    return {
        "type": "FeatureCollection",
        "features": features,
    }
```

- [ ] **Step 2: Commit**

```bash
git add api/routes/layers.py
git commit -m "feat(api): add /api/layers/{name} GeoJSON endpoint for map"
```

---

### Task 3: API Route — `/api/municipalities`

**Files:**
- Create: `api/routes/municipalities.py`

- [ ] **Step 1: Create the municipalities route**

Create `api/routes/municipalities.py`:

```python
"""Municipality listing and profile endpoints."""

from fastapi import APIRouter, HTTPException

from api.lib.database import get_cursor

router = APIRouter(tags=["municipalities"])


@router.get("")
def list_municipalities() -> list[dict]:
    """List all municipalities with delinquency stats."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT
                m.name,
                m.muni_type,
                COUNT(DISTINCT tc.pidn) AS delinquent_parcels,
                COALESCE(SUM(CASE WHEN tc.total > 0 THEN tc.total ELSE 0 END), 0) AS total_delinquent
            FROM staging.municipalities m
            LEFT JOIN staging.tax_claims tc
                ON UPPER(tc.tax_district_name) LIKE UPPER(m.name) || '%'
                AND tc.valid_to IS NULL
            WHERE m.valid_to IS NULL
            GROUP BY m.name, m.muni_type
            ORDER BY m.name
        """)
        return cur.fetchall()


@router.get("/{name}")
def get_municipality(name: str) -> dict:
    """Get a single municipality profile."""
    with get_cursor() as cur:
        # Find the municipality (case-insensitive partial match)
        cur.execute("""
            SELECT name, muni_type, county
            FROM staging.municipalities
            WHERE valid_to IS NULL AND UPPER(name) = UPPER(%s)
        """, (name,))
        muni = cur.fetchone()
        if not muni:
            raise HTTPException(status_code=404, detail=f"Municipality not found: {name}")

        # Delinquency stats
        cur.execute("""
            SELECT
                COUNT(DISTINCT pidn) AS delinquent_parcels,
                COALESCE(SUM(CASE WHEN total > 0 THEN total ELSE 0 END), 0) AS total_delinquent,
                MIN(tax_year) AS oldest_delinquent_year,
                COUNT(DISTINCT tax_year) AS delinquent_years
            FROM staging.tax_claims
            WHERE valid_to IS NULL
              AND UPPER(tax_district_name) LIKE UPPER(%s) || '%%'
        """, (muni["name"],))
        delinquency = cur.fetchone()

    return {
        **dict(muni),
        "delinquency": dict(delinquency) if delinquency else {},
    }
```

- [ ] **Step 2: Commit**

```bash
git add api/routes/municipalities.py
git commit -m "feat(api): add /api/municipalities listing and profile"
```

---

### Task 4: API Route — `/api/search`

**Files:**
- Create: `api/routes/search.py`

- [ ] **Step 1: Create the search route**

Create `api/routes/search.py`:

```python
"""Fuzzy search across addresses using pg_trgm."""

from fastapi import APIRouter, Query

from api.lib.database import get_cursor

router = APIRouter(tags=["search"])


@router.get("")
def search(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(default=20, le=100),
) -> list[dict]:
    """Fuzzy search on address points using pg_trgm similarity."""
    # Build a full address string to search against
    search_term = q.strip()

    with get_cursor() as cur:
        cur.execute("""
            SELECT
                add_number,
                street_name,
                st_pos_typ,
                inc_muni,
                CONCAT_WS(' ', add_number, street_name, st_pos_typ) AS full_address,
                similarity(
                    CONCAT_WS(' ', add_number, street_name, st_pos_typ),
                    %(q)s
                ) AS score
            FROM staging.address_points
            WHERE valid_to IS NULL
              AND CONCAT_WS(' ', add_number, street_name, st_pos_typ) %% %(q)s
            ORDER BY score DESC
            LIMIT %(limit)s
        """, {"q": search_term, "limit": limit})
        return cur.fetchall()
```

- [ ] **Step 2: Commit**

```bash
git add api/routes/search.py
git commit -m "feat(api): add /api/search fuzzy address search with pg_trgm"
```

---

### Task 5: API Route — `/api/ops/health` + Mount All Routers

**Files:**
- Create: `api/routes/ops.py`
- Modify: `api/main.py`

- [ ] **Step 1: Create the ops route**

Create `api/routes/ops.py`:

```python
"""Operational health endpoint."""

from fastapi import APIRouter

from api.lib.database import get_cursor

router = APIRouter(tags=["ops"])


@router.get("/health")
def health() -> dict:
    """System health — source record counts and database connectivity."""
    sources = {}
    with get_cursor() as cur:
        tables = {
            "parcels": "staging.parcels",
            "municipalities": "staging.municipalities",
            "address_points": "staging.address_points",
            "structures": "staging.structures",
            "roads": "staging.roads",
            "zoning": "staging.zoning",
            "flood_zones": "staging.flood_zones",
            "plcb_licenses": "staging.plcb_licenses",
            "pa_open_data": "staging.pa_open_data",
            "penndot_roads": "staging.penndot_roads",
            "penndot_projects": "staging.penndot_projects",
            "tax_claims": "staging.tax_claims",
        }
        for name, table in tables.items():
            try:
                cur.execute(f"SELECT COUNT(*) AS cnt FROM {table} WHERE valid_to IS NULL")
                row = cur.fetchone()
                count = row["cnt"]
                sources[name] = {
                    "status": "green" if count > 0 else "red",
                    "record_count": count,
                }
            except Exception:
                sources[name] = {"status": "red", "record_count": 0}

    green = sum(1 for s in sources.values() if s["status"] == "green")
    total = len(sources)

    return {
        "overall": "green" if green == total else "yellow" if green > total // 2 else "red",
        "sources": sources,
        "summary": f"{green}/{total} sources active",
    }
```

- [ ] **Step 2: Mount all new routers in main.py**

Replace `api/main.py` with:

```python
"""FastAPI application entry point for CountyIQ."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.scout import router as scout_router
from api.routes.stats import router as stats_router
from api.routes.layers import router as layers_router
from api.routes.municipalities import router as municipalities_router
from api.routes.search import router as search_router
from api.routes.ops import router as ops_router

app = FastAPI(
    title="CountyIQ API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    """Minimal health route for Lambda and smoke tests."""
    return {"status": "ok"}


app.include_router(scout_router, prefix="/api/scout")
app.include_router(stats_router, prefix="/api/stats")
app.include_router(layers_router, prefix="/api/layers")
app.include_router(municipalities_router, prefix="/api/municipalities")
app.include_router(search_router, prefix="/api/search")
app.include_router(ops_router, prefix="/api/ops")
```

- [ ] **Step 3: Test all API endpoints**

```bash
cd api && DATABASE_PORT=5433 uvicorn main:app --reload --port 8000 &
sleep 2

echo "=== /api/health ==="
curl -s http://localhost:8000/api/health

echo "=== /api/stats ==="
curl -s http://localhost:8000/api/stats | python3 -m json.tool

echo "=== /api/municipalities (first 2) ==="
curl -s http://localhost:8000/api/municipalities | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d[:2], indent=2))"

echo "=== /api/municipalities/DELTA BORO ==="
curl -s "http://localhost:8000/api/municipalities/DELTA%20BORO" | python3 -m json.tool

echo "=== /api/search?q=Main ==="
curl -s "http://localhost:8000/api/search?q=Main" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{len(d)} results'); print(json.dumps(d[:2], indent=2))"

echo "=== /api/layers/municipalities (feature count) ==="
curl -s http://localhost:8000/api/layers/municipalities | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{len(d[\"features\"])} features')"

echo "=== /api/ops/health ==="
curl -s http://localhost:8000/api/ops/health | python3 -m json.tool

kill %1
```

Expected: All endpoints return valid JSON with real data. Stats show 72 municipalities, 9025 delinquent. Layers return 72 municipality features. Search returns address matches. Health shows green for loaded sources, red for parcels.

- [ ] **Step 4: Commit**

```bash
git add api/routes/ops.py api/main.py
git commit -m "feat(api): add ops/health, mount all Phase 4.1 routers"
```

---

### Task 6: Frontend Scaffold

**Files:**
- Rewrite: `frontend/package.json`
- Create: `frontend/tsconfig.json`, `frontend/vite.config.ts`, `frontend/index.html`, `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/vite-env.d.ts`

- [ ] **Step 1: Initialize the Vite + React + TypeScript project**

```bash
cd frontend
npm create vite@latest . -- --template react-ts
```

If prompted about existing files, overwrite. This creates the scaffold.

- [ ] **Step 2: Install dependencies**

```bash
cd frontend
npm install
npm install maplibre-gl react-map-gl deck.gl @deck.gl/core @deck.gl/layers @deck.gl/mapbox
npm install react-router-dom
```

- [ ] **Step 3: Configure Vite proxy**

Replace `frontend/vite.config.ts`:

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
```

- [ ] **Step 4: Create App.tsx with routing**

Replace `frontend/src/App.tsx`:

```tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import HomePage from './pages/HomePage'
import MapView from './pages/MapView'
import MunicipalityList from './pages/MunicipalityList'
import OpsHealth from './pages/OpsHealth'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/map" element={<MapView />} />
        <Route path="/municipalities" element={<MunicipalityList />} />
        <Route path="/ops/health" element={<OpsHealth />} />
      </Routes>
    </BrowserRouter>
  )
}
```

- [ ] **Step 5: Create placeholder page files so imports resolve**

Create minimal placeholder files for each page:

`frontend/src/pages/HomePage.tsx`:
```tsx
export default function HomePage() {
  return <div>HomePage placeholder</div>
}
```

`frontend/src/pages/MapView.tsx`:
```tsx
export default function MapView() {
  return <div>MapView placeholder</div>
}
```

`frontend/src/pages/MunicipalityList.tsx`:
```tsx
export default function MunicipalityList() {
  return <div>MunicipalityList placeholder</div>
}
```

`frontend/src/pages/OpsHealth.tsx`:
```tsx
export default function OpsHealth() {
  return <div>OpsHealth placeholder</div>
}
```

- [ ] **Step 6: Update main.tsx**

Replace `frontend/src/main.tsx`:

```tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './styles/theme.css'
import 'maplibre-gl/dist/maplibre-gl.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
```

- [ ] **Step 7: Create empty theme.css so import resolves**

Create `frontend/src/styles/theme.css`:

```css
/* Theme variables — will be populated in Task 7 */
```

- [ ] **Step 8: Verify the dev server starts**

```bash
cd frontend && npm run dev &
sleep 3
curl -s http://localhost:5173 | head -5
kill %1
```

Expected: HTML returned, no build errors.

- [ ] **Step 9: Commit**

```bash
cd frontend
# Add specific files, avoid node_modules
git add package.json package-lock.json tsconfig.json tsconfig.node.json vite.config.ts index.html src/ .gitignore
git commit -m "feat(frontend): scaffold React + Vite + MapLibre + routing"
```

---

### Task 7: Theme CSS + Nav Component

**Files:**
- Rewrite: `frontend/src/styles/theme.css`
- Create: `frontend/src/components/Nav.tsx`

- [ ] **Step 1: Write the theme CSS**

The full theme CSS is extracted from the approved homepage mockup (`homepage-v2.html`). Write `frontend/src/styles/theme.css` with the CSS variables, body styles, grid background, and animation keyframes from that mockup. Include all `:root` variables (`--bg-deep`, `--bg-panel`, `--bg-card`, `--border`, `--text-*`, `--accent-*`, `--font-*`), the `body` styles, the `body::before` grid overlay, and the `@keyframes fadeUp` animation.

Reference: `.superpowers/brainstorm/26435-1774815587/content/homepage-v2.html` — copy the `<style>` block's `:root`, `*`, `body`, `body::before`, `body::after`, and `@keyframes` rules.

- [ ] **Step 2: Write the Nav component**

Create `frontend/src/components/Nav.tsx`:

```tsx
import { Link } from 'react-router-dom'
import { useEffect, useState } from 'react'

export default function Nav() {
  const [sourceCount, setSourceCount] = useState<number | null>(null)

  useEffect(() => {
    fetch('/api/ops/health')
      .then(r => r.json())
      .then(d => {
        const green = Object.values(d.sources as Record<string, { status: string }>)
          .filter(s => s.status === 'green').length
        setSourceCount(green)
      })
      .catch(() => {})
  }, [])

  return (
    <nav style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '0 32px',
      height: 56,
      borderBottom: '1px solid var(--border)',
      background: 'rgba(10, 14, 26, 0.85)',
      backdropFilter: 'blur(12px)',
      position: 'sticky',
      top: 0,
      zIndex: 100,
    }}>
      <Link to="/" style={{ display: 'flex', alignItems: 'center', gap: 12, textDecoration: 'none' }}>
        <div style={{
          width: 28, height: 28,
          border: '2px solid var(--accent-gold)',
          borderRadius: 4,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 11,
          color: 'var(--accent-gold)', letterSpacing: -0.5,
        }}>CIQ</div>
        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 15, letterSpacing: 0.5, color: 'var(--text-primary)' }}>
            CountyIQ
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', letterSpacing: 2, textTransform: 'uppercase' as const }}>
            York County · PA
          </div>
        </div>
      </Link>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>
        <div style={{
          width: 6, height: 6, borderRadius: '50%',
          background: 'var(--accent-green)',
          boxShadow: '0 0 6px rgba(61, 189, 111, 0.5)',
          animation: 'pulse 3s ease-in-out infinite',
        }} />
        <span>{sourceCount !== null ? `${sourceCount} sources active` : '...'}</span>
      </div>
    </nav>
  )
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/styles/theme.css frontend/src/components/Nav.tsx
git commit -m "feat(frontend): command-center theme CSS + Nav component"
```

---

### Task 8: HomePage Component

**Files:**
- Create: `frontend/src/components/StatCard.tsx`, `frontend/src/components/SearchBar.tsx`
- Rewrite: `frontend/src/pages/HomePage.tsx`

This is the largest frontend task. The homepage has: Nav, SearchBar, 3 StatCards, 8 quick-access tiles (4 active + 4 disabled), and 2 intel panels (tax delinquency + data sources).

- [ ] **Step 1: Create StatCard component**

Create `frontend/src/components/StatCard.tsx`:

```tsx
interface StatCardProps {
  label: string
  value: string | number
  detail: string
  color: string
}

export default function StatCard({ label, value, detail, color }: StatCardProps) {
  return (
    <div style={{
      background: 'var(--bg-panel)',
      border: '1px solid var(--border)',
      borderRadius: 6,
      padding: '20px 24px',
      position: 'relative',
      overflow: 'hidden',
    }}>
      <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 2, background: color }} />
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, textTransform: 'uppercase' as const, letterSpacing: 2, color: 'var(--text-muted)', marginBottom: 8 }}>
        {label}
      </div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 32, fontWeight: 700, letterSpacing: -1, lineHeight: 1, color }}>
        {typeof value === 'number' ? value.toLocaleString() : value}
      </div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)', marginTop: 6 }}>
        {detail}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Create SearchBar component**

Create `frontend/src/components/SearchBar.tsx`:

```tsx
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

export default function SearchBar() {
  const [query, setQuery] = useState('')
  const navigate = useNavigate()

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (query.trim().length >= 2) {
      navigate(`/search?q=${encodeURIComponent(query.trim())}`)
    }
  }

  return (
    <div>
      <div style={{ fontFamily: 'var(--font-serif)', fontSize: 28, fontStyle: 'italic', color: 'var(--text-secondary)', marginBottom: 16, opacity: 0.8 }}>
        What are you looking for?
      </div>
      <form onSubmit={handleSubmit} style={{ position: 'relative' }}>
        <span style={{ position: 'absolute', left: 18, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', fontSize: 16 }}>⌕</span>
        <input
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search by address, owner name, or parcel ID..."
          style={{
            width: '100%',
            background: 'var(--bg-panel)',
            border: '1px solid var(--border)',
            borderRadius: 6,
            padding: '16px 20px 16px 48px',
            fontFamily: 'var(--font-mono)',
            fontSize: 14,
            color: 'var(--text-primary)',
            outline: 'none',
          }}
        />
      </form>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', marginTop: 8, letterSpacing: 0.3 }}>
        Try: <kbd style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 3, padding: '1px 6px', fontSize: 10 }}>123 Main St</kbd>
        {' '}or <kbd style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 3, padding: '1px 6px', fontSize: 10 }}>KEYSTONE REALTY</kbd>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Build the full HomePage**

Rewrite `frontend/src/pages/HomePage.tsx`. This component fetches `/api/stats` and `/api/ops/health` on mount and renders the full dashboard layout from the approved mockup. Use the exact layout structure from `homepage-v2.html` — stats grid, quick-access tiles with accent bars, and the two intel panels (tax delinquency + data sources).

Reference the approved mockup HTML for exact layout, colors, and copy. The component should:
- Fetch `/api/stats` for stat card values
- Fetch `/api/ops/health` for data sources panel
- Render Nav, SearchBar, 3 StatCards, tiles grid, and intel panels
- Use `Link` from react-router-dom for tile navigation (`/map`, `/map?layer=flood`, `/municipalities`)
- Disabled tiles have `opacity: 0.3` and `pointerEvents: 'none'`

- [ ] **Step 4: Verify homepage renders**

```bash
# Terminal 1: API
cd api && DATABASE_PORT=5433 uvicorn main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend && npm run dev
```

Open `http://localhost:5173` — the homepage should render with live data from the API.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/StatCard.tsx frontend/src/components/SearchBar.tsx frontend/src/pages/HomePage.tsx
git commit -m "feat(frontend): homepage with stats, tiles, and intel panels"
```

---

### Task 9: MapView Component

**Files:**
- Create: `frontend/src/components/LayerToggle.tsx`
- Rewrite: `frontend/src/pages/MapView.tsx`

- [ ] **Step 1: Create LayerToggle component**

Create `frontend/src/components/LayerToggle.tsx`:

```tsx
interface LayerConfig {
  id: string
  name: string
  color: string
  enabled: boolean
}

interface LayerToggleProps {
  layers: LayerConfig[]
  onToggle: (id: string) => void
}

export default function LayerToggle({ layers, onToggle }: LayerToggleProps) {
  return (
    <div style={{
      position: 'absolute',
      top: 72,
      right: 16,
      background: 'var(--bg-panel)',
      border: '1px solid var(--border)',
      borderRadius: 6,
      padding: 16,
      zIndex: 10,
      minWidth: 200,
    }}>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, textTransform: 'uppercase' as const, letterSpacing: 2, color: 'var(--text-muted)', marginBottom: 12 }}>
        Map Layers
      </div>
      {layers.map(layer => (
        <label key={layer.id} style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '6px 0', cursor: 'pointer',
          fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--text-secondary)',
        }}>
          <input
            type="checkbox"
            checked={layer.enabled}
            onChange={() => onToggle(layer.id)}
            style={{ accentColor: layer.color }}
          />
          <span style={{ width: 8, height: 8, borderRadius: 2, background: layer.color, flexShrink: 0 }} />
          {layer.name}
        </label>
      ))}
    </div>
  )
}
```

- [ ] **Step 2: Build the MapView page**

Rewrite `frontend/src/pages/MapView.tsx`. This component:
- Renders a full-screen MapLibre map using `react-map-gl` with the `Map` component
- Uses CARTO dark-matter basemap: `https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json`
- Initial viewport: center `[-76.73, 39.92]` (York County), zoom `10`
- Fetches GeoJSON layers from `/api/layers/{name}` on mount
- Renders layers using Deck.gl's `GeoJsonLayer` via `DeckGL` overlay
- Has a `LayerToggle` panel for toggling municipalities (on by default), flood zones, zoning, PennDOT projects
- Has a Nav at the top
- Includes a "Back to Home" link

Use `react-map-gl`'s `Map` component with `mapLib={import('maplibre-gl')}`. Layer colors:
- Municipalities: green outline, transparent fill (`[61, 189, 111, 40]`)
- Flood zones: blue fill (`[74, 127, 255, 80]`)
- Zoning: purple fill (`[124, 92, 191, 60]`)
- PennDOT projects: orange points (`[255, 165, 0, 200]`)

- [ ] **Step 3: Verify map renders with layers**

Open `http://localhost:5173/map` — should show dark basemap of York County with municipality boundaries visible.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/LayerToggle.tsx frontend/src/pages/MapView.tsx
git commit -m "feat(frontend): MapView with MapLibre + Deck.gl layers"
```

---

### Task 10: MunicipalityList + OpsHealth Pages

**Files:**
- Rewrite: `frontend/src/pages/MunicipalityList.tsx`
- Rewrite: `frontend/src/pages/OpsHealth.tsx`

- [ ] **Step 1: Build MunicipalityList**

Rewrite `frontend/src/pages/MunicipalityList.tsx`. Fetches `/api/municipalities`, renders Nav + a sortable table with columns: Name, Type, Delinquent Parcels, Total Delinquent ($). Uses the command-center table styling (dark rows, monospace numbers, hover highlight).

- [ ] **Step 2: Build OpsHealth**

Rewrite `frontend/src/pages/OpsHealth.tsx`. Fetches `/api/ops/health`, renders Nav + a grid of source cards. Each card shows source name, record count, and a colored status dot (green/red). Shows the overall status banner at the top.

- [ ] **Step 3: Verify both pages**

- `http://localhost:5173/municipalities` — 72 rows with delinquency data
- `http://localhost:5173/ops/health` — source status cards, parcels showing red

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/MunicipalityList.tsx frontend/src/pages/OpsHealth.tsx
git commit -m "feat(frontend): municipality list and ops health pages"
```

---

### Task 11: End-to-End Verification

**Files:** None (verification only)

- [ ] **Step 1: Start both servers**

```bash
# Terminal 1
cd api && DATABASE_PORT=5433 uvicorn main:app --reload --port 8000

# Terminal 2
cd frontend && npm run dev
```

- [ ] **Step 2: Use Playwright to screenshot each page**

Navigate to each page and take screenshots to verify rendering:
- `http://localhost:5173/` — homepage with live stats
- `http://localhost:5173/map` — map with municipality boundaries
- `http://localhost:5173/municipalities` — municipality list
- `http://localhost:5173/ops/health` — system health

- [ ] **Step 3: Fix any rendering issues found in screenshots**

Iterate on CSS/layout issues caught by visual inspection.

- [ ] **Step 4: Final commit**

```bash
git add -u
git commit -m "fix(frontend): visual polish from Playwright verification"
```
