# Pass 2 parcel-link review — September 8, 2026

Pass 2 could confirm a subdivision as relevant to a particular parcel while its
explanation admitted that the plan's parcel coverage was unknown. The candidate
query admits plan points within 30 metres under `active_subdivision`; the label
alone therefore cannot establish participation in the proposal.

The revised prompt and acceptance gate require consistent `point_on_parcel`
metadata before an active-subdivision result can be confirmed, upgraded, or
assigned medium/high significance. A supplied distance must agree with that
classification. Nearby, unknown, and conflicting locations remain low/none
screening results. A displayed zero distance cannot override a proximity-only
classification. Even a consistent mapped point establishes neither the entire
plan boundary, applicant/owner participation, approval, nor construction start.

This is a focused correction to interpretation and acceptance. The candidate
records remain available for source review and neighborhood context. Rejected
model responses follow the existing validation-rejection path and cannot update
the active evidence projection.

## Evidence and validation

The native subscription comparison found this failure in both cheaper candidates
and Astra. Astra's original `p2x-089` confirmed a plan one metre away without an
established parcel link; `p2x-051` confirmed a plan with a zero distance and a
`within_30m_of_parcel` classification. Both are now downgraded to low significance
in the fresh Astra evaluation.

- 1,948 pipeline tests passed, with 137 integration tests deselected.
- Twenty new regressions cover the observed failures, unknown locations,
  conflicting distances, unsafe priority/status combinations, and valid mapped
  point controls. Ruff formatting and lint passed for all changed Python files.
- All 34 fresh Astra fixture responses passed the production acceptance gate.
  This includes ten historical pairs, twenty required stability cases, and four
  municipal feature cases. The primary AI reviewer read every complete response
  against the unchanged source contexts. Observed runtime: 696.365 seconds.
- Eight frozen live York City contexts also passed with the new system policy
  and individual native requests. The primary reviewed all responses: nearby
  plans remained unlinked, while the eight-unit mapped proposal was retained.
  Runtime: 230.934 seconds. These live regressions retained the original user
  prompts; the 34-case evaluation used the current maintained prompt builder.

Historical gold scores remain **8/34**, including **4/4 municipal feature cases**.
The labels were not rewritten. Several historical expectations conflict with
current missing-footprint, parcel-link, and neighbor-population policy; lexical
checks also penalize valid phrasing. This does not justify ignoring actual source
errors. The original failed outputs and scores remain available for comparison.

The revised sample preserved the reviewed source distinctions, but completeness
and priority calibration remain limited: for example, `p2x-086` retained the
tax-claim neighbor count without naming that neighbor or its supplied $254.94
balance. Small selected samples are not countywide accuracy evidence.

## Operational scope

The source review supports a bounded Astra/medium Pass 2 production canary after
deployment and an exact configuration-bound quality receipt. Inspect its source
decisions before expanding the backfill. Keep runtime disabled until then.
The September 8 production audit found zero active evidence rows and zero
accepted Pass 2 history rows, so there was no existing accepted population to
retract during this review. Future retries must preserve ordinary contradiction
handling and source-freshness checks.

Native receipts, complete outputs, source snapshots, and the primary review are
retained under `output/subscription-model-comparison-2026-09-08/`. The revised
fixture run is `pass2-astra-parcel-link-v2/results.json`; the live run is
`live-pass2-gpt-6-astra-trial2-individual/results.json`. No paid API calls or reset
credits were used.
