# LLM strategy and evaluation audit — 2026-08-30

## Decision

Keep CountyIQ hybrid and narrow: deterministic collection, change detection,
spatial logic, eligibility, scoring, and serving; LLMs only for document
extraction, genuinely ambiguous identity evidence, interacting-signal review,
and cached shortlist briefs.

Do not change production defaults from this probe. Keep Luna for Passes 0–3,
enable adaptive early stopping for Pass 1 voting, keep Pass 2 at one trial, and
keep Pass 4 off. The new labeled frozen Pass 2 corpus favors GLM 5.3 Flash FP8
on its first ten cases, but the 100-case stratified diagnostic reverses that
result and favors Luna, especially on unsupported-claim control. Retain Luna;
GLM is not ready to replace it for Pass 2.

## What the current evaluations actually use

| Pass | Current test information | Frozen? | Needs live data? | What it can prove |
|---|---|---:|---:|---|
| 0 | Six committed municipal PDFs, 17 rendered pages; five reviewed property matters and three negative controls with field-level gold | Yes | No | Extraction recall, false positives, duplicates, and field correctness under the production contract |
| 1 | Eight de-identified production-shaped contexts with acceptable partitions, hard negatives, a borderline case, and cross-source links | Yes | No | Stable entity partition/link regression quality |
| 2 | Ten reviewed gold contexts plus a separate 100-case rubric diagnostic covering 54 pairs, 29 three-signal cases, and all 17 observed four-signal cases | Yes | No | Gold regression quality on the reviewed set; broad interaction/slice diagnostics on the generated-rubric set pending human confirmation |
| 3/3b | Four production-shaped contexts derived from reviewed Pass 2 evidence, covering pursue/watchlist/pass and citations | Yes | No | Stable decision, citation, and fact-grounding regression quality |
| 4 | Historical two-area comparison; no maintained promotion corpus | No | Yes for any new probe | Too little evidence; pass correctly remains disabled |

Pass 1 name lists and the ten Pass 2 PIDNs still exist as a separate explicit
`--live` drift lane. Their gathered database context is mutable and must not be
confused with the fingerprinted promotion fixtures.

## Do accurate evaluations require live data?

Not for regression accuracy. Model comparisons are most accurate when every
candidate sees the same immutable, production-shaped source context and is
scored against explicit human labels or acceptable alternatives. Live database
lookups inside a model comparison introduce uncontrolled input drift.

Live data is still required for representativeness and operational drift. Run
it as a separate shadow lane after a meaningful backfill to answer: Are prompt
sizes and signal mixes still representative? Are new source shapes missing?
Does abstention or failure rate change? Freeze the complete gathered context
from each selected live case before adjudicating or comparing models.

The target workflow is therefore:

1. Frozen regression lane for promotion: immutable prompts/context, explicit
   labels, hard negatives, borderline cases, repeated trials, and mechanical
   invariants.
2. Live shadow lane for production reality: stratified post-backfill sampling,
   drift/coverage/latency/cost metrics, then snapshot any new failure modes back
   into the frozen corpus.

## Evaluation-code findings and fixes

- Production had moved static instructions into system messages, but the eval
  paths did not consistently send those messages or strict output schemas.
  `eval/protocol.py` now builds pass configs from the production contract.
- Pass 0 previously checked only two expected-zero counts. All PDFs were
  rendered and reviewed; `p0_expected.json` now defines five expected matters
  and three negative controls, and `eval/scoring.py` penalizes missing,
  duplicate, and extra records.
- Pass 1/2 now identify their dataset mode as live context from frozen
  selectors. `challenger.py` requires `--live` for those passes.
- Passes 1-3 now also have immutable, SHA-256-checked promotion fixtures and
  substantive deterministic scorers. Pass 2 aliases preserve ownership
  relationships and entity type without leaking direct identifiers or adding
  visibly synthetic shared-name artifacts.
- Pass 2 reports calibration, prohibited claims, required-fact recall, strict
  signal passes, and perfect-case passes separately. Evidence matching tolerates
  harmless modifiers/plurals, while offline rescoring refuses a changed context
  hash.
- The pairwise Pass 2 judge previously saw no source evidence; it now can see
  evidence, but paid judging is opt-in because another LLM is not ground truth.
