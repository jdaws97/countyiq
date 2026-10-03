# Decision Log

This file records decisions that define the current repository. Experiment
transcripts and superseded choices belong in git history or the gitignored
`pipelines/eval/results/` directory.

## Product and Architecture

| Area                              | Current decision                                                                                                                                                                                                                                                                                                                                                                                            | Consequence                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Product lane                      | Real-estate intelligence for investors and developers in South-Central PA, starting with York County                                                                                                                                                                                                                                                                                                        | Surfaces must serve an investor or developer job; the earlier civic and government product framing is retired.                                                                                                                                                                                                                                                                                                                                                                   |
| Repository                        | One modular monorepo                                                                                                                                                                                                                                                                                                                                                                                        | Frontend, API, pipelines, migrations, deployment, and current docs change together, while executable import/credential/network contracts prevent runtime coupling and preserve later extraction seams.                                                                                                                                                                                                                                                                           |
| Runtime                           | React/Vite, FastAPI/Uvicorn, Dagster, PostgreSQL 16/PostGIS                                                                                                                                                                                                                                                                                                                                                 | These are the only active application paths.                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| Deployment target                 | Docker Compose on the existing VPS behind Cloudflare; pipelines execute explicitly on the operator PC                                                                                                                                                                                                                                                                                                       | The VPS runs PostgreSQL, API, Caddy, and cloudflared. A separate one-shot image handles Alembic.                                                                                                                                                                                                                                                                                                                                                                                 |
| Frontend hosting                  | Caddy on the VPS, behind Cloudflare Tunnel                                                                                                                                                                                                                                                                                                                                                                  | Marketing and the protected product use separate hostnames and HTML entries.                                                                                                                                                                                                                                                                                                                                                                                                     |
| Object storage                    | Cloudflare R2                                                                                                                                                                                                                                                                                                                                                                                               | Raw source payloads and archives stay out of Postgres. `R2_ENDPOINT_URL` is required so boto3 cannot silently target AWS.                                                                                                                                                                                                                                                                                                                                                        |
| API routing                       | All service routes live under `/api/*`                                                                                                                                                                                                                                                                                                                                                                      | Caddy, frontend calls, tests, and documentation use one route convention.                                                                                                                                                                                                                                                                                                                                                                                                        |
| Database changes                  | Alembic migrations run only through the quiesced deployment path                                                                                                                                                                                                                                                                                                                                            | Runtime code does not mutate schema ad hoc. A started migration failure leaves application services stopped; downgrade safety is reviewed per revision.                                                                                                                                                                                                                                                                                                                          |
| Release identity                  | Exact reviewed Git SHA, SHA-tagged local images, fixed Compose/volume identity, and immutable release receipts                                                                                                                                                                                                                                                                                              | Moving branch tips, dirty worktrees, implicit directory project names, and blind backward deploys fail closed. On-host builds are repeatable operations, not registry-backed artifact promotion.                                                                                                                                                                                                                                                                                 |
| Backup completion                 | Unique immutable R2 objects plus checksums and a manifest uploaded/read back last; recent disposable restore receipt required before ordinary deploy                                                                                                                                                                                                                                                        | A partial upload is not a backup. Dagster cannot receive the distinct backup-bucket credential, the host has no scripted remote-delete path, R2 bucket lock/lifecycle own retention, and recovery never restores over the only live database.                                                                                                                                                                                                                                    |
| Operational health                | The local runner synchronously publishes job and per-source receipts to `meta.job_run_status` and `meta.asset_refresh_status`, including failed or incomplete checks                                                                                                                                                                                                                                        | The API combines receipts, current rows, and freshness windows. Full Dagster SQLite history stays on the PC; no daemon or sensor is required.                                                                                                                                                                                                                                                                                                                                    |
| Intelligence integrity operations | Model proposals are append-versioned; same-evidence semantic flips are quarantined; aggregate health is public but adjudication is a writer-only pipeline CLI                                                                                                                                                                                                                                               | A human resolution appends a human-origin accepted version and updates/retracts the serving projection atomically. Pre-gate rows are archived as `legacy_unverified` and retracted rather than silently grandfathered.                                                                                                                                                                                                                                                           |
| Human in the loop (2026-09-02)    | Intelligence does the volume; people set policy and audit samples. Routine same-evidence flips are resolved by a recorded rule policy (newer version wins; same-version noise keeps the incumbent), optionally confirmed by a judge model. Only consequential flips (person ↔ organization merges, approved ↔ denied, high ↔ non-actionable, pursue ↔ pass) and rule/judge disagreements wait for a person. | `meta.intelligence_auto_resolutions` records every assessment; `meta.intelligence_review_queue` is the human queue. The one-time Pass 2 label receipt is replaced after the first accepted run by the live gate pass rate. Weekly sampled audits (`sample` / `approve` / `reject`) feed gold candidates to the eval corpus instead of a separate labelling task. Person/organization merge questions are reviewed as a batch after the first Pass 1 backfill, not one at a time. |
| Paid-pass spend                   | Every enabled pass requires finite item, per-run dollar, and provider per-token price ceilings                                                                                                                                                                                                                                                                                                              | The runtime reserves a conservative maximum before each work item and stops when `usage.cost` is missing or would exceed the signed envelope.                                                                                                                                                                                                                                                                                                                                    |
| Parcel identity                   | PIDN                                                                                                                                                                                                                                                                                                                                                                                                        | No competing `parcel_id` identifier is introduced.                                                                                                                                                                                                                                                                                                                                                                                                                               |
| Durable owner identity            | Upsert `public.owners` by `canonical_name`; expose `owner_id` through the API                                                                                                                                                                                                                                                                                                                               | `owner_id` stays stable across ordinary rebuilds while the owner remains present, while briefs and reconciliation use `canonical_name` so a cluster change is explicit.                                                                                                                                                                                                                                                                                                          |
| Alpha experience                  | Prioritized evidence feed → property/project/entity case file → original source → browser-local watch loop                                                                                                                                                                                                                                                                                                  | Homepage metrics and feature tiles do not lead the product; every surfaced case answers what happened, why, what next, who/which parcels, and why to believe it.                                                                                                                                                                                                                                                                                                                 |
| Feed priority                     | Deterministic SQL score with visible reasons; users may switch to chronological order                                                                                                                                                                                                                                                                                                                       | Ranking is cheap, reproducible, and independent of LLM prose or provider availability.                                                                                                                                                                                                                                                                                                                                                                                           |
| Entity route                      | `/api/entities/:id` and `/entity/:id` reuse stable `public.owners.owner_id`                                                                                                                                                                                                                                                                                                                                 | No competing entity ID space; Pass 1 aliases/relationships are folded into the resolved owner.                                                                                                                                                                                                                                                                                                                                                                                   |
| County portability                | Validated TOML manifests, county-aware prompts/evidence labels, capability-derived asset selections, county-namespaced municipal source keys, and one isolated stack/database per county                                                                                                                                                                                                                    | A county needs source and rights work but no product-code fork; unconfigured optional assets do not enter refresh jobs, and loading multiple counties into the current county-local schema is prohibited.                                                                                                                                                                                                                                                                        |

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
eCode360, and explicit-disallow paths remain paused rather
than being treated as ordinary public pages. Revision 045 retires County
Scout; new sources enter through explicit county manifests and reviewed
source-policy migrations rather than arbitrary-URL discovery.

