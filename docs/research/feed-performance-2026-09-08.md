# Feed query and date-window correction

The feed rebuilt immutable municipal source JSON while checking whether published
records were still current. Research additionally joined the complete source set
through a query plan that repeatedly scanned materialized results. These costs
also affected municipality, property, project, and Following requests that share
the feed.

Migration 078 compiles accepted municipal reads into rebuildable read/card indexes
in the same transaction as immutable history insertion. Source text, model
outputs, canonical fingerprints, and account identity remain in their existing
ledgers. Current views still check source revisions, rights, accepted explanation
snapshots, and live property/owner connections. Separate query branches let the
database join municipal records and accounts through their event keys. Source
location lookup is bounded to the documents represented on the requested page.

The API reuses a bounded copy of a feed page for at most 60 seconds. A transactional
dependency revision and the database calendar date invalidate it; rights checks
still run for every request. Filters, pagination, watched subjects, view, and sort
are part of the cache key. Publication, source changes, rights changes, and
property/owner changes invalidate cached pages immediately after commit.

The date window now uses the displayed event date, falling back to the collection
date only when the event has no date. A historical record collected today no
longer counts as recent activity. Expanding the window cannot supply accounts
whose backfill is still unfinished.

## Verification

- A fresh dedicated test database upgraded through migration 078; 69 focused
  API/source/account tests passed, including date-window and sort-order behavior.
- The broader API run passed 338 tests and exposed three outdated test contracts.
  After correcting those contracts and the cache-aware mock, all 20 tests in the
  affected contract/unit modules passed.
- Pipeline non-integration suite: 1,886 passed, 136 deselected.
- Rollback-only production-data comparison: zero differences in 21,732 scope
  rows, 515 complete account rows, 21,595 Research event keys, and 22,516 complete
  served events. Every current compiled card source and fingerprint matched its
  canonical source construction.
- Diagnostic query trials reduced fresh Activity to approximately 1.9 seconds
  and Research to 3.3 seconds. The earlier API-handler baseline took about six
  seconds for Activity and reached its 15-second timeout for Research. These
  measurements exclude browser rendering, authentication, and network travel.

This removes repeated source construction and a poor join plan; it is not a
constant-time guarantee as history grows. Current scope validation still depends
on the available evidence set. Recheck fresh requests as the historical account
backfill expands, and retain the source-current withdrawal tests for any further
incremental serving changes. The browser available to this review was signed out,
so these results do not claim a completed authenticated live walkthrough.

## Municipality summary and duplicate source versions

The municipality profile repeated current-event validation for counts, recent
activity, upcoming items, and policy activity. One materialized query now returns
all four lists, using the same explained accounts and discovery eligibility as
Activity. Its summary uses the transactional revision cache; the remaining
profile fields are fetched normally. This also prevents counting an account and
its underlying raw cards as separate matters. The prepared handler reduced the
Conewago profile from 10.27 seconds to about 2.2 seconds during active backfill.

The two Conewago moratorium accounts came from the original and amended July 7
agendas. Both contain the exact named subject, Resolution 2026-13, but their card
titles omit the reference. Migration 079 also recognizes an ordinance/resolution
reference when its own selected subject line explicitly names the complete card
title after a colon. Context passages, neighboring subjects, ambiguous references,
and title similarity do not qualify. A rollback-only comparison across current
production evidence changed exactly these two cards into one candidate bundle.
The subsequent account merge requires an explicit source-hash/alias review and
retains both source histories. Existing watched identities still require a
reviewed watch migration.

Verification of this follow-up: 24 focused API/cache/account tests and three real
database identity-review tests passed; the pipeline suite passed 1,886 tests with
137 integration tests deselected. Complete candidate rows outside the two
intentionally regrouped records matched the previous production view exactly.

## Historical source loading and reviewed related updates

The historical backfill exposed a separate poor join plan when constructing all
candidate source bundles. Migration 080 builds source records and their passages
in a single grouped query over the compact, current scope inputs. A bounded
source function supports persistence and contradiction review. A rollback-only
production comparison found zero differences across all 21,762 complete source
bundles; constructing their roughly 64 MB of source JSON took about four seconds,
and a single-bundle check took about 1.5 seconds.

Cross-document updates without literal case references can now receive an
explicit candidate review through `review_municipal_candidates.py`. Reviews bind
every selected record to its current source fingerprint, require one municipality
and complete existing bundles, and cannot override property or formal case
scopes. Reviews are append-only; a later release restores default retrieval.
Every member must remain current for the group to apply. A candidate review does
not update matter aliases or establish a merged account: the existing complete
source, identity, watch, and contradiction checks still govern that separate step.
The same source-change revision invalidates cached Activity immediately.

Release `d9f683b` deployed successfully with schema 080. The four reviewed pairs
were grouped and merged through separate candidate and identity reviews:
Loganville's Westridge/Ferndale repaving and Columbia Gas main replacement,
Fairview's Green Lane crosswalk study, and East Hopewell's stormwater rewrite.
Each retains the earlier matter key and both source histories. The decisions
remain limited to what the documents establish, including study authorization
and ordinance drafting rather than installation or adoption.

All 24 profiled production API handlers completed during the resumed historical
backfill. Fresh Activity took 2.47 seconds, Research 3.61 seconds, and the Conewago
profile 2.26 seconds. Research's immediate repeat took 0.009 seconds; Activity's
repeat was invalidated by new accepted backfill output and took 2.48 seconds.
These remain handler measurements, excluding browser, network and authentication.

Historical processing found a valid `5/15.` date rejected because its sentence
period was treated as an unfinished numeric date component. The date validator
now permits sentence punctuation while still rejecting partial dates and changed
years. The source-supported account was separately reviewed and accepted with an
exact quote ending before the period. A further PDF record joins month and day as
`theMay27,2026`; that literal date can now be quoted without adding spaces to its
original text. All 59 record/account validation tests pass, including nine new
punctuation, joined-text and invalid-date regressions.