- Every paid eval call now records provider-returned tokens, provider, model,
  latency, and cost. Retries are aggregated, and the run stops when cost is
  missing or the configured ceiling is exceeded.

## Capped current-prompt probe

Three historical Pass 2 prompt archives were converted to the current batched
format. Only cases with at least two current interpretive signals were retained.
Each Luna and GLM case used three trials; DeepSeek received one trial per case.

| Model/use | Calls | Provider-reported cost | Trial-decision stability | Review |
|---|---:|---:|---:|---|
| `openai/gpt-5.6-luna` candidate | 9 | $0.007860220 | 14/18 modal votes; 3/6 unanimous | Generally calibrated about missing provenance; some zoning-status variation |
| `z-ai/glm-5.3-flash` FP8 candidate | 9 | $0.003540550 | 16/18 modal votes; 4/6 unanimous | Best small-sample cost/stability tradeoff; usually explicit about missing corridor/source evidence |
| `deepseek/deepseek-v4-flash-0731` candidate | 3 | $0.001363825 | Not measured (one trial/case) | Cheapest, but overclaimed plan authority and interpreted an evidence-capture timestamp as future planning intent |
| `qwen/qwen3.5-122b-a10b` judge | 3 | $0.017117680 | 1 usable, 2 truncated | Cost more than all 21 candidate calls combined; surviving verdict favored schema shape and missed unsupported certainty |
| `x-ai/grok-4.6` tightened judge | 3 | $0.025872000 | 3/3 human-oracle winners | Valid strict JSON each time and explicitly identified the expected unsupported authority, timestamp, absence, and background-causality claims |

The initial provider-reported experimental cost was **$0.055754275**, comfortably
inside the $1 cap. The OpenRouter credits endpoint moved from $7.157002477 to
$7.212756752 used—an identical $0.055754275 delta—so call-level and account-level
accounting reconcile exactly. This probe is intentionally not a benchmark:
three historical cases and no adjudicated outcome labels can rank stability and
expose failure modes, but cannot establish business correctness.

## Frozen Pass 2 GLM comparison

The reviewed ten-case corpus contains one case for every exact pair among
`active_subdivision`, `assemblage`, `ownership_change`, `vacancy`, and
`zoning_mismatch`. Each model saw the same production prompt and context. A
second run followed a fixture audit that replaced role-destroying placeholder
names with realistic stable aliases; only that corrected run is decision-grade.

| Metric | GLM 5.3 Flash FP8 | Luna incumbent |
|---|---:|---:|
| Calibrated decisions without prohibited claims | 17/20 | 16/20 |
| Required fact groups | 46/48 (95.8%) | 42/48 (87.5%) |
| Fully grounded signals | 15/20 | 11/20 |
| Perfect two-signal cases | 5/10 | 5/10 |

The corrected shared run used 20 calls and cost **$0.012709850**. The earlier
fixture-diagnostic run cost **$0.013013690** and is retained for audit but not
model selection. No paid judge was used; the human labels are the oracle.
Provider spend through this corrected ten-case comparison was **$0.081477815**.
The expanded work below supersedes that interim cumulative total. No backfill
was run.

## Expanded 100-case Pass 2 diagnostic

The expanded corpus samples all 24 interaction shapes currently present among
7,214 eligible parcels: 54 two-signal, 29 three-signal, and all 17 four-signal
cases. It freezes and de-identifies complete production contexts. Its labels are
generated from an explicit deterministic rubric and are marked diagnostic until
a person confirms them; they do not supersede the ten reviewed gold cases.

Both models returned valid outputs for all 100 parcels. The 100 contexts contain
263 signal decisions and 683 required fact groups.

| Metric | GLM 5.3 Flash FP8 | Luna incumbent |
|---|---:|---:|
| Status + significance calibration | 186/263 | 191/263 |
| Grounded decisions with no prohibited claim | 166/263 | 191/263 |
| Required fact groups | 573/683 (83.9%) | 595/683 (87.1%) |
| Fully grounded signals | 102/263 | 133/263 |
| Perfect multi-signal cases | 11/100 | 22/100 |
| Signals with a prohibited claim | 30/263 | 0/263 |

