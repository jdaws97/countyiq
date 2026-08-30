# Decision Log

This file records decisions that define the current repository. Experiment
transcripts and superseded choices belong in git history or the gitignored
`pipelines/eval/results/` directory.

## Product and Architecture

| Area | Current decision | Consequence |
|---|---|---|
| Product lane | Real-estate intelligence for investors and developers in South-Central PA, starting with York County | Surfaces must serve an investor or developer job; the earlier civic and government product framing is retired. |
| Repository | One monorepo | Frontend, API, pipelines, migrations, deployment, and current docs change together. |
| Runtime | React/Vite, FastAPI/Uvicorn, Dagster, PostgreSQL 16/PostGIS | These are the only active application paths. |
| Deployment target | Docker Compose on Hetzner behind Cloudflare; Netcup is the fallback VPS. Nothing is deployed yet. | AWS Lambda, Terraform, and managed-database plans are legacy. |
| Frontend hosting | Cloudflare Pages | Static delivery remains separate from the VPS services. |
| Object storage | Cloudflare R2 | Raw source payloads and archives stay out of Postgres. `R2_ENDPOINT_URL` is required so boto3 cannot silently target AWS. |
| API routing | All service routes live under `/api/*` | Caddy, frontend calls, tests, and documentation use one route convention. |
| Database changes | Alembic migrations applied deliberately during deployment | Runtime code does not create or mutate schema ad hoc. |
| Parcel identity | PIDN | No competing `parcel_id` identifier is introduced. |
| Durable owner identity | Upsert `public.owners` by `canonical_name`; expose `owner_id` through the API | `owner_id` stays stable across ordinary rebuilds while the owner remains present, while briefs and reconciliation use `canonical_name` so a cluster change is explicit. |
| Alpha experience | Prioritized evidence feed → property/project/entity case file → original source → browser-local watch loop | Homepage metrics and feature tiles do not lead the product; every surfaced case answers what happened, why, what next, who/which parcels, and why to believe it. |
| Feed priority | Deterministic SQL score with visible reasons; users may switch to chronological order | Ranking is cheap, reproducible, and independent of LLM prose or provider availability. |
| Entity route | `/api/entities/:id` and `/entity/:id` reuse stable `public.owners.owner_id` | No competing entity ID space; Pass 1 aliases/relationships are folded into the resolved owner. |
| County portability | Validated TOML manifests, county-aware prompts/evidence labels, capability-derived scheduled asset selections, county-namespaced municipal source keys, and one isolated stack/database per county | A county needs source and rights work but no product-code fork; unconfigured optional assets do not enter scheduled jobs, and loading multiple counties into the current county-local schema is prohibited. |

## Source and Data Decisions

### Scrape-free collection

Only sources whose collection and reuse posture supports the product are kept
in the production graph. Removed collection paths are not fallbacks:

- assessment portal and Tyler recorder scraping;
- PA Department of State browser scraping;
- eCode360 collection;
- Right-to-Know requests as an ingestion channel.

The replacements are the county OPEN_DATA ArcGIS services, complete parcel
field persistence, SCD2-derived `public.parcel_events`, and Pennsylvania's
statewide SODA registered-business dataset `xvd7-5r2c`.

`pa_dos_entities` treats matches as presence in the current dataset, not proof
that a business is active. It preserves the registered spelling in
`matched_name`; `entity_name` remains the parcel-owner search key.

### Parcel events

`parcels_arcgis` persists all parsed parcel attributes. Consecutive SCD2
versions produce transfer, value-change, and structure-change observations in
`public.parcel_events`. Those events describe county-record changes only;
mortgages, liens, easements, and complete title chains are out of scope.

`public.intelligence_events` is a rebuildable serving ledger that combines
parcel events, delinquency transitions, and cached development interpretations.
Rebuilding it does not invoke a model.

### York GIS reuse boundary

The current evidence supports derived commercial analytics from the county's
OPEN_DATA service: the catalog marks the service public, current metadata
documents report no access/use constraints, and the parcel metadata
contemplates cross-dataset analysis. CountyIQ does not scrape the separately
restricted Property Tax Viewer or expose a raw-source proxy, reconstructive
bulk export, or raw resale product. Written YCPC clarification remains prudent
for source-identical exports and indefinite history.

### Enforced source-rights states and scoring replacement

Migration 031 makes source posture executable rather than documentary. Each
governed source records acquisition, retention, derived-product, person-level
display, export, method, evidence, and review-date decisions in
`meta.source_rights`; every attempted acquisition writes a receipt to
`meta.source_rights_audit`. Missing, paused, method-mismatched, and overdue
policies fail closed.

The project-folder `EcoDev_Candidates_Parcels` and test-described CDBG housing
service are paused and removed from scheduled Dagster groups. Existing current
rows and their rebuildable signals are expired/deleted by the migration. Their
score contribution is replaced with OPEN_DATA business/industrial park
boundaries, development overlays, local traffic observations, soils, and
zoning constraints. PA DEP active storage-tank and land-recycling cleanup
locations add a portable statewide diligence layer. The resulting
`site_readiness_score` is presented as **site screening**, intentionally
separate from market momentum and opportunity scores; it is not an entitlement,
engineering, environmental, or official hazard determination.

