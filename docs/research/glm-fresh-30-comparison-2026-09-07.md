# Record explanation comparison on 30 fresh cases

September 7, 2026. Completed within the existing cumulative $5 test authorization.
No production configuration, quality receipt, or served explanation was changed.

## Result

Luna performed better on this fresh set than GLM through Sail Research: it
completed validation on all 30 cases and preserved municipal decision filters
more consistently. GLM's reported model cost was 37.0% lower, but it retained
classification problems and an unsupported property-boundary inference.

**This does not reproduce the earlier NextBit comparison.** NextBit returned
three upstream shared-pool rate-limit errors before producing any model output.
Sail Research was then added as a separately identified GLM provider, using the
same frozen cases and model settings. Results from the two providers were not
pooled. Sail also returned three rate-limit errors during its run; after
cooldowns, the remaining requests completed.

| Model and pinned provider | Effort | First validation | After at most one completed correction | Correction outputs | Reported model cost |
|---|---|---:|---:|---:|---:|
| Luna / OpenAI | low | 29/30 | 30/30 | 1 | $0.01763696 |
| GLM 5.3 Flash / Sail Research FP8 | low | 28/30 | 28/30 | 2 | $0.01111314 |

Costs include completed failed outputs and corrections, with actual caching.
The table excludes conservatively charged reservations for HTTP 429 responses
that supplied no usage. Validation is not a factual-accuracy score.

## Source review

The primary agent reviewed all 30 source bundles and both models' outputs,
including the final corrections. Review was not blinded to model/provider.

- **Luna's stronger municipal classification:** it retained approval tags for
  the passed volleyball-removal and committee motions, and upcoming-decision
  tags for proposed payment, grant-application, appointment, and contract
  actions. GLM omitted the upcoming-decision tag on at least six explicit
  proposed motions: `10415-1`, `10488-2`, `10406-3`, `10415-4`, `10262-6`, and
  `10406-4`. It classified both passed motions (`8766-8`, `8766-9`) as updates,
  omitting approval tags. Those omissions affect customer filters even when
  the prose describes the action correctly.
- **GLM's unsupported interpretation:** the Wyntre Brooke property summary
  says matching ownership and sale records suggest the plan area may span both
  holdings (`54000HI0327G0`). The supplied ownership records and planning point
  do not establish which parcels the plan includes. Its committee headline
  also adds “establishing” where the supplied minutes only say the committee
  was approved (`8766-9`). The Alarm Systems Code item is classified as
  land-use policy without a supplied land-use connection (`10688-8`).
- **Luna still loses meaningful property context:** the Thornton summary omits
  both newer touching purchases: 2996 Cape Horn Road on February 12, 2020 and
  565 Chapel Church Road on February 11, 2020, versus the subject's July 2017
  sale (`54000HJ0091A0`). It also emphasizes the older 2023 building plan without
  explaining the newer 2025 subdivision inventory. GLM retained some newer
  adjoining acquisition context, but its Thornton response exceeded the length
  limit. Luna also adds unsupported `condition` and `recommendation` tags to
  the road-payment and wellhouse-quote cases (`10415-4`, `10262-6`).
- **The shared quote failure is an OCR-contract issue:** both first responses
  correctly preserve the projected October 15, 2026 completion date for Hoff
  and Mill roads (`10488-3`). Both remove a stray standalone `o` from the exact
  supporting quote. Luna's correction restores it; GLM's correction still
  omits it. This is quote fidelity, not a fabricated date.
- **GLM's other remaining validation failure is length:** the Thornton summary
  falls from 149 to 143 words after correction, still above the 140-word cap.
  Neither the prompt nor validator was changed to obtain a pass.

These results favor Luna over this Sail Research configuration for municipal
classification. They do not establish that Luna is universally better than GLM,
invalidate the previous NextBit quality results, or approve either configuration
for an unattended full backfill. NextBit availability remains unproven for this
new cohort, and both tested GLM providers interrupted this session with 429s.

## Method and verification

- Thirty previously untested subjects: 26 municipal records from seven source
  documents and four property bundles. No subject or complete municipal passage
  repeats the preceding 30-case comparison. These are new passages and parcels,
  **not a holdout of entirely new documents**. Selection was frozen before
  dispatch using deterministic ordering, two ranked properties, and two
  municipal-linked properties.
- The frozen case file's SHA-256 is
  `86fff20dea0a21482b010ffd5013ae3d75e6e4c89e7c60b93ba83614cc82b913`.
- Production and evaluation use the shared configuration builder. GLM requests
  used low effort, temperature 1, top-p 0.95, and 4,096 output tokens; Luna used
  low effort and 2,048 output tokens. Strict schema, FP8 for GLM, provider pins,
  disabled fallback, and price ceilings were retained. Sail reported zero
  reasoning tokens in every final response; the archived request establishes
  the requested effort but cannot independently prove internal provider behavior.
- Every completed request was recomputed against the current builder, including
  the exact production correction prompt. Every source matched its frozen
  bundle, provider/model identifiers matched the assigned arm, and every
  accepted output passed offline revalidation. Resumed requests matched the
  original requests; already completed cases were not rerun.
- There were 63 model outputs and six HTTP 429 failures. Reported model cost was
  **$0.02875010**. Unknown-cost reservations were conservatively forfeited for
  **$0.026431168**, making this run's total budget charge **$0.055181268**.
  Cumulative budget charged is **$1.026869496 of $5**, with **zero outstanding
  reservations**. The forfeited amount is not a claim of actual provider billing.

Artifacts under `output/backfill-readiness/`:

- `comparison-fresh-30-plan.json`, `comparison-fresh-30-provider-addendum.json`,
  and `comparison-fresh-30-cases.json`: frozen selection and provider change.
- `comparison-fresh-30-results.json`: counts, accounting, request/source checks,
  transport failures, and hashes/paths of final results.
- `comparison-fresh-30-source-review.json`: case-specific review findings.
- `fresh30-*/`: immutable requests, sources, responses, configurations, and costs.
- `audit_fresh_comparison.py`: offline verification; executed successfully and
  passed Ruff formatting/lint. No application code changed during this test.
