# Frontend Architecture

## Product Boundary

The React client serves South-Central Pennsylvania real-estate investors and
small/mid-size developers. Its primary jobs are parcel/owner lookup, distress
and assemblage discovery, development-event monitoring, map exploration, and
retaining a small watchlist. It is public and read-only; there are no accounts
or server-side user preferences.

## Stack

| Concern | Choice |
|---|---|
| UI | React 19 + TypeScript |
| Routing | React Router 7 |
| Build | Vite 8, Node 22, npm lockfile |
| Map | MapLibre through `react-map-gl` |
| Overlays | Direct `@deck.gl/core`, `@deck.gl/layers`, and `@deck.gl/react` packages |
| Hosting direction | Static build on Cloudflare Pages; API remains behind Caddy |

The frontend intentionally avoids a global state library. Route state comes
from URLs, page data comes from `/api/*`, and the current watchlist is a small
versioned `localStorage` record. If interviews validate multi-device watchlists,
server persistence is a separate product decision.

## Routes

`frontend/src/App.tsx` is authoritative:

| Route | Purpose |
|---|---|
| `/` | Search-first dashboard and source summary |
| `/map` | Interactive parcel and reference-layer exploration |
| `/municipalities`, `/municipalities/:name` | County market summaries |
| `/property/:pidn`, `/owner/:id` | Property and owner intelligence |
| `/delinquent`, `/distressed`, `/assemblage` | Deterministic opportunity views |
| `/radar`, `/feed` | Development signals and unified events |
| `/licenses`, `/projects` | Source-specific browsers |
| `/search` | Fuzzy or typed natural-language results |
| `/watch` | Browser-local retained parcels/projects |
| `/ops/health` | Current-row availability and counts |

Home is loaded eagerly. Every other page is route-lazy so MapLibre and deck.gl
do not inflate the initial application chunk. Heavy map chunks are expected on
`/map`; a regression that pulls them into the entry chunk should fail review.

## Map Data Flow

The map currently consumes API GeoJSON, not pre-generated vector tiles:

1. Municipality, flood, zoning, and PennDOT project overlays load from
   `/api/layers/{layer_name}`.
2. Parcels are hidden below zoom 13.
3. At zoom 13+, a debounced viewport request calls `/api/parcels/bbox`.
4. Deck.gl renders the returned GeoJSON and opens a property panel after a
   parcel click.
5. The panel loads `/api/parcels/{pidn}`.

Do not document or provision an R2 tile pipeline unless one actually ships.
If county expansion makes bounded GeoJSON too slow, vector tiles are a future
optimization with its own measurement and cache-invalidation design.

## API and Failure Behavior

The browser uses relative `/api/*` URLs. Vite proxies those requests to
`localhost:8000` in development. A same-origin production proxy requires no
CORS grant; a separate frontend origin must be configured explicitly as
described in `docs/api/api.md`.

Pages treat optional sources as optional: failed overlays remain empty and
nullable report sections are hidden or labeled unavailable. Search and core
report failures show an explicit empty/error state rather than fabricated
zeroes. The ops page reports table presence and current row counts only; see
`docs/operations/health-dashboard.md` for the exact limitation.

## Verification

Use the committed npm lockfile and Node 22:

```bash
npm ci
npm run typecheck
npm run lint
npm run build
```

Meaningful UI work also requires a Playwright walkthrough of the affected
routes at desktop and narrow viewport sizes. Compilation and bundle creation
do not prove that navigation, data loading, map interaction, or layout works in
a browser.

Development Radar labels the historical `readiness` mode as **Site Screening**.
It displays loaded/missing evidence-layer coverage, and property case files
link matched screening signals to their official source. Product copy must not
describe ranked parcels as "ready sites."
