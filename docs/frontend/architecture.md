# Frontend Architecture

## Frontend Architecture

### Stack

| Component | Technology | Purpose |
|---|---|---|
| UI framework | React 18+ (TypeScript) | Component-based UI, hooks for state management |
| Map rendering | MapLibre GL JS (via `react-map-gl`) | Free, open-source vector tile map rendering with WebGL |
| Data visualization | Deck.gl | GPU-accelerated rendering of 220K+ parcel polygons with interactive tooltips |
| Build tool | Vite | Fast builds, hot reload for development |
| API backend | FastAPI (Python) | Async REST API for data queries |
| Lambda adapter | Mangum | Makes FastAPI work inside AWS Lambda with zero code changes |
| Hosting | S3 + CloudFront | Static site hosting with CDN and HTTPS |
| API routing | API Gateway (REST) | Routes `/api/*` requests to Lambda |

### Why MapLibre + Deck.gl

MapLibre GL JS renders the base map (streets, labels, terrain) as vector tiles in the browser using WebGL. It handles zoom, pan, rotation, and 3D tilt natively. `react-map-gl` wraps it in React components so it integrates cleanly with the rest of the UI.

Deck.gl sits on top of the map as a data visualization layer. The key advantage: it renders large datasets using the GPU instead of the CPU. Your 220,000 parcel polygons, color-coded by zoning or assessed value, with hover tooltips and click interactions — Deck.gl handles that at 60fps where raw MapLibre would start struggling past ~50K features. It's built by the same team that maintains `react-map-gl` (Vis.gl, originally from Uber), so the integration is seamless.

Both are free and open source with no usage limits. Unlike Mapbox, there's no per-map-load pricing.

### What the UI looks like

```
┌─────────────────────────────────────────────────────────────────┐
│  [🔍 Search owners, addresses, parcels...]     [Layer ▾] [⚙]  │
├────────────────────────────────────┬────────────────────────────┤
│                                    │                            │
│                                    │   PARCEL DETAILS           │
│                                    │                            │
│          MAP VIEW                  │   Parcel: 43-000-01-0001   │
│                                    │   Owner: JOHN A SMITH      │
│     (MapLibre + Deck.gl)           │   Assessed: $185,000       │
│                                    │   Zoning: R-1 Residential  │
│     Parcels color-coded            │   Municipality: Conewago   │
│     by active layer                │   Acres: 1.24              │
│                                    │                            │
│     Click parcel → details         │                            │
│     in side panel                  │   (Assessment data shown)  │
│                                    │   (Deeds, licenses, and    │
│                                    │    business records added   │
│                                    │    in Phase 2)             │
│                                    │                            │
│                                    │   [View Full Entity ▸]     │
│                                    │                            │
├────────────────────────────────────┴────────────────────────────┤
│  York County Civic Intelligence Platform     Data as of 3/20   │
└─────────────────────────────────────────────────────────────────┘
```

### Core views (MVP)

**1. Map view (default):** Full-screen map of York County with multiple data layers that create a rich, real-place feel:

- **Parcels** — polygons rendered at zoom 13+, colored by assessment value, zoning, or owner. Click to open side panel with details.
- **Building footprints** — polygon outlines of every structure, rendered at zoom 15+. Makes the map look like a real place instead of an empty grid. Parcels without footprints are visually flagged as likely vacant.
- **Address points** — geocoded points rendered at zoom 12-14 (before parcel polygons are visible). Clickable — returns parcel details for the containing parcel. Provides something to interact with at mid-zoom levels.
- **Municipal boundaries** — toggleable polygon overlay with labels.
- **Flood zones** — toggleable FEMA flood hazard overlay (AE/A zones highlighted).
- **Delinquent tax heatmap** — red = delinquent, from assessment data.
- **Roads** — reference layer.

Toggle layers via the [Layer] dropdown. Building footprints and parcels are on by default; others are opt-in.

**2. Search:** Text search for owner names, addresses, or parcel IDs. Results appear as a list and are highlighted on the map. Searches hit the `/api/search` endpoint which queries the `owners` and `parcels` tables with `pg_trgm` fuzzy matching.

