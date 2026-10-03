# York County site-intake research

Decision date: October 3, 2026. This is the selected implementation direction,
not evidence of customer demand or a completed product pivot.

## Buyer, trigger and deliverable

Serve the project manager at a small civil/site-engineering or land-planning
firm working in York County, Pennsylvania. The trigger is a client inquiry with
a candidate property and intended use. The recurring job is preparing a
research handoff for proposal scoping and the first municipal conversation.

CountyIQ should help the manager answer:

1. Have we identified the right parcel and municipality?
2. What do the available maps and records establish about this site?
3. Which prior municipal actions belong to this property or application?
4. Which questions still need an answer, and where should the reviewer look?
5. Can another team member check the research without repeating it?

The deliverable is a saved inquiry and an exportable, cited research packet.
The proposed use is client input. A mapped intersection is a calculation.
A municipal decision is a source-supported observation. Reviewer notes are
private work. These have distinct roles and must remain distinguishable.

## Why this direction

The earlier multifamily/entitlement-feed evaluation recorded 21 distinct
requests over eight months and reached five requests in only one month. That
failed its recurrence gate. This is historical evaluation evidence from the
September 27 niche work; its unpushed artifacts must be reconciled with the local
checkout before being treated as part of this branch. Generating more cards
from the same requests would not repair the failure.

