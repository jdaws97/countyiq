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
## Intelligence Pipeline

- Decide the Pass 0 and Pass 1 model defaults from the 2026-09-02 confirmation
  runs in `docs/research/llm-cost-reduction-2026-09-02.md`: GLM 5.3 Flash for
  Pass 1 and Gemini 2.5 Flash-Lite for Pass 0 both matched or beat Luna on the
  frozen corpora at a fraction of the cost, but the corpora are small. Promote
  by setting `COUNTYIQ_PASS{N}_MODEL` for the first canary rather than editing
  the code defaults until the canary's gate pass rate and sampled audit hold.
- Person-only Pass 1 clusters now default on after the 2026-09-04 audit; size
  and fund that larger canary/backfill estimate rather than silently disabling them.
- Re-run `pipelines/scripts/backtest_radar_weights.py` after the first live
  proceedings backfill and refresh `OPPORTUNITY_WEIGHTS` with the regenerated
  report; `municipal_action` and `entity_assemblage` currently carry priors
  because the local corpus had too few rows to calibrate them.
- Human-review a sample of Pass 0 `_no_landuse_terms` prefilter skips after the
  first backfill to confirm the vocabulary list has no false negatives.
- Measure the wall-clock and spend effect of `COUNTYIQ_PASS2_CONCURRENCY` and
  the fingerprint fast path on the first real Pass 2 run.
- Evaluate multi-parcel Pass 2 batching against the current per-parcel path
  using a judged, labeled sample before shipping that additional optimization.
- Measure the live candidate and token reduction from the shipped two-signal
  interpretive gate after the York parcel backfill; do not estimate savings
  from fixture counts.
- The refreshed 20-case Pass 2 release subset was reviewed on 2026-09-04 by
  OpenAI Codex GPT-5.6 Sol at the product owner's direction
  (`docs/research/pass2-rubric-review-2026-09-04.md`); its hash-bound receipt
  lives under ignored `receipts/`. The remaining 80 expanded cases still carry
  generated labels. After the first Pass 2 run the preflight's live gate pass
  rate replaces the receipt.
- After the first Pass 1 backfill, review the person/organization merge queue
  (`review_intelligence_contradictions.py list`) as one batch session; every
  other same-evidence flip is resolved by the recorded policy.
- Choose and budget a judge model (`COUNTYIQ_JUDGE_MODEL`) once the first
  backfill shows how many routine flips occur; the 2026-08-30 probe found
  `x-ai/grok-4.6` matched the human winner on all three bakeoff cases.
- Run the weekly sampled audit (`sample` → `approve` / `reject`) and promote
  reviewed candidates into the frozen eval corpus with `eval.build_fixtures`.
- After the York backfill, refresh the ten-combination Pass 2 live shadow to
  measure actual interaction mix, token/cost distribution, latency, and drift.
  Do not use mutable live selectors as model-promotion truth.

## Operations

- Set `COUNTYIQ_CORS_ORIGINS` if the production frontend is hosted on a
  different origin from the API; same-origin deployments need no entry.
- Keep `.env.example`, deploy scripts, and model-default documentation aligned.
- Run and record the first live R2 restore drill, enable/monitor the persistent
  systemd backup timer, and verify R2 bucket-lock/lifecycle settings plus
  Hetzner deletion protection and server backups on the actual account.
- Decide when deployment volume justifies publishing signed/SBOM-attested
  images to a registry instead of building exact-SHA images on the VPS.
- Complete a live external security/load scan after Cloudflare and the Hetzner
  origin exist; repository checks cannot validate WAF, firewall, TLS, SSH, or
  real proxy behavior before deployment.
