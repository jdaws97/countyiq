# LLM cost reduction and value audit — 2026-09-02

Goal: keep the CountyIQ intelligence outcomes (Pass 0 extraction, Pass 1
entity partitions, Pass 2 signal validation, Pass 3 briefs) while cutting the
first York backfill and the recurring spend, using public benchmarks
correlated with OpenRouter prices plus targeted evals on the frozen corpora.

Everything below was measured against the local database snapshot
(175,928 parcels, 6,692 proceedings, no prior inference rows) and the frozen
eval fixtures. Total provider-reported eval spend for this audit was
**$0.2097** (see `pipelines/eval/results/*20260902T*`).

## 1. Where the money goes today

Read-only estimator, Luna defaults, no cache (`scripts/estimate_llm_backfill.py`):

| Pass | Units | Planning calls | Planning cost | Notes |
|---|---:|---:|---:|---|
| 0 | 5,484 docs | 5,484 | $9.97 | 4,648 text inputs, 836 PDF fallbacks, 963 prefilter skips |
| 1 | 6,110 clusters | 12,776 | $21.14 | adaptive N=3 voting, effort=high |
| 2 | 5,548 parcels | 5,548 | $6.45 | two-signal gate, N=1, effort=low |
| 3 / 3b | 0 until Pass 2 exists | — | ~$2–4 expected | rank-limited to 500 |
| **Total** | | 23,808 | **$37.57** | retry ceiling $1,022 |

Measured Luna Pass 1 calls today cost $0.0013–0.0020 each; output tokens
(reasoning included) are roughly 85–90% of that cost. Input price and prompt
caching therefore matter far less than output price and reasoning length.

## 2. Findings that change the plan before any model swap

### 2a. The per-sentence citation gate rejects most current outputs (blocking)

`validate_entity_membership`, `validate_pass2_evidence_refs`,
`validate_parcel_brief_citations`, and `validate_owner_brief_citations` all
require an `[Evidence: …]` marker in **every sentence** of every reasoning
field. This contract and the matching prompt text were added after the last
commit and had never been run against live model output. Measured today with
the current production prompts:

| Pass | Model | Substantive result | Production gate |
|---|---|---|---|
| 1 | Luna high | 6/8 correct partitions, 0 fabrications | 2/8 accepted |
| 1 | Luna low | 6/8 | 1/8 |
| 1 | GLM 5.3 Flash | 8/8 | 1/8 |
| 2 | Luna low (incumbent, 4 runs) | 14–16/20 decisions | 1–4/10 accepted |
| 3 | every model tried | required facts 4/4 for GLM, Solar | 0–1/4 accepted |

