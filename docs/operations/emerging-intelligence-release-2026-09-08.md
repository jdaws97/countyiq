# Emerging intelligence pilot release — September 8, 2026

The product owner authorized deployment of the customer-flow pilot, a bounded YCCD source pilot, and a roughly 20-project usefulness evaluation in the same conversation. This release makes reviewed emerging cases available through the shared customer workspace, with profile-based selection and private pursue/follow/dismiss work. Generic research implications remain within cases; only separately supported qualify/act possibilities enter Opportunities.

## Release scope

- Customer intelligence list/case pages, shared source receipts, one Opportunities view, My work, and saved criteria/status/notes.
- API publication/currentness checks, cache invalidation, account isolation, and backward-compatible workspace updates.
- Migration 081: publication ledger, current source-serving views, and saved-work columns.
- Migrations 083–085 and indexed receipt lookup: geography/link indexes and shared current municipal inputs remove repeated evidence work from Emerging Intelligence requests without weakening source-current publication checks.
- Migration 082: conditional YCCD acquisition/retention policy. Its manual `plan_review_pilot` job archives the newest linked official PDF and normalized review rows. Customer-derived publication and raw export remain disabled for this source; no automatic PIDN/project links or approval inference.
- Coordinated backfill changes preserve complete case histories and add subscription-backfill tooling and evaluation support. The separate backfill task owns its reviewed native-worker restart after this release is deployed and the selected cases are published.
- MapLibre is upgraded to 6.8.0 with its production worker asset and compatible React binding, addressing [GHSA-jrc7-96c5-q579](https://github.com/advisories/GHSA-jrc7-96c5-q579). Accessible zoom buttons update the shared map view state.
- The manually scoped emerging-generation job remains unscheduled. This release does not enable provider-paid passes or a broad backfill.

The four prepared examples were rebuilt and reviewed against current production source packets before publication. Packets remained on the server; the review compared source hashes, exact public passages, current source identifiers, and public document metadata. Local inference IDs, review ledgers, and preview database records were not copied into production.

## Source-pilot evaluation

The collector fetched and retained the official August 31 YCCD PDF in a local end-to-end run, preserving all 35 rows. The publisher's five-second crawl delay is respected, every redirect stays within the configured origin, and robots/policy/archive failures abort the run. A tracked fixture reproduces multiline rows, missing permit IDs, and the two-page boundary in CI. Browser inspection confirmed the live listing and PDF link.

The primary reviewed the first 20 non-residence/dwelling entries in printed order against bounded searches of the isolated CountyIQ snapshot. Results:

- 20 dated review observations; 16 nonblank permit identifiers. None of those 16 identifiers appeared in current raw proceedings in that snapshot.
- Useful existing-project candidates include 1 Church Road, Franklin Commons, Forge Haven Valley, and the 1345 Mill Creek Road proceedings. The new source supplies review timing/identifiers, not proof of available work.
- Carvana's 30 versus 115 Industrial Road difference remains unresolved. Red Land's phase, Homewood's phase, the particular Adhesives Research scope, and Wawa's site/permit association need further checks.
- Broad searches also returned irrelevant Dairyland, McClain, Saubel's, and New View records from other municipalities. These are rejected candidate associations, not corroboration. BISES and York Synder returned no bounded candidate; absence from these searches is not exhaustive absence.
- **Zero automatic project links and zero qualified commercial opportunities** resulted from this source pilot. This supports retaining YCCD as a review feed; it does not measure opportunity precision, historical lead time, or customer conversion.

The reproducible inventory and exact search evidence are in `output/yccd-pilot-2026-09-08/`. The earlier [ten-example value test](../research/york-free-data-value-test-2026-09-08.md) covers building permits, sewer decisions, and funding background.

## Validation before promotion

The initial code release was `615a6d147e0f02e57b9a9053d42949969da54903`. Follow-ups add the Pass 2 parcel-link gate and Emerging Intelligence query fixes through `498bcae53b7a4ae5f6ae14cadf038f923f694e59`, available in [PR 22](https://github.com/jdaws97/countyiq/pull/22).

Frontend: 61 tests passed; TypeScript, lint, production build, and formatting passed. Combined pipeline regression: 1,928 passed, 137 integration tests deselected. Combined API suite: 215 passed. The fresh-database source/municipality contract passed after all migrations through 082 on a separate test database. Local-socket checks that failed under the sandbox passed when rerun with the necessary execution permissions.

For that exact commit, remote [CI](https://github.com/jdaws97/countyiq/actions/runs/34289704492) and [API Contract Tests](https://github.com/jdaws97/countyiq/actions/runs/34289704513) passed, including the pipeline integration suite. The separate [Security workflow](https://github.com/jdaws97/countyiq/actions/runs/34289704543) failed because dependency review and CodeQL result upload are unavailable under this private repository's current GitHub feature configuration. This is not a green security workflow. Existing dependency audits, Bandit, and secret scanning passed; no paid feature was enabled or check weakened to change that result.

Browser checks covered the customer case list and evidence, mobile layout, parcel rendering, and working zoom controls in the production frontend build. Live authenticated saved-work behavior remains a post-deployment check.

Migration 081 was rehearsed on the isolated full-data preview; migration 082 and an actual governed YCCD archive run also succeeded there. Source-current publication tests cover forged packets, withdrawn/changed evidence, immutable reviews, quarantine, and private workspace behavior.

The performance migrations were rehearsed in rolled-back transactions against the isolated full-data preview. They preserved the four canonical scope packets, all 20 property packets, and all 13 preview analysis IDs. Twelve relevant API tests passed after 084; a new shared/canonical-source equivalence check brings the relevant set to 13. The four Emerging Intelligence checks passed again with 085 and the indexed receipt query. Fifteen pipeline intelligence tests passed. Migration and helper code passed Ruff; documentation passed Prettier. Local setup attempts with a missing test filename, incorrect import directory, or incorrect Compose project were corrected before successful runs; no assertions were relaxed.

## Deployment and recovery

Use the ordinary `docker/deploy.sh` path against the reviewed commit. It verifies the rollback backup, quiesces writers, migrates, refreshes runtime grants, replaces images, and checks internal plus authenticated public readiness. The authoritative live result is `/var/lib/countyiq/releases/current.env`; retain its prior release and backup.

A code-only rollback retains the additive schema and audit/customer data. Do not automatically downgrade 081 or 082 after publication, workspace use, or source acquisition. Their guards preserve retained reviews and acquisition receipts.

The production source pilot and reviewed publication steps are complete. Authenticated customer saved-work interaction remains unverified in the available browser session, which stops at Cloudflare login; account isolation and saved-work contracts passed in integration checks.

## Current release status

The user explicitly approved the named production destination and deployment in the coordinated backfill task. The initial release completed on September 8 at 23:40:58 UTC, migrating schema 080 to 082. The parcel-link follow-up `3f1ee08014f5b8d5bf298430d561d1f8a5f1e48a` completed on September 9 at 00:01:11 UTC. Both used the ordinary verified-backup deployment path and passed internal plus authenticated public readiness checks.

Production `plan_review_pilot` run `1748a95d-0770-42c1-bbf2-64cb38146b4a` succeeded. The archived official PDF has SHA-256 `3bcd9ea41eceb29255d53d2334577a40ff9395a78f5ba6afec651eed5bb6e5e4`, matching the reviewed 35-row pilot source.

Four emerging research cases were retained as inferences 5235–5238 and separately published with review IDs 1–4: the Yoe hearing, Musser tract, Carvana plan consideration, and Dalfen boundary review. None was promoted to a qualified Opportunity. Carvana's differing Industrial Road addresses remain unresolved; Yoe's hearing consensus is not an adopted ordinance; Dalfen's review is not a site commitment.

The user's reported page timeout was reproduced in production. Migration 083 at `82f7cf3b627700094beee327ef56fc2abe2c5f73` completed on September 9 at 00:27:33 UTC with backup `20260909T002550Z-pre-deploy-82f7cf3b6277`. It improved local reads but was insufficient at production scale: the cold API snapshot still took 28.88/28.71 seconds over 25,041 current municipal records. Warm reads took 4 ms and all four publications remained current. Migration 084 shares the live scope inputs across those checks; its final production acceptance is recorded below.

Migration 084 at `d5526c562fe5781048898873cfc633e1cc2d4adf` completed at 00:37:28 UTC, with backup `20260909T003542Z-pre-deploy-d5526c562fe5`. It reduced cold API snapshots to 6.80/5.97 seconds, with warm reads at 4/3 ms and all four cases current. Profiling isolated the remaining costs: 3.66 seconds validating sources, 0.33 seconds counting coverage, and 2.01 seconds loading source receipts. The final follow-up indexes environmental geography and narrows receipt loading to indexed candidate inference IDs while retaining the final current event-key filter.

Final release `498bcae53b7a4ae5f6ae14cadf038f923f694e59` completed at 00:44:27 UTC on September 9 with schema 085 and backup `20260909T004244Z-pre-deploy-498bcae53b7a`. Internal and authenticated public readiness checks passed. The actual API snapshot path returned all four cases in **3.560 and 2.984 seconds cold**, with **3 and 1 ms warm**. All four publications remained current; coverage reported 25,041 available records, four assessed scopes, and zero awaiting refresh. These are server-side serving measurements, not signed-in browser end-to-end timings.

For that final code commit, remote [CI](https://github.com/jdaws97/countyiq/actions/runs/34296102011) and [API Contract Tests](https://github.com/jdaws97/countyiq/actions/runs/34296101976) passed. The [Security workflow](https://github.com/jdaws97/countyiq/actions/runs/34296101982) remains red; its unavailable repository-feature checks have not been disabled.

This fixes the reproduced timeout at the current four-case load. It does not establish a capacity guarantee: the serving query still validates every published scope before pagination. Shared municipal inputs remove repeated county-wide reconstruction, but the property and case validation work can still grow with the published case count. Increasing-case measurements and bounded serving design remain separate capacity work; they do not hold the approved backfill restart.

The coordinated task completed bounded native subscription canaries: five Pass 1 groups and eight Pass 2 parcels (16 signals), followed by current-source audits of all 13 subjects. It owns sustained backfill restart and completion. The final performance hold is released and the task was instructed to rebind, verify receipts, and resume the year-first controller against 498bcae/schema085. No provider-paid fallback is enabled. The earlier 1,926 missing past-year matter bundles was a work estimate, not a coverage-completeness claim.

## Pilot acceptance and market validation

The incomplete backfill prevents treating the current case sample as a representative test of the finished product. Complete the agreed backfill, audit expected source/date coverage and unresolved gaps, and inspect coherent case histories before assessing a customer trial. Buyer problem interviews can proceed while that work finishes.

The [competitor comparison](../research/permit-intelligence-competitors-2026-09-08.md) establishes existing permit and intelligence product claims; it does not establish willingness to pay for CountyIQ. A focused buyer trial still needs evidence that current, source-supported cases change a buyer's action or save enough research time to justify payment.