Revision 042 records a deliberate product-owner exception for the official
Franklintown Borough, Newberry Township, and Washington Township listing pages.
Their GoDaddy Website Services terms remain reviewed and risk-accepted rather
than being represented as unrestricted. Collection is limited to the official
listing URLs and exact `https://img1.wsimg.com` PDF origin. Derived proceedings
intelligence and private raw retention were enabled; person-level display and
raw-document export were disabled at that revision. Revision 054 later removed
the person-display switch while leaving raw export disabled.

Revision 043 records the narrower transport exception needed to execute that
decision: the three first-party GoDaddy listing origins returned TLS EOF/timeouts
to the direct client and their `robots.txt` endpoints also timed out in Chromium,
while the official listing pages remained reachable. Browser listing access is
therefore allowed only for those policy rows when robots is unavailable. An
explicit disallow still blocks access, and the separate `img1.wsimg.com` PDF
origin must pass its live robots policy on every run.

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
check `derived_product_allowed`. Owner names, previous owners, proceeding
applicants, and verified excerpts are public record and served under that
permission (see "Owner names are public record"). Exact tax-claim rows stay
behind the separate restricted-distress setting; municipality aggregates,
boolean delinquency, and evidence-grounded scores carry that signal instead.

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
templateable structured facts. As of radar score version 7 (2026-09-02) they
are also not used for scoring: Pass 2 validation status and significance no
longer multiply signal weights. They are stored and displayed as annotations
(reasoning, status, cross-signal insight) beside a score any reader can
recompute from the signal table. Buyer-facing saved intelligence is generated
offline and served from Postgres; ordinary feed and detail requests do not call
an LLM.

