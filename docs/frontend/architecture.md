# Frontend Architecture

## Product Boundary

The React client serves South-Central Pennsylvania real-estate investors and
small/mid-size developers. Its primary jobs are parcel/owner lookup, distress
and assemblage discovery, development-event monitoring, map exploration, and
retaining a small watchlist. It is public and read-only; there are no accounts
or server-side user preferences. Browser-local investigation state can be
exported as a versioned JSON workspace and imported on another device. This is
deliberate portability, not automatic account sync.

## Stack

| Concern | Choice |
|---|---|
| UI | React 19 + TypeScript |
| Routing | React Router 7 data router |
| Build | Vite 8, Node 22, npm lockfile |
| Map | MapLibre through `react-map-gl` |
| Overlays | Direct `@deck.gl/core`, `@deck.gl/layers`, and `@deck.gl/react` packages |
| Hosting direction | Static build on Cloudflare Pages; API remains behind Caddy |

The frontend intentionally avoids a global state library. Route state comes
from URLs, page data comes from `/api/*`, and watches, feed triage, saved
searches, and the four-parcel comparison are small versioned `localStorage`
records. If interviews validate automatic multi-device watchlists, authenticated
server persistence remains a separate product and security decision.

`RouteFrame` owns scroll restoration, route-specific document titles, loading,
and route error handling. `Nav` provides persistent search and a saved light/dark
theme preference. Shared page headers, buttons, empty states, status messages,
and print styles keep the primary investigation flows consistent and keyboard
focus is visible throughout.

## Routes

`frontend/src/App.tsx` is authoritative:

| Route | Purpose |
|---|---|
| `/` | Search-first dashboard and source summary |
| `/map` | Interactive parcel and reference-layer exploration |
| `/property/:pidn`, `/owner/:id` | Property and owner intelligence |
| `/radar`, `/feed` | Development signals (Opportunity, Momentum, Movers, Site Screening) and unified events |
| `/municipalities`, `/municipalities/:name` | Municipality index and the developer-facing municipality page: source-backed planning pipeline, top opportunity parcels with weekly change, recent feed events, and tax aggregates |
| `/delinquent`, `/distressed`, `/assemblage`, `/licenses`, `/projects` | Legacy bookmarks redirect into Radar, Feed, or Search; their standalone page chunks are no longer in the product router |
| `/search` | Fuzzy or typed natural-language results |
| `/watch` | Browser-local retained parcels/projects |
| `/compare` | Side-by-side diligence comparison for 2–4 parcels, with CSV and print/PDF output |
| `/ops/health` | Source availability, refresh freshness, run failures, policy health, aggregate intelligence integrity, and recent deterministic-gate rejection telemetry |

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

## Evidence UI

`EvidencePanel` is the shared customer-verification surface for feed events,
property reports, and owner/entity case files. It renders numbered receipts
with the source and record ID, effective/observed dates, public-safe excerpts or
facts, method, confidence, caveat, and links to the original record and related
CountyIQ page. `CitedText` turns the pipeline's inline signal, parcel, and
evidence markers into links to the matching receipt. If a receipt has no public
original URL, the UI says so and retains the remaining provenance instead of
creating a misleading link.

Property reports lead with the address and decision-relevant facts, followed by
the verification receipts. Feed cards are compact review items and expand into
the what/why/next-step analysis, connections, and evidence. Property and project
case files can be shared by URL or printed/saved as a PDF; parcel comparison and
watch summaries support CSV export.

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

Development Radar is stateful as of score version 7: the **Movers** tab reads
`/api/radar/movers` and every list row shows the change since the previous
weekly snapshot ("▲ 18", "New"). Lists filter by municipality, minimum acreage,
and property class, show up to three reason chips beside the headline signal,
and link to `/map?layer=radar&radar=opportunity|momentum`, where the map
draws score-coloured radar points from zoom 11 and parcel outlines from zoom
13. The feed toolbar has a municipality filter, and the home and feed requests
pass the browser-local watch state as boost parameters so watched subjects
rank first without hiding everything else.

Development Radar labels the historical `readiness` mode as **Site Screening**.
It displays loaded/missing evidence-layer coverage, and property case files
link matched screening signals to their official source. Product copy must not
describe ranked parcels as "ready sites."
