# Project data evaluation — 4 September 2026

> This is the pre-cleanup evaluation. See the [applied municipal cleanup](municipal-source-cleanup-2026-09-04.md) for corrected source identities, metadata, and current pilot eligibility.


## Decision

Projects are worth building as evidence-backed investigations within CountyIQ. They are not yet ready to be marketed as a populated, comprehensive opportunity directory. The current real database has zero accepted proceeding extractions and zero development-event case inventory. That is a processing/readiness gap, not evidence that municipal sources contain nothing useful.

Do not run a broad LLM backfill yet. Correct jurisdiction, board identity and meeting dates first; then run a small reviewed Pass 0 canary before building downstream project summaries. No paid model calls or production inference writes were made for this review.

## What was inspected

Read-only evaluation of the local real countyiq database, separate from countyiq_test. There are 7,414 current proceeding records, 6,037 with at least 500 text characters, and 842 such records dated January 1–September 4, 2026. Normalizing whitespace and deduplicating full text leaves 814 recent documents. There are also 13 future-dated records; an upcoming agenda can be legitimate and must not be presented as an event that already happened.

A coverage sample selected six documents per group (supervisors, council, planning, zoning), SHA256(id) order, distinct board within each group. This is deliberately balanced, not a statistical estimate of countywide project yield. The companion JSON retains IDs, source URLs, full-text hashes and individual assessments without copying the full corpus.

| Document assessment | Count of 24 |
| --- | ---: |
| Concrete matter worth investigating, including small/early cases | 12 |
| Minor or administrative site case; not a growth opportunity | 5 |
| Named plans needing stronger location anchors | 1 |
| Municipality-wide policy, not a site project | 2 |
| Routine/unrelated proceedings | 2 |
| Wrong county | 2 |

These are document counts, not distinct approved projects. A document may contain several matters, and a matter may recur in several documents.

## Customer value already visible in the source text

- Motor Technology, 515 Willow Springs Lane: building addition and a planning recommendation with outstanding review comments (record 2665). Useful to a broker, engineer or neighboring owner; it must not say final municipal approval.
- Wawa, 301 Eisenhower Drive: revised plan and review deadline on a Hanover planning agenda (1562). Useful project discovery; an agenda deadline does not establish a decision.
- Kinsley/Musser Farm, Board Road and Zions View Road: an industrial rezoning discussion, explicitly before a formal application (2221). Mentioned again in 2665, demonstrating a potential longitudinal case.
- Dalfen/Gateway Logistics Center: warehouse-related consolidation with wellhead/stormwater concerns, with land-development review still ahead (6843).
- Shaub subdivision, West Cloverdale Avenue: 19 lots and two cul-de-sacs mentioned for future review (6843).
- 99 Hokes Mill Road: residential-to-light-industrial rezoning hearing (4742).
- York City: a Spanish agenda includes retail, quick-service food, and a proposed fourth housing unit at identifiable addresses (5048). English-only screening would miss important content.
- 3 South Main Street, Stewartstown: acceptance of a municipal lot bid subject to a deposit (5324). Useful transaction context, but neither closing nor a development approval is established.

Smaller fence, steep-slope and lot-line cases belong in the site history and relevant customer watches. They should not fill the Development Radar merely because they contain zoning vocabulary. A consolidation at 609/613 Range End Road expressly states there is no intention for development (1234).

## Backfill blockers found

1. **Wrong jurisdictions:** penntownship.org identifies Penn Township, Butler County; paradisetownship.org identifies Paradise Township, Lancaster County. The current York corpus contains 342 and 211 records respectively from those document domains (553 total; 37 dated in the recent window). These are source-domain-associated counts, not a manual review of all 553 documents. The sampled Penn minutes explicitly give Butler PA 16002; the Paradise notice explicitly gives Lancaster County. Repair the configured sources and reviewed source policies, quarantine/re-version affected source records, and re-evaluate downstream derivatives. Do not silently delete raw evidence or rewrite historical migrations.
2. **Wrong dates:** 4742 is stored July 1 but its hearing header says July 23; 6843 is stored July 1 but its meeting header says July 27; 5048 is stored January 1 but its agenda says January 15; 5324 is stored April 1 but its minutes say April 6. Month-only metadata must not become an invented first-of-month event.
3. **Wrong board labels:** Hanover planning/ZHB and even library-board material appears under Council; Manchester ZHB appears under Supervisors. A recommendation from one board is not an approval by another.
4. **Mixed packets and duplicate coverage:** New Freedom's March packet includes February draft minutes, financial tables and the current agenda. Split the document into dated sections or preserve section-level provenance before deriving a timeline. The 28 duplicate recent documents are only exact normalized-text duplication; translated versions and slightly changed packets need additional handling.
5. **Case identity and stage:** names alone are insufficient for reliable merging. Use municipality, site/address/parcel and docket references. Keep proposed, recommended, approved-with-conditions, withdrawn and completed distinct. A template saying approve/deny is not a decision.

Official jurisdiction confirmation: [Penn Township contact/address](https://penntownship.org/) and the [Paradise ZHB notice](https://paradisetownship.org/wp-content/uploads/2025/02/ZHB-Notice-01152026.pdf). Individual source links are in the companion JSON.

## Product and cost recommendation

Ship the account workspace, organization directory and direct case search now. Make Projects a discovery section once accepted inventory exists; show coverage and source dates honestly. Keep Radar focused on material development signals rather than every municipal case.

After source correction, start with recent planning and zoning documents plus relevant supervisors/council follow-ups. Deduplicate before model calls, reuse extracted text, segment financial packets, retain no-action outcomes and process changed documents incrementally. Avoid an English-only hard filter. Produce one cited event extraction and reuse it for case timelines and watch notifications; do not pay for a new narrative per customer or per page load.

A small reviewed canary should include every failure category above and several recurring projects. Acceptance requires correct county/body/date, exact supporting evidence, correct decision stage and reliable site linkage. Measure actual useful unique cases and actual spend before expanding. This review establishes source usefulness, not model extraction accuracy or a projected dollar cost.

## Later local-state observation

At 22:05 UTC the real local database had migration 058 and metadata review version
2 applied: 3,267 currently eligible documents across 74 bodies, including 501
dated in 2026, with 3,192 current documents still requiring review. Extractions
remained zero. This updates processing status, not the source-sample assessments
or the decision to require a reviewed extraction canary. See the
[continued production review](production-readiness-review-2026-09-04.md) for the
read-only snapshot evidence and limitations.
