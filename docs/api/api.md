# CountyIQ API

## Runtime

FastAPI runs under Uvicorn in the `countyiq-api` container. Caddy proxies
`/api/*` from the public API domain to `api:8000`; PostgreSQL is reachable only
inside the Docker network and through the host's loopback binding.

```text
Browser -> Cloudflare -> Caddy -> FastAPI -> PostgreSQL/PostGIS
                              -> OpenRouter (natural-language intent only)
```

Map overlays and viewport parcels are served as bounded GeoJSON from the API;
no vector-tile pipeline exists (see `docs/frontend/architecture.md`).

## Registered GET Routes

The FastAPI OpenAPI schema is the executable authority. The current route
surface is:

| Area                      | Routes                                                                                                                                                                        |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Health and summary        | `/api/health`, `/api/ready`, `/api/ops/health`, `/api/stats`                                                                                                                  |
| Parcels                   | `/api/parcels/bbox`, `/api/parcels/near`, `/api/parcels/summary`, `/api/parcels/{pidn}/summary`, `/api/parcels/{pidn}`                                                        |
| Owners                    | `/api/owners/top`, `/api/owners/{owner_id}`                                                                                                                                   |
| Municipalities and layers | `/api/municipalities`, `/api/municipalities/{name}`, `/api/layers/{layer_name}`                                                                                               |
| Conditional distress      | `/api/delinquent/parcels`, `/api/delinquent/top-owners`, `/api/scores/distressed`, `/api/scores/assemblage` (not mounted by default)                                          |
| Development intelligence  | `/api/feed`, `/api/radar/development`, `/api/radar/development/bbox`, `/api/radar/movers`, `/api/radar/municipalities`, `/api/radar/opportunity`, `/api/radar/site-readiness` |
| Emerging cases            | `/api/intelligence`, `/api/intelligence/{case_key}`                                                                                                                           |
| Search                    | `/api/search`                                                                                                                                                                 |

Radar scores are **score version 7**: every score is a deterministic function
of `public.development_signals`, and Pass 2 output is carried only as a
display annotation. `/api/radar/opportunity` weights come from the
historical-plan back-test in `docs/research/radar-backtest-2026-09-02.md`.
Each full property signal adds a `presentation` object with a readable title,
trigger summary, interpretation, caveat, source facts, exact per-score point
effects, and eligibility effect; `evidence_receipt` resolves to the matched
source record where possible. `/api/parcels/{pidn}` also returns a parcel-wide
`soil_profile` and FEMA `overlap_pct`. Tax-signal claim amounts and history are
always suppressed in the public response.
The list routes accept `municipality`, `min_acres`, `max_acres`, and `class`
(comma-separated county class codes) and return compact signal JSON (per-signal
prose stays on `/api/parcels/{pidn}`). Each row carries `previous_score`,
`previous_opportunity_score`, `score_delta`, `opportunity_delta`,
`previous_computed_at`, and `is_new` from the previous weekly snapshot.
`/api/radar/movers` (`view=opportunity|momentum`, `direction=up|down|new`,
`min_delta`) lists the parcels whose score changed most since that snapshot.
`/api/radar/development/bbox` accepts `view=opportunity|momentum` for the map
layer. `/api/feed` priority now decays two points per fortnight of age (capped
at 25) and accepts `boost_pidns`, `boost_project_keys`, `boost_entity_ids`, and
`boost_municipalities`, which rank a caller's browser-local watches first
without filtering (a watched municipality earns a smaller boost than a watched
parcel, project, or entity).
`/api/municipalities/{name}` adds `development_pipeline` (source-backed
planning matters by event type, upcoming, recent, and municipality-wide
`policy` actions) and `radar_top`.

`/api/parcels/near` answers the corridor question: parcels within `radius_m`
(50–3000, default 800) of an anchor `pidn` or of every parcel linked to a
`project_key`, ranked by opportunity score then distance, with the parcel
facts, delinquency and likely-vacancy screens, radar scores when the radar
sources are permitted, and an owner label that follows source policy
(organizations link to their case file, individuals are labeled without a
name). `/api/feed` accepts `near_pidns` plus `near_radius_m` (default 400) to
return events on other parcels within that distance of the listed parcels.
`/api/parcels/{pidn}` reports the current `zoning` district at the parcel
center point with its own evidence receipt.

`/api/radar/site-readiness` retains its stable route name but is presented as
**site screening**. Its response reports coverage for seven deterministic
input families, and matched signals retain official evidence links. It is not
an official readiness, entitlement, engineering, flood, soil, or environmental
determination.

All routes are read-only. Conditional distress routes are mounted only when
`COUNTYIQ_ENABLE_RESTRICTED_DISTRESS=true`; the safe default is 404. Adding a public alias for an existing route requires
a real compatibility consumer; aliases are not kept speculatively.

## Emerging case pages

