# York municipal source recovery — September 8, 2026

The operator health page is deployed at <https://app.countyiq.net/ops/health>.
The API verifies the signed identity against the configured operator allowlist;
ordinary customer and anonymous requests cannot read operational health.
Municipal coverage alert reminders are limited to once per day.

## Scope and countywide reconciliation

The original 20 unhealthy body sources belong to 16 municipalities. Those
municipalities were already configured; the work repairs collection and archive
discovery rather than inventing 16 duplicate municipalities.

The broader inventory reconciles all **72 incorporated municipalities**
(35 townships, 36 boroughs, one city) against the York County Planning Commission
municipal boundary layer. Configuration grows from **104 to 112 body sources**
and **64 to 68 municipalities**. One configured source is county-level; a
municipality is counted when it has at least one configured body. This does not
claim complete coverage of every municipal board or every historical document.

The [municipal table](york-municipal-coverage-2026-09-08.md),
[machine-readable inventory](york-place-coverage-2026-09-08.json), and
[named-place CSV](york-named-place-coverage-2026-09-08.csv) contain the complete
reconciliation. The CSV covers all **383 York County USGS GNIS Populated Place
records**, including named villages, communities, and neighborhoods. The primary
review independently matched all GNIS IDs, names, and coordinates to the
downloaded source and recomputed every point-to-municipality assignment.
These are geographic names, not 383 independent municipal governments. The GNIS
point identifies a governing municipality; it does not define a community's full
extent or establish completeness for informal names absent from GNIS.

