# Record explanation comparison after harness corrections

September 7, 2026. Completed under the existing $5 cumulative test authorization.
No production configuration, quality receipt, or served explanation was changed.

Follow-up: [30 fresh cases](glm-fresh-30-comparison-2026-09-07.md) completed with
Luna and GLM/Sail Research because NextBit was rate-limited. The provider change
means that follow-up does not reproduce the NextBit results below.

## Result

GLM 5.3 Flash at low effort through NextBit is the best-value candidate in this
comparison. It reached the same final structural-validation rate as Luna while
costing 28.2% less. Increasing GLM effort did not improve validation results.
The large NextBit/Parasail difference means the result belongs to the tested
model, provider, and settings together, rather than to a model name alone.

| Model and pinned provider | Effort | First validation | After one permitted correction | Correction calls | Actual cost, 30 cases |
|---|---|---:|---:|---:|---:|
| GLM 5.3 Flash / NextBit FP8 | low | 28/30 | 30/30 | 2 | $0.01332983 |
| GLM 5.3 Flash / NextBit FP8 | high | 26/30 | 29/30 | 4 | $0.01882675 |
| GLM 5.3 Flash / Parasail FP8 | high | 19/30 | 29/30 | 11 | $0.02306550 |
| Luna / OpenAI | low | 29/30 | 30/30 | 1 | $0.01855836 |
| DeepSeek V4 Flash / Parasail FP8 | none | 14/30 | 24/30 | 16 | $0.01318450 |

Validation is not factual accuracy. Primary review found unsupported statements,
missing material context, or incorrect filtering metadata even among responses
that passed validation. None of these runs earns a clean production-quality
approval. The evidence supports retaining GLM/NextBit/low as the preferred
candidate; it does not support paying more for Luna solely on a claim of superior
factual quality, or selecting GLM high effort as an improvement.

## Material findings from source review

The review covered the final outputs against the supplied source bundles, not
just the JSON pass/fail flags. Examples that explain the decision:

- **GLM low / NextBit:** the emergency pump-repair summary says authorization
  happened “without prior approval,” which the source does not state
  (`holdout-8766-2`). The mini-storage summary says no plan document exists yet;
  the source only says a first draft is expected at a later meeting
  (`holdout-9659-3`). Its property summaries retained current zoning, severe
  septic screening limitations, proposed hearing status, and the newer adjoining
  purchase in the farm case. Its two validation failures—an inferred YMCA tour
  month and an unsupported hearing tag on an ordinary steering committee
  meeting—were corrected by the existing bounded correction prompt.
- **GLM high / NextBit:** it repeats the unsupported claim that no mini-storage
  draft exists (`holdout-9659-3`). The corrected restaurant property summary
  retains adjoining ownership but drops the newer adjoining acquisition date
  (`property-54000JJ0083A0`). It needed four content corrections, and the
  110 Yoe Drive hearing still failed its quote check. Higher reasoning therefore
  did not produce a better accepted-output rate or a cost advantage over Luna.
- **Luna / OpenAI:** the farm summary omits the December 2025 purchase of touching
  2934 Cape Horn Road and asks to verify whether a rezoning was adopted despite
  the supplied current zoning record already recording adoption
  (`property-54000HJ012400`). The data-center/solar hearing item omits the
  `hearing` filter tag (`municipal-10415-8`). The liquor-license item uses a
  scheduled record status despite its recommended date remaining proposed
  (`municipal-10688-12`). The Water Street road-work summary drops the governing
  2027 budget year (`holdout-9659-8`). These are gaps in useful content and
  filtering, not JSON failures.
- **GLM high / Parasail:** repeated extra hearing and completed-decision tags
  caused many first-pass rejections. Even a structurally accepted church
  property summary says “no new lots” where the planning record supplies one
  proposed lot (`property-30000DE0017L0`). Other accepted records add unsupported
  continuance tags, and an emergency-repair summary invents the absence of
  prior meeting action. The remaining structural rejection is the mini-storage
  record, which still introduces an unconfirmed completed decision.
- **DeepSeek without reasoning / Parasail:** six records still fail after one
  correction, including unsupported dates/times, missing citations, and false
  hearing or completed-decision tags. Its structurally accepted church property
  summary reverses the chronology by describing October's recommendation as
  occurring after November's waivers (`property-30000DE0017L0`). This tested
  configuration is not a suitable replacement. It does not establish the
  quality of other DeepSeek providers or reasoning settings.

No prompt, validator, source, or model prose was changed during the comparison.
No third attempts or semantic repair prompts were used to manufacture a pass.

## Method and accounting

- The same 30 frozen bundles were used in every run: 26 municipal records and
  four property bundles, combining the previous 20-case set and 10-case holdout.
  These are regression cases already used in earlier development, not a fresh
  population sample. The source review was performed by the primary agent and
  was not blinded to model identity.
- Production and evaluation share the corrected model configuration builder.
  GLM used temperature 1 and top-p 0.95, with default output limits of 4,096 at
  low effort and 8,192 at high effort. Luna used low effort and 2,048 tokens;
  DeepSeek used reasoning disabled and 2,048 tokens. All requests required
  strict schema, used one pinned provider with fallback disabled, and retained
  provider price ceilings. Endpoint listings were captured immediately before
  the runs.
- Each completed structurally invalid response received at most one correction
  using the production correction prompt and its original source. All costs
  include failed and correction calls, including billed reasoning. Actual cache
  discounts are included; these are measured cohort costs, not a guaranteed
  backfill rate or an uncached pricing comparison.
- Every archived request was recomputed and compared with the current builder;
  every archived source matched its frozen case; all returned providers and
  model IDs matched their assigned arm. Every accepted result was revalidated.
- There were **184 paid calls costing $0.08696494**. Cumulative testing spend is
  **$0.971688228 of $5**, with **zero outstanding reservations**. No full
  backfill or production deployment was launched.

Artifacts in `output/backfill-readiness/`:

- `comparison-fixed-harness-plan.json`: configuration and acceptance rules
  recorded before dispatch.
- `comparison-fixed-harness-cases.json`: frozen shared case set.
- `comparison-fixed-harness-results.json`: exact counts, costs, request/source
  verification, remaining failures, and hashes of final result files.
- `comparison-fixed-*/` and `comparison-corrected-*/`: immutable requests,
  configurations, original sources, provider responses, and parsed results.
