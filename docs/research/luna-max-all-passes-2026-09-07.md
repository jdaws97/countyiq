# Luna max reasoning across CountyIQ passes

Evaluation completed September 7, 2026 (America/New_York).

Max produced useful improvements in document context, property ownership chronology,
and the small investigation-brief set. It was substantially more expensive in every
tested branch, mostly because of reasoning tokens. The results support selective
use rather than a blanket max setting.

| Work | Matched cases/trials | Baseline cost | Max cost | Multiplier | Max cost attributable to reasoning |
| --- | ---: | ---: | ---: | ---: | ---: |
| Pass 0 document reading | 9 | $0.014585 | $0.271458 | 18.6× | 96% |
| Pass 1 identity verification | 8 × 3 trials | $0.041898 | $0.119200 | 2.8× | 88% |
| Pass 2 signal validation | 30 | $0.040502 | $0.473185 | 11.7× | 93% |
| Pass 3 investigation briefs | 4 | $0.003545 | $0.037132 | 10.5× | 94% |
| Municipal record summaries | 52 | $0.026599 | $0.128629 | 4.8× | 85% |
| Property record summaries | 8 | $0.009597 | $0.181724 | 18.9× | 94% |
| Owner briefs, synthetic controls | 2 | $0.002033 | $0.009334 | 4.6× | 82% |
| Pass 4 county narratives, mixed fixtures/live | 5 | $0.002997 | $0.009275 | 3.1× | 73% |

Baseline means Luna low except Pass 1, which uses high. Costs include the first
complete response and any required record correction. They exclude charges for
discarded token-cap attempts and the redundant capacity probe, so they describe
the observed completed workflow rather than the cost of repairing this experiment.
They include actual cache reads/writes and are not uncached population forecasts.
Reasoning cost is the provider-reported reasoning-token count times $1.20/million.

All 134 final max outputs passed their structural/citation gates. The original
record attempts passed 54/60; six were cut off by the initial output cap. After
capacity retries, 58/60 complete record responses passed; the two overlong property
summaries passed their one production correction, reaching 60/60. These are
validation results, not semantic-quality percentages.

Frozen scores: identity trials improved from 20/24 to 21/24; investigation briefs
from 2/4 to 4/4. Signal-validation fixture passes fell from 7/30 to 4/30, with
accepted status/significance decisions at 71/79 versus 69/79. The scoring
limitations below materially constrain interpretation, especially for Pass 2.

The 255 new API calls cost **$1.939099760**, including every incomplete output,
correction, and redundant probe. The shared authorization increased from
$1.026869496 to **$2.965969256 of $5**. There are no active reservations,
unfinished dispatches, unknown costs, or transport errors. Of the new calls,
44 ended at an output cap; one additional completed capacity probe was redundant.
Their combined $0.60360141 remains in the experimental total above.

The saved `results-summary.json` reconstructs every actual request from its
archived configuration and production prompt, revalidates accepted outputs,
checks unchanged frozen inputs and returned provider/model, and reconciles usage
and charges to the shared ledger. Evaluation helpers pass Ruff formatting and
lint. No application code changed in this experiment.

The user requested Luna at max reasoning for every pass, a mathematical comparison
with several cases grouped into ordinary Sol requests, and an assessment of using
the existing Codex subscription to produce backfill results and teacher examples.
No Sol inference calls are part of this experiment.

## Reproducible experiment

Artifacts live in `output/luna-max-all-passes-2026-09-07/`. Each dispatch saves the
source, exact request, configuration, raw response, provider-reported usage, and
validation result. All calls pin `openai/gpt-5.6-luna` to the OpenAI provider with
fallbacks disabled. The experiment uses the existing durable $5 authorization;
the starting cumulative charge was $1.026869496. No production data, model
configuration, prompts, or release approvals are changed by this evaluation.

- **Pass 0:** ten frozen real source documents; one cancellation is skipped by
  the existing value gate, leaving nine paired model reads.
