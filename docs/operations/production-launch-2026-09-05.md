# Production launch record — September 5, 2026

Status: active implementation and verification. **Full backfill is not approved.**
The user authorized product iteration, bounded canaries, commits/pushes to main,
and deployment. Full backfill remains a separate explicit user decision.

## Product acceptance work

The launch lane is one York County investigation workspace for local developers
and acquisition teams. See [product direction](../products/real-estate-intelligence.md).
Pricing is a $79/month pilot hypothesis, not validated demand or a published offer.

Customer review uses current source at port 5180 against the real local API and
real county database, not the stale built UI container or synthetic API.
The browser review covers a known-property search, property evidence, watch
persistence and map selection at desktop and 390px phone widths.

Changes made during this review:

- A new workspace starts with property search and useful browsing paths.
- Property pages lead with three distinct development scores and a concise
  evidence disclosure. Print packets include the expanded evidence.
- Empty activity states explain unpublished/limited records and lead to search
  or radar. Baseline tax imports are not represented as new county activity.
- Radar labels assessed value clearly and indicates additional results.
- The map uses a light basemap by default and honors the selected dark theme.
  Optional static layers load when enabled; municipality outlines are subdued.
- Viewport requests use the actual canvas bounds, split at the API span limit,
  and deduplicate parcel IDs. Invalid URL coordinates retain the county view.
- A linked parcel fits its full geometry, stays highlighted, and loads the
  surrounding parcels. A deliberate pan prevents delayed automatic recentering.
- Real browser testing found that synchronous graphics picking could delay a
  click by 498 ms, exceeding Deck's 250 ms tap limit. A 1000 ms click limit
  retains the built-in movement threshold; clicks select and drags do not.
- The map panel now shows the lead signals and a few key facts, with a prominent
  route to the full evidence. Tax details withheld by policy read as unavailable.
  Vacancy remains a footprint screen; recorded sale amounts are labeled.

Screenshots and interaction records are under
`output/playwright/production-*`. These are local evidence, not committed assets.
Final map layers, drag, theme and navigation checks remain in progress.

## Verification

Artifacts: `output/production-readiness-2026-09-05/`.

- Pipeline unit/regression suite after changes: **1355 passed, 101 integration
  tests deselected**. Definitions import also passed earlier in this review.
- API unit tests: **120 passed**. API database integration: **108 passed** against
  the isolated `countyiq_test` database. The real county database was not reset.
- Frontend: **30 tests passed**, TypeScript and lint passed, production build
  passed. The lazy map bundle still produces a size warning; the marketing entry
  does not load it. The final frontend release build, TypeScript and lint also passed after the map panel edits.
- Real host-preflight integration cases: **8 passed**.
- Cloudflare configuration validates and its cost-policy check passes. The new
  readiness service token is a reviewed Access credential, not a metered Worker.
- Dirty-tree whitespace check passed. Existing staged/unstaged/untracked work
  was preserved in `/tmp/countyiq-production-20260905/` before editing.

No commit, push or application release has been completed by this launch review
as of this entry. Those remain required work, with exact SHA and receipts to be
added below when verified.

## LLM evidence

The first finite evaluation made 59 calls for **$0.08241129**: Pass 1's eight
partition cases, two Pass 2 trials across 20 source cases (59 signals per trial),
four parcel-brief cases, and seven supplemental municipal/owner cases.
Pass 1 passed 8/8. The supplemental cases passed 7/7.

Source review found a real Pass 3 recommendation collapse: all four briefs said
investigate. Updated parcel/owner instructions distinguish a specific activity
requiring verification from a change to watch and static screening evidence.
A subsequent four-case run has 4/4 source-consistent structured decisions and
4/4 production citation gates. The seven supplemental cases also pass after
the owner prompt change. Total for this launch review is **70 calls,
$0.09453171**. All are evaluation-only; no serving data was written.

The deterministic scorer also had defects. It treated explicit missing or
unconfirmed evidence as prohibited assertions, mishandled decimal sentence
boundaries and equivalent number wording, accepted substring matches inside
larger numbers, and excluded factual anchors in the cited top-risk field.
Regression tests cover these issues, including separate positive assertions
that must still fail. Original provider results are preserved. Offline rescoring
of the revised P3 outputs yields 4/4 strict passes; this is not a new paid run.
The frozen source contexts and labels were not edited to obtain that result.