The paired exact test favors Luna for fully grounded signals (`p=0.0010`) and
grounded decisions (`p=0.0015`). Parcel-bootstrap GLM-minus-Luna differences
were -11.8 percentage points for grounded signals (95% interval -18.0 to -5.4),
-9.5 for grounded decisions (-14.7 to -4.5), and -3.2 for fact recall (-6.4 to
0.0). The repeated GLM failure mode was unsupported inference from price or
planning context: arm's-length sale, development intent, rezoning pressure, or
development-readiness claims not established by source evidence.

The 20 highest-disagreement cases received two additional trials per model.
Luna led grounded decisions, strict signals, and fact recall in all three
trials. GLM had more unanimous raw status/significance choices, but only 44/65
grounded-decision outcomes were unanimous versus Luna's 52/65 because GLM's
unsupported claims varied between trials.

The 100-case paired run cost **$0.151362330**. Two 20-case repeat runs cost
**$0.031978890** and **$0.033542400**. Including all earlier research and one
checkpointed pair from the interrupted sequential attempt, provider-reported
spend is **$0.299886735**, leaving **$0.700113265** of the authorized `$1` cap.
One interrupted in-flight request lacked returned usage; even its full reserved
ceiling would keep total spend below `$0.31`. No backfill was run.

Qwen 3.8 Flash (released 2026-08-26) was considered as the newest cheap judge,
but its sole OpenRouter endpoint did not satisfy the CountyIQ ZDR route and was
excluded without billing. GPT-5.6 Sol also had no route matching the full ZDR,
price, and structured-output constraints in this environment and was excluded
without billing. Grok 4.6 (released 2026-08-12) is therefore the recommended
optional diagnostic judge. It is better than the prior judge on this tiny
oracle, but human labels remain cheaper and more authoritative for promotion.

## Cost-conscious pass strategy

- **Pass 0:** prefer scraper-extracted text; use native PDF only when text is
  absent or clearly failed. Keep Luna until the new gold corpus is rerun for
  Luna and GLM on identical PDFs.
- **Pass 1:** deterministic exact/normalized identity work first. For remaining
  ambiguity, Luna high-reasoning voting with adaptive early stop. Archived
  replay stopped 10 of 11 clusters after two agreeing trials, saving 30.3% of
  calls without changing any final partition.
- **Pass 2:** preserve the two-interpretive-signal gate and context-only facts.
  Keep Luna N=1. GLM FP8 is cheaper and stable at raw classifications, but the
  expanded paired test found materially worse unsupported-claim discipline and
  grounding. Do not promote it without a prompt/model change that clears both
  reviewed gold and the expanded diagnostic. DeepSeek should not be the
  preferred quality lane despite its price.
- **Pass 3/3b:** generate only for materially shortlisted parcels/owners and
  only when the input hash changes. Evaluate factual citation support and
  decision usefulness on frozen Pass 2 outputs before changing models.
- **Pass 4:** leave disabled until a concrete user surface and county-level gold
  corpus justify recurring synthesis.
- **Evaluation:** spend candidate tokens on diverse labeled cases, not a large
  generic judge. Use deterministic schema/coverage/identifier checks first and
  human adjudication for consequential semantic decisions.

## Current price/routing notes

OpenRouter's model listing reported Luna at $0.20/M input, $1.20/M output, and
$0.02/M cache reads. GLM 5.3 Flash displayed a time-sensitive discounted route,
while normal FP8 providers and the tested route billed $0.15/M input and
$0.50/M output; the eval ceiling is pinned above the normal route at $0.16/M
and $0.55/M rather than trusting the promotion. DeepSeek V4 Flash was listed at
$0.065/M input and $0.18/M output. Routed provider prices can differ. Keep
the static system prefix byte-identical to benefit from supported prompt
caching, pin acceptable quantization/provider policy, retain zero-data-retention
controls, and use provider-returned `usage.cost` as the spend ledger.

Official references: [OpenRouter prompt caching](https://openrouter.ai/docs/guides/best-practices/prompt-caching),
[provider routing](https://openrouter.ai/docs/guides/routing/provider-selection),
[usage accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting),
and [zero data retention](https://openrouter.ai/docs/guides/features/zdr).
