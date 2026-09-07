# Frontend Architecture

## Product Boundary

The React client serves South-Central Pennsylvania real-estate investors and
small/mid-size developers. Its primary jobs are parcel/entity lookup,
deterministic development screening, development-event monitoring, map
exploration, and retaining investigations. The public marketing site is separate from the protected app host; verified accounts receive a personal workspace at the app root with synchronized watches, saved searches, comparisons and recent investigations. Guest browser work remains portable through explicit export/import. See [account workspaces](../operations/account-workspaces.md).

The accepted customer journey and page composition are documented in
[Customer experience](customer-experience.md). Read that contract before changing
navigation, investigation layouts or evidence presentation.

## Stack

| Concern  | Choice                                                                        |
| -------- | ----------------------------------------------------------------------------- |
| UI       | React 19 + TypeScript                                                         |
| Routing  | React Router 7 data router                                                    |
| Build    | Vite 8, Node 22, npm lockfile                                                 |
| Map      | MapLibre through `react-map-gl`                                               |
| Overlays | Direct `@deck.gl/core`, `@deck.gl/layers`, and `@deck.gl/react` packages      |
| Hosting  | Separate marketing/app HTML entries served by Caddy through Cloudflare Tunnel |

The frontend intentionally avoids a global state library. Route state comes
from URLs, page data comes from `/api/*`, and watches (parcels, projects,
entities, municipalities), feed triage, saved searches, and the four-parcel
comparison use small versioned browser records. Verified identity selects an account-specific cache; the server owns synchronized snapshots and optimistic versions. Event triage and visit markers remain local to that account.

`RouteFrame` owns scroll restoration, route-specific document titles, loading,
and route error handling. `WorkspaceShell` provides grouped desktop navigation,
a mobile drawer, persistent search and a saved light/dark theme preference.
`PageShell` wraps it for normal pages; the map uses its full-height mode. Shared page headers, buttons, empty states, status messages,
and print styles keep the primary investigation flows consistent and keyboard
focus is visible throughout.

## Routes

`frontend/src/App.tsx` is authoritative for app-host routes. The marketing host uses the independent frontend/src/marketing.tsx entry:

| Route                                                                 | Purpose                                                                                                                                                                            |
| --------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/`                                                                   | Account workspace on app host; marketing homepage on public host                                                                                                                   |
| /app                                                                  | Compatibility alias for the account workspace                                                                                                                                      |
| /organizations                                                        | Searchable directory of business and government ownership groupings                                                                                                                |
| `/map`                                                                | Interactive parcel and reference-layer exploration                                                                                                                                 |
| `/property/:pidn`                                                     | Mapped property investigation with Activity, Site & ownership, Property records and Sources views                                                                                  |
| `/entity/:id`, `/owner/:id`                                           | Entity case file over the stable `public.owners` identity; the owner path is a compatibility alias                                                                                 |
| `/project/:key`                                                       | Project case file: evidence timeline, connected entities/parcels, parcels near the project, CSV export, watch action                                                               |
| `/radar`, `/feed`                                                     | Property screening and the queue/reading-pane activity workspace                                                                                                                   |
| `/municipalities`, `/municipalities/:name`                            | Municipality index and the developer-facing municipality page: source-backed planning pipeline, top opportunity parcels with weekly change, recent feed events, and tax aggregates |
| `/delinquent`, `/distressed`, `/assemblage`, `/licenses`, `/projects` | Legacy bookmarks redirect into Radar, Feed, or Search; their standalone page chunks are no longer in the product router                                                            |
| `/search`                                                             | Fuzzy or typed natural-language results                                                                                                                                            |
| `/watch`                                                              | Account-synced watches and searches (browser-local for guests), with new-since-last-visit flags, activity within 400 m of watched parcels, and workspace export/import             |
| `/compare`                                                            | Side-by-side diligence comparison for 2–4 parcels, with CSV and print/PDF output                                                                                                   |
| `/ops/health`                                                         | Source availability, refresh freshness, run failures, policy health, aggregate intelligence integrity, and recent deterministic-gate rejection telemetry                           |

Marketing has its own entry and stylesheet, and makes no API calls. Product
pages are route-lazy so MapLibre and deck.gl do not inflate the initial application chunk. Heavy map chunks are expected on
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
`localhost:8000` in development on the app.localhost host only. Public-host
API requests are rejected. See [host rollout and local preview](../operations/account-workspaces.md). A same-origin production proxy requires no
CORS grant; a separate frontend origin must be configured explicitly as
described in `docs/api/api.md`.

Pages treat optional sources as optional: failed overlays remain empty and
nullable report sections are hidden or labeled unavailable. Search and core
report failures show an explicit empty/error state rather than fabricated
zeroes. The ops page reports table presence and current row counts only; see
`docs/operations/health-dashboard.md` for the exact limitation.

## Evidence UI

`SourceViewer` is the shared customer-verification surface. `EvidencePanel`
provides source access and a print appendix; `CitedText` opens a resolved citation
directly in the viewer. `customerEvidence.ts` explicitly presents useful public
facts. Never serialize arbitrary evidence dictionaries into the customer UI.
Hashes, event/inference IDs, model versions and scoring weights stay internal.
Public legal identifiers, dated excerpts, relevant page links and clear source
relationships remain available. Missing originals or citations are labeled
unavailable rather than replaced by misleading links.

`WorkspaceOverview` opens with available records, stated dates and recent work.
`InvestigationDesk` pairs a desktop queue with a complete selected account and
source-document view; phones use list-to-detail navigation. `investigation.ts`
keeps explanation dates/next checks together with the underlying proceeding's
conditions and milestones. Selecting an explanation must not discard those facts
or shift their original source indexes.

`PropertyDetail` uses separate property views instead of a long stacked report.
`ParcelContextMap` renders a bounded GeoJSON parcel preview as SVG without loading
MapLibre or deck.gl; the full map remains route-lazy. Property view state and
activity selection are carried in URLs. Comparison URLs carry their explicit
parcel selection, including incomplete editing state; share is available for a
valid set of two to four properties. Watch, account and export semantics continue
to use the existing workspace stores.

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
draws score-coloured radar points from zoom 11 and parcel outlines from zoom 13. The feed toolbar has a municipality filter, and the home and feed requests
pass the browser-local watch state as boost parameters so watched subjects
rank first without hiding everything else.

Development Radar labels the historical `readiness` mode as **Site Screening**.
It displays loaded/missing evidence-layer coverage, and property case files
link matched screening signals to their official source. Product copy must not
describe ranked parcels as "ready sites."
