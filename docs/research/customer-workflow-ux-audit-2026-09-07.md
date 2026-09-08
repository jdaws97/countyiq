# CountyIQ customer workflow and information-design audit

September 7, 2026. Follow-up to the earlier customer intelligence assessment.
Read-only application review; no application changes, database writes, paid model
calls, deployment, or backfill. Temporary guest watches and comparison selections
were removed after testing. Screenshots and browser snapshots are in
`output/playwright/ux-walk-20260907/`.

## Decision

**A broad redesign of information hierarchy and navigation is justified.** The
problem extends beyond verbose copy: discovery is divided between Activity and
several score views; useful explanations repeat across a property report; source
verification exposes implementation data; and following a matter does not yet
give the customer a clear account of what changed.

Retain the useful foundations: search, parcel maps, ownership records, municipal
passages, explicit coverage, watches, and source links. Organize them around:

1. What changed in the places or properties I care about?
2. What does the record establish, and why might it affect my investigation?
3. What remains uncertain or needs checking next?
4. Where is the exact supporting passage?
5. How will I find the next development in this matter?

This is a product-design recommendation based on an observed walkthrough and
published research. It is **not validated customer demand**. Actual customers may
prioritize acquisition sourcing, active-project tracking, or feasibility work
differently. The design should preserve those paths while testing which is the
recurring paid job.

**Before a full LLM backfill:** settle and validate the explanation, relationship,
date, and source presentation contract on a bounded representative sample. Avoid
generating a large stock of summaries whose meaning, granularity, or required
facts will immediately need revision. Completing every proposed interface change
is unnecessary before backfill.

## Scope and limits

I used the actual local application at `app.localhost:5180` and its marketing page
at `localhost:5180`, with real served records. I inspected desktop at 1440 × 1000
and selected flows at 390 × 844. I followed the restaurant hearing from discovery
through explanation, evidence, original PDF, property, owner/adjoining context,
watch, and comparison. I also investigated the highest-ranked Radar property,
its map and owner portfolio; searched plan names, plan IDs, addresses, and a
municipality; and inspected the municipality directory and detail page,
organization directory, workspace, and all four Radar modes.

This covers the major customer surfaces and their recurring field types. It does
not claim every possible data-dependent variant was available. Project case-file,
authenticated watch controls, and print preparation received code inspection;
there was no populated project case-file journey in this local sample. Live
sign-in, cross-device synchronization, actual notification delivery, and print
layout remain unverified. This was not a comprehensive accessibility audit.

The application and local data changed during the review. The later snapshots
contain the new explanations and hearing dates. **The Hearing filter now returns
two records, and the owner profile now shows the correct December 1, 2025 latest
sale.** The earlier report's zero-hearing and owner-date findings are historical,
not current defects. The recommendations below use the later state where it was
available. All local coverage and counts are sample observations, not production
coverage claims.

## What the walkthrough demonstrated

| Journey                         | Observed result                                                                                                                                                          | Customer consequence                                                                        |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------- |
| First visit → useful activity   | Workspace emphasizes property search, with Radar and municipality entry cards.                                                                                           | Good for a known address; weak preview of why a customer would return daily.                |
| Feed → restaurant hearing       | Later card has a useful title, address link, date and substantive explanation. Its summary remains clamped to two lines after expansion.                                 | Improved discovery, but the action intended to reveal nuance still conceals it.             |
| Explanation → original          | Original PDF opens successfully. Earlier flow required details, receipt, then original; newer date citations shorten part of this path.                                  | Source access exists, but it competes with nested disclosure and technical metadata.        |
| Restaurant → property detail    | Explanation, source list, municipal record and lower timeline repeat the matter.                                                                                         | More scrolling produces repeated information rather than deeper understanding.              |
| Top Radar property → map        | Map fits the property. A polygon click is needed to open its detail panel. The adjoining acquisition and nearby plan are not jointly presented as investigation context. | The customer must reconstruct the reason for opening the map.                               |
| Property → owner                | Portfolio and linked parcels work; the corrected latest sale is visible.                                                                                                 | Useful foundation, but recent ownership activity is harder to scan than holdings totals.    |
| Known plan ID → search          | Exact `LD2025-5-1`, copied from a visible municipal record, returns no results.                                                                                          | A customer cannot recover a matter using its own public identifier.                         |
| Municipality → search/directory | “York Township” search produces ownership/property results; directory emphasizes delinquent parcels and debt.                                                            | Neither entry naturally answers “what is happening in this municipality?”                   |
| Watch → return                  | Restaurant watch survives reload. Row says “No recent recorded change” while municipal activity appears below.                                                           | Persistence works locally; the change language leaves the customer unsure what was checked. |
| Compare → share                 | Two properties compare locally. Share copies `/compare`; that URL in a fresh browser has no selected properties.                                                         | The recipient cannot reproduce the comparison.                                              |
| Compare → mobile                | Table container is about 341 px wide with 760 px of content and no clear scroll prompt.                                                                                  | The second property can be missed.                                                          |

