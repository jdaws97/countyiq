# Passes 0–3: useful records at lower cost

Implemented follow-up: [municipal intelligence product completion](pass03-product-completion.md)
adds property/watch connections, coverage, stage/context repairs and acquisition
prioritization. Its revised $5.55 backfill estimate supersedes the estimate here.

Follow-up: the [intelligence-gap review](pass03-intelligence-gap-review.md)
identifies useful omissions and downstream property/owner coverage gaps. The
quality percentages below measure source selection, not complete business-value
retention. The follow-up recommends targeted corrections before treating this
profile as a full replacement.

Validated September 7, 2026 against local York County records. The implemented
`records` profile estimates **$5.05 for the current backfill**, compared with the
starting estimate of $14–39 before owner briefs. The saving combines a cheaper
municipal reader, narrower paid identity work, and summaries assembled from
existing facts. It is not a claim of equivalent county-wide inferred coverage.

## What changed

| Pass | Implemented behavior | Cost consequence |
| --- | --- | --- |
| 0 | One GLM 5.3 Flash read per source; retain literal source passages and PDF page links | No discovery/review cascade or automatic stronger-model escalation |
| 1 | Resolve unambiguous exact PA DOS legal-name partitions without inference; pay for ambiguity in whole clusters connected to current plan or municipal activity | Defer speculative county-wide alias work; skip vote three when two valid partitions already agree |
| 2/3 | Assemble property investigation summaries and owner portfolio summaries from served records | No model call to render those summaries |

Pass 0 uses `z-ai/glm-5.3-flash`, high reasoning effort, FP8 providers, an
8,192-token maximum, strict structured output and no client retries. Provider
fallback stays within prompt/completion price ceilings of $0.16/$0.55 per
million tokens. The output is a source selection, not a generated assertion that
a proposal was approved, a parcel is implicated, or an investment is attractive.

The value filter removes recognizable standalone expense tables, check registers
and accounting appendices before inference. It skips accounting-only documents
and short cancelled-meeting notices when conservative checks establish that no
substantive record remains. Narrative project funding, contract awards, capital
work, development applications, enforcement changes and next dates remain in
scope. Unknown documents receive a semantic read. Accounting tables are not
treated as investment intelligence merely because they contain vendor names.

Source offsets, pages, original wording and source hashes are retained. Failures
remain failures, rather than becoming successful empty documents. Immutable
inference history and contradiction handling preserve prior decisions. The API
checks current source identity, metadata readiness and current municipal source
permissions before exposing a selection. New municipal cards appear at the
municipality level; they do not create guessed parcel links.

Pass 1 preserves complete candidate clusters and existing abstention rules.
Different official registrations do not become a corporate affiliation through
the free tier. `COUNTYIQ_PASS1_SCOPE=all` retains the optional broader workflow.
The default `active_records` scope defers 5,833 clusters in this snapshot, so
county-wide alias recall is deliberately lower. Recorded-name portfolios remain
available. Existing paid signal validation and generated briefs remain optional;
the new summaries provide sourced facts and verification questions with less
inferred interpretation.

## Quality and model selection

The primary agent reviewed all selections against frozen topic references.
These are agent-reviewed evaluations, not independent human certification.

| Final GLM development evaluation | Result |
| --- | ---: |
| Documents / cards | 44 / 323 |
| Useful-topic coverage | 274 / 291 (94.16%) |
| Material-topic coverage | 209 / 215 (97.21%) |
| Document-average topic coverage | 92.89% |
| Relevant selections | 91.33% |
| Correct semantic context | 96.90% |
| Self-contained selections | 95.67% |
| Duplicate selections | 0.62% |
| Critical invented or inverted claims observed | 0 |

The original denominator was 298 topics: seven standalone expense entries were
removed only after the user explicitly changed the desired product scope.
Unadjusted coverage is 274/298 (91.95%). This scope change is separate from model
quality. Matching a topic means retaining its subject, not every possible detail.

Six fresh documents were frozen after the final prompt and policy: all 16
reference topics were retained, three cancellation controls produced no cards,
and one of 18 selections was irrelevant. Eight negative controls passed across
the development and fresh sets. All frozen acceptance thresholds passed.

There are still ten contextual defects in the development output, principally
neighboring fragments in flattened source lines and missing budget-year headings.
Several useful updates were missed. OCR and source layout remain limitations;
the evaluation does not establish perfect extraction or investor outcomes.