- **Pass 1:** eight frozen identity cases, three trials per effort. The baseline
  is high, matching the existing identity workflow; max gets the same cases.
  Production can stop after two agreeing trials, so the three-trial cost is an
  experiment cost rather than a fixed production multiplier.
- **Pass 2:** ten original frozen cases and twenty expanded stability cases.
- **Pass 3:** four frozen investigation briefs; two explicitly synthetic owner
  controls; and sixty real record-explanation bundles, comprising fifty-two
  municipal items and eight properties. Record low baselines reuse the earlier
  two thirty-case comparisons, including their one allowed correction.
- **Pass 4:** three existing synthetic fixtures covering corridor, portfolio,
  and municipal narratives; two real distress-query rows from the read-only
  local snapshot. The snapshot has no eligible real rows for the other three
  branches. This is branch coverage, not a county-wide quality certification.

These are targeted cases, not a random population sample or a fresh blind test.
The record bundles reuse previously reviewed evidence. Quality review compares
outputs with the supplied evidence; passing JSON and citation checks alone is
not treated as semantic correctness.

### Capacity and input limits

The initial experiment used 8,192 output tokens, or 16,384 for Pass 0. Those were
test guardrails chosen by the evaluator, not model limits. Reasoning consumes
the same output allowance. Several max requests exhausted them before producing
JSON, so those results cannot establish that the model was unable to do the task.
An initial set of 32,768-token capacity retries was followed by retries using the
model's documented 128,000-token maximum. All earlier charges remain recorded.

Primary results select the **first complete response**, followed by the production
record-correction prompt once if that response fails record validation. They do
not select the best-looking answer from repeated attempts. Overlapping capacity
plans scheduled one redundant restaurant-property probe, which had already
started when its earlier response and production correction were reviewed. Its
charge remains in experiment accounting, and it does not replace the primary
response.

The evaluation adds no input truncation. The existing production builders do have
their own context policies: Pass 2 shows at most ten portfolio rows and fifteen
neighbors, among other list limits; some expanded fixtures exceed them. Both arms
receive the same resulting production prompt. Record bundles above 36,000
characters are rejected, rather than silently shortened. Pass 1's production
context fetch also has detail limits, although these eight fixtures are smaller.
This experiment compares reasoning effort within the current pipeline; it does
not test a redesigned pipeline supplying every available related row.

### Scoring limitations

Frozen fixture scores are reported as fixture scores, not a universal quality
percentage. Some older Pass 2 labels conflict with newer evidence policy: for
example, `p2-003` expects confirmed vacancy from a missing building footprint,
while the current prompt explicitly says that missing footprints do not prove
vacant use. Literal keyword scoring can also miss equivalent representations
such as `prop_lots=4`. Source review must distinguish these from actual mistakes.
No labels or prompts were changed during the experiment.

## Source-review findings

Max is useful in specific places; the completed evidence does not support turning
it on for every pass simply because it is the highest reasoning setting.

**Pass 0:** Max restores the enforcement-action headings in source `11777`, so a
violation description retains whether a letter or citation was issued. It also
recovers the named notice-to-comply case at 2109 TwinBrooks Drive. In `6414`, it
combines the generator's installed/in-service update with its earlier project
entry and avoids attaching the data-center paragraph to SolAmerica's separate
financial-assurance matter. These are useful context improvements.

The same max reads also select extra noise: a police warrant service at 50 Highland
Avenue, a fragmentary `#1 Pump Station (on agenda)` entry, and the unlocated `60 Day
Mandatory Sewer Connection: 1` count. Source `10260` gains an anonymous enforcement
agreement without identifying a property. In `9659`, max preserves more headings
but incorrectly carries the Park Improvements heading into separate road-work
budget cards. More cards therefore do not consistently mean better coverage.
All selected text remains source-bound; the problems concern selection and context.

