# LLM product enhancements and release gates

Implemented 2026-09-04. These changes are code-complete candidates, not evidence
that a new model or prompt has passed a paid evaluation.

## Source and metadata readiness

The [September 4 municipal cleanup](../research/municipal-source-cleanup-2026-09-04.md)
is applied to the local real-data database through migration 058. It preserves
source evidence while quarantining 925 wrong-jurisdiction documents and 30 exact
duplicates. The reviewed recent pool contains 494 documents across 46 municipalities.
The [30-document baseline pilot](../research/municipal-llm-pilot-results-2026-09-04.md)
has completed. Its [corrections and revised evaluation plan](../research/municipal-llm-fixes-2026-09-04.md)
are implemented. The [revised paid evaluation](../research/municipal-llm-v2-results-2026-09-04.md)
has completed, and local real data is on migration 061. The extraction contract
still fails the quality release decision; no proceeding extraction was published. Metadata eligibility does not replace the extraction quality gates
below. Replacement sources remain paused pending collection and policy release.

## Latest Pass 0 evaluation

The [September 5 readiness evaluation](../research/pass0-readiness-2026-09-05.md)
is complete. Its final source-qualified candidate meets the frozen real-document
coverage and discovery thresholds in regression/repeated-generation checks.
The holdout informed the final fixes, so this is not independent blind evidence.
The engineering recommendation is a reviewed, capped rollout after the existing
quality signoff and preflight. No quality receipt or backfill authorization was
issued by this evaluation; customer publication remains gated.

## Customer behavior

- Project case files combine accepted source events into a conservative recorded
  status, decision history, conditions to verify, and dated milestones. Same-day
  disagreements remain visible; later activity does not silently repeat an old
  approval. Dates without a full unambiguous year/month/day remain source wording.
  This does not establish permits, construction readiness, or condition satisfaction.
- Parcel and owner briefs use investigate, watch, or insufficient_evidence.
  Urgency is none. Missing evidence becomes a verification step; ownership, tax
  balances, proximity and shared addresses do not prove intent or motivation.
- Cross-signal prose uses the existing clickable evidence renderer. Assessment
  badge colors match the current assessment vocabulary.
- Every entity membership merge or split waits for human contradiction review,
  including person-to-person and organization-to-organization changes.
- Verified accounts retain watches, saved searches, comparisons and recent
  investigations across devices. Guest browser work stays separate until explicitly
  imported. Account setup, isolation and conflict recovery are documented in
  [account workspaces](account-workspaces.md).
- The deterministic event refresh creates a durable unread inbox for newly detected
  matching events. Rebuilds do not duplicate the same event key. Existing history is
  not an initial alert blast. Source policy is reapplied when inbox content is read.
  Acknowledgement only marks the displayed IDs in the authenticated workspace.
- Browser notifications require an explicit user opt-in and an open application.
  This is not background web push or email delivery. The unread inbox persists while
  the app is closed. Clearing saved work retains the account identity. Local
  conflict recovery and portable exports remain available.
- Home search has a dedicated responsive submit button and plain wording. Radar
  exposes product signals instead of an internal score-version label.

## Cost controls

Project chronology, watch matching, inbox summaries and viewing cached briefs make
no model calls. Reuse existing accepted extraction facts for these features.
Pass 2 remains selected for interacting interpretive signals; deterministic flags
do not need narrative validation. Brief prompts ask for concise investigation
summaries. Keep optional search inference, county narrative generation, judges and
escalation disabled until their separate value and budget are established.

No new per-token price assumptions or measured dollar savings are claimed here.
Measure provider-reported spend per accepted useful output, rejection/retry cost,
citation correctness and customer usefulness before increasing volume.

## Required quality evidence before backfill

Runtime structural acceptance is not a quality approval. Both intelligence preflight
and the shared paid harness now require COUNTYIQ_PASS0_QUALITY_RECEIPT through
COUNTYIQ_PASS3_QUALITY_RECEIPT for the relevant enabled pass. Receipts bind to the
model, prompt versions, schema/prompt source hashes, relevant generation settings
and frozen fixture hashes; Pass 0 includes the actual PDF bytes.