PLCB, tax claims, sheriff sales, and public proceedings remain conditional:
only recorded official acquisition methods are allowed, raw archives stay
private, and raw/source-replacement exports remain out of scope. Tax claimant
search and municipality-level people rankings are removed; conditional
person-linked distress pages are default-off while aggregate and backend
parcel-level signal value remains available.

Migrations 032 through 034 close the municipal bypasses. Each board/document
source now has its own exact municipality, body, URL, proceeding type, method,
terms-review, retention, allowed-origin, and review-date policy. Authorization
occurs before listing or document access; every HTTP redirect is checked before
the destination request; browser document/API calls cannot cross to an
unreviewed vendor; robots uncertainty fails closed; health is recorded per
body; and both policy-audit tables are append-only. Rep'd, Google Drive,
GoDaddy-CDN-only, eCode360, and explicit-disallow paths remain paused rather
than being treated as ordinary public pages. County Scout is a
paused governed source, absent from schedules, and blocked at its jobs and API
until its arbitrary-URL discovery model receives a separate approval.

Independent `development_signals` and `development_momentum` runs reauthorize
only the configured sources contributing to the active county. The deterministic
screening segment uses county open data plus configured PennDOT, FEMA, and PA
DEP capabilities. Tax claims are separately audited as an optional opportunity
segment: a pause, expiry, or missing county capability suppresses
`tax_distress` without blocking the screening rebuild. Each receipt now stores
the exact policy version, canonical snapshot, and SHA-256 fingerprint, so later
policy edits cannot make an old decision irreconstructable.

On municipal pages with both reviewed first-party records and unreviewed
vendor links, the collector retains the reviewed links and records the blocked
origins as policy metadata. An unreviewed link is neither fetched nor counted
as a network error, preventing a compliant first-party archive from losing its
signal merely because the page contains an unrelated external document.

The serving boundary is enforced independently of collection. API routes must
check `derived_product_allowed`; natural-person display additionally requires
`person_level_display_allowed`. A false people-display flag does not erase
recognized legal organizations (`llc`, `corporation`, `partnership`,
`nonprofit`, or `government`), because organization identity is core B2B
signal. Exact tax rows, claimant names, licensee names, proceeding applicants,
source excerpts, and personal relationships are otherwise withheld. Product
replacements are derived flags, municipality aggregates, site-readiness
layers, organization/entity case files, and evidence-grounded scores.

## LLM Boundary

CountyIQ is intentionally hybrid.

LLMs are used for:

- extracting structured facts from unstructured municipal documents;
- resolving genuinely ambiguous entity clusters;
- validating interacting signals after deterministic shortcuts;
- generating evidence-grounded briefs for materially shortlisted cases;
- optional interactive natural-language-to-search-intent parsing.

LLMs are not used for source downloads, SCD2 diffs, parcel-event generation,
spatial joins, rankings, feed filtering, watch state, API serialization, or
templateable structured facts. Buyer-facing saved intelligence is generated
offline and served from Postgres; ordinary feed and detail requests do not call
an LLM.

Pass 2 requires at least two interpretive signals from `active_subdivision`,
`ownership_change`, `vacancy`, `assemblage`, and `zoning_mismatch`. Tax status,
economic-park membership, transportation, flood, soils, zoning overlays,
conservation/agriculture restrictions, and PA DEP proximity records remain
context-only deterministic facts. A singleton fact cannot spend a model call.

### Current model defaults

The executable source of truth is `_PASS_MODEL_DEFAULTS` in
`pipelines/countyiq/lib/pass_llm_config.py`. Environment precedence is
`COUNTYIQ_PASS{N}_MODEL`, then the code default, then
`COUNTYIQ_OPENROUTER_MODEL`.

| Use | Default | Evidence |
|---|---|---|
| Pass 0 PDF extraction | `openai/gpt-5.6-luna`, native PDF input | Historical runs covered the real PDF corpus; the 2026-08-30 audit replaced count-only checking with five human-reviewed expected matters and three zero-extraction controls. Re-run the new gold gate before any model change. |
| Pass 1 entity verification | `openai/gpt-5.6-luna`, high reasoning, adaptive N=3 voting | Strong abstention discipline; stability testing produced 97% pairwise verdict agreement. Replaying 11 archived three-trial clusters showed that stopping after an irreversible 2-0 decision saved 10 of 33 calls (30.3%) with no partition changes. |
| Pass 2 signal validation | `openai/gpt-5.6-luna`, low reasoning | Retained after a 100-case paired diagnostic reversed the initial ten-case GLM result. Luna led grounded decisions (191/263 vs 166/263), strict signals (133/263 vs 102/263), required facts (595/683 vs 573/683), and prohibited-claim control (0 vs 30 signals). |
| Pass 3 and 3b briefs | `openai/gpt-5.6-luna` | Won all eight salvageable current-prompt comparisons against MiniMax. |
| Pass 4 county narratives | Disabled by default; `openai/gpt-5.6-luna` is the opt-in provisional model | The small two-area comparison split and no alpha surface requires it. Enable only with `COUNTYIQ_PASS4_ENABLED=true` after a product/eval gate. |
| Interactive search | Disabled by default; opt-in pool is `qwen/qwen3.5-flash-02-23`, then `mistral-small-2603`, then `qwen/qwen3.5-9b` | Owner/address/PIDN lookup remains free; an API key alone cannot silently enable live inference spend. |

