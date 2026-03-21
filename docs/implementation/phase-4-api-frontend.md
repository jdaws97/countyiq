# Phase 4: API, Frontend & Operations Stack

**Goal:** The API and frontend are built, tested, and verified **locally**. Everything works end-to-end against Docker Postgres before any AWS deployment.

**Time estimate:** 2-3 days

**Prerequisites:** Phase 3 complete. Local Docker Postgres is populated with real data from pipeline runs.

> **Local-first:** The API runs on `localhost:8000` (uvicorn), the frontend on `localhost:5173` (Vite dev server), both hitting Docker Postgres on `localhost:5433`. Slack setup (Step 4.3) is the only step that touches external services. AWS deployment happens in Phase 5.

### Step 4.1: Build the FastAPI Lambda API

**Before writing API code:** Use Context7 to pull current FastAPI, Mangum, and psycopg2 docs. Verify the Mangum adapter pattern for Lambda integration and FastAPI's current middleware/dependency injection API.

Reference: Infrastructure Plan, Frontend Architecture → Lambda Configuration section.

| File | Purpose |
|---|---|
| `api/main.py` | FastAPI app with routes |
| `api/handler.py` | Mangum adapter for Lambda |
| `api/requirements.txt` | Python dependencies |
| `api/routes/parcels.py` | Parcel search/detail/comparables/adjacent endpoints |
| `api/routes/owners.py` | Owner entity + concentration endpoints |
| `api/routes/search.py` | Cross-entity search (uses address_points for canonical matching when available) |
| `api/routes/changes.py` | Change detection feed |
| `api/routes/municipalities.py` | Municipality profiles and listing |
| `api/routes/stats.py` | Homepage stats (total parcels, changes this week, total assessed) |
| `api/routes/ops.py` | Health dashboard endpoint |
| `api/lib/database.py` | RDS connection (reads DATABASE_* env vars set by Terraform — NOT Parameter Store at runtime; see Infra Plan, VPC networking constraint) |

