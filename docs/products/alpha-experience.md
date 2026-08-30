# CountyIQ alpha product contract

**Decision date:** 2026-08-27
**Status:** active product and architecture contract

## Product decision

CountyIQ is not a cheaper parcel database and it is not a county chatbot. Its
job is to tell a South-Central Pennsylvania investor or developer what locally
important property or development change occurred, prove it, connect the
properties and entities involved, and preserve a useful watch loop.

The shortest valuable session is:

1. See a material change the user did not already know.
2. Understand what happened, why it may matter, and what happens next.
3. Open the linked property, project, or entity case file.
4. Verify the original evidence.
5. Watch the subject and see later linked changes in one place.

The alpha is worth putting in front of an unaided user when that loop works in
under ten minutes on real, current York County evidence. Empty or thin evidence
must produce an explicit absence, not generated filler.

## Competitive boundary

Nationwide parcel search, map layers, owner portfolios, distress filters, and
saved properties are established features in [Regrid](https://regrid.com/property-app),
[PropStream](https://www.propstream.com/propstream-features),
[Crexi Intelligence](https://www.crexi.com/intelligence), and
[LandTech](https://landtech.us/product). Crexi also markets source-linked AI
research and document enrichment through [Crexi AI](https://www.crexi.com/ai).

CountyIQ therefore does not claim differentiation from any one of those
features. Its differentiated bundle is:

- municipality-level planning, zoning, and governing-body proceedings;
- chronological county and municipal changes connected to parcels and stable
  local entity IDs;
- source evidence and original documents visible beside every interpretation,
  with excerpts shown only when the recorded source policy permits them;
- an explicit “what next” field and entity/project/parcel watch loop;
- local source-coverage knowledge and provenance that a nationwide product is
  unlikely to maintain at the same depth.

If CountyIQ cannot maintain materially better local proceedings coverage and
freshness than a user can get from the municipality sites, the product loses
its reason to exist.

## Where LLMs belong

| Pass / surface | Alpha decision | Why |
|---|---|---|
| Pass 0 — municipal document extraction | **Required** | Heterogeneous PDFs and meeting language need structured extraction. Every result remains source-linked and must pass negative controls. |
| Pass 1 — ambiguous entity resolution | **Required only for ambiguous clusters** | Exact identifiers and deterministic name/address matches run first. LLM merging is valuable only when evidence is ambiguous, must support abstention, and must never invent identifiers. |
| Pass 2 — cross-signal validation | **Selective** | Run on shortlisted parcels with multiple meaningful signals, not the county universe. Geometry, thresholds, eligibility, and ranking remain deterministic. |
| Pass 3 / 3b — parcel and owner briefs | **Selective and cached** | A grounded brief helps a user synthesize a real case file. Generate only for materially signaled parcels/owners and only when the input hash changes. |
| Pass 4 — county narratives | **Off by default** | It does not power the alpha loop, has only provisional two-area evaluation evidence, and adds recurring synthesis cost. Enable explicitly with `COUNTYIQ_PASS4_ENABLED=true` only for a tested product surface. |
| Feed ranking, map layers, change detection, watch matching, filters | **No LLM** | These are auditable SQL/geometry/rules problems. The API exposes deterministic importance reasons. |
| General chatbot / unrestricted natural-language analysis | **Not in alpha** | It weakens evidence discipline, raises latency/cost, and duplicates a capability customers already have elsewhere. |

### Model decision

Luna remains the incumbent for Passes 0–3. The 2026-08-30 audit strengthened
Pass 0 into a human-reviewed frozen corpus with five expected property matters
and three negative controls, and added immutable labeled Pass 1–3 contexts.
The old names/PIDNs remain only as an explicit live-drift lane and cannot
support cross-run promotion claims by themselves.

GLM 5.3 Flash FP8 led the initial ten-case Pass 2 comparison, but a stratified
100-case diagnostic reversed the result. Luna led grounded decisions (191/263
vs 166/263), strict signals (133/263 vs 102/263), required facts (595/683 vs
573/683), and prohibited-claim control (0 vs 30 signals). Luna remains N=1.
The broader rubric labels still require human confirmation before becoming
promotion gold, while live post-backfill data should measure drift and cost
rather than define truth. DeepSeek remains configured as the cost fallback, but
manual review found unsupported certainty in its probe output.

No model is promoted on benchmark reputation, provider claims, or price alone.
`pipelines/eval/challenger.py` runs the frozen Pass 0–3 corpus by default and
requires `--live` for the mutable Pass 1/2 lane. Groundedness, false-positive
control, abstention, and human-labeled task quality—not a generic LLM judge—are
the promotion gate. The 2026-08-30 research used a funded OpenRouter credential
for tightly capped probes and recorded provider-reported cost for every call.

### ChatGPT subscription decision

A ChatGPT subscription is not an application inference credential. The
[OpenAI API quickstart](https://platform.openai.com/docs/quickstart/make-your-first-api-request)
requires an API key and API credits. Codex/ChatGPT can be used interactively for
development, review, and human-in-the-loop evaluation, but CountyIQ cannot use
this logged-in ChatGPT session as an unattended backend. Runtime choices are:

1. OpenRouter with explicit pass budgets and provider controls; or
2. a separately funded provider API.

## Cost contract

- Buyer-facing intelligence work is offline and cached; feed, map, case-file,
  and watch views never make an LLM call. Search is deterministic/fuzzy by
  default; constrained LLM intent parsing requires the explicit
  `COUNTYIQ_SEARCH_LLM_ENABLED=true` opt-in and its own budget.
- Every pass uses input hashes and skips unchanged work.
- Pass 4 is opt-in.
- Pass 2 and Pass 3 operate only on eligibility gates, not every parcel.
- The harness records OpenRouter's actual `usage.cost` and `cost_details` with
  token/provider telemetry; projections are not accepted as invoices.
- Price ceilings and zero-data-retention routing remain configurable.
- A model change must demonstrate a CountyIQ-specific quality/cost improvement
  on the frozen corpus before promotion.

## Data-rights contract

`docs/research/york-pa-dataset-register-2026-08-27.csv` and the companion
landscape review are governance inputs, not customer-facing intelligence rows.
They decide which sources may enter the pipeline and under what restrictions.

Current York `OPEN_DATA` services have a defensible path for private backend
ingestion and derived analytics. Backend-only use reduces redistribution risk;
it does not erase source terms. CountyIQ must not scrape the separately
restricted Property Tax Viewer, resell raw county compilations, expose a source
proxy API, or offer reconstructive bulk exports. Written YCPC confirmation is
prudent for source-identical exports, unusual retention, or ambiguous
non-`OPEN_DATA` sources, but it is not recorded as a categorical blocker to the
current derived alpha.

## Alpha acceptance gates

All must be true before public trial traffic is invited:

- The root page leads with current intelligence, not operations metrics or a
  feature directory.
- Feed cards expose what happened, why it matters, what happens next, related
  subjects, confidence, interpretation kind, and original evidence. A governed
  excerpt is either shown or explicitly withheld without hiding the derived
  organization/project intelligence.
- Priority ordering is deterministic and can be switched to latest.
- A related entity opens one stable case file containing aliases/verification,
  relationships when available, recent events, portfolio, and cached brief.
- A related project opens one case file containing its evidence timeline,
  connected entities, linked parcels, municipality context, and watch action.
- Entities, projects, and parcels can be watched and their later linked events
  are visible after navigation/reload in the same browser.
- Missing data and empty evidence are explicit.
- Distress/person-linked features remain off unless their separate privacy and
  counsel gates are intentionally enabled.
- API unit tests, database-backed contracts, pipeline tests, definitions import,
  frontend typecheck/lint/build, and the Playwright investigation flow pass on
  the release candidate.
- Source coverage is described honestly; a partial proceedings or scored-parcel
  corpus is not marketed as comprehensive county intelligence.

## What is not yet proven

Passing this contract produces a coherent alpha, not market fit. Market fit is
only demonstrated when target users repeatedly discover useful changes, watch
subjects, return for new evidence, and pay. The first product conversations
should happen after users can explore this loop, using observed sessions and
specific missed/valuable events instead of a broad feature pitch.