The frozen fixture check makes no database or provider calls:

    cd pipelines
    .venv/bin/python -m eval.build_fixtures --check

--refresh-live is explicitly separate and writes only the mutable Pass 2 shadow
selection and PIDN list. It cannot overwrite the frozen gold fixtures.
The old p3_frozen.json is retained; p3_investigation_frozen.json preserves its source
contexts while migrating recommendation and urgency labels to the new contract.
The challenger runner uses the new fixture. feature_cases.json adds four municipal
and three owner cases with synthetic, source-reviewed contexts. These are useful
supplemental checks, not a claim of measured model performance or broad coverage.

Export supplemental prompts without spending:

    .venv/bin/python -m eval.feature_cases

Score complete archived responses:

    .venv/bin/python -m eval.feature_cases --responses /path/to/responses.json

A paid supplemental run requires --run, --model, --max-cost-usd and a new --output
path. Run only after a concrete budget is approved. The main challenger corpus
must also be run for the exact pass/model/config being considered.

Prepare a pending receipt after evaluating and reviewing the archived outputs:

    .venv/bin/python scripts/prepare_quality_receipt.py --pass-number 2

The operator fills reviewer, reviewed_at (ISO date), decision=approved,
catastrophic_errors=0 and evaluation_record={path, sha256}. The record must exist
and its bytes must match the hash; a relative path resolves beside the receipt.
Keep the actual scored outputs and human source review in that artifact.
Do not approve a receipt from format acceptance alone or from an unevaluated prompt
export. Review municipal linkage, decision scope, invented owner intent, quotations
and every consequential error. Changed artifacts/configurations invalidate approval.

The existing durable spend authorization, finite item limits, provider-price ceilings
and maximum run cost are still required separately. An approved quality receipt does
not authorize spend. Start with a capped representative canary, review source
correctness and actual cost, then decide whether to expand the backfill.

## Deployment

Use the [operations runbook](runbook.md) for the deployment sequence and the
[account guide](account-workspaces.md) for authentication, same-origin settings
and database grants. Deploy the reviewed migration head; stopping at the original
watchspace migration is insufficient for accounts and metadata readiness.
Ordinary deployment keeps paid passes disabled.

Before enabling intelligence processing:

1. Review source coverage and jurisdiction findings in the
   [project-data evaluation](../research/project-data-evaluation-2026-09-04.md).
   Apply reviewed metadata repairs and verify the resulting source records.
   Unreviewed, review-required and quarantined proceedings are ineligible.
2. Mount approved quality receipts and their evaluation artifacts where pipeline
   workers can read them. Compose forwards all four receipt paths;
   /opt/countyiq/archives is the existing archive mount.
3. Verify source-governed project pages, account isolation and a representative
   event-refresh notification. A healthy database probe does not prove these flows.
4. Complete the separately authorized, capped quality canary before considering
   a broad backfill. Configuration checks and metadata status are not extraction
   accuracy evidence.

Current review findings and verification boundaries are maintained in the
[production-readiness review](../research/production-readiness-review-2026-09-04.md).
The verification log below describes the earlier implementation, not the current
release candidate or live production state.

## Local isolation

Current source UI: app.localhost:5180 (product) and localhost:5180 (marketing).
Port 5173 is an older built container. The September 4 Vite review used 5174.
Normal API: localhost:8000 -> localhost:5433/countyiq, the real local dataset.
Synthetic API: localhost:8002 -> localhost:5433/countyiq_test.
Synthetic Vite: localhost:5175, with
COUNTYIQ_DEV_API_PROXY=http://localhost:8002.
Only the dedicated test database is seeded/reset. Never redirect the normal API to
test fixtures, and never seed synthetic records in countyiq.

## Historical verification: initial implementation on 2026-09-04

- Pipeline suite: 950 passed, 44 integration tests deselected; the final focused
  quality/config/contradiction checks passed 36 tests after the last evaluation edit.