**Municipal record summaries:** The fifty-two max outputs all pass validation on
their first attempt. Max restores the missing hearing tag for the data-center/solar
item (`municipal-10415-8`), keeps the restaurant hearing as proposed rather than
scheduled (`municipal-10688-12`), retains the 2027 road-budget year
(`holdout-9659-8`), and uses a short exact date quote that avoids the OCR-artifact
failure in `fresh-municipal-10488-3`. It also removes the extra condition tag on the
road-program change order and the extra recommendation tag on the wellhouse quote.
Most other outputs make the same grounded decision as low. These examples are
source-reviewed improvements, not a blind estimate of error reduction.

**Property summaries:** Max's completed farm response for `54000HJ012400` retains
the December 1, 2025 adjoining purchase that low omitted, describes the current
mapped zoning correctly, and asks about sewer capacity instead of rechecking
whether an already-mapped zoning change occurred. The restaurant's first complete
max response retained the newer adjoining purchase but exceeded the summary word
limit; its one production correction passed and retained that purchase. A higher
token allowance does not remove the product's separate concise-summary contract.
The Thornton property's corrected max output retains both newer adjoining
purchases from February 2020, which low omitted. It still emphasizes the older
2023 inventory entry instead of the newer 2025 plan; max does not eliminate
coverage tradeoffs in a short summary.

**Investigation briefs:** Max moves the 101.13-acre farm sale to watch status and
the owner-matched subdivision case to a concrete records investigation, bringing
the small frozen set from 2/4 to 4/4 passes. It retains scope and approval
uncertainty. The prose still sometimes calls compatible facts a tension—for
example, a missing mapped structure and a proposed subdivision—so the four passing
scores are not proof that every sentence is ideal.

**Owner controls:** Both efforts leave static zoning evidence at insufficient
evidence with no urgency. For the tax-claim control, max leaves strategy unclear
and explicitly distinguishes recorded claims from unknown payment status; low
labels the portfolio strategy distressed despite that uncertainty. Neither
response invents seller willingness, a forced sale date, or acquisition intent.

**Pass 4:** Both efforts still infer a spreading/expanding distress trend from the
Hanover row's zero historical count, without establishing comparable historical
coverage. Max's York City prose does mention possible reporting changes but still
says forced sales are more plausible than ninety days earlier. In the synthetic
municipal narrative, both efforts omit the supplied $285,000 delinquent balance,
45 delinquent parcels, three sheriff sales, and the zoning-decision totals from
the narrative, even though the citation metadata names those topics. Max does
not cure these evidence and coverage problems. Its portfolio prose better states
that undated project signals cannot be sequenced relative to the dated deed.

## Ordinary grouped Sol requests: mathematical method

This calculation concerns multiple cases in one normal request, with reusable
instructions or shared evidence supplied once. It does not apply a Batch API
discount. Official standard prices per million tokens are:

| Model | Input | Cached input | Output, including reasoning |
| --- | ---: | ---: | ---: |
| GPT-5.6 Luna | $0.20 | $0.02 | $1.20 |
| GPT-5.6 Sol | $4.00 | $0.40 | $20.00 |

