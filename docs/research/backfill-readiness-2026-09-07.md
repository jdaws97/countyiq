# Backfill readiness and summary-model comparison

September 7, 2026. Local implementation and primary-agent review; no production
deployment, full backfill, or human customer pilot.

## Harness correction after model-comparison review

The [Luna max comparison across every pass](luna-max-all-passes-2026-09-07.md)
is complete. Max improved selected source context, property chronology, and the
small investigation-brief set, at 2.8–18.9 times the completed-workflow cost of
the lower-effort Luna baselines. The report separates reasoning charges and
capacity retries, calculates ordinary grouped Sol requests without a Batch API
discount, and covers subscription-based teacher examples. No production model
configuration or quality release was changed.

The follow-up on 30 fresh subjects is also complete: see
[the fresh-case comparison](glm-fresh-30-comparison-2026-09-07.md). NextBit was
rate-limited before producing output, so GLM was separately tested through Sail
Research. Luna reached 30/30 final structural passes versus GLM/Sail's 28/30;
GLM's reported model cost was 37.0% lower. Source review favored Luna's municipal
classification on this set while finding property-context omissions. This does
not retest NextBit quality, and no production-quality receipt was issued.

The corrected live comparison is now complete: see
[the comparison report](glm-harness-comparison-2026-09-07.md). GLM low effort on
NextBit reached 30/30 structural passes after two corrections, versus Luna's
30/30 after one, at 28.2% lower measured cost. Source review still found material
issues in both; no new production-quality receipt was issued.

The earlier model comparison is insufficient to reject GLM. The explanation
asset and comparison script overwrote its sampling preset, provider routing
mixed four GLM providers, and two residual format failures were recoverable
without changing factual prose. The decision below records the earlier tested
configuration; its quality receipts are now stale after the shared harness fix.
Paid execution remains disabled pending a reviewed calibration of the new code.

Production and evaluation now share model defaults: GLM uses temperature 1,
top-p 0.95, and default output limits of 4,096 tokens at low effort or 8,192 at
high/max effort. Explicit token limits remain authoritative. Truncation retries
use max → high → low for GLM and reject unsupported efforts before dispatch.
Known grouped citations and typographic quotation differences normalize;
unknown citations, changed quote wording, and unsupported dates still fail.

The canary requires one provider with fallback disabled and archives its exact
request, configuration, served model, and provider. It refuses to mix changed
requests into an existing output directory. Strict-schema routing fails closed
by default. An explicit general-harness fallback includes the schema in the
prompt and records the downgrade; record explanations always require strict
schema. Quality identities now include shared harness source hashes and routing,
schema, and price settings.

Verification: 1,727 non-integration pipeline tests passed, including configuration
parity, GLM retry, citation/date, routing, and receipt invalidation regressions.
Both original formatting failures pass offline replay in
`output/backfill-readiness/glm-harness-fix-replay.json`; no new inference was run.
This establishes harness compatibility, not a new semantic quality approval.

## Decision

**GO on technical/product readiness for the tested configuration: GLM 5.3 Flash
document reading plus Luna record explanations. NO-GO on claiming the expanded
backfill costs about $6, or substituting the tested cheaper explanation models
without further qualification.** Paid execution remains disabled. The user has
not authorized a larger full-backfill spend.

The original GLM document-reading scope is still estimated at **$4.57** for 3,504
eligible documents. The additional per-selection explanation design accounts
for the increase: approximately 14,000–42,000 municipal explanations, plus a
bounded property set. That scope increase should have been made explicit before
quoting the combined estimate.

The working summaries and UI now satisfy the four product-readiness checks in
[the original assessment](customer-intelligence-ui-review-2026-09-07.md).
The cheaper model comparison does not establish a replacement of equal quality.
It is a reason to keep the cost/model decision explicit, not to silently launch
the more expensive configuration.

## Delivered behavior

- Property reports combine current source facts and accepted municipal passages
  into cited explanations. Municipal explanations are available independently
  of opportunity rank. Source excerpts and deterministic findings remain the
  fallback when generation fails.
- Feed labels and hearing filters use the interpreted action and retain its
  scope. Proposed, scheduled, expected and passed dates remain distinct.
- Exact source receipts resolve from inline citations. Changes to sources,
  property facts, associations or permissions retract stale explanations and
  dependent events. Existing owner identities are reused; this release does not
  approve additional identity merges.
- Each item gets at most one content-correction attempt. A second invalid result
  leaves the source evidence available. Transport failures do not trigger another
  paid attempt in this path. No model can create property links or alter scores.
- Owner portfolio sale dates now sort chronologically, including county
  `DD-MON-YYYY` strings. BARLEY FARMS 2 LLC correctly shows December 1, 2025,
  at 2934 Cape Horn Road as the latest recorded sale.

## Model comparison

The same frozen source bundles and unchanged explanation prompt were used.
Validation counts below include production-compatible JSON parsing and current
source/date checks. These counts are **not factual-accuracy scores**.