Pass 2 remains under source-level review. Under scoring version 2026-09-05.1,
the two initial trials yield 54/59 and 56/59 grounded decisions, 170/178 facts
in each, zero prohibited assertions, and 10/20 strict case passes each.
Remaining issues include conservative vacancy dispositions, the significance of
fragmented neighboring ownership, and fact wording/omissions. Neither a high
format-gate rate nor a changed scorer is sufficient quality approval.

The previous [Pass 0 readiness report](../research/pass0-readiness-2026-09-05.md)
meets its final regression coverage/discovery criteria, but its holdout informed
fixes. Six new source documents were selected with zero historical ID/text-hash overlap,
read before generation, and evaluated with frozen expectations. The first six-call
run cost **$0.02937440**. It retained 16/19 expected useful matters and surfaced
7/19 for discovery. No unsupported approval, wrong-property association or false
terminal status was found. Three valid additional capital projects were omitted
from the source-first reference; raw frozen precision is 6/9, with all 9 candidates
source-supported on subsequent review. The reference remains unchanged.

These results are not sufficient for release. Fixed explicit plan-review relevance,
capital upgrades and bidding-stage exclusions, and unambiguous short Board authority.
Added 21 regression cases; the complete pipeline suite passes 1338 tests. Prompt
instructions now cover comprehensive-plan procurement/funding omissions, material
project votes and exact project-reference passage selection. A second six-document
run is capped at $0.30, with no retries or publication. It is regression evidence
after source review, not an unseen holdout. Original outputs/projections and a
source-by-source review are preserved under `pass0-new-canary/run1`.

Total completed launch evaluation spend before this repeat: **76 calls, $0.12390611**.
Source-to-publication checks and exact-version receipts remain outstanding. Pass 4 and AI search stay
off; they are outside the launch offer.

## Infrastructure actually changed

- VPS SSH now rejects password and keyboard-interactive authentication; a fresh
  key session was verified. The effective configuration previously differed
  from the intended hardening because cloud-init's earlier file took priority.
- Corrected application UID traversal to `/var/lib/countyiq/cost-guard`; the
  Ansible parent-directory mode now reflects the tested configuration.
- Applied guarded `app.countyiq.net` DNS and its dedicated Access application,
  and routed that hostname through the existing Tunnel to Caddy.
- Published encrypted production configuration with the product Access audience,
  verified-account workspace origins and private watch sync enabled. Inference
  passes remain disabled.
- The apex Access gate remains in place until the split origin is verified.

The VPS does not yet run the application stack. The real local database remains
on revision 061; migrations 062–064, protected migration backups, production
restore/transfer, commit-addressed release, off-host restore drill and live
customer authentication checks remain to be completed.

The user added the requested Cloudflare token permission. A refreshed plan with
**two additions, zero changes/deletions** was applied: one readiness service
token and a separate Access application restricted to `app.countyiq.net/api/ready`.
The token expires September 5, 2027. Its curl configuration was streamed directly
to `/etc/countyiq/readiness.curl` on the VPS and verified root:root mode 0600.
The encrypted production env points to that file and was republished. With this
credential the readiness route reaches the undeployed origin (HTTP 530), while
`/api/session` still receives the customer Access challenge (302). This verifies
the Access boundary, **not application readiness**. End-to-end HTTP 200 remains
required after deployment.

## Customer contact

No MX records exist for the domain. The intended contact is
`hello@countyiq.net`; it is not published as a working address. The user uses
Gmail/Proton. Proton custom-domain mail requires a paid plan and supplies the
DNS records to configure in Cloudflare. Cloudflare forwarding is another option
for receiving mail, but replies use the destination mailbox's address.
Mailbox setup and a working pilot inquiry path remain launch dependencies.

## Remaining acceptance order