DeepSeek V4 Flash was tested with thinking enabled, low/high reasoning, strict
schema and ordinary JSON with the full contract, larger output limits and
alternate providers. Some completed selections were useful. Larger cases
timed out or consumed their 8,192-token allocation in reasoning without a valid
answer; a final larger-allocation provider attempt was rejected upstream. On one
completed common source, DeepSeek cost $0.001590 versus GLM's $0.001457.
DeepSeek's lower token price did not yield a dependable cheaper completed reader
in these trials. The JSON contract support remains available for explicit
experiments, but GLM is the selected evidence-profile default.

## Costs

The snapshot contains 175,928 parcels, 148,461 owners and 6,459 proceedings.
Planning uses no-cache rates and 1,500 billed output tokens per GLM call,
including reasoning; the measured development mean was approximately 992.

| Current records-profile backfill | Planning calls | Estimated cost |
| --- | ---: | ---: |
| Pass 0 eligible sources | 3,504 | $4.4390 |
| Pass 1 paid work, 138 clusters | 289 | $0.6061 |
| Pass 2/3/owner summaries | 0 | $0 |
| Total | 3,793 | **$5.0452** |

The runtime reservation/output ceiling is $35.54, not expected spending. A
cumulative authorization cap stops before exceeding its amount; a $5 cap does
not guarantee completion of this estimated $5.05 backfill. OCR costs remain
unpriced where extraction is required; this particular eligible snapshot has
zero such rows. This estimate does not price unrelated infrastructure or source
acquisition.

The last 365 meeting-date days contain 675 eligible sources, estimated at $0.80
to process, or **about $0.067 per month** at that observed volume. This is a
meeting-date scenario, not a measured forecast of incoming documents. Even
reprocessing all 138 currently paid identity clusters every month adds about
$0.61, giving a conservative illustrative **$0.67/month** combined scenario.
Actual identity churn is unmeasured; unchanged source/config hashes permit reuse.

The entire optimization experiment charged **$0.721509246 against the original
$5 test authorization**, with no outstanding reservations. This is conservative
budget accounting: unknown-cost failures consumed their full reservation, so it
is not an exact provider invoice. The selected 44-document run reported
$0.040421 and the fresh six-document run $0.002659. No full paid backfill or
production deployment was performed.

## Verification and operation

The required non-integration pipeline suite passed: **1,665 tests**, with 124
integration tests deselected. The Dagster definitions import passed. API unit
tests passed **129 tests**; the municipal evidence integration suite passed
**9 tests** against isolated Postgres. Frontend TypeScript, ESLint, formatting
and the earlier production build passed. Local browser checks cover property,
owner and municipality views, mobile layout, source expansion and PDF links.
Newberry pagination was verified at 12 initial cards and 16 after expansion on
desktop and mobile. A source marked `review_required` was correctly withheld;
the final pagination sample uses eligible, reviewed GLM selections.

Ruff passes for the other changed Python files. The broader check reports six
pre-existing violations in the legacy `proceeding_extraction.py`: two import
issues and four broad exception handlers. The orchestration ledger validator
also retains a pre-existing malformed record; this work did not rewrite it.

Migration 067 provides retained municipal evidence. `.env.example` selects
`COUNTYIQ_PASS0_MODE=evidence` and `COUNTYIQ_PASS1_SCOPE=active_records`, with
paid passes disabled. Enablement still requires the applicable current quality
receipt, provider price ceilings and a cumulative spend authorization. A
Pass 0 receipt does not approve Pass 1 identity merges or paid Pass 2/3 judgments.

Reproduce the estimate from `pipelines/`:

```bash
DATABASE_PORT=5433 COUNTYIQ_PASS0_MODE=evidence PYTHONPATH=. \
  .venv/bin/python scripts/estimate_llm_backfill.py \
  --profile records --sample-size 300
```

Local evidence is under `output/pass03-optimization/`: `records-final-estimate.json`,
`quality-evaluation.json`, `primary-quality-final.json`,
`primary-quality-holdout.json`, `quality-receipt.json`, `glm-high-full/`,
`glm-release-holdout/` and `openrouter-budget.json`. Browser screenshots are in
`output/playwright/`, including `newberry-16-desktop-after.png` and
`newberry-16-mobile-after.png`.
The quality receipt binds the current code/config identity and the evaluation
artifact hash. Changing the bound code, model or settings invalidates it.
