# Lower-cost model review — September 5, 2026

**Decision: compare Luna Batch alongside both alternative models before selecting
the backfill route; do not switch every pass yet.** GLM 5.3 Flash is the stronger
current alternative model, with entity verification the first pass to qualify.
DeepSeek V4 Flash 0731 needs more work on provider routing, reasoning allocation
and the output contract before it is a dependable default.
This review does not approve a quality receipt or a backfill.

## Controlled comparison

The user reopened model choice after correctly identifying that earlier failures
could arise from prompts, input formatting and the harness. We fixed omitted
neighbor tax-claim years, a balance-only delinquency count, evidence-wrapper
parsing, municipal scope rules and several scorer defects before this comparison.

The request audit found additional confounds:

- GLM inherited generic temperature 0.1/top-k 40. Its publisher/OpenRouter defaults
  are temperature 1/top-p .95, and its mandatory reasoning defaults to maximum
  when effort is absent. The harness now uses those sampling defaults and an
  explicit low reasoning default instead of silently requesting maximum.
- DeepSeek V4 now uses OpenRouter's provider-independent reasoning control and
  omits ignored sampling parameters in thinking mode. Earlier output truncation
  had already been traced to insufficient reasoning/output allowance.
- The mixed-pass README example forced low effort on Pass 1, unlike the high
  effort selected for Luna. That override was removed.