1. Finish browser interaction/coverage checks and fix observed problems.
2. Review remaining Pass 2 differences; freeze and evaluate new Pass 0 canaries.
3. Reconcile launch docs, release identities, source policies and source freshness.
4. Commit/push the reviewed release, complete backups/migrations and deploy the
   private app. Verify Cloudflare/identity boundaries and recovery.
5. Complete a real source-to-event-to-property-to-watch canary in the deployed
   environment; review every consequential output and rejection.
6. Verify customer contact and public marketing, then present the full-backfill
   estimate, exact versions, evidence and proposed limits for user approval.


## September 5 follow-up: corrected inputs and model comparison

The second six-document Pass 0 run completed for $0.03087060. Source review
found all 19 expected useful matters retained and 18/19 surfaced for discovery;
all 20 surfaced candidates were supported (including three valid capital
projects absent from the frozen reference). Release is still withheld: bare
vote-tally excerpts did not establish the voted action, and one meeting was
mislabeled as a hearing. Those guards/prompts were corrected and regression
tested. These are repeat-case results after fixes, not independent holdout data.

Pass 2 supplied incomplete context: adjacent tax-claim years were omitted, and
the precomputed delinquent count considered positive balances only. Both are
corrected. Four targeted preserved cases were run twice for $0.01212522.
Fragmented neighboring ownership now stays low significance and claim years
are preserved. One output used exact display wrappers around valid evidence
IDs. Bounded normalization fixes that parser issue; offline reparse of all eight
saved outputs passes 8/8 evidence-reference gates (previously 7/8). Unknown IDs
still fail. Case p2x-050 retains a fixture-level 11-versus-12 neighbor-count
ambiguity; citation validity does not resolve that semantic issue.

Before the new three-model comparison, completed evaluation totals were
**90 calls, $0.16690193**. No serving writes or quality approvals were made.
The full non-integration pipeline suite now passes **1355 tests**, with 101
integration cases deselected. This includes corrected context, citation,
municipal decision-scope and model-request tests.

The user explicitly reopened GLM 5.3 Flash and DeepSeek V4 Flash 0731 selection.
Audit confirmed that historical DeepSeek truncation and missing claim-year
facts were harness/input defects; GLM also inherited generic sampling and its
mandatory reasoning defaulted to max when omitted. GLM now has publisher
sampling defaults and explicit bounded reasoning; DeepSeek V4 uses portable
OpenRouter reasoning controls and omits ignored sampling parameters. Production
model defaults are unchanged while the comparison is pending.

The frozen comparison under `output/production-readiness-2026-09-05/fair-model-comparison/`
allows 36 calls for at most $1.50, with six transport/semantic smoke calls before
a 30-call continuation. All models get identical corrected evidence/prompts,
explicit low effort for Passes 0/2/3 and high for Pass 1, the same output ceiling
per pass, and no generation retries. Both open models require FP8 providers.
Every request payload, original response, gate result, fallback, token count,
elapsed time and provider-reported charge is preserved. This is a controlled
screen; favorable regression results alone do not authorize a full backfill.

The three-model comparison is complete: **36 calls, $0.046138529**, bringing
completed launch evaluation to **126 calls, $0.213040459**. See the
[model review](../research/model-comparison-2026-09-05.md) for source-level
findings and the distinction between harness failures and substantive errors.
GLM is a promising per-pass replacement; no model default was promoted yet.

Final database contracts pass **101/101** on a new isolated PostGIS container
migrated through 064. A reused API test database initially failed one fixed-seed
policy-count assertion due to a synthetic municipality left by API fixtures;
the real county DB was never reset. Dependencies have no known reported
vulnerabilities, and definitions import passes. History secret scanning passes;
working-tree scanning found only a public localStorage name and Docker image
digest, now documented with line-specific false-positive annotations.

Browser verification confirms map layer off/pan/on fetches fresh parcels, with
no fetch while disabled and no mobile overflow. Property printing opens 11
evidence sections then restores their previous state. Nearby parcels now show
five initial results, expand to all 40, and retain all rows in print; mobile rows
show labeled facts without a horizontally clipped table. Vacancy copy remains a
screen requiring verification. A protected revision-061 database dump was
created and its PostgreSQL restore listing verified before any migration.