| Configuration | First-pass validation | After bounded corrections | Primary finding |
| --- | ---: | ---: | --- |
| Luna, low effort, 2,048 output-token limit | 29/30 | 30/30 | Accepted for this release after source review. One incomplete source date required correction. |
| GLM 5.3 Flash, FP8 providers, low effort, 4,096 limit | 23/30 | 28/30 | Readable and promising, but not approved as a replacement. Seven items needed correction; two still failed. Additional source overstatements remained in otherwise well-formed output. |
| DeepSeek V4 Flash 0731, FP8 providers, reasoning disabled, 2,048 limit | 7/20 | Not pursued | Frequent missing citations, an invented date, and a proposed award represented as a completed decision. This specific configuration failed the acceptance bar. |

GLM source-review examples include a property next step treating a very-limited
septic screen as proof that septic is largely infeasible, and wording that
extends a parcel's zoning record to an administrative district. The source
supports neither stronger claim. A 30-case higher-effort GLM comparison did not
eliminate the classification and citation problems. This is evidence about the
tested prompt/provider configurations, not a general claim that these models
cannot summarize.

The initial unrestricted-provider Flash comparison was stopped after output
truncation and a provider reporting more output than requested. Unsettled calls
retain their full reserved charge in the original testing ledger. No allowance
was reset. All subsequent trials remained within that original $5 authorization.

The final Luna 30-case cohort, including its correction, cost about **$0.0187**.
The GLM low-effort cohort, including seven corrections, cost about **$0.0154**,
while delivering fewer acceptable results. These are actual routed cohort costs;
caching, provider choice and correction frequency make token-list prices an
incomplete predictor of the real saving. All session testing is charged against
the same ledger, approximately **$0.885 of $5**, with no outstanding reservations.

Provider listings were checked on September 7. The complete model and endpoint
responses are archived with the comparison; estimates use observed routable
prices rather than assuming every advertised minimum provider is suitable.

## Cost and execution scope

| Selected work | Model | Planning cost |
| --- | --- | ---: |
| Complete municipal-document reading | GLM 5.3 Flash | $4.57 |
| Municipal and property explanations | Luna | $17.79–$53.17 |
| Additional identity merges, Pass 2, owner briefs, county narratives | Omitted | $0 |
| Combined expanded profile | GLM + Luna | **$22.36–$57.74** |

The central scenario is approximately **$43.40**. The range extrapolates the
observed minimum/mean/maximum selections per document from seven reviewed
documents; it is neither a confidence interval nor a hard bound. Recount after
the document-reading pass. The property synthesis set is capped at 500 ranked
properties plus 1,000 recently municipal-linked properties, with overlaps removed.

Planning assumes 600 billed output tokens per municipal explanation and 1,000
per property explanation, no cache discount, and a 5% correction rate for the
approved Luna configuration. These are conservative planning assumptions; the
canary averaged about 300 and 590 output tokens respectively. The estimate must
not be reused as a GLM estimate with the observed higher correction rate.

A reviewable expanded-run spending envelope is **$65 total**, split into persistent
Pass 0 and Pass 3 authorizations of $10 and $55. This is a proposal, not an issued
authorization. Existing runtime gates require both quality approval and durable
authorization before a paid job runs; restarting does not reset the allowances.
If a limit is reached, processing stops with a partial backfill. Merely switching
on an environment flag is insufficient. Deterministic jobs remain free of model
calls, and no new schedules enable paid work.

The original approximately-$6 expectation remains appropriate for the original
document-reading scope. Changing only the explanation model does not remove the
new per-passage call volume. Batching or reducing that volume is a separate design
change; it has not been implemented or claimed as a validated saving here.

## Acceptance evidence

- 30 actual local browser cases: 26 municipal explanations and four properties.
  All rendered with resolvable citations and no explanation-container overflow.
  Cases cover church final-plan consideration, liquor-license hearings, rezoning,
  routine extensions, expected openings, contract stages, budgets, soils and
  adjoining-property acquisitions.
- Primary screenshot review at 1,440 and 390 pixels; no mobile horizontal
  overflow. Clicking a citation opens its corresponding receipt. Hearing
  filtering and the corrected owner date were checked in the live local app.
- 1,694 pipeline tests passed; 124 integration-marked tests excluded. The 17
  definitions/wiring tests passed. Migration 067 through 069 upgraded successfully
  on the isolated test instance, in addition to the seeded API database checks.
- 282 API tests passed, including source invalidation, permission revocation,
  event replacement, hearing tags, and private watch behavior. The five focused
  explanation integration tests also passed after the final validation changes.
- Frontend TypeScript, lint, build and both date regressions passed. Build retains
  the existing warning about large map-related bundles.

Artifacts are under `output/backfill-readiness/`: frozen sources, unedited provider
responses, current-validation reports, the read-only estimate, browser receipts,
screenshots, test logs, local import receipts, and the version-bound quality
receipt. Existing dirty work was preserved.