- API: 90 unit tests and 36 PostgreSQL-backed integration tests passed using the
  dedicated countyiq_test database and restricted test API role.
- Frontend: TypeScript build check, ESLint, 8 Node tests, and production build passed.
  The existing map bundle size warning remains.
- Dagster definitions loadable; frozen context hash check passed without DB access.
- Firefox browser checks covered desktop/mobile home search, successful search
  navigation, project status/evidence anchors, saving a private workspace, a
  synthetic inbox event, acknowledgement, stale-save rejection and server-copy restore.
  Browser evidence is in output/playwright/. OS notification delivery itself was
  not exercised; it requires browser permission.
- Normal local ports 5173/5174/8000 were verified against the real dataset after
  tests; synthetic API/UI are isolated on 8002/5175. No test event was inserted in
  the real event ledger.


### Cached brief provenance transition

The API serves parcel/owner briefs only when accepted Pass 3 history contains
current signal-version receipts. Old briefs with missing history, empty receipts,
or signal-key-only receipts are retained in storage but hidden. Property/owner
facts remain available; public reads do not initiate generation.

Before rollout, inventory both brief tables in the target environment. The local
review inventory found zero rows on 2026-09-04; this is not evidence about a
different environment. Where legacy briefs exist, plan for their temporary
absence. Regenerate only through the normal authorized, budgeted validation and
brief passes after source/quality gates pass. Do not fabricate historical
dependencies from current projections or issue bulk paid generation merely to
restore page text. Missing versioned signal context stops new brief generation
before its paid invocation.


Parcel context checks require migration 059 before running the updated API or
parcel brief generator. New parcel briefs carry parcel-context:v1 references;
new owner briefs carry owner-context:v2 references including signal-parcel
municipalities. Old receipts do not establish these dependencies and their
narratives remain hidden until authorized regeneration. Do not downgrade 059
while application code still calls its functions.


### County narrative serving restriction

Property reports withhold Pass 4 county narratives because those projections
lack immutable upstream dependency receipts and serving-time freshness checks.
Stored rows are retained; expiry alone does not qualify them for display.
Re-enable only after implementing and testing source revocation, evidence
replacement and legacy-cache handling. This restriction does not disable the
separately validated parcel and owner brief surfaces.


Cached parcel/owner claims must also match their accepted inference payload,
including narrative text, structured claims and citations. A history ID alone
does not certify an altered projection. Missing or mismatched payloads withhold
the brief; investigate publication drift or use the normal authorized regeneration
path rather than synthesizing historical acceptance records.

## Municipal Pass 0 follow-up — 2026-09-05

The [fixes and ten-source regression](../research/municipal-llm-v3-fixes-2026-09-05.md)
retain valid sibling matters while quarantining unsupported claims. The wire
contract now requires item-specific action and relevance excerpts, and quality
identity includes the semantic validator. The final saved-response replay retains
46 of 52 matters, with six quarantined, for $0.04428219 in new evaluation spend.

This is previously reviewed regression evidence, not independent accuracy
approval. Remaining conversion classification and named-matter recall gaps keep
the backfill recommendation closed. No quality receipt was issued or production
data written. Preserve normal spend and quality gates; the legacy forty-response
diagnostic cannot authorize publication under the new contract.

## Municipal accuracy decision — 2026-09-05

The [fresh twelve-document accuracy pass](../research/municipal-accuracy-2026-09-05.md)
implements conversion relevance, bounded exact-excerpt relocation and named-matter
review telemetry. The evaluated code/reference remained frozen. The model mentions
all 22 useful reference topics, but runtime validation retains 18 and discovery
exposes 16. Reference-scored discovery precision is 16/18. These fail the frozen
90% thresholds; one deferred case is also labeled removed.

No additional review backfill, quality receipt or customer publication was issued.
Keep the normal release gates. New spend was $0.03945302, with zero retries.
Address the documented validation, scope/lifecycle and deferred-status categories
against the saved results before choosing another finite canary; low-impact
individual omissions belong in the backlog.