Sources: [Luna model documentation](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
and [Sol model documentation](https://developers.openai.com/api/docs/models/gpt-5.6-sol).
Both list a 1.05-million-token context window and a 128,000-token maximum output.
A stronger model's ability to use evidence well is distinct from its nominal
context limit. These pages also specify higher prices above 272,000 input tokens
and a cache-write premium; crossing that threshold must be priced separately.

Let `N` be the case count, `S` repeated shared instructions, `D` total distinct
case input, `V` total visible answer tokens, `RL` Luna's summed reasoning, and
`RS` Sol's grouped reasoning. Ignoring caching and long-context premiums:

```text
Luna dollars = [0.2 × (N×S + D) + 1.2 × (V + RL)] / 1,000,000
Sol dollars  = [4 × (S + D) + 20 × (V + RS)] / 1,000,000

Sol is cheaper only if:
RS < (0.01×N − 0.2)×S − 0.19×D − 0.94×V + 0.06×RL
```

Shared case evidence can also be deduplicated; when it is, use the actual reduced
Sol input instead of assuming that every byte in `D` must recur. Grouping saves
tokens only where content is reused. It does not divide all per-token prices by
the number of cases. Pass 1 already groups candidate records, and Pass 2 already
groups a property's signals.

For the measured-cost comparison, let `C` be Luna's actual dollars and `I` Sol's
effective billable input: uncached input plus 0.1 times cache-read input plus 1.25
times cache-write input. At standard context length, for equal visible answer
length `V`, the exact break-even condition is:

```text
I + 5×RS < 250,000×C − 5×V
```

A negative right-hand side rules out cheaper Sol answers of that length even with
free input and zero reasoning. A positive value provides a budget for input and
reasoning, not proof of savings. Different answer lengths change the arithmetic.
Grouped output identifiers and framing may add tokens. No calculation can infer
Sol's actual reasoning-token consumption at a particular effort without measuring
it; this report makes no such inference.

### Measured break-even results

For the fifty-two municipal summaries, max cost $0.128629. Sol's visible-output
floor at the same 10,057-token answer length is $0.201140, before any input or
reasoning. Grouping input alone therefore cannot make equal-length Sol answers
cheaper than those max answers. The low summaries are cheaper still. The same
zero-input/zero-reasoning floor rules out savings over the measured max workflows
for identity, signal validation, owner briefs, and county narratives at their
observed final answer lengths.

Pass 0 differs: its nine max responses spent $0.271458, of which $0.261491 was
reasoning. Sol can beat that if effective grouped input plus five times its
reasoning tokens stays below **52,244.51 tokens**, assuming the same 3,124 visible
answer tokens. For example, using the entire measured 37,531 input tokens without
crediting grouping savings leaves room for fewer than **2,943 reasoning tokens
total** at ordinary uncached rates. If all those inputs incur the cache-write
premium, the allowance falls to about **1,066 reasoning tokens**. Deduplicating
shared instructions or evidence increases the allowance. These are break-even
conditions, not measured Sol usage or a claim that a named effort meets them.

Property explanations also have a positive bound: **30,411.07 effective-input-plus-
five-times-reasoning tokens** across eight cases, using their correction-inclusive
Luna cost and equal final answer length. The four investigation briefs have only
548.105 such tokens available, which leaves very little room for their source
material unless heavily cached or compressed. For every low/high baseline in
this experiment, Sol's equal-length output floor alone exceeds Luna's cost.

Thus ordinary grouping can plausibly make a stronger, much more reasoning-efficient
reader cheaper than max Luna in selected tasks. It does not establish that Sol is
cheaper across the whole pipeline, and the requested arithmetic cannot identify
the best Sol reasoning effort without its actual token consumption.

## Subscription and teacher examples

Codex can read local source bundles, reason over them under the signed-in ChatGPT
subscription, and write structured results locally for the same deterministic
validators. A staged backfill using that execution route is technically feasible.
Calling OpenAI or OpenRouter APIs from a script is separate paid API usage; the
subscription is not API credit. Codex usage limits depend on the work and model,
so a $200 subscription does not establish a fixed number of county documents or
tokens that can be processed. See [Codex pricing](https://learn.chatgpt.com/docs/pricing)
and [authentication](https://learn.chatgpt.com/docs/auth).

The existing snapshot estimates 3,504 source documents before downstream work.
That scale prevents promising that a full backfill fits the remaining subscription
window without an observed subscription-throughput sample. No reset credit was
redeemed and no subscription backfill was started by this experiment.
The account snapshot during final review showed 16% of the weekly Codex allowance
remaining, resetting September 12, 2026 at 10:41:56 a.m. America/New_York. This is
account-wide usage, not an attribution of usage to this task.

Reviewed outputs can become teacher examples containing the source bundle, exact
citations, desired JSON, and a short evidence-grounded explanation of the decision.
They can support few-shot prompts, retrieval, and held-out evaluations for smaller
models. They should not be accepted solely because a larger model produced them.
Use fresh held-out sources to check generalization and preserve examples of
uncertainty and abstention. Luna's cited model page does not currently list
fine-tuning support, so examples in prompts/evaluations are the immediately
available approach.