Authorities: [YCPC municipal contacts](https://www.ycpc.org/325/Municipal-Contacts),
[YCPC boundaries](https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/Municipal_Boundary/FeatureServer/0),
[USGS GNIS populated places](https://prd-tnm.s3.amazonaws.com/StagedProducts/GeographicNames/Topical/PopulatedPlaces_National_Text.zip).

## Added York sources

Migration 077 creates eight new source identities with reviewed official
listings, origins, sample records, and robots evidence. The obsolete sources
that pointed to similarly named municipalities in other counties/states stay
paused; their retained evidence is not reassigned.

| Municipality | Added bodies | Verified official archive |
| --- | --- | --- |
| Penn Township | Commissioners, Planning Commission, Zoning Hearing Board | [Commissioners minutes](https://penntwp.com/directory/committees/board-of-commissioners-meeting-minutes/), [Planning](https://penntwp.com/commissions/planning-commission/), [Zoning](https://penntwp.com/directory/boards/zoning-hearing-board/) |
| Paradise Township | Supervisors, Planning Commission | [Supervisors](https://paradisetwpyorkco.com/board-of-supervisors-meeting-agendas-and-minutes/), [Planning](https://paradisetwpyorkco.com/planning-commission-meeting-agendas-and-minutes/) |
| Jackson Township | Supervisors | [Minutes](https://jacksontwpyork.org/township-calendar-meetings/township-meetings-minutes/board-of-supervisors-meetings-minutes) |
| Windsor Township | Supervisors, Planning Commission | [Supervisors](https://windsortwp.com/board-of-supervisors-meeting-minutes-agenda/), [Planning](https://windsortwp.com/planning-commission-meeting-minutes-agenda/) |

Every added body has a public linked PDF independently retrieved and checked for
the expected municipality/body. Some Windsor Planning PDFs are scans without
extractable text; archival success does not imply searchable text extraction.

## Recovery of the original problem sources

The [original source-by-source audit](municipal-source-health-2026-09-08.md)
records the reported failures and the subsequent public-source findings.

| Municipality | Change or verified limitation |
| --- | --- |
| Goldsboro | Council uses its dedicated current minutes table, including rendered pagination. Planning has no supported records found; the ZHB zoning map is excluded as a non-meeting document. |
| Manheim | Reviewed Chromium transport retrieves public meeting documents after checking robots with the same transport. |
| North York | Reviewed Chromium transport retrieves public PDF and Word records. |
| Springettsbury | Current archive exposes HTML agendas/minutes. Only Supervisor links and the reviewed main content are collected; the published ten-second delay is honored. |
| Yorkana | Replaced expired domain with the official hyphenated domain; HTML minutes are archived and readable content extracted. Publication dates are excluded when identifying the meeting date. |
| Hellam | Current meeting archive, bounded detail-page traversal, and body-specific agenda/minute/packet discovery. Shared storage is restricted to the township's reviewed ProudCity directory, including redirects. ZHB agendas/packets are evidence even when minutes were not confirmed. |
| Dover | Current document archive is scoped to Planning minutes. Document landing pages are followed to their actual PDF attachment. Cancellation notices are excluded as non-document entries; historical broken downloads remain possible. |
| Manchester | Supervisor archive articles are selected explicitly so ambiguous Planning filenames cannot be attributed to Supervisors. |
| Peach Bottom | The Supervisor column is selected from the rendered page, excluding Planning files previously misattributed to Supervisors. |
| East Hopewell | Public first-party Wix documents are discoverable and some download successfully. Other files redirect to an unreviewed filesusr origin whose robots response denies access; those remain visible failures. |
| Lower Windsor | Working current Planning minutes verified; dead older links are not concealed. |
| North Codorus | Valid minutes coexist with historical 404s; partial failures remain reported. |
| Spring Grove | Valid Council minutes coexist with old broken links. |
| Shrewsbury Borough | Official download handler sometimes labels DOCX as legacy Word; recognized file signatures determine the extension before validation. |
| Shrewsbury Township | ZHB meeting schedules are not minutes and are excluded. Remaining public links and broken historical paths stay accurately classified. |
| Delta | Current archive and embedded Drive folder are identified. Automated document collection remains blocked on the Drive delivery paths; the public folder is not evidence that no records exist. |

Reviewed browser transport uses Chromium's actual identity plus CountyIQ
identification, checks robots before collection, and does not retry an explicit
denial using another transport. Browser documents share the existing global and
per-body request budgets. Bytes are spooled to disk until the download phase;
the browser stays on the main thread and database writes remain serialized.
Raw HTML is archived alongside extracted text using the existing evidence and
SCD2 workflow. No LLM extraction or customer publication is triggered by the
collection-only verification.

## Four remaining municipal coverage gaps

| Municipality | What was found online | Remaining gap |
| --- | --- | --- |
| Cross Roads Borough | Official county directory, officials/contact information, meeting schedule, and [OOR agency record](https://www.openrecords.pa.gov/RTKL/AOROInfo.cfm?id=2837). | No usable official online minutes archive confirmed. This is not a claim that no information or obtainable records exist. |
| Railroad Borough | County directory and [OOR agency record](https://www.openrecords.pa.gov/RTKL/AOROInfo.cfm?id=2883), which says the borough does not maintain an Internet website. | No usable official online minutes archive confirmed. |
| West Manheim Township | [Public minutes archive](https://westmanheimtwp.com/boards-comissions/board-of-supervisors/minutes/) and downloadable meeting records. | Current [robots file](https://westmanheimtwp.com/robots.txt) explicitly disallows all automated paths. |
| West York Borough | [Official minutes page](https://www.westyorkpa.gov/borough-meeting-minutes/) and public Drive folders. | Drive embedded/download paths and drive.usercontent delivery are robots-blocked; no alternative first-party document archive confirmed. |

Cross Roads and Railroad are archive-discovery gaps. West Manheim and West York
have records online but lack a usable automated collection route under the
current checks. These cases remain visible rather than being marked healthy.

## Validation and rollout

- Operator access: authentication/authorization tests, API contract check,
  frontend typecheck/lint/build, and desktop/mobile Chromium checks passed.
  Production anonymous access returns 401; configured operator identities pass.
- Migration 077 upgraded normally from 076 on the dedicated test database.
  All 112 configured source tuples matched their reviewed policies. Sampled
  obsolete Penn, Paradise, Jackson, and Windsor policies remained paused.
- Pipeline regression: 1,884 passed, 136 integration tests deselected. Definitions
  imported successfully. After the final Peach Bottom and Dover corrections,
  150 focused collection/parser/configuration tests passed.
- Bounded live-web collection used the dedicated test database with strict local
  raw archives, 28 selected bodies, and one new document request per body.
  Retrieval, archive, text, source attribution, and health results were inspected.
  Remaining live failures include historical 404s, restricted delivery redirects,
  absent meeting records, and image-only PDFs. The final 28-body run archived
  19 documents and inserted 18, retaining one interrupted test-database write as
  a partial error. A subsequent Dover-only check retrieved and inserted the
  August 5, 2026 Planning minutes with zero errors. Peach Bottom found all 12
  current Supervisor links and correctly skipped its already-known documents.

Production collection results are recorded after the coordinated release.