Sources: [GLM publisher model card](https://huggingface.co/zai-org/GLM-5.3-Flash),
[DeepSeek thinking controls](https://api-docs.deepseek.com/guides/thinking_mode/),
[OpenRouter reasoning controls](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens).

A protocol was frozen before dispatch: 12 identical source cases per model,
36 calls total, maximum $1.50. Cases comprise two full municipal documents, two
entity-partition cases, four previously difficult signal contexts and four brief
cases. Every model received the same corrected prompts, explicit low effort for
Passes 0/2/3 and high for Pass 1, and the same output allowance per pass. Both
open models required FP8 routes. There were no generation retries, paid judges,
serving writes or label changes. These are selected regression cases, not an
independent or statistically representative holdout.

| Model | Actual total, 12 calls | Parseable | Parse + reference gate | Median / worst latency | Reasoning tokens |
|---|---:|---:|---:|---:|---:|
| Luna | $0.024388 | 12/12 | 12/12 | 12.9 / 27.6 s | 4,615 |
| GLM 5.3 Flash | $0.011820 | 12/12 | 10/12 | 15.1 / 23.4 s | 1,755 |
| DeepSeek V4 Flash 0731 | $0.009931 | 11/12 | 7/12 | 33.4 / 441.9 s | 47,132 |

**Total: $0.046138529.** Gate counts are diagnostic, not useful-output acceptance:
Pass 0 can pass its envelope while individual items are quarantined or its
extraction list is empty. Every consequential claim still requires source review.
GLM cost 52% less and DeepSeek 59% less in this small run; those are observed
route/cache/usage results, not a forecast for the pass mix in a full backfill.

## What failed, and what it means

**Pass 0:** Luna and GLM retained useful matters but still made some agenda-stage
errors. Guards quarantined individual items, so document-level success conceals
recall loss. A source stating an earlier award or completion can legitimately
appear on an agenda; that is different from inventing a new vote at the listed
meeting. The agent evidence inventory overflags all non-scheduled agenda states;
its warnings must be adjudicated using the actual source wording.

DeepSeek returned an empty extraction list for Dallastown after substantial
reasoning. For Loganville it copied the source fingerprint incorrectly. That is
an interface/transcription failure, not proof that the model read another source.
An offline diagnostic bound the original claims to the trusted input fingerprint:
five items then passed projection and five were rejected for agenda-stage or
literal-reference problems. The original failure is preserved and nothing was
published. Requiring an LLM to reproduce a 64-character source hash deserves
architectural simplification; source binding should be owned by the caller.

**Pass 1:** Luna and GLM pass both difficult partitions and their citation gates.
DeepSeek passes one; the other has uncited reasoning. Two cases are insufficient
to replace identity resolution: run the remaining six frozen partitions and the
supplemental cross-source cases before choosing GLM for this pass.

**Pass 2:** GLM gives useful calibrated explanations and, in the school-property
case, explicitly distinguishes a nearby plan from a plan established on the
subject parcel. Two of four outputs fail citation checks. One copies the example
`context:growth_area` ref even though it is not in the case, and several list
unused refs. DeepSeek omits material acreage/claim facts and a synthesis citation
in one case; another run spends 5,300 reasoning tokens on that small input.
The prompt's global examples and requirement to reproduce the same IDs in prose
and arrays add avoidable opportunities for errors. Keep unknown IDs rejected;
simplify the contract and retest before attributing the whole gap to capability.

Source-supported conservative vacancy dispositions remain disagreements with the
older diagnostic rubric. The p2x-050 fixture also contains different 11/12 neighbor
counting bases. Neither is repaired by changing model labels after seeing output.

**Pass 3:** Luna passes all four frozen cases. GLM passes three; it classifies a
material farm transfer as insufficient evidence rather than watch. That misses the
intended product distinction but invents no acquisition thesis. DeepSeek has an
empty response, corrupted citation IDs on another case, and an overly definite
zoning-density claim in a third. Its route matters: the empty/corrupted responses
came from OpenInference, while its two Baidu briefs were parseable. This tiny
sample does not establish that the provider caused those errors.

## Next qualification steps

1. Qualify GLM on all eight entity partitions and supplemental cases. Promote
   only the exact tested settings and provider constraints, per pass.
2. Remove avoidable prompt/output obligations: example IDs that look like current
   evidence, duplicated citation bookkeeping, and model-generated source hashes.
   Preserve raw responses, exact input binding, unknown-ID rejection and source
   review. Compare revised contracts against Luna on the same frozen cases.
3. Test DeepSeek with a controlled provider and a smaller supported reasoning
   allocation. Count latency, reasoning and rejected/retried output in its price.
4. Use varied new municipal canaries after correcting the remaining stage/recall
   issues. Favorable repeats on documents that drove fixes are regression evidence.

Artifacts are under `output/production-readiness-2026-09-05/fair-model-comparison/`:
frozen protocol/payloads, unmodified responses, actual usage, source evidence,
smoke review and the separate fingerprint diagnostic. The public route snapshot
is `model-route-audit-20260905.json`. Promotional prices and provider offerings
change; route ceilings must be checked again before a funded run. Current listings:
[GLM](https://openrouter.ai/z-ai/glm-5.3-flash),
[DeepSeek 0731](https://openrouter.ai/deepseek/deepseek-v4-flash-0731).

## Follow-up qualification and prompt repeat

Six additional GLM entity cases cost **$0.002455925**. Together with the two
matched cases, GLM produces 8/8 valid, source-cited partitions/abstentions and
7/8 exact gold decisions. The remaining case abstains because the two recorded
names have conflicting middle initials despite a matching address and spouse.
That is a defensible uncertainty, not an invented identity. Keep the frozen
merge label unchanged and adjudicate the ambiguity before choosing a fallback;
forcing a merge to raise a score would be the wrong identity policy.

The citation prefix then lost its concrete example IDs and factual examples;
Passes 2 and 3 received concise checks restating the existing citation contract.
The eight P2/P3 cases were repeated for all three models with unchanged input,
labels, validators, model settings and output ceilings: **24 calls, $0.018893261**.

| Model | Cost for 8 cases | Reference gate | Median / worst latency |
|---|---:|---:|---:|
| Luna | $0.009514 | 8/8 | 7.2 / 11.2 s |
| GLM 5.3 Flash | $0.005410 | 7/8 | 9.9 / 17.0 s |
| DeepSeek V4 Flash 0731 | $0.003970 | 7/8 | 31.3 / 182.1 s |

DeepSeek's four briefs now all parse and pass reference checks. This supports
the user's concern that prior failures partly reflected the interface. It does
not establish semantic equivalence: its school-acquisition brief suggests
development interest from the price/assessment gap; its fragmented-neighbor
brief suggests an assemblage play and a low-density restriction without the
necessary source evidence. An owner-matched nearby plan can reasonably prompt
a question about parcel inclusion, provided inclusion remains unestablished.
Watch itself is valid for a documented transfer and is not an intent claim.

GLM's former invented `context:growth_area` reference disappeared, but one new
output misspells `zoning_mismatch`. DeepSeek adds an invalid `Parcel:` entry to
a P2 evidence-reference array. Both remain rejected. GLM still misses the
watch-versus-static distinction for the large farm transfer. Both models also
need better handling of footprint-screen uncertainty and the ambiguous neighbor
counting bases in p2x-050. No model default or quality receipt was promoted.

Luna's farm brief exposed another scorer defect: explicit "absence of" a
coordinated acquisition was counted as asserting it. Added that negation with
regressions retaining rejection of a separate positive claim. Offline scoring
version 2026-09-05.2 gives Luna 4/4 strict brief cases, GLM 3/4 and DeepSeek 1/4.
The raw scores and responses are preserved; this is not another paid run or a
changed gold label. The full launch ledger is now **156 calls, $0.234389645**.

## Direct OpenAI Batch must be included in the backfill decision

The user identified an omission in the initial cost comparison: the current
OpenRouter harness uses synchronous Chat Completions. Grouping all signals for
a parcel into one Pass 2 request does not receive asynchronous Batch pricing.
[OpenAI's current pricing](https://developers.openai.com/api/docs/pricing) lists
Luna Batch short-context input at $0.10/M, cached input at $0.01/M and output at
$0.60/M. [Batch](https://developers.openai.com/api/docs/guides/batch) processes
uploaded request files within 24 hours at half the direct standard rate.

The eight Luna retest cases used 18,938 input tokens (10,086 cached) and 5,917
output tokens. Repricing those counts yields an illustrative **$0.00453626**,
versus $0.00540953 actually charged for the eight GLM calls. This is not a Batch
invoice: cache behavior, cache-write charges and direct-provider execution must
be tested. Nevertheless, comparing alternative models only against synchronous
Luna overstates their potential backfill savings.

Keep synchronous canaries for short feedback cycles. Before requesting full
backfill approval, qualify a bounded direct Batch sample and estimate accepted
output cost, including retries, rejects, cache effects and dependent-pass
turnaround. Batch results must retain frozen input/model/prompt identity and be
revalidated before publication; asynchronous processing does not relax the
existing evidence or authorization gates.