`GET /api/intelligence` returns `cases` containing summaries, `has_more`,
`next_cursor`, and page-scoped `coverage`. Its default `limit` is 20 and its
maximum is 100. Send the returned cursor with the same filters to continue;
nonzero legacy offsets and malformed or mismatched cursors return 422. The
cursor uses assessment time and case key, so later pages do not pay an
increasing offset cost. Filter changes start from the first page.

The indexed candidate lookup applies family, municipality, property, project
type, text, saved-case exclusions, and commercial filters before its limit.
Audience, service, and readiness must match the same possibility. Only the
selected candidates undergo canonical source equality checks, in one consistent
database snapshot. Withdrawn, superseded, or stale cases cannot be served merely
because they have an index entry. An entirely stale candidate page may be empty
while still returning a continuation. `checked_scopes` and
`awaiting_refresh_in_page` describe that page, not the full county. There is no
exact all-case `total` in this response.

Summaries omit evidence payloads, source excerpts, and citation markers.
`GET /api/intelligence/{case_key}` validates only that case's scope, then returns
the complete case and its shared evidence receipts. Both paths are read-only
and reuse bounded caches only while the transactional source revision and policy
date match. Requests never run a model or write a currentness projection.

## Source-Use Boundary

Backend storage does not by itself authorize customer-facing use. Each route
that depends on governed data checks the current database policy for derived
product use; missing, paused, or overdue policy fails closed. Owner names,
previous owners, proceeding applicants, and verified source excerpts are
public record and are served under that same permission (`docs/decisions.md`,
"Owner names are public record"). Exact tax-claim rows and totals remain the
one restricted surface: boolean delinquency, municipality aggregates, and
scores retain the signal without exposing the debt.

`/api/ops/health` also returns an `intelligence_integrity` aggregate containing
accepted/quarantined counts, unresolved contradiction age, resolution counts,
unlinked or mismatched serving projections, and aggregate deterministic-gate
rejection counts/timestamps. It never returns inference
payloads, source excerpts, or a mutation route. A fresh unresolved item is
yellow; an item older than `COUNTYIQ_CONTRADICTION_MAX_AGE_HOURS`, an unlinked
projection, or a history/projection mismatch is red. A validation rejection in
the last 24 hours is yellow.

`/api/ops/health` reports municipal-source configured, active, healthy,
blocked, unchecked, stale, and document counts. Scheduled staging sources also
report their refresh job, latest run outcome, latest successful completion, and
freshness deadline. A missing run, failed latest run, or expired freshness
window fails red even when current rows still exist, so operational
reachability cannot be mistaken for legal approval or current data.

## Natural-Language Search Boundary

`GET /api/search` uses a deterministic fuzzy path for ordinary owner, address,
and parcel lookups. It normalizes common street suffixes, ignores ordinary
PIDN punctuation, accepts useful PIDN prefixes, searches personal names in
both first/last and county last/first order, and ranks duplicate parcel matches
by their strongest evidence. Owner names are lookup inputs but are not echoed
on fuzzy result cards; those cards return the matched parcel address, PIDN, and
municipality. Longer natural-language requests can use a dedicated
low-cost LLM to emit a typed plan containing only:

- an allowlisted table and fields;
- typed filters and sort directions;
- fixed parcel signals such as likely vacancy, delinquency, or flood overlap;
- an allowlisted municipality or ZIP location; and
- a bounded aggregate and result limit.

The compiler owns all SQL expressions and spatial joins, and binds every
model/user value as a query parameter. The model cannot author SQL. Execution
also uses a read-only transaction and a five-second statement timeout.
Per-client rate limiting and a daily LLM-call budget bound interactive spend;
model failure or exhausted budget falls back to fuzzy search. Tax claims are
aggregate-only in the typed plan; claimant-name search and row-returning tax
claim plans are rejected.

## Unified Intelligence Feed

`GET /api/feed` reads the rebuildable `public.intelligence_events` ledger. It
accepts `category`, comma-separated `event_type` tags, comma-separated
`municipality` names (a plain name matches both the county spelling and the
public-body spelling; a value containing `%` is used as a literal ILIKE
pattern), `since_days`, comma-separated `pidns`, `project_keys`,
`entity_names`, and `entity_ids`, the `boost_*` watch parameters, `sort`
(`priority` or `latest`), `limit`, and `offset`.

Each event separates what happened, why it matters, and what happens next;
links related parcels/entities/projects and sources; and identifies whether
interpretation was deterministic or cached from an offline LLM pass. Serving
and filtering the feed never calls an LLM.

## Customer Evidence Receipts

Customer-facing intelligence responses use a shared evidence-receipt shape so
the UI can show what supports a claim without asking the customer to trust the
summary. Receipts include a stable `evidence_id`/`citation_key`, source type and
record identifier, effective and observed dates, a public-safe excerpt or fact
set, the derivation method, confidence/caveat text, and links when available.
`url` points to the original public record and `internal_url` points to the
relevant CountyIQ record. A missing original URL is represented honestly rather
than replaced with a generic source homepage.

The contract is exposed as:

- `sources` on `/api/feed` events;
- `evidence` plus brief/narrative `citation_evidence` on parcel reports; and
- `verification_evidence` plus brief `citation_evidence` on owner/entity case
  files.

