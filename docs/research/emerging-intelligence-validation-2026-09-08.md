# Emerging intelligence: local validation

September 8, 2026. This validates a bounded implementation and selected
source-reviewed examples. It does not establish customer demand, investment
returns, won contracts, model precision or production early-warning lead time.

## Delivered behavior

- Emerging intelligence and Opportunities share source-current cases and the
  existing original-evidence viewer. Investor and service-business actions have
  separate readiness, next action, blockers and disqualifiers.
- Six hypothesis families are supported by the contract. Four initial cases
  cover business expansion, use transition and possible land consolidation.
  No family is populated merely to fill a dashboard.
- Generation is an explicit-scope manual job using existing Pass 4 execution
  limits. Draft retention and publication review are separate. Reading pages
  never starts inference. No paid inference or production deployment was run.
- Source packets bind municipal records, current property/GIS context and up to
  six adjoining parcels by default. Their relationships remain retrieval
  context, rather than asserted project membership or corporate control.
- A new record, changed source/parcel context, revoked rights or withdrawal
  retracts the affected current interpretation. Same-evidence changes to a
  hypothesis or commercial action are quarantined, even if its status is unchanged.
- Personal profiles, notes and case status remain account-scoped. Older clients
  that omit the new fields preserve existing intelligence work. Guest export and
  import include it; invalid imports fail before changing stored work.

## Source-reviewed examples

| Case                                                     | Retained conclusion                                                                                       | Important limit                                                                                   |
| -------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Carvana at 115 Industrial Road, Conewago Township        | A proposed new car-auction building warrants checking expansion or operational reorganization.            | Added capacity versus replacement, approvals, delivery commitments and open scope remain unknown. |
| 110 Yoe Drive, York Township                             | Rezoning and subdivision records at the same address support a possible residential/mixed-use transition. | Agendas do not establish adopted rezoning, approved buildings or a construction start.            |
| Musser Farm at 4390 Board Road, East Manchester Township | Specific proposed district acreages justify entitlement research.                                         | A rezoning proposal does not establish development intent, adoption or site availability.         |
| Dalfen Industrial Warehouse, Shrewsbury Borough          | A reverse-subdivision title is an early site-consolidation lead.                                          | It may be administrative boundary work; parcel identity and physical improvements need the plan.  |

The isolated preview has **four hypotheses, five audience-specific early
implications, zero qualified opportunities, and nine abstentions from thirteen
assessed scopes**. The abstentions
include seven general data-center ordinance scopes, an unlinked Carvana sewer
module and Eagle Rock's community-water bond-reduction action. Those records do
not justify a site-specific data center, an inferred cross-document site link or
an open infrastructure contract.

These analyses were authored and reviewed in the Codex session using the retained
source excerpts. They were not produced by a paid backfill or an independently
calibrated automated classifier. The Carvana next-check jurisdiction was corrected
to Conewago Township during review; the corrected version has its own audit entry.

## Historical cutoff check

For each of four selected cases, replay was reconstructed at July 31 and August
31, 2026. Eligible excerpts must have both a meeting date and an original source
observation time by the cutoff. Present-day property facts, neighboring-scope
retrieval and geometric relationships are excluded from model-visible input.

| Selected case    | Eligible excerpts at July 31 | Eligible excerpts at August 31 | August review                                                                         |
| ---------------- | ---------------------------: | -----------------------------: | ------------------------------------------------------------------------------------- |
| Yoe Drive        |                            0 |                              7 | Rezoning/subdivision hypothesis from agendas; later-collected board minutes excluded. |
| Musser Farm      |                            0 |                              2 | Early entitlement hypothesis from its agenda item.                                    |
| Carvana building |                            0 |                              0 | Abstain.                                                                              |
| Dalfen           |                            0 |                              0 | Abstain.                                                                              |

These are retrospectively selected current cohorts. They do not reconstruct all
past source versions, the exact historical extraction/linking state or what the
production system would have surfaced. Prospective frozen packets and later
outcomes are still needed to measure useful lead time.