Pass 2 requires at least two interpretive signals from `active_subdivision`,
`municipal_action`, `ownership_change`, `vacancy`, `assemblage`,
`entity_assemblage`, and `zoning_mismatch`. Tax status, economic-park
membership, nearby plans, transportation, flood, soils, zoning overlays,
conservation-easement restrictions, agricultural-area context, and PA DEP proximity records remain
context-only deterministic facts. A singleton fact cannot spend a model call.
Pass 0 additionally skips documents with no land-use vocabulary before any
call and records an explicit `_no_landuse_terms` marker. Pass 3 briefs are
generated only for the top-N radar parcels (`COUNTYIQ_PASS3_RANK_LIMIT`), so
the deterministic rank, not the model's own significance label, decides where
synthesis money is spent.

### Radar score version 6 (2026-09-02)

The 2026-09-02 product review found four defects in the version-5 radar:
the LLM multipliers ranked every validated parcel below unvalidated ones;
the product's own proceedings never fed the score; `active_subdivision` gave
any parcel within 250 m the neighbour's plan and label; and a stateless
weekly `TRUNCATE` made "what changed" impossible. Version 6 therefore:

- scores deterministically from `public.development_signals` only;
- adds `municipal_action` (Pass 0 matters linked by PIDN or normalized
  address), `entity_assemblage` (one owner accumulating contiguous parcels
  with a recent acquisition), and `nearby_subdivision` (corridor activity,
  separated from the parcel's own plan);
- decays `ownership_change` and `municipal_action` by age and fixes the
  substring "LP"/"INC" investor-buyer bug with word boundaries;
- calibrates opportunity weights with `pipelines/scripts/backtest_radar_weights.py`
  against believable plans received on the parcel in the last 24 months
  (report: `docs/research/radar-backtest-2026-09-02.md`: 131,701 eligible
  parcels, 496 positives; AUC 0.73 for the rounded v6 weights versus 0.62 for
  the v5 weights, precision@250 7.6% versus 3.2% against a 0.38% base rate),
  while momentum keeps activity weights;
- appends every rebuild to `public.development_momentum_history` and exposes
  movers (`/api/radar/movers`, the Radar "Movers" tab, municipality pages).

Re-run the back-test and update `OPPORTUNITY_WEIGHTS` in one commit with the
regenerated report after the first live proceedings backfill, when
`municipal_action` has enough rows to calibrate instead of carrying a prior.

### Radar score version 7 (2026-09-02)

Version 7 preserves version 6's deterministic and back-tested opportunity
weights while correcting the evidence contract uncovered in a property-page
audit:

- Agricultural Security Area enrollment is neutral planning context, not an
  eligibility exclusion. Pennsylvania's official guidance says enrollment
  does not itself prevent sale, subdivision, or development. Agricultural
  conservation easements remain the sole hard radar exclusion.
- Soil screening uses every materially overlapping mapped unit rather than the
  parcel centroid. The property API reports parcel share, slope range and
  representative slope, drainage, hydrologic group, hydric rating, and on-lot
  septic rating. The signal headline names the field that actually triggered
  it, so a steep well-drained unit is not mislabeled as a drainage problem.
- FEMA Special Flood Hazard Area screening uses parcel overlap and reports the
  overlap percentage rather than claiming the entire parcel is in a zone from
  a center-point match.
- Non-completed PennDOT projects remain eligible for the proximity signal;
  completed project points do not add current momentum or site points.
- Every serialized signal carries explicit Momentum, Opportunity, and Site
  Screening point effects plus its eligibility effect. Public tax signals
  suppress claim amounts and history regardless of person-display policy.
- Signal labels distinguish evidence from inference: organization-looking
  names are not called investors, same-name contiguous parcels are not called
  active assemblage, missing footprints are not called proven vacancy, and
  nearby DEP records are not called contamination.

The complete trigger/meaning/caveat matrix is maintained in
`docs/research/development-signal-contract-v7.md`.

### Investor-scenario gaps closed (2026-09-03)

Walking concrete investor jobs ("a mall is going in, find the parcel next
door", "what is this township up to", "who is assembling along this road")
against the code found four gaps that were deterministic, not model, work:

- **Proximity**: `/api/parcels/near` and the feed's `near_pidns` filter give
  the corridor view around a parcel, a project, or a watched parcel. No radar
  filter or map mode could answer "what is within 800 m of this plan".
- **Zoning on the report**: the property page now shows the current district
  from the county zoning layer, not only the plan/zoning divergence signal.
  The county layer keeps a superseded district polygon alongside a rezoning
  (7 parcels on 2026-09-03; 54000HJ012400 was CI until a 2026-06 ordinance
  made it RL), so both the report and `zoning_mismatch` now take the newest
  adopted district rather than an arbitrary intersecting polygon.
- **Municipality-wide policy actions**: Pass 0 gained `ordinance_action`
  (ordinance text or map amendments, comprehensive plan actions, Act 537 and
  sewer/water capacity decisions, moratoria, LERTA/KOZ/TIF designations). They
  carry a `policy_action` tag, filter in the feed, and list on the municipality
  page. This changes the Pass 0 schema and prompt; rerun the frozen Pass 0
  eval before the backfill.
- **Resolved-owner assemblage**: `assemblage` and `entity_assemblage` compare
  resolved owner identity (deterministic name-variant merging plus Pass 1
  merges) with the raw name as fallback, so a person assembling under
  "SMITH JOHN" and "SMITH JOHN A" is one owner. Pass 2 and Pass 3 read the
  same resolved variants to supply an owner portfolio for the 87% of parcels
  with no verified entity. Both change Pass 2 input hashes, which is why they
  landed before the backfill.

### Owner names are public record (2026-09-03)

Product decision: CountyIQ shows parcel owner names, previous owners, mailing
addresses, proceeding applicants, and verified excerpts for every parcel.
County assessment and meeting records are public, and an investor deciding
whether to approach the owner next to a new plan needs the name, not
"individual owner".

- The per-source `person_level_display_allowed` switch is removed (migration 054) rather than flipped, so no route can silently withhold identity again.
  `derived_product_allowed` is the single serving gate.
- The person-safety gate drafted earlier the same day (prompt rules against
  naming people, `person_safe` columns, organization-only owner briefs) was
  withdrawn before it shipped. Pass 2, 3, and 3b prompts may name the owner,
  and owner briefs are generated for any owner with three or more
  signal-bearing parcels.
- Exact tax-claim balances stay behind `COUNTYIQ_ENABLE_RESTRICTED_DISTRESS`
  because that is debt detail rather than identity; the boolean delinquency
  flag remains public.
- Person-only Pass 1 clusters are included by default. A 20-cluster live audit
  found deterministic normalization covered only 1.6% of unresolved clusters;
  Luna recovered 8/10 positive pairs with no false merge in the sample. Set
  `COUNTYIQ_PASS1_INCLUDE_PERSON_CLUSTERS=false` only to accept lower recall.

### Current model defaults

The executable source of truth is `_PASS_MODEL_DEFAULTS` in
`pipelines/countyiq/lib/pass_llm_config.py`. Environment precedence is
`COUNTYIQ_PASS{N}_MODEL`, then the code default, then
`COUNTYIQ_OPENROUTER_MODEL`.

| Use                                    | Default                                                                                                                                                                                                                                                 | Evidence                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Pass 0 PDF extraction                  | `openai/gpt-5.6-luna`, native PDF input                                                                                                                                                                                                                 | Historical runs covered the real PDF corpus; the 2026-08-30 audit replaced count-only checking with five human-reviewed expected matters and three zero-extraction controls. Re-run the new gold gate before any model change. Re-run 2026-09-03 after the `ordinance_action` schema/prompt change: 5/6 gold, 5/5 records matched, 0 extra extractions ($0.011); the only miss is the known unreadable Dillsburg PDF (quote gate).                                                                                                                                                                                                                                                                                   |
| Pass 1 entity verification             | `openai/gpt-5.6-luna`, high reasoning, adaptive N=3 voting; person and organization clusters included, registered-agent hub addresses excluded                                                                                                          | Strong abstention discipline; stability testing produced 97% pairwise verdict agreement. A 2026-09-04 live person-only audit found deterministic variants covered only 82 of roughly 5,072 unresolved clusters (1.6%); Luna recovered 8/10 positive pairs with 100% sampled pair precision and 80% recall. Person clusters therefore default on; operators may explicitly disable them to accept lower identity recall. GLM 5.3 Flash remains a canary challenger based on the 2026-09-02 frozen/live comparison (`docs/research/llm-cost-reduction-2026-09-02.md` sections 10–11); change the code default only after its live gate rate and sampled audit hold.                                                    |
| Citation gate granularity (2026-09-02) | `[Evidence:]`/`[Signal:]`/`[Parcel:]` markers are required per reasoning field, not per sentence; identifier, membership, quote, and unknown-marker checks are unchanged                                                                                | The per-sentence rule rejected 6/8 correct Luna Pass 1 partitions and 6–9/10 Luna Pass 2 validations on the frozen corpora because models write one uncited lead sentence before the cited one; production writes a rejection without retry, so the spend was lost. Prompts still ask for a marker on every factual sentence. The Pass 0 quote check also accepts a whitespace-free match because PDF extraction splits tokens at line breaks.                                                                                                                                                                                                                                                                       |
| Cached prompt prefix (2026-09-02)      | Every pass system prompt carries static schema, field-contract, and citation-format blocks and must stay at or above 4,600 characters (`tests/test_prompt_cache_prefix.py`); prefix blocks may restate format and contract only, never signal semantics | OpenAI caches only identical prefixes of at least 1,024 tokens; the bare instruction blocks were 487–838 tokens and every audited call reported `cached_tokens: 0`. After the change the live Pass 0 canary reported cached tokens on 24 of 25 Luna calls. A trial signal glossary ("trigger / means / does not establish") shifted Luna's Pass 2 statuses from downgraded to confirmed on the reviewed gold cases and was removed.                                                                                                                                                                                                                                                                                  |
| Pass 2 signal validation               | `openai/gpt-5.6-luna`, low reasoning; evidence contract v6                                                                                                                                                                                              | The 2026-09-03 recall comparison was invalid: 15/100 cases could contain an unlabeled `entity_assemblage` signal and the rubric still expected obsolete evidence fields. The 2026-09-04 corpus covers all six production signals, 46 observed combinations, and enforces exact selected/context/label key equality. All 20 release-subset cases were re-reviewed against rubric v5. Archived-output rescoring plus four targeted reruns produced 59/59 grounded decisions, 0 prohibited claims, and 20/20 production gates; the targeted four had 31/34 required facts. A final current-prompt case reached 8/8 facts after the reviewed phrasing correction. See `docs/research/pass2-rubric-review-2026-09-04.md`. |
| Pass 3 and 3b briefs                   | `openai/gpt-5.6-luna`                                                                                                                                                                                                                                   | Won all eight salvageable current-prompt comparisons against MiniMax. Re-run 2026-09-03: 1/4 gold; p3-004 flipped on the recommendation check only, p3-002 and p3-003 fail exactly as before (N=4).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| Pass 4 county narratives               | Disabled by default; `openai/gpt-5.6-luna` is the opt-in provisional model                                                                                                                                                                              | The small two-area comparison split and no alpha surface requires it. Enable only with `COUNTYIQ_PASS4_ENABLED=true` after a product/eval gate.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| Interactive search                     | Disabled by default; opt-in pool is `qwen/qwen3.5-flash-02-23`, then `mistral-small-2603`, then `qwen/qwen3.5-9b`                                                                                                                                       | Owner/address/PIDN lookup remains free; an API key alone cannot silently enable live inference spend.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |

`z-ai/glm-5.3-flash` (FP8) remains a low-cost Pass 2 challenger, not the
preferred replacement. The historical 100-case diagnostic favored Luna on
grounded decisions and prohibited-claim control, but the 2026-09-04 audit found
that corpus omitted one production signal from its stratification and retained
obsolete required-fact fields. Treat its exact strict/fact totals as historical
diagnostics, not a current promotion gate. Luna remains the default because the
corrected prompt cleared all 59 reviewed-subset decisions with no prohibited
claim; rerun a challenger only when a model or price change justifies the paid
comparison. GLM's historical failure mode was unsupported actionability or
causality, especially arm's-length sale, development-intent,
rezoning-pressure, and development-readiness claims. The other 80 current
expanded cases remain generated diagnostic labels rather than promotion gold.
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

| Area                        | Question                                                                                                        | Status                                                                                                                                                                                                                                                                                  |
| --------------------------- | --------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Passes 1-3 promotion corpus | What immutable production-shaped contexts and acceptable outcomes cover the consequential and borderline cases? | Initial human-reviewed corpus shipped: eight Pass 1 partitions, all ten exact Pass 2 signal pairs, and four Pass 3 decisions. A separate 100-case Pass 2 rubric diagnostic now broadens all observed interaction shapes; human-confirm its labels before promotion-gate use.            |
| Pass 2 voting/model         | Does voting or GLM 5.3 Flash improve labeled quality enough to justify cost after deterministic shortcuts?      | Luna remains N=1. The expanded paired diagnostic materially favors Luna and exposes variable unsupported GLM claims. Revisit only after adjudicating the expanded labels or testing a materially changed challenger/prompt; use post-backfill live data for drift, not promotion truth. |
| Pass 4 model                | Does county-wide backfill confirm Luna or favor the MiniMax fallback?                                           | Provisional until enough narratives exist.                                                                                                                                                                                                                                              |
| York GIS reuse              | Will YCPC confirm source-identical export and indefinite-history rights in writing?                             | Derived analytics supported; clarification still prudent for those edge cases.                                                                                                                                                                                                          |
| Distress access             | Which person-linked distress details may be distributed after legal/privacy review?                             | Default-off in API/frontend; aggregate and backend uses remain active.                                                                                                                                                                                                                  |
| Paused York layers          | Will YCPC confirm reuse rights and publication intent for the project-folder ecodev and CDBG test services?     | Paused until written confirmation; open-data replacements are live in the graph.                                                                                                                                                                                                        |

## Accepted Tradeoffs

| Tradeoff                                            | Reason                                                                                                                                                            |
| --------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| One VPS is a single point of failure                | Current scale does not justify clustered operations.                                                                                                              |
| Self-managed Postgres                               | It is substantially cheaper and keeps the stack portable.                                                                                                         |
| Migrations are manual                               | Deliberate rollout is safer during rapid schema iteration.                                                                                                        |
| Source and model archives live outside Postgres     | They preserve replay and audit evidence without bloating the serving database.                                                                                    |
| Raw LLM transcripts expire after 90 days by default | Prompts and outputs can contain owner/parcel evidence; the harness and R2 backup path enforce the same bounded retention, with `0` reserved for an approved hold. |
| Weekly rather than instant data                     | Source cadence does not support instant-alert claims.                                                                                                             |
| No email product                                    | In-app watch state and change flags are the chosen retention mechanism.                                                                                           |
| ChatGPT subscription is not a runtime backend       | Interactive ChatGPT/Codex use can support development and evaluation; unattended inference requires separately funded API credentials.                            |
| Pass 4 is opt-in                                    | It does not drive the alpha loop, and disabling it removes recurring synthesis cost without losing feed or case-file functionality.                               |