**API endpoints to implement:**

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/parcels/bbox?west=...&south=...&east=...&north=...` | Parcels within map bounding box (supports `&layer=delinquent` for heatmap) |
| GET | `/api/parcels/{pidn}` | Property report card — full details + computed fields (assessment ratio, flood status, vacancy, owner portfolio summary). Queries `staging.parcels` directly (not the VIEW) to get all 37 columns. |
| GET | `/api/parcels/{pidn}/comparables` | Similar nearby properties with percentile ranking |
| GET | `/api/parcels/{pidn}/adjacent` | Neighboring parcel owners — uses `ST_Touches` on parcel geometries for assemblage planning. Performance note: use `ST_Touches` (cheaper than `ST_DWithin`); GIST index on `staging.parcels.geom` makes this fast. |
| GET | `/api/owners/top?by=parcel_count&limit=50` | Top owners leaderboard |
| GET | `/api/owners/{owner_id}` | Owner profile with all linked properties |
| GET | `/api/search?q=...` | Full-text search across owners, addresses, PIDNs. Uses `staging.address_points` for canonical address matching when available; falls back to `staging.parcels.propadr` if address_points table is empty. |
| GET | `/api/changes?since=7d&limit=5` | Recent changes: ownership transfers, delinquencies, value changes. Supports both `since` (time window) and `limit` (count) params. |
| GET | `/api/municipalities` | List all 72 municipalities with summary stats |
| GET | `/api/municipalities/{name}` | Municipality profile: parcels, assessed value, delinquency rate, top owners |
| GET | `/api/stats` | Homepage stats: total parcels, changes this week, total assessed value |
| GET | `/api/ops/health` | System health dashboard data |

**Test locally:**

```bash
cd api/
uv pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Test endpoints
curl http://localhost:8000/api/parcels/bbox?west=-76.8\&south=39.9\&east=-76.7\&north=40.0
curl http://localhost:8000/api/parcels/4300006006500/comparables
curl http://localhost:8000/api/owners/top?by=parcel_count\&limit=10
curl http://localhost:8000/api/changes?since=7d
curl http://localhost:8000/api/ops/health
```

**New endpoint implementation notes:**

| Endpoint | SQL approach |
|---|---|
| `/api/parcels/{pidn}` | Query `staging.parcels` directly (all 37 columns) + LEFT JOIN `staging.flood_zones` via `ST_Intersects` for flood status + LEFT JOIN `staging.structures` via `ST_Intersects` for vacancy indicator + aggregate owner portfolio from `public.owners`/`public.owner_source_links`. Returns template-ready JSON with computed fields (assessment ratio, flood zone name, vacancy boolean). |
| `/api/parcels/{pidn}/comparables` | Window function over `staging.parcels` — filter by same `class` and `municipality`, rank by `aprtotal` difference, return top 10 with `PERCENT_RANK()` for the queried parcel |
| `/api/parcels/{pidn}/adjacent` | `SELECT pidn, owner_full, aprtotal FROM staging.parcels WHERE ST_Touches(geom, (SELECT geom FROM staging.parcels WHERE pidn=$1)) AND valid_to IS NULL`. Uses GIST index. |
| `/api/owners/top` | `SELECT * FROM public.owners ORDER BY parcel_count DESC LIMIT $limit` with optional `WHERE municipality = $muni`. Already computed by entity resolution. |
| `/api/search` | Fuzzy match via `pg_trgm` on `owner_full` and `propadr` in `staging.parcels`. When `staging.address_points` exists, also matches against canonical addresses for better accuracy. Falls back gracefully if address_points table is empty. |
| `/api/changes` | Query SCD2 tables for recent activity: `WHERE valid_to >= NOW() - INTERVAL $since` (expired records = changes) UNION `WHERE valid_from >= NOW() - INTERVAL $since AND valid_to IS NULL` (new records). Categorize as ownership_transfer, value_change, new_delinquency based on which columns changed. |
| `/api/municipalities` | `SELECT name, COUNT(*) as parcels, SUM(aprtotal::numeric) as total_assessed FROM staging.parcels WHERE valid_to IS NULL GROUP BY municipality`. |
| `/api/municipalities/{name}` | Same aggregation for one municipality + top owners + recent changes + delinquency count. |
| `/api/stats` | Simple aggregation: `SELECT COUNT(*), SUM(aprtotal::numeric) FROM staging.parcels WHERE valid_to IS NULL` + changes count from SCD2 history. Cached aggressively (1 hour TTL). |
| `/api/parcels/bbox` with `layer=delinquent` | Same bbox query but joins `staging.assessment_properties` and includes `delinquent_taxes IS NOT NULL` as a boolean flag for the frontend heatmap layer |

**Implementation notes:**

- **`saledt` is a string, not a date.** The "recently sold" filter needs `CAST(saledt AS DATE)` or a regex parse. Consider adding a `sale_date DATE` computed column in a future migration for index-friendly date filtering.
- **Export strategy:** CSV export is client-side — the frontend converts JSON API responses to CSV/downloadable files using a library like `papaparse`. PDF export for the property report card uses client-side `html2pdf.js` or `jspdf` — avoids adding heavy PDF libraries to the Lambda package (which has a 250MB limit). No server-side export endpoints needed.
- **Owner profile depends on entity resolution.** Until the entity resolution pipeline runs, `/api/owners/{owner_id}` returns empty results and the "Also owns X other parcels" field in the property report card will be absent. The frontend should handle this gracefully (hide the section rather than show "0 other parcels").
- **`public.properties` VIEW is too narrow for the property report card.** The VIEW only includes a subset of parcel columns. The `/api/parcels/{pidn}` endpoint should query `staging.parcels` directly to get all fields (year built, living area, deed book/page, previous owner, previous price). Consider widening the VIEW in a future migration.

**Package and deploy to Lambda (Phase 5 — after `terraform apply`):**

```bash
cd api/
pip install -r requirements.txt -t package/
cp -r *.py routes/ lib/ package/
cd package && zip -r ../lambda.zip .

aws lambda update-function-code \
  --function-name countyiq-api \
  --zip-file fileb://lambda.zip