Local receipts are in `output/emerging-intelligence/`: canonical packet/analysis
pairs, `historical-replay.json`, replay pairs and publication receipts. These
contain full source provenance and are local artifacts rather than fixture data
presented as customer facts.

## Verification

- The complete non-integration pipeline suite passes: **1,912 passed, 137
  deselected**. Local-server checks were run with the required network permission.
- Twelve focused pipeline tests cover exact source quotes, unknown citations,
  duplicate observations, same-document corroboration, alternatives, action
  readiness, temporal cutoffs, excluded current neighbor discovery, zero-source
  abstention without inference, and source-policy substitution.
- Real-role API/database checks cover forged packet rejection, draft invisibility,
  reviewed publication, page-located evidence, filtering/pagination, stable case
  keys across reassessment, semantic-change quarantine, cached rights/context
  retraction, withdrawal and account/legacy-client isolation.
- Existing account workspace tests pass. Frontend workspace tests cover hydration,
  synchronization, account switches/logout, export roundtrip, old files and atomic
  invalid-import rejection.
- TypeScript, ESLint and production build pass. All frontend test files pass;
  the routing file requires permission to start its local HTTP servers. The
  existing large map-bundle build warning remains.
- Fresh schema installation through migration 081, empty-data downgrade to 080
  and re-upgrade pass in a separate disposable database. The migration refuses a
  downgrade that would discard retained analyses, reviews or customer work.
- Dagster definitions import successfully and the new manual job is registered.

Real Firefox checks at 1440px and 390px verify list → case → source viewer →
subject property, saved status/note after reload, saved-case return on Overview,
service selection, URL changes and a truthful empty state. The phone cases and
profile/empty-state screens have no horizontal overflow. Screenshots include
`desktop-list.png`, `desktop-source.png`, `mobile-case.png`,
`mobile-opportunity.png` and `mobile-saved-work.png` in the local receipt directory.

The first full-data check of thirteen reviewed scopes took approximately ten
seconds. Repeated filtered reads took approximately four milliseconds after
revision-aware snapshot reuse. Every context layer and publication action
invalidates that cache alongside existing source and policy dependencies. Cold
checks need optimization before a substantially larger corpus is served.

## Environment note

### Customer-flow follow-up

The later customer-flow revision separates early implications from qualified
opportunities. Qualification requires source claims for commercial need, timing
and a route to qualify the work. The API no longer promotes legacy research
actions into opportunities. Multiple commercial scopes can share a case and
audience. Project-type and readiness filters apply before pagination; investor
matching ignores unrelated saved service filters.

The required frontend typecheck, lint and build pass after the final navigation
and selection-explanation changes. The follow-up pipeline suite passes with
1,912 tests; API intelligence and existing workspace checks pass together (11
tests), and the three intelligence API checks pass after the final filter change.
Frontend flow tests cover matching the same possibility across criteria,
project-type gaps, dismissed-work exclusions and review status. Browser checks
verify the single Opportunities link, its empty qualified queue, profile-driven
matching, follow/dismiss/recovery and notes surviving reload. The saved-case
revision check uses a changed local last-seen value; it does not simulate a new
source publication. Additional screenshots are under `output/playwright/` with
the `customer-flow-` prefix.

### Database setup

Work used an isolated PostgreSQL container on port 5436 with separate preview,
API-test and schema-check databases. A migration-target mistake initially applied
078–081 to the local source database because Alembic ignored the DATABASE_PORT
variable. The unused 081 additions were removed safely; the source database was
left at 080 with the preceding migration prerequisites. Source data was not
reset. Subsequent migrations used explicit DATABASE_URL targets. The preview
copy omits an unrelated, expensive entity-candidate materialized-view refresh;
its source records and the affected intelligence views were restored.

No production database, external account, outreach channel or deployed site was
changed. The next product-validation step is a small customer pilot using the
initial cases and explicit qualification outcomes described in
[the product contract](../products/emerging-intelligence.md).