The failing sentences are ordinary ("This exact candidate name appears as the
owner of parcel P1D002.") followed by a correctly cited sentence carrying all
the markers. Production does not retry with feedback: the cluster or parcel is
written to the rejection ledger and the spend is lost. Left as-is, the first
backfill would pay full price and serve almost nothing.

Recommended fix (deterministic, no quality loss):

1. Gate: require at least one valid marker per reasoning field, no unknown
   markers, every `cross_reference` used somewhere in the reasoning, and keep
   every identifier/membership/quote check unchanged.
2. Prompt: "End every sentence with its `[Evidence: …]` marker" as an explicit
   format rule, so models that comply reduce review noise.
3. Optional: one repair retry that feeds the gate errors back before rejecting.

Also observed: the Pass 0 quote gate rejects one Westman ZHB extraction for
every model because the model's `supporting_text` differs from the extracted
text only by whitespace/line breaks; normalize whitespace before the
substring check.

### 2b. Eval harness bug fixed today (worktree change)

The frozen Pass 1 lane passed partition record IDs (`P1A001`) as the cluster
names and omitted `candidate_names` from the prompt, so no candidate refs were
printed and every model failed the membership gate for reasons unrelated to
quality. `eval/challenger.py` now derives candidate names from the frozen
context's owner-name fields and injects them into the prompt copy; the hashed
context is untouched. `eval/protocol.py` gained price ceilings for the eight
candidates below.

### 2c. Prompt caching is not engaging

OpenAI caches only prompts whose identical prefix is at least 1,024 tokens.
The static system prompts are 487–838 tokens, and the user message starts
with per-item data, so every call today reported `cached_tokens: 0`. Moving
the output schema and static rules into the system message (pushing the
static prefix past ~1,100 tokens) would bill that prefix at $0.02/M instead
of $0.20/M on Luna. Worth roughly $3–4 on the Luna backfill and ~10% of Luna
recurring input cost; smaller with cheaper models. Do it before the backfill
because it changes `PROMPT_VERSION`.

## 3. Scope levers (largest savings, no model change)

### 3a. Pass 1 spends 83% of its budget on person-name clusters with no served value

| Cluster set | Clusters | Luna cost (adaptive N=3) |
|---|---:|---:|
| Current: all clusters | 6,110 | $21.12 |
| Person-only clusters | 5,078 | $17.47 |
| Clusters containing at least one organization | 1,032 | $3.67 |
| Same, with 14 registered-agent hub addresses excluded | 1,073 | $3.87 |

Person-level display is off by policy, and the `entity_assemblage` radar signal
matches on raw `owner_full`, not the merged owner, so person merges reach no
customer surface today. Gate Pass 1 to clusters with at least one organization
(or with a PA DOS / PLCB / proceedings record) until a surface needs person
merges. Separately, 14 office addresses shared by 10–51 entities (registered
agents in Harrisburg and Erie) generate 3,673 candidate pairs and 28 clusters
of 10+ names; exclude hub addresses from the shared-address join.

### 3b. Pass 0 recency

Only 1,611 of 5,484 eligible documents are dated within 730 days. A
recency-first backfill costs $2.93 at Luna prices (under $1 with the models
below); older minutes mainly serve the radar back-test and can follow later.

## 4. Model evidence

### 4a. Public benchmarks vs OpenRouter price (2026-09-02)

| Model | AA Intelligence Index | OpenRouter $/M in / out | Notes |
|---|---:|---|---|
| GLM-5.3-Flash | 57 | 0.075 / 0.25 (promo route; normal 0.15 / 0.50) | open weight, verbose, 42 t/s |
| DeepSeek V4 Flash 0731 | 52 | 0.065 / 0.18 | long reasoning traces, slow |
| GPT-5.6 Luna (max / high / medium) | 52 / 47 / 39 | 0.20 / 1.20 | incumbent; `:batch` variant 0.10 / 0.60 |
| Gemini 3.5 Flash-Lite | 37 | 0.30 / 2.50 | not competitive on price |
| gpt-oss-120b | 24 | 0.037 / 0.17 | very long reasoning |
| GPT-5 nano | 20 | 0.05 / 0.40 | not tested |
| Solar Pro 4 | not indexed | 0.03 / 0.12 | cheapest candidate |
| Gemini 2.5 Flash-Lite | not indexed | 0.10 / 0.40 | fastest; accepts PDFs |
| Qwen3.5 Flash | not indexed | 0.065 / 0.26 | failed both tasks below |

Sources: Artificial Analysis leaderboard and model pages, BenchLM's mirror of
the index dated 2026-09-02, llm-stats, and the OpenRouter `/models` listing.
Benchmark rank did not predict task fit (GLM led the index and the Pass 1/2
gold sets, yet emitted 30 prohibited claims on the 100-case Pass 2 diagnostic
on 2026-08-30), so the frozen evals remain the promotion oracle.

### 4b. Pass 0, text mode (6 frozen PDFs; production sends text for 85% of docs)

| Model | Records matched | Extra | Cost / 5 docs | Avg s |
|---|---:|---:|---:|---:|
| Solar Pro 4 | 4/4 | 0 | $0.0006 | 5.4 |
| Qwen3.5 Flash | 0/4 | 0 | $0.0008 | 2.0 |
| DeepSeek V4 Flash 0731 | 4/4 | 0 | $0.0015 | 12.7 |
| Gemini 2.5 Flash-Lite | 4/4 | 0 | $0.0019 | 1.5 |
| gpt-oss-120b | 4/4 | 0 | $0.0021 | 33.5 |
| Qwen3.8 Flash | 4/4 | 0 | $0.0054 | 18.2 |
| Luna (incumbent) | 4/4 | 0 | $0.0055 | 3.9 |
| GLM 5.3 Flash | 4/4 | 0 | $0.0061 | 28.4 |

Every model except Qwen3.5 Flash matched the same records with zero extras and
the same single whitespace-quote gate failure. Gemini 2.5 Flash-Lite also
accepts native PDF input, so it can cover the 836 PDF-fallback documents that
text-only models cannot. Corpus is tiny; confirm on a 25-document canary.

### 4c. Pass 1, frozen gold (8 de-identified partition cases, N=1)

| Model | Correct partitions | Fabrications | Cost / 8 | Avg s |
|---|---:|---:|---:|---:|
| GLM 5.3 Flash | 8/8 | 0 | $0.0037 | 57 |
| Solar Pro 4 | 7/8 | 0 | $0.0036 | 39 |
| Luna high (incumbent) | 6/8 | 0 | $0.0158 | 14 |
| Luna low | 6/8 | 0 | $0.0104 | 8 |
| DeepSeek V4 Flash 0731 | 6/8 | 0 | $0.0061 | 79 |
| gpt-oss-120b | 6/8 | 0 | $0.0067 | 94 |
| Gemini 2.5 Flash-Lite | 6/8 | 0 | $0.0042 | 3 |
| Qwen3.8 Flash | 5/7 | 0 | $0.0287 | 120 |
| Qwen3.5 Flash | 4/8 | 0 | $0.0004 | 4 |

Luna low matched Luna high case-for-case at two-thirds the cost. GLM solved the
two cases (same-couple alias merge, household alias with conflicting co-owner)
that every Luna configuration missed, at 23% of Luna high's cost, so three GLM
voting trials cost less than one Luna call.

### 4d. Pass 2, 10 reviewed gold cases (challenger vs Luna-low incumbent in the same run)

| Model | Grounded decisions | Status | Forbidden claims | Fact groups | Cost / 10 |
|---|---:|---:|---:|---:|---:|
| GLM 5.3 Flash | 17/20 | 19 | 0 | 40/48 | $0.0045 |
| Luna low (same run) | 15/20 | 16 | 0 | 33/48 | $0.0076 |
| Solar Pro 4 | 13/20 | 14 | 0 | 35/38 | $0.0062 |
| gpt-oss-120b | 11/20 | 13 | 1 | 39/48 | $0.0017 |
| Gemini 2.5 Flash-Lite | 10/20 | 13 | 1 | 36/43 | $0.0056 |
| DeepSeek V4 Flash 0731 | 10/20 | 12 | 0 | 39/48 | $0.0057 |

Luna's own incumbent score moved between 14 and 16 decisions across the four
paired runs, which is as large as the gap to GLM. The 2026-08-30 100-case
diagnostic (Luna 191 vs GLM 166 grounded decisions, 0 vs 30 prohibited claims)
remains the deciding evidence for Pass 2; keep Luna there unless a 100-case
rerun with the current prompt (~$0.15) reverses it.

## 8. Implemented the same day

- Citation gates in `countyiq/lib/intelligence_integrity.py` are per field:
  a reasoning field must carry at least one valid marker, unknown markers and
  unused cross-references still fail, and every identifier, membership, and
  duplicate-matter check is unchanged. The Pass 0 quote check also accepts a
  whitespace-free match.
- Every system prompt gained static blocks (Pass 0 definitions plus schema,
  Pass 1 schema, Pass 2 schema plus citation-format rules, Pass 3/3b field
  contract plus citation-format rules), all above the 1,024-token caching
  floor; `tests/test_prompt_cache_prefix.py` guards it. A first attempt
  appended a signal glossary from the version 7 contract to Passes 2/3/3b;
  on the reviewed Pass 2 gold set it moved Luna from 15–16 to 10 status
  matches by flipping "downgraded" signals to "confirmed", so it was
  replaced with format-only blocks. Prefix blocks must not carry signal
  semantics.
- Pass 1 sends only organization-involving clusters and excludes pairs from
  office addresses shared by ten or more entities
  (`countyiq/lib/pass1_entity_verification.py`, shared by the asset and the
  estimator; `COUNTYIQ_PASS1_INCLUDE_PERSON_CLUSTERS=true` restores people).
  The read-only estimate moved from 6,110 clusters / $21.14 to 995 clusters /
  $3.81.
- The estimator prices at no-cache rates, so with the longer prefixes its
  Pass 0 and Pass 2 lines rose to $11.54 and $7.72; the cached cost is lower.
- The frozen Pass 1 eval lane and the live lane's date serialization were
  fixed in `pipelines/eval/`.

## 9. Post-fix confirmation (same day, $0.13 additional)

Frozen corpora with the final gate and prompts:

| Lane | Model | Before | After |
|---|---|---|---|
| Pass 1 gold accepted | Luna high | 2/8 (6/8 correct partitions) | 6/8 accepted, 7/8 correct partitions |
| Pass 1 gold accepted | Luna low | 1/8 | 5/8 |
| Pass 1 gold accepted | GLM 5.3 Flash | 1/8 (8/8 correct partitions) | 3/8 accepted, 7/8 correct; 4 outputs cite corporate identifiers absent from the input |
| Pass 2 status matches | Luna low (two runs) | 15–16/20, 1–4/10 cases accepted | 17/20 and 17/20, 4/10 and 1/10 cases accepted, 0 forbidden claims |
| Pass 3 gold | Luna | 0–1/4 | 2/4 |
| Pass 0 native PDF | Gemini 2.5 Flash-Lite | — | 3/6 gold, 4/5 records matched, 6 extra extractions |

Live, read-only Pass 0 canary on 25 recent York documents from 25 bodies
(`eval/results/p0live_20260902T204003Z.json`):

| Model | Docs with extractions | Extractions | Quote gate | Cost | Cached calls |
|---|---:|---:|---:|---:|---:|
| Luna | 21/25 | 61 | 18/25 | $0.0351 | 24/25 |
| Gemini 2.5 Flash-Lite | 17/25 | 60 | 20/25 | $0.0145 | 0/25 |

The two models produced identical extraction sets on 12 documents. Gemini
over-extracts on native PDFs (6 extras on the frozen corpus) and finds fewer
documents with matters in live text, while Luna now caches its prefix on 24
of 25 calls. Keep Luna for Pass 0; the caching change removes most of the
price gap. GLM remains the Pass 1 candidate on partition quality but needs
the identifier-copying discipline fixed (a prompt instruction or a cheaper
repair retry) before it clears the gate; Luna stays the default.

The live Pass 1 shadow was delayed because the local `staging.parcels` table
held zero rows at 20:17 UTC: an integration test whose connection defaulted
to the live `countyiq` database ran `DELETE FROM staging.parcels`
(175,935 rows). The table was restored from the pre-test snapshot, every
integration test now targets `countyiq_test`, and `pipelines/tests/conftest.py`
refuses connections to `countyiq` for the whole test session.

Live Pass 1 shadow, 12 current clusters from the committed name selectors,
no labels (`eval/results/challenger_*_live_shadow_20260902T21*.json`):

| Model | Valid JSON | Fabricated PIDNs | Gate accepted | Abstained / rejected pairs | Cost |
|---|---:|---:|---:|---:|---:|
| Luna low | 12/12 | 0 | 12/12 | 3 / 1 | $0.0245 |
| GLM 5.3 Flash | 12/12 | 0 | 9/12 | 5 / 13 | $0.0107 |

GLM's three rejections were unknown evidence markers in relationship evidence
and rejected-match names not in the candidate cluster, the same identifier
discipline gap seen on the frozen corpus. It also rejected 13 pairs where Luna
rejected one; without labels that is a difference to adjudicate, not a score.
Luna stays the Pass 1 default; GLM is worth a prompt iteration on identifier
copying because its partition quality and price remain attractive.

### 4e. Pass 3, 4 frozen brief cases

Only Solar Pro 4 passed a case end to end (required facts 4/4 for GLM and
Solar; citation-format failures dominated). Pass 3 is small money and
customer-visible prose; keep Luna until the gate fix lands and a Luna baseline
is rerun.

## 5. Recommended configuration and projected cost

| Pass | Recommendation | Projected backfill |
|---|---|---:|
| 0 | Gemini 2.5 Flash-Lite for text and PDF paths (or DeepSeek text + Luna PDF); recency-first | ~$2.5 |
| 1 | Org-involving clusters only, hub addresses excluded, GLM 5.3 Flash with the existing adaptive N=3 voting; keep Luna as `COUNTYIQ_PASS1_ESCALATION_MODEL` for abstentions | ~$1.0–1.5 |
| 2 | Luna low, unchanged; static prefix over 1,024 tokens for caching | ~$5.5 |
| 3 / 3b | Luna, rank-limited; consider on-demand generation (section 6) | ~$2–4 |
| **Total** | | **~$11–14** vs $37.57 plus Pass 3 today |

Prerequisites in order: citation-gate fix and whitespace-normalized quote
check; system-prompt prefix change; Pass 1 selector change; rerun the frozen
lanes for the chosen models (about $0.05); commit; then canary per
`docs/operations/intelligence-rollout.md`. Any prompt or model change after the
backfill re-keys the input hashes, so freeze these choices first.

OpenRouter's Batch API (50% off, 24-hour window, inline JSON requests, poll
for results) only pays off for passes that stay on Luna; the harness has no
batch submitter today. Defer unless Pass 2 and Pass 3 remain on Luna at scale.

