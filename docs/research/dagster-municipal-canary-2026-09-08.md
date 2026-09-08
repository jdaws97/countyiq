# Dagster municipal canary: stopped on incorrect property associations

Follow-up: the observed associations were repaired under a new subject/reference
contract. See [Municipal case boundaries and property references](municipal-subject-fix-2026-09-08.md)
for the implementation, 31-record replay and audited local repairs. The report
below preserves the original failed canary and its accounting.

Run locally on September 7–8, 2026. The planned 50-document canary stopped after
the first 25 documents failed the source/property quality gate. This is evidence
against starting an unattended backfill with the current selection/linking path.

Actual Dagster execution successfully persisted 107 source cards and indexed 31
card/property associations. Primary subscription review of all 25 complete
sources, all cards, and all associations found **five incorrect associations in
two documents**. Both source reads were withdrawn through the existing audited
contradiction-resolution workflow. Original outputs remain in immutable history.
The second batch, Pass 3 explanations, and the unchanged paid-mode repeat were
not run after this failure. A disabled-pass Dagster refresh completed successfully
after withdrawal, rebuilding the derived links, signals, events and momentum.
The canary now contributes 23 current reads, 92 cards and 23 property associations.
Both withdrawn documents are absent from serving; original history is unchanged,
with zero unresolved contradictions or projection mismatches. The owned Dagster
daemon is stopped.

## What failed

| Source | Saved selection | Consequence |
| --- | --- | --- |
| Conewago supervisors, August 5, source 8078 | Carvana sewer module selects lines 26–28, including Miller subdivision at 95 Butter Road on line 27 | Carvana linked to Miller's PIDN 23000MG002000 |
| Same source | Stonegate street adoption selects lines 26–29 | Street adoption linked to the same unrelated Miller property |
| Same source | Freedom Square Phase II extension selects lines 26–30 | Freedom Square linked to the same unrelated Miller property |
| North Codorus supervisors, July 7, source 8268 | Both named hearing cards select lines 92–94, containing both cases | Landing Opportunities inherits Eichelberger's 1381 Sunnyside Road property |
| Same source | Same shared selection | Eichelberger inherits Landing Opportunities' 2025 Stoverstown Road property |

The model preserved literal source text, so source-membership checks passed.
The selections nevertheless crossed case boundaries. The deterministic linker
then treated every matching address in each selection as a property reference
for that card. Exact address matching cannot establish which case an address
belongs to. These are observed downstream errors, beyond the latent speaker-role
problem identified in the earlier evaluation.

Other reviewed defects include an omitted Emig Park surveillance-system item,
loss of a “Briefing Items” heading, omission of a hearing's 5:30 pm time, cumulative
cross-subject selections in Felton and Lower Chanceford, and low-value routine
repair fragments. Those findings remain in the case-by-case review; withdrawing
the two consequential failures does not certify the remaining cards as error-free.

Useful behavior also survived the full path: the Spanish York City hearing
agenda retained seven separate cases and unresolved approve/deny alternatives;
the Musser Farm item retained all three acreage/district allocations; and the
Neal subdivision preserved votes, abstention, waivers, and planning-module action.
The employee-insurance-only meeting correctly produced no cards or broker-address
property links.

## Runtime issue fixed

The first live attempt failed after its first provider response because the
municipal reader omitted the transcript archive key. No inference was published.
Both municipal evidence and record explanation calls now supply source-bound
archive keys. Correction attempts get distinct keys. The shared harness rejects
a missing required key before contacting the provider.

After that correction, all 25 calls archived successfully. The audit reconstructs
their exact request hashes, verifies OpenAI routing and Luna low settings, and
rebinds each response to the frozen source and saved cards. No prompt or model
selection changes were made to improve the canary's measured outputs.

Optional Dagster scope configuration was added for proceeding IDs, municipal
explanation subject keys, and property PIDNs. This allows a canary or repeat to
target an explicit set instead of advancing the general backlog. Ineligible
explicit proceeding IDs fail rather than silently widening the run. These
  controls do not change the default unscoped behavior.

## Scope, accounting, and validation

- Fifty eligible, previously unread 2026 documents from fifty recorded bodies
  were frozen before dispatch. The first twenty-five were actually processed.
- Real jobs ran against the local `countyiq` database, with a readable database
  backup and an isolated Dagster instance. Paid passes remained manual; no
  deployment or paid schedule was enabled.
- Successful calls: **$0.01451105**. The failed, unarchived first call has an
  unknown actual charge; its full **$0.186558624** reservation remains charged
  conservatively. Total canary accounting bound: **$0.201069674**.
- The shared $5 ledger now accounts for **$3.30026749**, including that conservative
  charge. No reservations remain. Pass 3 spent zero.
- Full non-integration pipeline suite: **1,730 passed, 126 deselected**. Dagster
  definitions load and validate. All thirteen changed application/test/helper
  Python files passed the formatter check. Focused regression checks cover the
  archive failure and bounded selection. Existing unrelated Ruff diagnostics
  remain in older harness/proceeding files; this is not a claim of a clean
  repository-wide lint run.
- The canary quality approval is explicitly withdrawn. Two rejected audit
  records and two `discard_both` resolutions identify the primary assistant as
  an AI reviewer; neither is represented as a human review.

## Required next change

Fix and test case-boundary preservation before accepting extracted cards. Property
association also needs evidence that a reference belongs to the card's subject;
literal appearance somewhere in its selected text is insufficient. Use these
five observed failures as regression cases, then run a fresh bounded canary and
the unchanged-repeat check. Pass 3 should resume only on reviewed upstream
evidence. Increasing the extraction batch size now would multiply the same error.

Artifacts: `output/dagster-pass0-canary50-2026-09-08/`. `source-review.md` contains
all twenty-five source assessments; `snapshots/first25-audit/` preserves the
pre-withdrawal database state and full numbered review packets; `audit.json`
verifies requests, source binding, and cost; `withdrawal-receipts.json` identifies
the audited retractions; and `runs/` retains actual Dagster run receipts and logs.