Client-supplied inquiries provide a different source of work. York-based
[Site Design Concepts](https://sitedc.com/our-services/master-planning-site-feasibility-analysis/)
lists due diligence, site selection, feasibility studies and zoning/ordinance
review among its services. This establishes a local professional task; it
does not establish a bottleneck, purchase intent, or permission to contact the
firm.

Competitors prevent claiming that combined parcel maps or citations are a
defensible advantage:

- [SiteFacts](https://www.sitefactsreport.com/) advertises sourced parcel
  screening and human-verified, jurisdiction-specific reports.
- [PlotForge](https://siteplangenerator.com/feasibility-report/) advertises
  printable parcel screening with named and dated public datasets.
- [Zoneomics](https://get.zoneomics.com/zoning-reports-and-compliance) offers
  zoning reports and compliance reviews.
- [Shovels Decisions](https://www.shovels.ai/blog/decisions-api-launch/) competes
  in early municipal development intelligence.

These are current vendor claims reviewed on October 3, not independent tests of
their accuracy or York County coverage. Competitors' existence supports a
recognized task but does not validate CountyIQ's version.

The advantage to earn is reliable local research handoff: correct municipal
jurisdiction, correctly linked site history, transparent source gaps, and
less review/research time on the firm's own checklist. CountyIQ already has
useful identity, spatial, municipal-history and citation components. That is
an implementation advantage, not yet a commercial moat. A citation drawer
alone does not satisfy this direction.

## Primary customer journey

**My site inquiries → identify property → describe intended use → review site
evidence and municipal history → resolve or retain questions → save/export the
handoff → return when inputs change.**

The shared workspace shell, property page, source viewer and export behavior
remain the foundation. Source/activity/map/organization views are supporting
research paths. A general opportunity ranking should not be the first task
for this buyer.

An inquiry needs a stable identity, its PIDN, the user's proposed use and notes,
review state, outstanding questions, and the source revision last reviewed.
Account isolation, existing workspace conflicts, guest export/import and clear
storage failure behavior must be preserved. Saved notes cannot confer truth on
a source finding. Changed or withdrawn evidence must require renewed review
without silently rewriting the user's notes.

The handoff should put the site, proposed use, findings and unresolved questions
before assessment values or speculative commercial scores. It should retain
the original document links, relevant passages, dates and the limits of the
research in print/export. Empty, ambiguous and stale cases are first-class
journeys, not fallback success screens.

## Data acquisition and cleaning

Prioritize sources that can change an intake decision:

| Source                                                             | Role in the packet                                    | Required truth boundary                                                          |
| ------------------------------------------------------------------ | ----------------------------------------------------- | -------------------------------------------------------------------------------- |
| County parcels, addresses and municipal boundaries                 | Confirm the site and reviewing jurisdiction           | PIDN remains canonical; an address match can need review                         |
| Zoning map and the actual municipal zoning/SALDO text              | Locate mapped zoning and the rules to verify          | A center-point zoning match does not establish the whole parcel or permitted use |
| FEMA, soils, conservation and agricultural layers                  | Identify mapped constraints for further investigation | Missing, partial or stale coverage cannot become a cleared constraint            |
| Site-linked municipal applications, agendas, minutes and decisions | Explain the relevant procedural history               | Discussion, recommendation, proposed motion and final action remain distinct     |
| Project-specific utility and access records                        | Support a question or documented commitment           | Proximity does not establish service, capacity, legal access or availability     |

The [YCPC mandated-review page](https://ycpc.org/323/Mandated-Reviews) explains
that county review and municipal decision-making are different roles, with
county approval applying to the listed borough exceptions. Review the actual
governing source for the case; do not infer approval from a county plan listing.

Before adding broad new feeds, establish current health and freshness of the
existing layers. Check per-job failure and sensor/run-ledger state. Do not
solve a stale-source warning by increasing its threshold or replacing an
unknown value with zero.

For every acquired document, retain publisher/jurisdiction/body identity,
document kind, original URL, observation time, stated meeting/effective date,
content hash, and coverage status. Reject wrong-state/same-name municipalities.
Deduplicate repeated files independently from mutable board/display labels;
preserve multiple source memberships when the same file is legitimately listed
by more than one body. Exact duplicate files and distinct project revisions
are different cases.

Acquisition/retention/display rights and publisher restrictions remain governed.
New ordinances, review letters and utility documents require their own verified
source and use policy. Prior permission for a municipal minute source is not
blanket permission for every linked system.

## Intelligence contract

Use deterministic code for identity validation, spatial intersections,
freshness, duplicate handling, source-current checks, and saved-work state.
Use semantic interpretation only for bounded unstructured document tasks that
are supported by the existing inference and citation review boundary.

Every finding must state what its source establishes. Unknowns should point to
a useful next verification step. A new inference needs supporting passages,
contrary evidence where present, and review of source meaning; literal quote
matching alone is insufficient.

Do not generate a single buildability score, assert that the proposed use is
permitted from a zoning label, infer available sewer capacity from a nearby
line, treat an agenda motion template as a decision, or turn source silence
into no restriction. A source's last successful refresh and the date of its
underlying record are separate facts.

Reading an inquiry must not start paid model work. Generation remains bounded
and explicit under the existing cost controls. This direction does not
authorize an unbounded county-wide backfill.

## Acceptance and commercial test

Technical acceptance must demonstrate the complete journey with actual current
records and include wrong/ambiguous identity, absent or stale layers, partial
mapping, repeated/changed documents, conditional versus final decisions,
source withdrawal, save/reload, account isolation, export, and desktop/phone
behavior. Tests of one helper cannot certify the entire journey.

For a commercial pilot, use three firms' actual new client inquiries over
30 days. Proposed continuation gates are:

- At least five distinct qualifying sites per firm; revisions do not inflate
  the count.
- Median net staff time saved of at least 45 minutes after verification and
  corrections, measured against the firm's present workflow.
- Every substantive finding is checkable; zero wrong-jurisdiction results or
  material constraints incorrectly described as cleared.
- At least two firms purchase their next two packets at a price agreed before
  the trial, with delivery cost below half the price.

These thresholds are product decisions, not measured results. No interviews,
outreach, paid pilots or customer savings have been established by this work.
Do not describe the niche as commercially validated until that evidence exists.

## Implementation and acceptance — October 3

The site-inquiry branch implements property identification, intended use, private
notes and questions, review state, current source receipts and text handoff
export. Account snapshots retain existing conflict detection and now include
inquiries; older clients preserve the new field. Guest export/import includes it.
Source evidence is resolved live rather than copied into private saved work.
Export rechecks policy and the evidence revision before downloading.

Flood screening now distinguishes positive SFHA overlap, complete explicitly
classified non-SFHA coverage, and unknown coverage. Zone D, missing mapping,
partial coverage, boundary-only contact and rounding do not establish a negative
result. Acquisition freshness and map-effective dates remain separate. Property,
map, comparison, source viewer and CSV consume this distinction.

Local acceptance passed 242 real PostgreSQL/PostGIS API tests, 70 frontend tests,
TypeScript, ESLint and the production build. A real browser verified parcel
search, save/reload, review and export, with no horizontal overflow at 390 pixels.
The municipal history preserves literal source passages and record kinds rather
than generating new conclusions or invoking paid models on read.

Production acceptance is recorded separately after release. Customer demand,
pricing and measured time savings remain unvalidated. The existing data cannot
establish utility capacity, permitted use or complete municipal history. New
ordinance and utility sources still need verified source rights and bounded
acquisition before they can become product evidence.