Generated prose (Pass 2 validation reasoning and cross-signal insight, the
Pass 3 parcel brief, and the Pass 3b owner brief) is served whenever the
parcel source permits derived-product use.

Inline `[Signal: ...]`, `[Parcel: ...]`, and `[Evidence: ...]` markers resolve
to these receipts in the frontend. Source-use policy still governs every field:
exact tax-claim facts remain suppressed, while the receipt explains the fact,
identifier, method, and limitation that can be shown.

## Browser Access

The same-origin production path requires no CORS grant. Local development
allows only the two Vite origins in `api/lib/settings.py`. If the frontend is
hosted on a separate production origin, set a comma-separated
`COUNTYIQ_CORS_ORIGINS`; wildcard and path-bearing values are rejected.

## Database Connections

API connections disable PostgreSQL JIT compilation at connection startup. The
interactive serving views can spend seconds compiling queries that execute in
milliseconds without JIT. This setting is scoped to the API pool; pipeline
connections retain their own configuration.

Each of the two Uvicorn worker processes owns a thread-safe psycopg2 pool using
the dedicated `DATABASE_API_USER` login. That role can read the serving schemas and can write only private watchspace
state and account identity/membership: workspace/item creation and updates, saved investigations, deletion, and notification review. These writes require verified identity and account ownership.
It defaults every transaction to read-only and has server-side
statement and idle-transaction timeouts. The administrator credential is not
present in the API container. Grants are refreshed after every migration by
`pipelines/init-db/03-api-role.sh`.

`DATABASE_POOL_MIN` defaults to 1 and `DATABASE_POOL_MAX` to 8, so the API is
bounded at 16 connections instead of creating a new PostgreSQL connection per
request. Broken connections are discarded and the pool closes during FastAPI
shutdown. When all connections are busy, requests wait for at most
`DATABASE_POOL_WAIT_SECONDS` (default 5) and then receive HTTP 503 instead of
an internal-server error.

Map selection uses `/api/parcels/{pidn}/summary`, which preserves the full
report's displayed parcel, flood, structure, tax, momentum and accepted source
explanation fields but skips its soil coverage query. The complete
`/api/parcels/{pidn}` contract still includes detailed soils. Both routes retain
the same source policy and explanation freshness checks. Municipality profiles
render independently of their recent-activity feed's loading and error state.

The API accepts `COUNTYIQ_TRUSTED_HOSTS` plus loopback/test hostnames required
for internal health checks; unrestricted wildcard, URL, and path values are
rejected. Public documentation routes are disabled unless
`COUNTYIQ_EXPOSE_API_DOCS=true`. Owner/entity portfolio routes have a dedicated
per-client abuse throttle. Caddy validates Cloudflare's proxy ranges and
overwrites the forwarding chain before Uvicorn interprets it.

## Container and Deployment

`api/Dockerfile` uses Python 3.11 and a locked uv environment, then runs:

```text
/app/.venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 2
```

GitHub Actions currently verifies the locked API and pipeline environments,
unit tests, Docker-backed API contracts, and the frontend build. It does not
publish CountyIQ images. Production deployment therefore pulls the selected
Git commit on the VPS, builds the Compose services, applies Alembic migrations
explicitly, and restarts the stack. See `docs/operations/runbook.md` for the
commands and rollback procedure.

### Isolated database verification

The API integration fixture always seeds the dedicated countyiq_test database.
To verify a fresh schema without touching an existing local Compose project,
choose an unused host port and a unique project name:

    COUNTYIQ_TEST_DATABASE_PORT=5434 COMPOSE_PROJECT_NAME=countyiq-review api/.venv/bin/python -m pytest api/tests -q

Run from the repository root with uv on PATH. The fixture starts postgres-test
in that project, initializes its own named volume, migrates the database, and
refreshes API-role grants. Pipeline integration tests can then use DATABASE_PORT=5434
and DATABASE_NAME=countyiq_test. Preserve those environment settings when stopping
the isolated Compose project. The default test port remains 5433.

### Account sessions and discovery

GET /api/session reports verified sign-in state without provisioning. POST /api/session creates the provider-independent account and personal workspace after signed Cloudflare Access verification. Private /api/watchspaces requests resolve membership from that verified identity and require X-CountyIQ-User to match the account; writes additionally require X-CountyIQ-Workspace: 1 and an allowed Origin. Anonymous access-code creation is retired. Session and workspace responses are no-store.

GET /api/directory/organizations supports literal name/alias search with pagination, limited to business/government groupings. GET /api/directory/projects searches source-governed development events and groups them into case links. It does not manufacture cases from raw, unaccepted extraction input.

See [account runtime configuration](../operations/account-workspaces.md).

Property and owner profile assembly uses a short read-only, repeatable-read
database snapshot. Their policy checks, cached-brief dependency checks and
displayed facts therefore observe one committed database state during a request.
The pool resets transaction-local settings when the context exits; account
writes retain their existing transaction mode.
