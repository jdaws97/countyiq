# Emerging intelligence pilot release — September 8, 2026

The product owner authorized deployment of the customer-flow pilot, a bounded YCCD source pilot, and a roughly 20-project usefulness evaluation in the same conversation. This release makes reviewed emerging cases available through the shared customer workspace, with profile-based selection and private pursue/follow/dismiss work. Generic research implications remain within cases; only separately supported qualify/act possibilities enter Opportunities.

## Release scope

- Customer intelligence list/case pages, shared source receipts, one Opportunities view, My work, and saved criteria/status/notes.
- API publication/currentness checks, cache invalidation, account isolation, and backward-compatible workspace updates.
- Migration 081: publication ledger, current source-serving views, and saved-work columns.
- Migration 082: conditional YCCD acquisition/retention policy. Its manual `plan_review_pilot` job archives the newest linked official PDF and normalized review rows. Customer-derived publication and raw export remain disabled for this source; no automatic PIDN/project links or approval inference.
- The manually scoped emerging-generation job remains unscheduled. This release does not enable provider-paid passes or a broad backfill.

Previously prepared examples must be rebuilt against current production source packets and reviewed before publication. Local inference IDs, local review ledgers, and preview database records are not copied into production. If source meaning or site identity differs, withhold the affected case.

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

Customer-flow frontend tests, TypeScript, lint and build passed. Pipeline regression: 1,925 passed, 137 integration tests deselected. API unit tests: 142 passed; focused emerging/private-workspace database contracts: 11 passed. The full API database suite and remote CI are part of release acceptance. The first sandboxed API unit run stalled in its local-socket fixture; the permitted rerun completed successfully.

Migration 081 was rehearsed on the isolated full-data preview; migration 082 and an actual governed YCCD archive run also succeeded there. Source-current publication tests cover forged packets, withdrawn/changed evidence, immutable reviews, quarantine, and private workspace behavior.

## Deployment and recovery

Use the ordinary `docker/deploy.sh` path against the reviewed commit. It verifies the rollback backup, quiesces writers, migrates, refreshes runtime grants, replaces images, and checks internal plus authenticated public readiness. The authoritative live result is `/var/lib/countyiq/releases/current.env`; retain its prior release and backup.

A code-only rollback retains the additive schema and audit/customer data. Do not automatically downgrade 081 or 082 after publication, workspace use, or source acquisition. Their guards preserve retained reviews and acquisition receipts.

After deployment, run `plan_review_pilot` once, review current production packets before publishing the selected cases, and verify the live evidence and saved-work journey. Record actual release and publication results below when completed.