**3. Entity profile:** Clicking "View Full Entity" in the side panel opens a full-page view of a resolved owner — every parcel they own, and their assessment data.

**4. Property detail — comparables:** The parcel side panel includes a "Similar Properties" section. Shows nearby properties of the same class with comparable acreage/year built and their assessed values. Includes a percentile ranking ("Assessed higher than 72% of residential parcels in Conewago Twp"). Queries `/api/parcels/{pidn}/comparables`. No ML — SQL window functions over assessment data.

**5. Ownership concentration dashboard:** Accessible from the nav bar. Shows a leaderboard of top property owners by parcel count, total assessed value, or total acreage. Filterable by municipality. Click an owner → highlights all their parcels on the map. Queries `/api/owners/top`. This is the "who owns York County" view that no existing tool provides.

**6. Change detection feed:** "What changed this week" page. Shows recent ownership transfers, new delinquencies, assessment value changes, and new parcels — all derived from SCD2 history (records where `valid_to` was set recently = expired, `valid_from` is recent = new). Queries `/api/changes`. Filterable by change type and municipality.

> **MVP scope:** Entity detail shows parcels + assessment data only. Deeds, business filings, and licenses are added to entity views as their Phase 2 pipelines are built.

### What it does NOT include (MVP)

- **No user accounts or login** — fully public, read-only
- **No editing or data entry** — read-only intelligence platform
- **No real-time updates** — data refreshes weekly; frontend serves cached responses

### API endpoints (FastAPI on Lambda)

| Endpoint | Method | Purpose | Example |
|---|---|---|---|
| `/api/parcels/bbox` | GET | Parcels within a map bounding box | `?west=-76.8&south=39.8&east=-76.6&north=40.0` |
| `/api/parcels/{pidn}` | GET | Single parcel full details | `/api/parcels/4300006006500` |
| `/api/owners/{owner_id}` | GET | Resolved entity with all source links | `/api/owners/12345` |
| `/api/search` | GET | Fuzzy search across owners, addresses, parcels | `?q=smith+main+st&municipality=Conewago` |
| `/api/ops/health` | GET | System health dashboard data | See `docs/operations/health-dashboard.md` |

### Vector tiles

Tiles are **not served by Lambda**. They are pre-generated by the Dagster tile pipeline, uploaded to `s3://countyiq-tiles/`, and served via CloudFront at `/tiles/{layer}/{z}/{x}/{y}.pbf` (7-day cache). The API has no tile routes. MapLibre loads tiles directly from the CloudFront URL.

**Tile layers generated at MVP:**

| Layer | Source table | Geometry | Zoom range | Notes |
|-------|-------------|----------|------------|-------|
| `parcels` | `staging.parcels` | MultiPolygon | 13-18 | Color-coded by value/zoning/owner |
| `footprints` | `staging.structures` | Polygon | 15-18 | Building outlines, on by default |
| `addresses` | `staging.address_points` | Point | 12-14 | Clickable targets at mid-zoom |
| `flood_zones` | `staging.flood_zones` | MultiPolygon | 10-18 | FEMA hazard areas, toggleable |
| `municipalities` | `staging.municipalities` | MultiPolygon | 8-14 | Boundary outlines + labels |

**See `docs/api/lambda-api.md` for Lambda configuration, FastAPI app code, package size awareness, handler entry point, and CORS setup.**

### CloudFront distribution

CloudFront sits in front of everything and routes requests:

| Path Pattern | Origin | Cache Behavior |
|---|---|---|
| `/api/*` | API Gateway | No cache (dynamic queries) |
| `/tiles/*` | S3 (tile bucket) | Cache 7 days (tiles regenerated weekly) |
| `/*` (default) | S3 (static site bucket) | Cache 1 hour (React app assets) |

This means a single CloudFront URL serves both the React app and the API. No CORS issues between frontend and backend since they share the same domain.

### SPA routing (CloudFront Function)

React Router uses client-side URLs like `/ops/health` or `/search?q=smith` that don't correspond to real files in S3. A CloudFront Function (`countyiq-spa-rewrite`) is attached to the **default cache behavior only** and rewrites extensionless URIs to `/index.html` so React Router can handle them.

