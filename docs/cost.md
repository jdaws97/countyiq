# Cost Breakdown

CountyIQ is not deployed. Current serving spend is therefore **$0/month**; the
figures below are a planning model for the first hosted county, not a description
of a production bill.

The preferred hosting lane was selected 2026-08-02 after a verified-pricing
review: **Hetzner VPS + Cloudflare free tier + separately funded OpenRouter LLM
opex.** Full Cloudflare was disqualified
(no PostGIS path — D1 is SQLite; container disk is ephemeral so Postgres can't
live there; the Dagster daemon has no durability guarantee). Managed Postgres
(Neon/Supabase) adds $25–50/mo to offload the one component that costs ~$2/mo
of the VPS while the VPS can't shrink below 4 GB anyway (Dagster + in-process
Chromium set the floor). Hostinger was rejected: $8.79 promo requires a 2-year
prepay and renews at $14.99.

Infrastructure prices were verified 2026-08-02. OpenRouter model prices were
re-queried 2026-08-30. Hetzner raised shared-vCPU prices ~30–40% effective
2026-06-15 (existing servers keep old pricing; new orders/rescales pay the new
rates below).

## Monthly Cost

| Service | Cost | Notes |
|---|---|---|
| Hetzner CX23 + IPv4 | EUR 5.99 (~$6.50) | 2 vCPU x86, 4 GB RAM, 40 GB SSD, 20 TB traffic. IPv4 is now a separate EUR 0.50 line. |
| Cloudflare Free | $0 | CDN, DNS, Pages (static hosting free/unlimited), WAF |
| Cloudflare R2 | $0 (current scale) | 10 GB storage, 1M Class A + 10M Class B ops free; $0.015/GB/mo after. Egress always free. |
| Domain | ~$12/year (~$1/mo) | .com registration |
| **Infra subtotal** | **~$7.50/mo** | No free-tier expiration. |
| OpenRouter LLM opex | ~$38–48/mo at the prior projected workload | Mechanical current-price refresh for enabled Passes 0–3; validate with a backfill telemetry sample before budgeting. There is no charge while no provider key or jobs are running. |
| **Projected hosted total** | **~$46–56/mo** | Infrastructure subtotal plus the unverified workload model. Actual provider telemetry is the customer-pricing oracle. |

## LLM Opex (the line item the old cost model omitted)

Per-pass models are pinned in `pipelines/countyiq/lib/pass_llm_config.py`
(`_PASS_MODEL_DEFAULTS`) with the eval evidence cited inline. Steady-state
estimate at current volume (~5K Pass 2 revalidations/week, ~100 meeting
PDFs/week, ~500 brief refreshes/week):

| Line | Model | Est. monthly |
|---|---|---|
| Pass 0 — PDF extraction | gpt-5.6-luna ($0.20/$1.20 per M; $0.02/M cache read) | ~$0.70 |
| Pass 1 — entity verification | gpt-5.6-luna, effort=high, adaptive N=3 voting | ~$2.8 mechanical estimate after the archived 30.3% call reduction; verify on live clusters |
| Pass 2 — signal validation | gpt-5.6-luna, effort=low (ds-v4-flash-0731 fallback ≈ $9.15) | ~$30–40 |
| Pass 3/3b — briefs | gpt-5.6-luna | ~$4 |
| Pass 4 — county narratives | disabled by default | $0 (about $0.80 if explicitly enabled) |
| NL search (`/api/search`) | disabled by default; qwen3.5-flash when explicitly enabled | $0 by default; about $0.30 if enabled at projected use |
| Current one-time backlog | — | $39.41 modeled on the 2026-08-30 live selectors; a one-off catch-up estimate, not a fee or commitment, and a lower bound while proceedings and PA DOS are incomplete |

Passes 0–3 use the CountyIQ-evaluated Luna defaults when explicitly enabled.
No pass is scheduled or enabled by default: an API key alone does not authorize
spend. Pass 4 is outside the alpha lineup because deterministic feed ranking
plus source-backed case files provide the alpha value without paying for
county-wide prose.
The previous $19–25 estimate used Luna's old $0.10/$0.60 pricing. Luna is now
$0.20/$1.20 per million input/output tokens, so the prior workload model is
roughly $38–48/month after applying the archived adaptive Pass 1 voting proxy.
This is still a planning estimate, not a forecast: caching, actual output
lengths, the two-signal gate, and backfill eligibility can move it materially.
Luna cache reads remain 90% below uncached input ($0.02/M vs $0.20/M).
DeepSeek is cheaper but showed unsupported certainty in the 2026-08-30 probe.
GLM 5.3 Flash FP8 led Luna on the first ten reviewed Pass 2 cases, but a
stratified 100-case diagnostic reversed that result: Luna led grounded decisions
(191/263 vs 166/263), strict signals (133/263 vs 102/263), and required-fact
recall (595/683 vs 573/683), while GLM emitted prohibited claims on 30 signals
versus Luna's zero. Keep Luna. The expanded rubric labels require human review
before becoming promotion gold, but the observed unsupported-claim failure is
too material to justify a cheaper model switch.