`z-ai/glm-5.3-flash` (FP8) remains a low-cost Pass 2 challenger, not the
preferred replacement. It led the first ten reviewed cases, but a stratified
100-case diagnostic spanning all 24 observed signal combinations favored Luna:
191/263 versus 166/263 grounded decisions, 133/263 versus 102/263 strict
signals, 595/683 versus 573/683 required fact groups, and 0 versus 30 signals
with a prohibited claim. Paired exact tests favored Luna for strict signals
(`p=0.0010`) and grounded decisions (`p=0.0015`), and Luna led all three trials
on the 20 highest-disagreement cases. The expanded labels are deterministic
rubrics derived from evidence, not yet human-confirmed promotion gold; review
them before turning this diagnostic into a regression gate. GLM's repeated
failure was unsupported actionability or causality, especially arm's-length
sale, development-intent, rezoning-pressure, and development-readiness claims.
`deepseek/deepseek-v4-flash-0731` remains the configured cost fallback, but the
earlier probe exposed unsupported certainty about plan authority and timestamp
meaning; treat it as an emergency cost lane until a frozen labeled Pass 2
corpus clears it.
`minimax/minimax-m3` is the cross-vendor fallback for Passes 1, 2, and 4.
Anthropic models are excluded from OpenRouter eval lineups by owner decision.

Model reevaluation is trigger-based, not scheduled. Run
`pipelines/eval/challenger.py` when a default is deprecated, production quality
telemetry regresses, provider pricing changes, or a materially better cheap-tier
candidate emerges. Passes 0-3 now have fingerprinted frozen evidence and
human-reviewed gold; Pass 2 also reports decision accuracy, required-fact
recall, strict signal passes, and perfect-case passes separately. The explicit
`--live` lane measures current-database drift and is not a promotion oracle.
A generic pairwise LLM judge is diagnostic only.
When a diagnostic judge is useful, the evaluated choice is `x-ai/grok-4.6`
with the strict evidence-auditor schema and ZDR routing. It matched the human
winner on all three 2026-08-30 bakeoff cases and explicitly caught the expected
unsupported claims for $0.025872. It is opt-in and does not replace labels.

## Open Decisions

| Area | Question | Status |
|---|---|---|
| Passes 1-3 promotion corpus | What immutable production-shaped contexts and acceptable outcomes cover the consequential and borderline cases? | Initial human-reviewed corpus shipped: eight Pass 1 partitions, all ten exact Pass 2 signal pairs, and four Pass 3 decisions. A separate 100-case Pass 2 rubric diagnostic now broadens all observed interaction shapes; human-confirm its labels before promotion-gate use. |
| Pass 2 voting/model | Does voting or GLM 5.3 Flash improve labeled quality enough to justify cost after deterministic shortcuts? | Luna remains N=1. The expanded paired diagnostic materially favors Luna and exposes variable unsupported GLM claims. Revisit only after adjudicating the expanded labels or testing a materially changed challenger/prompt; use post-backfill live data for drift, not promotion truth. |
| Pass 4 model | Does county-wide backfill confirm Luna or favor the MiniMax fallback? | Provisional until enough narratives exist. |
| York GIS reuse | Will YCPC confirm source-identical export and indefinite-history rights in writing? | Derived analytics supported; clarification still prudent for those edge cases. |
| Distress access | Which person-linked distress details may be distributed after legal/privacy review? | Default-off in API/frontend; aggregate and backend uses remain active. |
| Paused York layers | Will YCPC confirm reuse rights and publication intent for the project-folder ecodev and CDBG test services? | Paused until written confirmation; open-data replacements are live in the graph. |

## Accepted Tradeoffs

| Tradeoff | Reason |
|---|---|
| One VPS is a single point of failure | Current scale does not justify clustered operations. |
| Self-managed Postgres | It is substantially cheaper and keeps the stack portable. |
| Migrations are manual | Deliberate rollout is safer during rapid schema iteration. |
| Source and model archives live outside Postgres | They preserve replay and audit evidence without bloating the serving database. |
| Raw LLM transcripts expire after 90 days by default | Prompts and outputs can contain owner/parcel evidence; the harness and R2 backup path enforce the same bounded retention, with `0` reserved for an approved hold. |
| Weekly rather than instant data | Source cadence does not support instant-alert claims. |
| No email product | In-app watch state and change flags are the chosen retention mechanism. |
| ChatGPT subscription is not a runtime backend | Interactive ChatGPT/Codex use can support development and evaluation; unattended inference requires separately funded API credentials. |
| Pass 4 is opt-in | It does not drive the alpha loop, and disabling it removes recurring synthesis cost without losing feed or case-file functionality. |