- Requests with file extensions (`.js`, `.css`, `.png`) pass through unchanged — these are real S3 objects.
- Requests without extensions (`/ops/health`, `/search`) are rewritten to `/index.html`.
- This function does NOT affect `/api/*` or `/tiles/*` — those have their own cache behaviors routed to API Gateway and S3 tiles respectively.

This replaces the `custom_error_response` approach (which would have been distribution-wide and would swallow real API 403/404 errors as HTML).

### API Gateway origin verification

API Gateway should only accept requests from CloudFront — not direct calls to its invoke URL. CloudFront adds a custom header on all `/api/*` requests, and API Gateway rejects anything without it.

```hcl
# infra/modules/frontend/cloudfront.tf — add to the /api/* cache behavior
custom_header {
  name  = "x-origin-verify"
  value = var.origin_verify_secret  # Random string, stored in terraform.tfvars (gitignored)
}
```

```hcl
# infra/modules/api/gateway.tf — API Gateway checks the header
resource "aws_api_gateway_request_validator" "origin_check" {
  rest_api_id           = aws_api_gateway_rest_api.countyiq.id
  name                  = "origin-verify"
  validate_request_body = false
}
```

```python
# api/main.py — FastAPI middleware verifies the header
import os
from fastapi import Request, HTTPException

ORIGIN_SECRET = os.environ.get("ORIGIN_VERIFY_SECRET")

@app.middleware("http")
async def verify_origin(request: Request, call_next):
    if ORIGIN_SECRET and request.headers.get("x-origin-verify") != ORIGIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    return await call_next(request)
```

The secret is set as a Lambda environment variable by Terraform (same pattern as DB credentials). Locally, omit `ORIGIN_VERIFY_SECRET` and the middleware passes everything through — so `uvicorn` dev still works.

### S3 buckets

| Bucket | Purpose | Public Access |
|---|---|---|
| `countyiq-frontend` | React build output (HTML/JS/CSS) | Via CloudFront only (OAC) |
| `countyiq-tiles` | Pre-generated vector tiles (.pbf) | Via CloudFront only (OAC) |
| `countyiq-raw` | Raw scrape archives (existing) | No public access |

**OAC (Origin Access Control):** S3 buckets are not publicly accessible. Only CloudFront can read from them, enforced by bucket policies referencing the CloudFront distribution.

### Frontend deployment workflow

```bash
# Local development
cd frontend
npm install
npm run dev          # Vite dev server on localhost:5173
                     # API calls proxied to local FastAPI or Lambda

# Production build + deploy
npm run build        # Outputs to frontend/dist/
aws s3 sync dist/ s3://countyiq-frontend --delete
aws cloudfront create-invalidation --distribution-id <id> --paths "/*"
```

**See `docs/infrastructure/cicd.md` for API deployment workflow and CI/CD automation.**

### Cold start mitigation

Lambda cold starts (1-3 seconds) happen when the function hasn't been invoked for ~5-15 minutes. Two options:

**Option 1 (free): CloudWatch keepalive.** A CloudWatch Events rule pings `/api/health` every 5 minutes. Keeps one Lambda instance warm. Cost: $0 (within free tier).

**Option 2 ($5-6/month): Provisioned Concurrency.** Keeps one Lambda instance permanently initialized. Eliminates cold starts entirely. Only worth it if you have real users noticing the delay.

**Recommendation:** Start with the CloudWatch keepalive. Add provisioned concurrency later if needed.

**See `docs/api/lambda-api.md` for connection pooling strategy, concurrency cap configuration, and connection limit planning.**

### Custom domain (future)

Not needed for MVP. The CloudFront distribution URL (`d1234abcd.cloudfront.net`) works fine. When you want a custom domain:

1. Register a domain (Route 53: ~$12/year for `.com`)
2. Create a hosted zone in Route 53
3. Request an ACM certificate (free)
4. Add the domain as an alternate domain name on the CloudFront distribution
5. Create an A record (alias) pointing to CloudFront

All of this is Terraform-able and can be added to the `frontend` module later.