The `$39.41` backlog number is the modeled cost to catch the currently eligible
historical rows up once. After that, ordinary spend should be incremental on
new or changed inputs because input hashes skip unchanged work. It can still
move upward before the first backfill as more proceedings, entity links, or
eligible candidates arrive, so rerun the dry estimate immediately before
authorizing paid assets.

These estimates are not an invoice. The shared harness now records the provider's
returned `usage.cost` and cost details for every completed call; aggregate that
telemetry before buying capacity or setting customer prices.
The manual eval harness additionally reserves a conservative maximum charge
before every dispatch and checkpoints each case. The complete 2026-08-30
research/eval sequence used `$0.299886735` of the user's `$1` cap, including the
100-case paired Pass 2 run and two 20-case stability repeats. One interrupted
request did not return usage; even charging its full reservation keeps the
bounded total below `$0.31`. No backfill was run.

A ChatGPT subscription does not offset this runtime line item. It can support
interactive development and evaluation, but an unattended CountyIQ job needs a
separately funded provider API credential. With no `OPENROUTER_API_KEY`, pipeline
passes do not call a provider. Public search remains on the free lookup/fuzzy
path even when a pipeline key exists unless `COUNTYIQ_SEARCH_LLM_ENABLED=true`
is also set.

Cost controls in place: paid passes are manual and opt-in, each explicit pass
run has a finite 25-item default ceiling (`COUNTYIQ_PASS{N}_MAX_ITEMS`), scheduled
enrichment is deterministic-only, per-pass evidence-backed defaults are not
shadowed by a global model variable, input-hash skip handles unchanged parcels, and a rules-first
Pass 2 gate requiring at least two interpretive signals. Deterministic tax,
park, transportation, flood, soil, zoning-overlay, conservation, and PA DEP
facts cannot trigger a model call. Measure the live reduction after backfill
rather than projecting it from fixtures. `/api/search` has a per-IP rate limit + daily LLM
budget with free-fuzzy fallback. Added 2026-08-06: every pass now sends its
static instruction block as a byte-identical system message so providers
with implicit prompt caching (OpenAI ~90% off cached input, DeepSeek,
Gemini) can reuse it across the batch; Pass 0's inline-PDF fallback pins
the `native` file-parser engine (`COUNTYIQ_PASS0_PDF_ENGINE`) so uploads
can't silently route to OCR pricing. The remaining planned reduction is
multi-parcel batching (expP: 6.8× cheaper, quality-neutral at batch=50 — still gated on
the judged sample in `docs/open-items.md`).

## Cost Traps to Avoid

- **Deprecated model slugs.** OpenRouter silently redirects retired slugs to
  successor models at the successor's price (grok-4.1-fast → grok-4.3 was a
  silent ~6× increase). Re-verify slugs whenever a pass's spend jumps.
- **OpenRouter PDF parsing fees.** Inline PDFs without a pinned `plugins`
  engine can route to OCR at ~$2/1,000 pages — ~8× the token cost of a
  typical minutes doc. Prefer `staging.public_proceedings.raw_text`. The
  harness now pins `native` by default for the Pass 0 fallback
  (`COUNTYIQ_PASS0_PDF_ENGINE`); only override to `mistral-ocr` knowingly.
- **Hetzner snapshots:** $0.012/GB/mo if enabled. Use `pg_dump` + R2 instead.
- **R2 Class A operations (PUT/POST):** $4.50/million past the free 1M. Pipeline writes are <10K/week.
- **Domain auto-renewal:** set a calendar reminder. Losing a domain is the one cost trap that actually hurts.

## When to Upgrade

| Trigger | Action | New Cost |
|---|---|---|
| Memory > 80% sustained | CX23 → CX33 (4 vCPU, 8 GB, 80 GB) | EUR 8.99/mo w/ IPv4 (~$9.80) |
| Disk > 80% | Add Hetzner volume | EUR 0.044/GB/mo |
| R2 > 10 GB | Pay-as-you-go | +$0.15–0.75/mo |
| 3 counties | CX33 is the initial capacity hypothesis (~45 GB fits 80 GB); keep a separate database/stack identity per county and load-test before committing | ~$11–14/mo infrastructure only |

Resize is a ~2-minute console action, no architecture change. Fallback
provider if Hetzner hikes again: Netcup VPS 1000 G12 (4 vCPU/8 GB/256 GB,
~EUR 8.71/mo, 12-month term) — comparable price, 3× the disk, less flexible.
ARM (CAX line) is no longer cheaper than x86 post-hike; ignore it.
