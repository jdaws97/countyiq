# Open Items

This is the single working backlog. Completed work belongs in git history and
durable architectural decisions belong in `docs/decisions.md`.

## Product

- Backfill real York intelligence events and run the alpha acceptance flow on
  current official evidence before inviting public trial traffic.
- Add server-side watchlist change detection and multi-device persistence if
  customer interviews validate the browser-local MVP.
- Conduct ten investor/developer interviews before committing to pricing or a
  paywall.
- Add an access-control decision for the distressed and delinquent-owner
  surfaces before broader distribution.
- Add a dedicated property timeline only if the embedded linked feed on case
  surfaces proves insufficient in user trials.
- Seek written YCPC clarification before source-identical exports, unusually
  long raw retention, or other delivery outside the derived-backend boundary;
  do not treat it as a categorical blocker to the current derived alpha.
- Obtain separate written YCPC/York County confirmation before reactivating
  `EcoDev_Candidates_Parcels` or the CDBG housing test service. Until then they
  remain in Dagster's unscheduled `paused_sources` group.
- Optional enrichment sources when entity matching needs more corroboration:
  IRS EO BMF (nonprofits), SEC EDGAR (public companies).
- Pass 4 escalation cascade: the Pass 1 cascade shipped 2026-08-06
  (`COUNTYIQ_PASS1_ESCALATION_MODEL`, off by default — enable once an
  escalation model is chosen). Apply the same abstention-routing pattern to
  Pass 4 synthesis once narrative data exists to evaluate on.

## Reliability and Data Quality

- Continue live checks for fragile public sources such as sheriff sales.
- Resolve the 12 paused municipal body policies. The gaps comprise Cross Roads
  and Railroad (no web presence); Shrewsbury Township/eCode360; Dover BOS and
  ZHB/Rep'd; West York/Google Drive; West Manheim BOS, PC, and ZHB/explicit
  robots disallows; and Franklintown, Newberry, and Washington/GoDaddy CDN.
  Resume only through a new reviewed migration after written permission or a
  municipality-hosted original is available.
- Recheck the active but currently unhealthy listings recorded in
  `docs/research/york-pa-municipal-source-static-audit-2026-08-27.json`.
  Browser validation has been completed for the successful pages with no
  static links and found no collectable supported documents; 403, 404, robots
  uncertainty, and no-document states remain visible and fail closed.
- Review the `policy_blocked_documents` count on each proceedings run. Mixed
  pages continue to yield approved first-party records, but a new external
  document origin remains excluded until a migration records a separate terms,
  robots, and origin review.
- Review tax-claim, sheriff, public-proceeding, and municipal-body policies
  before `2026-11-27`; review PLCB and green/open-data policies before
  `2027-02-27`. Update evidence and methods in a new migration rather than
  bypassing `authorize_source`.
- Do not invest in County Scout for the York alpha. It remains paused with zero
  runtime rows and no product/scoring dependency. Reconsider only for later
  multi-county expansion, and then only as candidate-only discovery with human
  rights approval before fetch, retention, monitoring, or promotion.

## Intelligence Pipeline

- Evaluate multi-parcel Pass 2 batching against the current per-parcel path
  using a judged, labeled sample before shipping that additional optimization.
- Measure the live candidate and token reduction from the shipped two-signal
  interpretive gate after the York parcel backfill; do not estimate savings
  from fixture counts.
- Human-review the expanded Pass 2 rubric labels, prioritizing the 20 selected
  high-disagreement cases and GLM's arm's-length, development-intent,
  rezoning-pressure, and development-readiness claims. Luna remains N=1 unless
  a changed challenger or prompt clears both the reviewed gold and this wider
  diagnostic.
- After the York backfill, refresh the ten-combination Pass 2 live shadow to
  measure actual interaction mix, token/cost distribution, latency, and drift.
  Do not use mutable live selectors as model-promotion truth.

## Operations

- Extend `/api/ops/health` from current-row presence to source freshness and
  last-run failure state; a populated but stale table is currently green.
- Set `COUNTYIQ_CORS_ORIGINS` if the production frontend is hosted on a
  different origin from the API; same-origin deployments need no entry.
- Keep `.env.example`, deploy scripts, and model-default documentation aligned.
- Add automated backup-restore verification when manual monthly checks become
  unreliable or burdensome.
