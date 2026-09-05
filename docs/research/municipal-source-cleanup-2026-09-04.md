# Municipal source cleanup — September 4, 2026

The cleanup is implemented and applied to the **local real-data database**, countyiq on port 5433, through migration 058. No paid LLM calls or production deployment ran. Synthetic fixtures stayed in countyiq_test.

The corpus supports a small project-extraction pilot. It does **not** yet justify a full LLM backfill: metadata eligibility is not proof of useful projects, correct parcel links, or reliable extraction.

## Measured result

| Measure | Result |
| --- | ---: |
| Original current proceedings audited | 7,414 |
| Wrong-jurisdiction records quarantined | 925 |
| Exact duplicate records quarantined | 30 |
| Remaining current records | 6,459 |
| Original records receiving metadata corrections | 3,700 |
| Corrected SCD2 versions created during review | 3,809 |
| Current records passing metadata checks | 3,264 |
| Current records held for further review | 3,195 |
| Eligible recent documents, January 1–September 4, 2026 | 494 |
| Municipalities represented in that recent set | 46 |
| Recent documents matching the existing land-use prefilter | 476 |
| Prepared pilot | 30 documents across 19 municipalities |

The 3,264 metadata-ready total includes verified future-dated documents. The extraction query excludes them until their meeting date. The 494 recent documents are already date-eligible.

All **7,414 original source fingerprints matched after cleanup**, including original date, board, document URL, source URL, content hash, and text. Corrections create new versions; quarantines expire current validity without deleting evidence. The original 175,928 current parcels remain unchanged. No proceeding extractions existed before or after this work.

[Machine-readable audit and source comparisons](municipal-source-cleanup-2026-09-04.json) · [Prepared pilot manifest](municipal-source-pilot-2026-09-04.json)

## Wrong-jurisdiction sources

| Configured municipality | Retired domain | Actual jurisdiction | Current records quarantined | Correct York County site |
| --- | --- | --- | ---: | --- |
| Penn Township | penntownship.org | Butler County, PA | 342 | [Penn Township](https://penntwp.com/) |
| Paradise Township | paradisetownship.org | Lancaster County, PA | 211 | [Paradise Township](https://paradisetwpyorkco.com/) |
| Windsor Township | windsortownship.com | Eaton County, MI | 345 | [Windsor Township](https://windsortwp.com/) |
| Jackson Township | jackson-township.org | Huntingdon County, PA | 27 | [Jackson Township](https://jacksontwpyork.org/) |

Nine old board policies are paused. Their domains are removed from active county configuration and explicitly rejected by ingestion. Penn’s correct governing body is the **Board of Commissioners**.

The identity comparison covered the original 113 configured board entries. Its baseline is the [2025 York County directory hosted by Warrington Township](https://warringtontwp.org/wp-content/uploads/2025/02/2025-Directory-York-County-Officials.pdf), with current municipal-site checks for changed domains. The 2026 directory could not be retrieved successfully; this is not a claim that every identity was freshly certified against that edition. The audit separates directory matches, current-site checks, and wrong-jurisdiction findings.

Legitimate domain changes were retained, including New Salem, East Hopewell, East Prospect, West Manchester, York Township, Loganville, and Washington Township. Goldsboro’s current site was verified directly; its directory entry lacked a website. Directory/manual checks cover Spring Garden, Springettsbury, York City, and York County.

## Replacement acquisition status

Eight identity-verified replacement listings are recorded separately in county configuration. They are **not active collection sources** and do not reuse the contaminated source identities.

Static checks followed robots rules and recorded status, document counts, and origins:

- Penn Commissioners / Planning / Zoning: reachable, with 30 / 31 / 26 document links.
- Jackson Supervisors: reachable, with 14 document links.
- Windsor Supervisors / Planning: reachable, with 244 / 103 document links.
- Paradise Supervisors / Planning: robots endpoint returned HTTP 403; collection skipped.
- Paradise Zoning: no verified dedicated proceedings listing; no replacement invented.

Link counts are discovery counts, not verified individual meetings. Penn’s combined annual documents need a collection and document-boundary check. The six reachable replacements still need a limited collection test and source-policy release before activation. Existing reviewed municipalities provide sufficient material for the first extraction pilot.

## Metadata corrections and guards

Month-only filenames no longer manufacture the first day of the month. Calendar-invalid dates are rejected, exact header dates are preferred, and conflicting dates are held. Spelled-out dates in filenames are supported without joining unrelated lines into a date.

Examples from the original source IDs:

- Stewartstown 5324: April 1 corrected to **April 6, 2026** from the header.
- West Manchester 4742: July 1 corrected to **July 23, 2026**; retained on hold because the primary board still needs confirmation.
- Hanover 1562 and 1577: catchall Council attribution corrected to the **Planning Commission** and **Zoning Hearing Board**.
- Franklin 1234: conflicting 2025/2026 header dates remain unresolved.

Committee meetings, joint meetings, library/fire boards, annual calendars, mixed agenda/minutes packets, cancelled meetings, missing board identities, and inadequate text are held conservatively. These holds overlap; issue totals must not be added as distinct-document totals.

The scraper records review status before paid processing. Pending extraction also checks current source permission and meeting date. Historical repair no longer runs an in-place date-clearing UPDATE during scraping.

The cleanup command defaults to a dry run. Apply recomputes the reviewed plan under row/policy locks, rejects stale inputs, checks retained ready records for incremental duplicates, and refuses affected records with existing extractions. An append-only review ledger connects originals and replacements. Repeating the final audit produced zero unapplied records.

## Pilot and customer-value decision

The manifest contains eight planning, eight zoning, and eight governing-body property candidates, plus six documents without the current prefilter vocabulary. The latter test potential missed leads as well as true negatives; absence of vocabulary is **not** a human relevance judgment. One includes a site-specific liquor-license transfer, which should be assessed against the intended product scope.

This is a deliberately enriched sample, not a random estimate of countywide project yield. No pilot extractions have run.

Use the existing quality-release process to measure:

1. Whether a customer can identify a real property/project and verify the source.
2. Whether agenda proposals, notices, recommendations, and final decisions remain distinct.
3. Whether parcel/organization links are correct and uncertain matches stay unresolved.
4. Whether repeated meetings improve one case file instead of generating duplicate projects.
5. False positives, missed leads, extraction failures, and actual cost per useful case.

A useful next result is a reviewed pilot with actual case yield and cost. A full backfill should wait for that evidence.

## Verification

- 998 pipeline tests passed; 71 integration tests deselected from that broad run.
- 25 targeted schema/cleanup database tests passed against countyiq_test.
- 15 API contract tests passed.
- Dagster definitions import/load validation passed.
- All original source fingerprints preserved; no wrong-jurisdiction current records remain.
- Final repeat audit: zero unapplied records.
- Local API readiness and frontend returned HTTP 200: API localhost:8000, frontend localhost:5173.

One pre-existing Dagster deprecation warning appeared in a development-momentum schema test. Municipal source health remains degraded where sources are blocked; an HTTP 200 health response is not a claim that all municipal feeds are healthy.

## Reproducing the cleanup

From pipelines/, using the intended database connection in DATABASE_URL:

~~~sh
.venv/bin/alembic upgrade head
.venv/bin/python -m scripts.review_proceeding_metadata --plan /path/to/review.json
# Inspect the plan before applying the same file.
.venv/bin/python -m scripts.review_proceeding_metadata --plan /path/to/review.json --apply
~~~

Apply requires a same-day, unchanged plan. It does not run extraction or activate replacement sources. If existing derivatives are detected, review/retract those through the intelligence lifecycle before attempting source repair.