Selected evidence:

- [Expanded mobile card](../../output/playwright/ux-walk-20260907/25-mobile-details-current.png)
  and [expanded source fields](../../output/playwright/ux-walk-20260907/26-explained-source.txt).
- [Updated mobile property](../../output/playwright/ux-walk-20260907/28-explained-property-mobile.png)
  and [updated desktop property](../../output/playwright/ux-walk-20260907/29-explained-property-desktop.png).
- [Map after selecting the parcel](../../output/playwright/ux-walk-20260907/14-map-selected.png),
  [plan-ID search](../../output/playwright/ux-walk-20260907/17-project-id-search.png),
  and [municipality directory](../../output/playwright/ux-walk-20260907/19-municipalities.png).
- [Watches](../../output/playwright/ux-walk-20260907/08-watches.png),
  [mobile comparison](../../output/playwright/ux-walk-20260907/35-compare-mobile.png),
  and [fresh-browser comparison](../../output/playwright/ux-walk-20260907/36-comparison-fresh.txt).

## Research and its implications

These sources inform the design; they do not substitute for interviewing CountyIQ
customers.

| Research or local workflow                                                                                                                                                 | What it supports here                                                                                                                                                                                                                                                                            |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| [NN/g: Progressive Disclosure](https://www.nngroup.com/articles/progressive-disclosure/)                                                                                   | Present frequent decisions first and make deeper material easy to find. An explanation followed by sources is useful; several nested disclosures around the essential caveat are not.                                                                                                            |
| [GOV.UK: Accordion](https://design-system.service.gov.uk/components/accordion/)                                                                                            | Do not hide information all users need to complete the task. The proposed/confirmed distinction belongs beside the hearing date.                                                                                                                                                                 |
| [NN/g: Recognition and Recall](https://www.nngroup.com/articles/recognition-and-recall/)                                                                                   | Preserve recognizable names and context across navigation. Show the adjoining property's address and link it; do not make the customer remember it and search again.                                                                                                                             |
| [NN/g: Information Scent](https://www.nngroup.com/articles/information-scent/)                                                                                             | Link wording should reveal the destination and value. “August 11 agenda · relevant passage” is more useful than an unexplained E8 or generic record link.                                                                                                                                        |
| [GOV.UK: Writing for user interfaces](https://www.gov.uk/service-manual/design/writing-for-user-interfaces)                                                                | Use short, task-oriented labels and copy. Explain the record's consequence rather than the application's extraction method.                                                                                                                                                                      |
| [NN/g: Concise, Scannable, and Objective Writing](https://www.nngroup.com/articles/concise-scannable-and-objective-how-to-write-for-the-web/)                              | Use concrete action titles, short explanations, and restrained claims. Its older study supports direction, not a predicted percentage improvement for CountyIQ.                                                                                                                                  |
| [Fairview Township: subdivision submission/review information](https://twp.fairview.pa.us/wp-content/uploads/2025/10/SUBDIVISION-INFORMATION-SHEET-2025-final-REVISED.pdf) | The official workflow distinguishes submission, technical review, planning recommendations, governing-body action, other approvals, and recording. Stage and deciding body materially affect what a record means. Do not generalize one municipality's specific procedure to every municipality. |
| [YCPC: project review process](https://www.ycpc.org/678/Ordinance-Review-Process-Guidelines-PDF)                                                                           | Proposed and adopted ordinance actions are distinct. A customer-facing account must preserve procedural status.                                                                                                                                                                                  |
| [GOV.UK: Start by learning user needs](https://www.gov.uk/service-manual/user-research/start-by-learning-user-needs)                                                       | Treat our proposed recurring jobs and relevance preferences as hypotheses until observed with customers.                                                                                                                                                                                         |

The working customer hypothesis is a York County developer or acquisition
researcher who needs to triage local changes, understand a site's context, verify
consequential claims, and return when something changes. Public procedures support
the importance of dates, stages, conditions and actors. They do not establish
which customer segment will pay or how often it will use CountyIQ.

## Element-by-element disposition

“Remove” below means remove from the customer interface. Preserve internal
provenance needed for reproducibility and operations. “Secondary” means an
explicitly named, easy-to-find detail area, not an indiscriminate data dump.

### Entry points, navigation, and search

| Element                                              | Disposition                  | Proposed treatment and reason                                                                                                                                                                                 |
| ---------------------------------------------------- | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Brand and county identity                            | Keep                         | Useful orientation. Keep the actual geographic scope legible.                                                                                                                                                 |
| Global search                                        | Keep and extend              | Recognize addresses, public parcel identifiers, organizations, project names, plan IDs and municipalities; label result types clearly.                                                                        |
| Search placeholder “Property, organization, project” | Make truthful                | Current exact plan-ID failure breaks the promise. Add record/project lookup or narrow the stated capability until it works.                                                                                   |
| Workspace / Activity / Radar                         | Reorganize                   | Workspace becomes the personalized activity entry. Discovery can offer Recent activity and Property screening as clear modes, preserving deep links. Three competing starting concepts need less explanation. |
| Map                                                  | Keep                         | A spatial view of the current investigation or selected discovery results. Preserve scope and selection on arrival.                                                                                           |
| Watches                                              | Keep                         | Persistent followed matters and changes, accessible directly from workspace.                                                                                                                                  |
| More menu                                            | Simplify                     | Secondary directories, comparison and settings belong here. Municipality discovery deserves a visible path within activity and search.                                                                        |
| Back action                                          | Keep, clarify when necessary | Preserve filter, scroll and selected matter when returning from a property or source. Avoid an investigation that restarts after every detour.                                                                |
| Fresh workspace “Start with a property”              | Broaden                      | Offer known-property search and a small, coverage-scoped set of recent meaningful activity. Do not require a new customer to know an address.                                                                 |
| Recent investigations                                | Keep and enrich              | Show recognizable address/name plus latest known change or pending date when available.                                                                                                                       |
| Empty saved-search block                             | Reduce                       | Small invitation until used; do not let empty tools outrank actual intelligence.                                                                                                                              |
| Guest-storage warning                                | Keep once                    | “Saved in this browser” beside saving controls; account persistence belongs in the account area.                                                                                                              |
| Address search alternatives                          | Clarify                      | Exact address first; alternatives explicitly marked. “Strong match” on a nearby different address can mislead.                                                                                                |
| Municipality search results                          | Add direct destination       | A municipality page with activity, upcoming dates and coverage should precede incidental owner/address matches.                                                                                               |
| Organization search results                          | Keep, enrich selectively     | Identify recorded ownership and relevant activity without implying verified common control.                                                                                                                   |
| Marketing headline and workflow                      | Keep                         | “Follow local development. See the evidence.” describes a clear job. Preserve illustrative-view labeling and private-alpha coverage wording.                                                                  |
| Marketing repetition                                 | Trim later                   | Several sections retell discover/investigate/follow. One concrete sourced example would communicate more than another slogan. Lower priority than application friction.                                       |

### Discovery feed and cards

| Element                                       | Disposition                | Proposed treatment and reason                                                                                                                                     |
| --------------------------------------------- | -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Large heading, count, queue and filter area   | Compress                   | Keep useful scope and filters together so substantive activity appears sooner, particularly on mobile.                                                            |
| “Needs review” queue wording                  | Rewrite                    | Distinguish a customer's unread activity from records awaiting CountyIQ processing. A customer should not feel assigned an extraction-review queue.               |
| Municipality and date-window filters          | Keep prominent             | These are recognizable working scopes. Display active selections and an obvious reset.                                                                            |
| Matter/topic/category filters                 | Consolidate                | Use development applications, hearings, zoning changes, ownership activity and other meaningful topics. Avoid several overlapping classification controls.        |
| Latest/relevance ordering                     | Keep with clear basis      | Distinguish document date, actual event date and newly collected history. Relevance is a working preference, not an investment judgment.                          |
| Upcoming dates                                | Elevate                    | A small upcoming section with proposed/confirmed status; never turn an agenda's recommendation into a confirmed appointment.                                      |
| Routine extensions and administrative records | Group or filter            | Preserve access. Let relevance depend on what the customer follows; do not permanently discard extensions that matter to an active project.                       |
| “Development” badge plus repeated metadata    | Combine                    | One useful category/stage label. Do not repeat the same category above and below the title.                                                                       |
| Record title                                  | Rewrite                    | Lead with the action: “Restaurant liquor-license hearing requested.” Put the address in a separate linked location line.                                          |
| Short explanation                             | Keep primary               | Two or three concise sentences explaining what the record establishes and the material limit. No rigid truncation of essential nuance.                            |
| Expanded summary                              | Fix                        | The inspected `.intelligence-card-summary` styling clamps text to two lines even after details open. Expanded state must reveal the full explanation.             |
| Proposed hearing date chip                    | Keep                       | Show “Proposed: Sep 8, 6 pm” and the record supporting it. Proposed status must survive narrow widths and exports.                                                |
| Address/PIDN                                  | Address primary            | Public parcel ID is useful for precise lookup in details, but an address is the better ordinary link label.                                                       |
| “Near” versus “at”                            | Enforce consistent meaning | The restaurant property explanation says “near” in the heading but “at” in the body. Headline, map and relationship labels must agree with the accepted evidence. |
| Record/evidence counts                        | Secondary                  | Counts are not significance. Use “View source” or “3 related records” only when it helps predict useful depth.                                                    |
| “Review details & evidence”                   | Split by purpose           | “Read explanation” and “View source.” Readers should choose more context or verification without guessing what a combined control opens.                          |
| Related owner/property links                  | Keep specific              | Address/name plus a plain relationship: subject property, adjoining parcel, same recorded owner, nearby activity.                                                 |
| Generic next-step prompts                     | Replace                    | Give a supported next check, such as checking minutes for a recorded decision. Avoid asking questions the source already answers.                                 |
| Raw next-step citation token                  | Remove from rendering      | `[Evidence:source:P1]` appeared inside an expanded raw field. Render a usable source control and never expose unresolved citation syntax.                         |
| Coverage                                      | Place beside scope         | “1 of 95 known York Township records reviewed” is more useful near the feed than a distant general disclaimer. Allow dates/body detail on demand.                 |

### Explanations and source verification

| Field or element                                        | Disposition                   | Customer replacement                                                                                                                                      |
| ------------------------------------------------------- | ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Concise explanation                                     | Primary                       | Action, stage, scope, material date, significance and limitation. Significance may simply be that a decision remains pending.                             |
| Expanded nuance                                         | Keep                          | Conditions, prior steps, conflicts, related records and missing information that change understanding. Expand the same account rather than repeat it.     |
| Source excerpt                                          | Keep prominent in source view | Exact wording with relevant passage highlighted where available. Preserve qualifications and enough surrounding context.                                  |
| Source publisher/body                                   | Keep                          | York Township Board of Commissioners, for example; this tells readers who produced the record.                                                            |
| Document title, type and date                           | Keep                          | Distinguish agenda, minutes and decision; these support different claims.                                                                                 |
| Page/section                                            | Keep                          | Locate the claim. Open the original to the relevant page when available; page 1 of a multipage PDF is not always the supporting page.                     |
| Original document link                                  | Keep conspicuous              | “Open original agenda” predicts the destination better than a generic evidence action.                                                                    |
| Source relationship                                     | Keep in plain language        | “The agenda names this address,” “adjoining parcel,” or “nearby matter; not linked to this property.”                                                     |
| E1/E2/E8 citation labels                                | Rework                        | A compact marker may remain, but its accessible name/preview must identify the source. Avoid separate panels restarting numbering ambiguously.            |
| Twelve-item source list below property explanation      | Move                          | Open the relevant source beside the claim; provide a secondary “All sources” list. Unused receipts should not precede the next useful part of the report. |
| Generic duplicate source titles                         | Rewrite                       | Name the actual address or matter; two “Touching parcel” entries do not help a reader select the right one.                                               |
| Event Key / source record UUID or internal key          | Remove                        | No customer purpose. Retain internally.                                                                                                                   |
| Source Text SHA256 / other hashes                       | Remove                        | Internal integrity metadata; not a customer trust explanation.                                                                                            |
| Inference ID / explanation version / contract version   | Remove                        | Operational provenance. Do not move these into a customer “advanced” accordion.                                                                           |
| Base Weight / Weight / extraction confidence percentage | Remove from ordinary evidence | Model/ranking mechanics are not the confidence that a hearing occurred. Show the actual substantive uncertainty instead.                                  |
| Nested SourceId P1 / serialized Record Dates            | Replace                       | Present a readable date and its status, tied to the passage.                                                                                              |
| Empty “Decision Scope —” and similar fields             | Omit                          | If decision scope is unknown and consequential, state that once in the explanation. Empty database-shaped rows add no information.                        |
| “LLM interpretation is visibly separated…”              | Remove                        | The layout should demonstrate the distinction. One short “CountyIQ explanation” label is sufficient.                                                      |
| “How CountyIQ used it” boilerplate                      | Replace selectively           | Include only a helpful explanation of a non-obvious relationship, calculation or limitation.                                                              |
| Observed/imported date                                  | Secondary, precise label      | “Added to CountyIQ…” only when freshness matters; never substitute it for the record or event date.                                                       |
| Public plan number / deed book and page / parcel ID     | Keep in details               | These help customers search official systems. Unlike internal keys, they have an external investigative purpose.                                          |

The engineering cause is broader than a missed field name. `EvidencePanel.tsx`
iterates through `item.details` using a short denylist and generically renders
nested objects. Hiding `source_sha256` therefore does not hide
`source_text_sha256`, new inference fields, or future internal facts. Use explicit
customer presenters for each source type and an allowlist of useful fields.
Keep complete provenance in internal storage and operational tools. This is a
presentation contract, not a request to delete evidence.

### Property, map, owner and municipality

| Element                                                    | Disposition                | Proposed treatment and reason                                                                                                                                                  |
| ---------------------------------------------------------- | -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Five header actions before mobile property title           | Reduce prominence          | Address and current intelligence first. Watch is primary; map and source are contextual; compare/share/print can sit in a compact action menu.                                 |
| Tax/class codes in initial property view                   | Secondary                  | Keep a compact identity strip, with assessed value labeled. A tax class is not the reason a hearing matters.                                                                   |
| Property explanation + municipal card + timeline retelling | Combine                    | One current account, followed by a chronological history of changes. Record details and sources belong to that account.                                                        |
| Old adjoining acquisition in hearing explanation           | Include only if relevant   | Explain its relationship to the current investigation or move it to ownership context. Mere availability does not justify headline space.                                      |
| Opportunity / Momentum / Site scores                       | Demote and explain         | Use facts and changes as the lead. Screening scores can help interested users sort, but do not measure whether a municipal record deserves reading.                            |
| Constraints                                                | Summarize by consequence   | Current zoning, flood overlap, soils and unresolved utilities are useful site questions. Do not claim feasibility from a high screening score.                                 |
| Current zoning versus future use                           | Keep distinct              | Future-use mapping does not establish current permitted use. This distinction belongs next to the values.                                                                      |
| “No mapped FEMA SFHA overlap”                              | Rewrite                    | “No overlap with the mapped high-risk flood area,” with map/source date and scope in details. Avoid implying all flood risk is excluded.                                       |
| Soil codes / “Not Hydric”                                  | Plain summary first        | Explain the mapped soil characteristics relevant to the investigation; retain map-unit codes in source detail. Avoid treating one label as a site approval.                    |
| Repeated generic soil caution                              | Consolidate                | One concrete limitation with an appropriate next check. Repetition dilutes the caveat.                                                                                         |
| Two identical “AUXILLARY BUILDING” rows                    | Clarify and verify         | Could be separate structures. Give each a distinguishing location/type/record reference; investigate the source before deduplicating.                                          |
| Assessment and sale figures                                | Keep labeled               | Assessment is not market value; show sale date beside consideration and clarify transaction scope where known.                                                                 |
| Previous owner / deed fields                               | Secondary                  | Preserve full names, readable dates and useful official references. Avoid arbitrary truncation.                                                                                |
| Nearby parcels ranked by scores                            | Reorient                   | First offer adjoining parcels, same-owner holdings and related municipal activity. Unrelated residential results several hundred metres away distract from the current matter. |
| Adjoining-property evidence text                           | Make internally navigable  | An address link should open the property; the GIS source remains available separately.                                                                                         |
| Map parcel highlight                                       | Keep                       | Good spatial orientation. Open the selected property context on arrival.                                                                                                       |
| Map investigation context                                  | Add                        | Subject, adjoining acquisition and nearby plan should have distinct labels and relationships; carry them from the explanation.                                                 |
| Map layer controls                                         | Keep, group by job         | Parcel/zoning/flood layers aid screening. Distress/vacancy/radar filters should not define every investigation.                                                                |
| Owner portfolio totals                                     | Keep                       | Useful overview, with clear recorded-ownership scope.                                                                                                                          |
| Owner narrative empty state                                | Rewrite                    | State the actual source/time coverage and absence of qualifying changes. Remove prose about CountyIQ not inventing narratives.                                                 |
| Owner portfolio table                                      | Reorder                    | Address, relevant recent action, sale date/consideration, acreage and municipality before technical identifiers. Add a portfolio map when useful.                              |
| Organization directory grid                                | Reconsider default ranking | Largest holdings are not necessarily recent activity. Offer activity and municipality filters alongside name lookup.                                                           |
| Repeated organization verification sentence                | Consolidate                | Explain recorded-name grouping once; show record-specific uncertainty only where it changes interpretation.                                                                    |
| Municipality directory debt columns                        | Replace default            | Show latest relevant action, upcoming date and coverage; retain delinquency as a separate optional lens.                                                                       |
| Municipality totals                                        | Reduce headline space      | Static parcel/debt/opportunity counts should not precede what happened and what is next.                                                                                       |
| Long municipality record list                              | Add structure              | Topic/date controls and useful current-matter grouping, rather than repeating the same expansive card everywhere.                                                              |
| Coverage processing counts                                 | Keep available             | Compact “reviewed / known” summary with source/body/date scope; awaiting/review/future categories can expand. Never translate partial processing into “no activity.”           |

In the updated mobile restaurant report, the document measured about 8,064 px
tall. Municipal records began around y=2,181, scores around 3,225, and the timeline
around 7,556. These measurements depend on that viewport and data, but demonstrate
the cost of placing a receipt list and repeated sections between the explanation
and the history. The goal is fewer competing sections, not smaller typography.

### Following, screening, comparison and conditional features

| Element                                            | Disposition                   | Proposed treatment and reason                                                                                                                                                  |
| -------------------------------------------------- | ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Watch action and reload persistence                | Keep                          | Worked in the isolated guest session. Live account persistence still needs separate acceptance.                                                                                |
| “No recent recorded change”                        | Fix scope                     | Specify “No parcel-record changes…” if that is all it covers; otherwise integrate municipal changes into the watched property's summary.                                       |
| Prominent unlabeled assessed amount on watch row   | Label or demote               | Latest relevant action and pending date are more useful return cues.                                                                                                           |
| Watched properties versus matching activity        | Unite visually                | Each followed matter should show what changed and why it matched, with access to its full activity.                                                                            |
| Why watched / private next action                  | Consider lightweight addition | A note or follow-up reason helps resume an investigation; validate demand before building a CRM.                                                                               |
| Export/import workspace                            | Secondary                     | Utility belongs in workspace settings; it is not the primary experience of monitoring.                                                                                         |
| Sync now / Load saved copy / Clear saved workspace | Account/error recovery        | Code-inspected controls. Surface only when needed, with the consequence explained; ordinary use should not require understanding synchronization.                              |
| Browser alerts                                     | Clarify capability            | Do not imply email or reliable background delivery from an in-browser setting. Live delivery was not tested here.                                                              |
| Radar Opportunity/Momentum/Movers/Site Screening   | Reorganize                    | Separate observed recent changes from static site screening. Customers should not need to learn three score models to find relevant activity.                                  |
| Minimum score defaults such as “recommended”       | Reword                        | A threshold is a screening preference, not evidence of suitability. Prefer recognizable property and activity filters.                                                         |
| “Why It Ranked”                                    | Keep, improve specifics       | State which property changed, on what date, and its relationship. The top common-owner claim needs those details.                                                              |
| Movers: “0 risers” / generic no matches            | Improve empty state           | Explain the selected period/basis and available history. Offer reset without implying that no development occurred.                                                            |
| Site screening score 95                            | Demote                        | Top result's park designation and mapped attributes should be readable first; high score alone is insufficient for a site decision.                                            |
| Comparison table fields                            | Refocus                       | Preserve physical/ownership facts; add the relevant action, current zoning, constraints and unknowns when comparing an investigation. Evidence count is not evidence strength. |
| Comparison introduction mentioning scores          | Correct                       | The observed table does not show the scores its introduction references. Copy must match the surface.                                                                          |
| Comparison Share                                   | Fix before release            | Encode the selected properties in a reproducible URL or saved report; fresh-recipient acceptance is required.                                                                  |
| Mobile comparison                                  | Redesign                      | Sticky field labels plus explicit horizontal controls, or a readable stacked comparison; keep both compared properties discoverable.                                           |
| Print / Save PDF                                   | Verify separately             | Code opens all receipts before printing, risking a long technical appendix. Design a concise report with optional sources and inspect rendered output.                         |
| Project case-file sections                         | Integrate and validate        | Existing status, conditions, milestones, participants and timeline support the proposed journey. No populated real case was available for acceptance here.                     |
| Unresolved parcel references                       | Explain without false linkage | “Location not yet established” with the actual named place; do not force uncertain matters into a property report.                                                             |

## Proposed customer presentation

Use one coherent matter account across discovery, property, municipality and
watches. Each surface can choose its depth; avoid independently authored summaries
that conflict or repeat the same information at different points on one page.

### First level: enough to decide whether to open it

**Restaurant liquor-license hearing requested**
2861 East Prospect Road · York Township
**Proposed hearing: September 8, 6 pm**

The August 11 agenda requests a hearing for a liquor-license transfer to a
restaurant at this address. It recommends September 8 at 6 pm; this agenda does
not confirm that the hearing was scheduled or that the transfer was approved.

**Read more** · **View source** · **Watch**

This is editorial example copy grounded in the
[inspected official agenda](https://yorktownshippa.gov/wp-content/uploads/BOC_2026-08-11-Agenda.pdf),
not a newly tested model output. The proposed date should not appear as a
confirmed countdown. The date/status wording remains visible at this first level.

### Second level: nuance that changes the investigation

Explain the request, procedural stage, relevant prior actions, subject-property
relationship and unresolved questions. For this example, the next useful check is
the meeting notice or subsequent minutes for scheduling and action. Do not add an
investment recommendation or an unrelated ownership narrative merely to fill a
“Why it matters” field.

On a property report, put this current account before a short site/ownership
context section, followed by history. Use clear section links on long reports.
The source opens beside the relevant claim in a panel on desktop and a readable
full-width view on mobile, with a return to the same reading position.

### Third level: verification

Show publisher/body, agenda date, exact passage, page/section if known, the
relationship to the matter, and **Open original agenda**. Keep all relevant
sources available through an explicitly labeled list. Do not show hashes,
inference IDs, model weights, serialized objects or boilerplate about extraction.

The important distinction is **summary versus supporting record**. Customers do
not need to understand the internal pipeline to assess a claim.

## Work before backfill versus later work

| Sequence                   | Required outcome                                                                                                                                      | Why it belongs here                                                                                               |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Before broad generation    | Agree on the short explanation, expanded nuance, dates/status, subject relationship and source fields using real examples.                            | These choices affect what must be generated and retained.                                                         |
| Before broad generation    | Review a bounded end-to-end canary in the intended presentation, including low-score but valuable records and unresolved locations.                   | JSON correctness alone cannot establish readable, complete intelligence.                                          |
| Before broad generation    | Ensure related records can retain their stage, deciding body, conditions, references and history without overwriting earlier meaning.                 | Backfill should produce reusable evidence and useful accounts rather than disconnected prose.                     |
| Before broad generation    | Re-estimate cost and apply the authorized cumulative budget to the actual selected explanation/interpretation passes.                                 | A changed generation contract changes the run being approved.                                                     |
| Before customer release    | Fix expanded text, customer evidence allowlists, missing citation rendering, contradictory location/status labels and misleading empty/change states. | These directly impair comprehension and trust. A representative version should already work during canary review. |
| Before customer release    | Deliver the discovery → explanation → source → persistent follow → subsequent change journey in the deployed environment.                             | Guest reload and local data do not prove production monitoring.                                                   |
| Before advertising sharing | Make comparison links reproducible and verify mobile/print output.                                                                                    | Recipients must receive the intended content. This does not determine LLM backfill semantics.                     |
| Iterative redesign         | Consolidate navigation and repeated report sections; improve search, relevance controls and map context.                                              | High-value UX work can proceed alongside accepted generation once the content contract is stable.                 |
| After workflow validation  | Expand permits, utility coverage, richer ownership history or CRM-like collaboration.                                                                 | These add scope; none is necessary to prove the current core intelligence journey.                                |

This supersedes the earlier assumption that most interface work could wait as
visual polish. The observed defects include hidden explanation text, misleading
relationships, inaccessible context and non-reproducible sharing. Some are
presentation fixes; others reveal missing product contracts. They should not be
collapsed into either “just trim text” or “rebuild the whole platform.”

## Acceptance and customer research

Use an initial twenty-case review as a practical proposal, not a statistically
representative accuracy claim. Include requested versus confirmed hearings,
recommendations versus governing-body decisions, conditional actions, extensions,
ordinance changes, low-score properties, nearby-but-unlinked matters, conflicting
records, repeated project appearances, stale records and missing dates/locations.
Inspect the source document for material events omitted from cards, as well as
checking generated cards for unsupported claims.

For each case, a reviewer should be able to:

1. Identify the action, place, stage and material date/status from the collapsed
   presentation without reading raw evidence.
2. Open a complete expanded explanation with no concealed essential qualification.
3. Explain what is known, what is uncertain, and what would change the account.
4. Open the supporting passage in one deliberate source action, then the original
   document with one further action, with the relevant location supplied when known.
5. Follow linked properties/organizations without confusing subject, adjoining,
   same-owner and nearby relationships.
6. Save the matter and later recognize a substantive change, while distinguishing
   a newly imported historical document from a new event.
7. Complete the same reading task at 390 px without clipped dates, concealed
   explanation text, or undiscoverable comparison content.

These are proposed acceptance criteria, not results already achieved.

Recruit a small first round across local developers/acquisition researchers,
brokers doing land research, and planning/entitlement consultants. Ask them to
bring a recent real investigation and the documents/tabs they used. Observe them
finding a relevant change, explaining it aloud, deciding whether to verify it,
following the source, saving it and returning to a later update. Record wrong
stage/date interpretations, navigation detours, missing information and whether
the result changes their next action. Compare a concise presentation with the
current one using different but similar records to reduce learning effects.

Ask what they monitored repeatedly, what they missed, how they currently detect
updates, and which decisions they would pay to make faster. Do not infer demand
from agreement with a proposed feature. A small usability round can identify
friction; repeat use and willingness to pay need subsequent behavioral evidence.

## Implementation touchpoints for a future change

No code was changed in this audit. The most relevant starting points are:

- `frontend/src/components/IntelligenceEventCard.tsx` and
  `frontend/src/styles/theme.css`: collapsed/expanded card contract and text clamp.
- `frontend/src/components/EvidencePanel.tsx`: generic field rendering, citation
  navigation, customer source vocabulary and disclosure structure.
- `frontend/src/components/SourceExplanation.tsx`, `RecordBrief.tsx`,
  `MunicipalEvidence.tsx`, and `frontend/src/pages/PropertyDetail.tsx`: unify the
  current account and remove duplicate presentation paths.
- `api/lib/evidence.py`, `source_explanations.py`, and `record_briefs.py`: separate
  customer evidence presentation from stored operational provenance; retain the
  content needed for meaningful dates, stages and relationships.
- `frontend/src/pages/WorkspaceHome.tsx`, `CountyFeed.tsx`, `SearchResults.tsx`,
  `MunicipalityList.tsx`, and `MunicipalityDetail.tsx`: customer entry and discovery.
- `frontend/src/pages/Watchlist.tsx` and `frontend/src/lib/watchSync.ts`: readable
  change scope and production follow-up acceptance.
- `frontend/src/pages/ParcelCompare.tsx` and
  `frontend/src/components/ReportActions.tsx`: reproducible sharing and report output.

Application test suites were not run because this task changed only the review
document. Verification consisted of actual browser interactions, screenshots,
DOM measurements, a fresh-session share check, source-document opening, and
focused code inspection. The findings should be rechecked against the final
implementation because concurrent local work changed some behavior during review.