## 6. Other ways to get more from LLMs at flat cost

- **On-demand briefs.** Generate Pass 3/3b briefs when a parcel or owner page
  is opened (cached by input hash) instead of precomputing the top 500. Spend
  tracks what customers read; five to ten seconds of latency is acceptable
  behind a loading state.
- **Cheap triage with escalation for Pass 2.** Run GLM first and escalate to
  Luna only when GLM asserts high significance or an actionable status. This
  reuses the Pass 1 cascade pattern and caps the unsupported-claim risk where
  it matters.
- **Turn on natural-language search.** The Qwen3.5 Flash intent parser is built
  and budget-capped; per-query cost is well under a cent.
- **Embeddings for entity blocking.** Replace trigram pair generation for
  organization names with an embedding nearest-neighbor pass (about $0.05
  one-time for all owners). It removes generic-suffix collisions such as
  "HCK PROPERTIES LLC" vs "LL PROPERTIES LLC" (7,768 of 19,549 trigram pairs
  share no distinctive token).
- **One-time LLM-built deterministic assets.** Use a cheap model once to
  expand the Pass 0 land-use vocabulary, the generic-token list, and municipal
  body aliases, then review the 963 prefilter skips it predicts; the runtime
  stays deterministic.
- **Judge only on sampled disagreements.** Keep `x-ai/grok-4.6` for the weekly
  audit sample rather than as an inline gate.

## 7. Caveats

- All candidate results are N=1 on 6–10 case corpora: screening evidence, not
  promotion gold. Confirm GLM for Pass 1 on a 20-cluster live shadow and Pass 0
  on a 25-document canary before enabling.
- GLM's promotional route price ($0.075/$0.25) is time-limited; the eval
  ceiling is pinned at $0.16/$0.55, which is still 2.5× cheaper than Luna on
  output.
- DeepSeek, gpt-oss, and Qwen3.8 produce very long reasoning traces (28k–54k
  tokens per 8 calls); their low list price does not translate into low cost.