```

> **Checkpoint:** Hit the API Gateway URL in a browser. `/api/ops/health` returns JSON with source statuses. `/api/parcels/{pidn}` returns a real parcel record. Run `superpowers:requesting-code-review` against the API code before proceeding.
>
> **Note on tiles:** Vector tiles are NOT served by Lambda. They're pre-generated by the Dagster tile pipeline and uploaded to S3. CloudFront routes `/tiles/*` directly to the S3 tiles bucket (7-day cache). The API has no tile routes.

### Step 4.2: Build the React Frontend

**Before writing frontend code:**
- Use **Context7** to pull current docs for MapLibre GL JS, Deck.gl, and react-map-gl. These libraries have breaking changes between major versions — verify the integration pattern (especially Deck.gl's MapboxOverlay vs. older GoogleMapsOverlay approach) before writing components.
- Use the **`frontend-design` skill** when building each view/component. It produces distinctive, production-grade UI that avoids generic AI aesthetics — important for a public-facing civic platform.

Reference: Infrastructure Plan, Frontend Architecture section (UI mockup, core views, stack table).

**Core views to implement:**

| View | Route | Description |
|---|---|---|
| **Homepage** (default) | `/` | Search-first dashboard: search bar, stats cards, quick-access tiles (Explore Map, Vacant Land, Top Owners, Recent Sales, Flood Risk, Delinquent Taxes), recent changes feed, top owners preview. Queries `/api/stats`, `/api/changes?limit=5`, `/api/owners/top?limit=3`. |
| **Map View** | `/map` | MapLibre GL JS + Deck.gl. Parcels + building footprints + toggleable layers (municipal boundaries, flood zones, delinquent tax overlay). Filter bar with presets: vacant land, recently sold, flood risk, by municipality/class/value range. Click parcel → property report card in side panel. |
| **Property Report Card** | Side panel on map | Template-rendered summary: owner, address, assessment ratio, flood status, comparable percentile, sale history, vacancy indicator, owner portfolio count, deed reference. Actions: Full Profile, Compare, Export PDF. |
| **Owner Profile** | `/owners/{id}` | All properties owned by a resolved entity. Map highlighting + sortable table. **Depends on entity resolution pipeline being operational.** |
| **Parcel Comparison** | Modal/panel | Select 2-3 parcels → side-by-side table (assessed value, sale price, ratio, acres, year built, flood zone). |
| **Municipality Profile** | `/municipality/{name}` | Township/borough dashboard: total parcels, assessed value, delinquency rate, top owners, recent changes, vacant land count, class breakdown. Export CSV for municipal meetings. |
| **Top Owners** | `/owners` | Leaderboard by parcel count/assessed value/acreage. Filter by municipality. Click owner → highlights parcels on map. Export CSV. |
| **Change Feed** | `/changes` | "What changed this week" — ownership transfers, new delinquencies, value changes, suspicious transfers ($1 sales). Filter by type and municipality. |
| **Ops Health** | `/ops/health` | Operational dashboard (see `docs/operations/health-dashboard.md`). |

```bash
cd frontend/

# Initialize React app with Vite
npm create vite@latest . -- --template react-ts
npm install
npm install maplibre-gl deck.gl @deck.gl/mapbox @deck.gl/layers
npm install react-router-dom

# Develop
npm run dev
```

**Per-component workflow:**

```
1. Design:          Use frontend-design skill for the component
2. Check lib docs:  Use Context7 for MapLibre/Deck.gl/React APIs
3. Build:           Write the component
4. Visual verify:   Use Playwright MCP to navigate to localhost:5173,
                    take a screenshot, confirm the component renders correctly
5. Iterate:         Fix layout/styling issues caught in the screenshot
6. Repeat for each view
```

**Deploy to S3/CloudFront (Phase 5 — after `terraform apply`):**

```bash
npm run build
aws s3 sync dist/ s3://countyiq-frontend --delete
aws cloudfront create-invalidation \
  --distribution-id <distribution-id> \
  --paths "/*"
```

> **Checkpoint:** Use Playwright MCP to navigate to the CloudFront URL and take screenshots of each view. The map loads with parcel boundaries. Click a parcel and see real data in the sidebar. Search returns results. `/ops/health` page shows green/yellow/red statuses. Run `superpowers:requesting-code-review` against the frontend code before proceeding.

### Step 4.3: Set Up Slack Workspace & Integrations

1. ~~Create a free Slack workspace~~ **Done** — workspace is `CountyIQ` (countyiq.slack.com)
2. Create channels: `#alerts-critical`, `#alerts-warning`, `#pipeline-runs`
3. Turn ON phone notifications for `#alerts-critical` (this is the only channel that should buzz your phone)
4. Create a Slack App at [api.slack.com/apps](https://api.slack.com/apps) → "Create New App" → "From scratch" → name it `CountyIQ`
5. Enable Incoming Webhooks in the app settings, then "Add New Webhook to Workspace" **three times** — once per channel. Each gives a separate URL.
6. Store all three webhook URLs in Parameter Store:

```bash
aws ssm put-parameter \
  --name "/countyiq/slack-webhook-critical" \
  --value "https://hooks.slack.com/services/T.../B.../..." \
  --type SecureString

aws ssm put-parameter \
  --name "/countyiq/slack-webhook-warning" \
  --value "https://hooks.slack.com/services/T.../B.../..." \
  --type SecureString

aws ssm put-parameter \
  --name "/countyiq/slack-webhook-pipeline" \
  --value "https://hooks.slack.com/services/T.../B.../..." \
  --type SecureString
```

7. Test each webhook: `curl -X POST -H 'Content-type: application/json' --data '{"text":"Test from CountyIQ"}' YOUR_WEBHOOK_URL`
8. Deploy the CloudWatch → Slack forwarder Lambda (see Infrastructure Plan, Error Handling section)
9. Subscribe the Lambda to the SNS topic used by CloudWatch alarms

> **Checkpoint:** Manually trigger a test message to each Slack channel. Verify phone push notifications work for `#alerts-critical`. Stop and restart Dagster to trigger the success sensor — verify `#pipeline-runs` gets a message.

---
