# Current State

This file is the fast answer to "where are we really with this repo?"

For the current deployed commit, recovery receipts and qualification evidence,
use the [September 5 launch record](operations/production-launch-2026-09-05.md).
The private app is live; municipal extraction publication and full backfill
remain gated. The model defaults below are configuration, not quality approval.

## October 3 direction and assessment status

The selected next direction is [site-intake research for York County civil and
land-planning firms](products/site-intake.md): a client-supplied property and
proposed use become a cited research handoff with explicit unresolved questions.
This deliberately reopens the earlier investor-only audience below. Customer
demand and pricing remain unvalidated; implementation and live acceptance are
unfinished.

The current remote product baseline is `codex/emerging-intelligence-pilot`,
35 commits ahead of `main`. Its release record documents production through
September 9; the live deployed commit has not been re-read in this assessment.
October 2 Grafana email reports 23 source warnings. See
[the repair PR](https://github.com/jdaws97/countyiq/pull/36) for tested code changes
and remaining runtime verification. The historical counts and status below are
dated records, not current production measurements.

## What CountyIQ Is Right Now

CountyIQ is a real-estate intelligence platform for York County, PA. The repo contains:

- a React frontend with home, feed, radar, map, municipality, search, property, entity/owner, project, watch, compare, and ops-health views; the legacy `/delinquent`, `/licenses`, `/projects`, `/distressed`, and `/assemblage` bookmarks redirect into Feed, Radar, or Search
- a FastAPI API serving those surfaces under `/api/*`
- a Dagster pipeline layer that handles both source ingestion and an LLM-backed intelligence workflow

## Target Buyer

CountyIQ is a **real-estate intelligence product for private-market investors and
developers in South-Central PA**, starting in York County. See
`docs/products/real-estate-intelligence.md` for the full lane, personas, and
roadmap. All new surfaces should serve an investor or developer job. This is
the only audience; earlier civic/journalist/government framings are dead.

## Honest Gap Assessment (2026-08-28 review)

The first usable intelligence loop is now implemented, but it still needs live
data backfill and customer use before CountyIQ is sales-ready:

- **Entity case file** (`/entity/:id`) — implemented over the stable
  `public.owners` ID space, with relationships, linked events, portfolio, brief,
  and entity watching.
- **Unified intelligence feed** (`/feed`) — combines deterministic parcel,
  value, structure, and delinquency changes with source-grounded development
  applications, hearings, revisions, continuances, decisions, conditions, and
  upcoming actions extracted once in Pass 0.
- **Customer verification receipts** — feed events, property reports, and
  owner/entity case files expose numbered evidence cards with source record
  IDs, dates, supporting facts or excerpts, derivation method, caveats, and
  original/internal links when available. Inline brief citations resolve to the
  same receipts; governed fields remain redacted when source policy disallows
  customer display.
- **Investigation workspace** — browser-local entity, parcel, municipality, and
  development-project watches now include in-app "new since last visit" alerts, reviewed/dismissed feed
  triage, saved Feed/Radar searches, 2–4 parcel comparison, CSV exports, and
  print/save-PDF evidence packets. A versioned JSON export/import moves the
  workspace between browsers without implying that CountyIQ has customer
  accounts. Optional private watchspace synchronization and a durable unread inbox are now implemented behind COUNTYIQ_WATCH_SYNC_ENABLED; deployment and customer acceptance remain unverified.
- ~~Weekly digest email~~ — dropped by decision (2026-08-02): no email features planned.
- The radar (score version 7, 2026-09-02) is deterministic, includes
  proceedings-linked `municipal_action` and owner `entity_assemblage`
  signals, and keeps weekly history for the Movers view and municipality
  pages. Opportunity weights are back-tested in
  `docs/research/radar-backtest-2026-09-02.md`. Version 7 also exposes exact
  per-score signal effects, uses parcel-wide soil and SFHA overlap, treats
  Agricultural Security Areas as neutral context rather than prohibitions,
  and documents all trigger/meaning/caveat pairs in
  `docs/research/development-signal-contract-v7.md`.
- Owner names are public record and shown everywhere (2026-09-03,
  `docs/decisions.md`): the per-source person-display switch is gone and
  generated prose (Pass 2/3/3b) is served under the ordinary derived-product
  permission.
- Pass 2+ intelligence has run on ~75 of 176,060 parcels. The municipal
  proceedings registry covers all 72 municipalities explicitly: 66 currently
  have an authorized main governing-body source and 68 have at least one active
  board source. All vendor, robots, and no-web-presence gaps remain as paused
  policy rows rather than being treated as empty activity.
- Zero customer conversations logged; pricing is unvalidated.

The active work queue is `docs/open-items.md`. Model choices and the evaluated
LLM/non-LLM boundary are recorded in `docs/decisions.md`; reusable comparison
tools remain under `pipelines/eval/`.

## Current Runtime Assumptions

| Area | Current state |
|---|---|
| Frontend | React + Vite; the production Compose web image serves the built frontend through Caddy and Cloudflare Tunnel |
| API | FastAPI + Uvicorn |
| Pipelines | Dagster |
| Database | PostgreSQL 16 + PostGIS (self-managed) |
| Object storage | Cloudflare R2 (via `R2_ENDPOINT_URL` — required, otherwise boto3 targets AWS) |
| Front door | Cloudflare |
| Inference backend | OpenRouter |
| Deployment | Private application live at app.countyiq.net on the configured VPS behind Cloudflare Access and Tunnel. Exact-commit releases, R2 backup/restore verification and the backup timer are operational. Live customer sign-in and cross-session workspace checks remain outstanding. Current release and evidence: [launch record](operations/production-launch-2026-09-05.md). |

## Current Model Lineup

Per-pass defaults live in `pipelines/countyiq/lib/pass_llm_config.py`
(`_PASS_MODEL_DEFAULTS`) with eval citations inline. Summary (2026-08-30):

| Pass | Default |
|---|---|
| Pass 0 (PDF extraction) | `openai/gpt-5.6-luna` (native PDF input) |
| Pass 1 (entity verification) | `openai/gpt-5.6-luna` (high reasoning, adaptive N=3 voting) |
| Pass 2 (signal validation) | `openai/gpt-5.6-luna` (low reasoning) |
| Pass 3/3b (briefs) | `openai/gpt-5.6-luna` |
| Pass 4 (narratives) | Disabled by default; Luna remains the opt-in provisional model pending wider data and a required product surface |
| NL search | Disabled by default; `qwen/qwen3.5-flash-02-23` is the opt-in intent parser |

Precedence: `COUNTYIQ_PASS{N}_MODEL` env > code default > `COUNTYIQ_OPENROUTER_MODEL`.
`z-ai/glm-5.3-flash` FP8 led the initial ten-case Pass 2 comparison but did not
generalize. On a stratified 100-case diagnostic, Luna led grounded decisions
(191/263 vs 166/263), strict signals (133/263 vs 102/263), required facts
(595/683 vs 573/683), and prohibited-claim control (0 vs 30 signals). Luna
therefore remains the default. The expanded rubric labels still require human
confirmation before they become promotion gold; a post-backfill live shadow is
for workload drift and cost, not model promotion. `deepseek/deepseek-v4-flash-0731`
remains the configured Pass 2 cost fallback with a renewed quality caveat;
`minimax/minimax-m3` is the cross-vendor fallback. Retired model slugs must not
be restored from old docs or git history.

LLMs are deliberately limited to work that needs semantic interpretation:
extracting and explaining unstructured municipal proceedings, entity ambiguity,
and selected synthesis. Parcel diffs, delinquency transitions, joins, filters,
ranking, radar scoring (score version 7, back-tested against historical plan
filings), API responses, and watch state remain deterministic. The feed
rebuild uses cached Pass 0 output and makes no additional model call, and the
radar keeps weekly score history so movers are visible without a model.

Pass 0–3 outputs now cross a fail-closed integrity boundary before serving:
document quotes must occur in locally extracted source text; entity partitions
must account for candidate names and may use only input record identifiers;
signal reasoning must cite machine-readable evidence refs; and parcel/owner
brief claims must use known inline signal/parcel citations. Accepted outputs
are append-versioned. If a later run changes the semantic decision while the
evidence-only hash is unchanged, the challenger is quarantined and the prior
serving projection remains active. These controls improve auditability and
consistency; they do not turn LLM judgment into independently verified fact.
Migration 040 archives and retracts any pre-gate serving row that cannot prove
this provenance, exposes aggregate integrity health, and supports atomic human
resolution through `pipelines/scripts/review_intelligence_contradictions.py`.
The product API remains read-only. Every enabled paid pass also requires an
explicit per-run dollar ceiling plus provider price ceilings; the harness
reserves the conservative maximum before dispatch and stops if provider cost
cannot be verified.
Migration 041 also persists every deterministic validation failure in an
append-only rejection ledger. The health API and Dagster guard warn when a
rejection occurred in the last 24 hours, so an invalid output cannot disappear
into worker logs or be treated as a clean canary.

Relevant env vars: `OPENROUTER_API_KEY`, `COUNTYIQ_PASS{0-4}_MODEL`,
`COUNTYIQ_PASS{0-4}_ENABLED`,
`COUNTYIQ_OPENROUTER_MODEL`, `COUNTYIQ_THINKING`, `COUNTYIQ_ARCHIVE_DIR`,
`COUNTYIQ_ARCHIVE_STRICT`, `COUNTYIQ_LLM_ARCHIVE_RETENTION_DAYS`,
`COUNTYIQ_PASS{0-4}_MAX_COST_USD`, `COUNTYIQ_MAX_PRICE_PROMPT`,
`COUNTYIQ_MAX_PRICE_COMPLETION`, `COUNTYIQ_PASS{0-3}_BACKFILL_MODE`,
`COUNTYIQ_PASS2_TRIALS`,
`COUNTYIQ_SEARCH_LLM_ENABLED`, `COUNTYIQ_SEARCH_API_KEY`,
`COUNTYIQ_SEARCH_RATE_PER_MIN`, `COUNTYIQ_SEARCH_DAILY_LLM_BUDGET`, and the
default-off `COUNTYIQ_ENABLE_RESTRICTED_DISTRESS` deployment gate.

The production Compose boundary uses an independent read-only API database
role, withholds pipeline/R2/Slack secrets from the API, runs application
containers as a non-root UID, validates proxy-derived client addresses, and
keeps public API docs off by default. API and pipeline packages may not import
one another, only the migration service receives the administrator URL, and the
release script stops both runtimes before backup and migration. The 2026-08-31
repository security review and remaining live-environment gates are in
`docs/operations/security.md`.

## Source Posture (2026-08-31)

Source reachability is not treated as permission. Migrations 031 through 036
establish use-specific source policy, immutable source-decision ledgers,
per-municipal-body policy and health state, and exact municipal origin
allowlists. Governed collection and API serving fail closed for unknown,
paused, disallowed-method, disallowed-use, unreviewed-origin, or overdue-review
policies.

- The YCPC project-folder economic-development candidates and CDBG housing
  layers are paused, removed from scheduled jobs, and expired from current
  scoring inputs pending written reuse confirmation.
- PLCB, tax claims, sheriff sales, and municipal proceedings are conditional.
  Collection uses allowlisted official methods; proceedings fail closed on
  robots/access uncertainty and sheriff collection no longer disguises a
  browser client.
- Municipal proceedings contain 107 configured source entries (105 distinct
  listing URLs) across 66 municipalities. All 72 municipalities remain in 122
  policy rows: 107 are conditional and 15 are paused after migration 057. Pauses cover two
  no-web-presence bodies, eCode360, Rep'd, Google Drive, and three explicit
  West Manheim robots disallows, plus six Penn/Paradise entries whose configured
  domains belong to Butler/Lancaster counties rather than York. Migration 057
  pauses acquisition and derived use while retaining evidence for repair. Every
  configured body must match its policy's municipality, URL, proceeding type,
  acquisition method, and allowed origin before any request is made;
  listing/document health, scheduled refresh freshness, and latest job failure
  state are visible in `/api/ops/health`.
- Franklintown Borough, Newberry Township, and Washington Township use official
  listing pages whose PDFs are delivered by GoDaddy's `img1.wsimg.com` CDN.
  Revision 042 records explicit product-owner risk acceptance for automated
  retrieval from that exact origin. Revision 043 narrowly accepts unavailable
  robots endpoints on those three first-party listing origins; the CDN document
  origin remains live robots-gated. Raw archives remain private and
  raw-document export remains disabled.
- York `OPEN_DATA`, PennDOT open data, FEMA NFHL, and data.pa.gov business data
  are approved for derived analytics within the recorded delivery boundary.
- PA DEP's public, non-sensitive GIS is approved for attributed derived
  screening. Active storage-tank facilities and land-recycling cleanup
  locations are deterministic proximity evidence, never contamination claims.
- Tax-claim row queries and claimant-name search are disabled; exact-debt
  distress routes and frontend pages are default-off. Owner names are public
  record and shown. Municipality aggregates, boolean parcel delinquency, and
  backend scores preserve the useful signal without exposing exact debt.
- Replacement scheduled inputs are York zoning overlays, business parks,
  industrial parks, soils, and local traffic counts. They power a separate
  site-screening score and buyer-facing Radar view. The 2026-08-28 local live
  verification loaded 85 overlays, 160 business-park records, 344
  industrial-park records, 16,735 soils, 3,010 traffic observations, 384 York
  active storage-tank facilities, and 1,314 cleanup-location records from the
  conservative county query envelope.
- Revision 036 makes source receipts reconstructable with the exact policy
  version, canonical snapshot, and SHA-256 fingerprint used for the decision.
  It also namespaces new-county municipal source keys and scopes policy-health
  reporting to the active isolated county stack.

RTKL responses, assessment-portal scraping, Tyler recorder scraping, eCode360,
and browser-based PA DOS scraping remain outside the production collection
path. Details and reactivation conditions are in `docs/decisions.md` and the
database source-rights rows.
