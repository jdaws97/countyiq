# Parcel spatial facts — September 5, 2026

A customer walkthrough of `54000HJ012400` (495 Chapel Church Road) found two
contradictions: its zoning card selected Residential Low Density while cached
signals cited Commercial Industrial, and identical MOD soil fragments appeared
as separate 13.2% and 12.0% cards. The zoning inconsistency was independently
confirmed in the private production database before any changes.

Revision 066 gives reports and deterministic signals shared read-only spatial
functions. Zoning selection uses the newest adoption date, then the highest
record ID, before testing for divergence. Future-land-use selection also occurs
before comparison. The county's M code means mixed use in the observed records;
the old manufacturing comparison was wrong. The commercial comparison now
recognizes the county's `Commerical` spelling. A category code that conflicts
with both county district labels no longer supplies a divergence inference.
Original labels and source records remain intact. This remains a broad mapped
label screen, not a finding about ordinance permissions or rezoning prospects.

Soil fragments combine only when their map-unit key and material attributes
match. Missing keys remain separate. Coverage is calculated from unioned,
parcel-clipped geometry, including parcel-wide and septic-rating totals; neither
overlap nor per-polygon rounding can inflate the calculation. Every group
retains all contributing source IDs. The report and cached soil screen now both
show MOD at 25.2% from records 810 and 16498, and CeB at 10.8% from records 10193
and 14764. Eight source polygons become six distinct soil units.

The local revision-066 database retains 175,928 current parcels. A full rebuild
of only the existing `development_signals` and `development_momentum` assets,
without source ingestion or LLM calls, completed in 264.45 seconds:

| Screen | Before | After | Added | Removed |
| --- | ---: | ---: | ---: | ---: |
| Zoning / plan divergence | 13,351 | 11,569 | 0 | 1,782 |
| Soil constraint | 38,701 | 38,735 | 62 | 28 |

All 361,293 resulting signal rows have unique PIDN/key pairs. The current
six-signal Pass 2 eligibility rule selects 3,160 parcels, down from 3,404 before
this correction. No model is thereby qualified; quality receipts now also bind
the source-generation SQL and spatial migration.

Eight changed soil canaries were inspected against the original polygons.
Added examples include 84 Good Road (MOD 7.0709% across six records),
4870 Fiscal Road (GbD 5.4932% across two), 4379 Rockbridge Lane (MOD 5.9177% across
two), and 6631 Fair School Road (MOD 9.6997% across three). Removed examples at
1697 Furnace Road, 365 Locust Point Road, 402 Summit Road, and 697 Pleasant View
Road have largest qualifying units between 4.9722% and 4.9885%. The 5% rule now
uses unrounded union coverage; display percentages remain rounded.

That full refresh exposed a separate availability problem: TRUNCATE held a
read-blocking lock during the entire spatial calculation. Both assets now build
session-private temporary tables first, serialize concurrent rebuilders, and
publish after computation. Signal replacement and stale-evidence retraction
remain in one transaction. Momentum history comparisons are computed before
publication, with the serving snapshot and history committed together. The
short final replacement still requires a table lock; this change does not
promise zero publication latency.

The first production rebuild computed the replacement but rolled back at
publication: `RESTART IDENTITY` requires ownership of the administrator-owned
signal sequence. The runtime pipeline role has write, truncate and sequence
usage privileges, so the refresh now keeps allocating IDs without resetting
the sequence. The four real database publication/rollback cases now run under
that restricted role. The original production snapshot remained readable and
intact after the failed attempt; no broader permission was granted.

The corrected production rebuild finished at 21:56:56 UTC in 677.05 seconds.
Its full added/removed PIDN sets exactly match the local receipt. Production now
has 361,293 unique source signals, 162,886 scored parcels, 175,928 current parcel
records and zero accepted LLM evidence rows. The shared helper and cached signal
both select zoning record 1706 and MOD 25.2% for the example. Readiness remained
available through computation and passed after publication. The immutable
deployment receipt is
`/var/lib/countyiq/releases/20260905T214434Z-6b661c4adae1c7f84d64e6d6faa2aa83a23de88d.env`;
`production-refresh.json` and the source/momentum/readiness logs record verification.

The report keeps soil findings visible and puts detailed unit cards behind one
expansion. Print expands those details and restores their prior state. The
header identifies the municipality; school district remains in property facts.
Nearby table columns have spacing so adjacent headings and values stay distinct.

Validation: 15 PostGIS geometry/category cases; six publication, rollback,
history and validation-lock integration checks; 24 API contract/radar/spatial
tests; 1,390 pipeline unit/regression tests; Dagster definitions import;
TypeScript, lint and production build. Real Chromium checks at 390px and 1440px
confirm grouped units, source IDs, agreement with cached signals, expansion,
print restoration and no page overflow. The existing map bundle size warning
remains. Local evidence is under
`output/production-readiness-2026-09-05/spatial-facts/`; screenshots are
`output/playwright/spatial-report-*.png`. No full LLM backfill was run or approved.
