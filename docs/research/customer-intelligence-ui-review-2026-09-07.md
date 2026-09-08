# Customer assessment of CountyIQ intelligence

September 7, 2026. Read-only assessment of the current local application at
`app.localhost:5180`, its serving data, and the Pass 2/3 implementation and
existing evaluation artifacts. No application changes, database mutations,
provider calls, production deployment, or customer interviews were performed.

## Judgment

**Follow-up:** The implementation and 30-case review are now documented in
[Backfill readiness and summary-model comparison](backfill-readiness-2026-09-07.md).
That follow-up distinguishes technical readiness of GLM reading plus Luna
explanations from the unapproved higher spending scope and the cheaper models
that did not meet the same release bar. The assessment below records the original
pre-implementation findings.

**Backfill decision: NO-GO for the full customer-intelligence backfill today.**
The intended outcome includes concise explanations of the records. The current
records profile does not generate Pass 2/3 summaries, and the existing paid
brief path excludes evidence needed for that experience. The passing Pass 0
quality receipt establishes extraction readiness within its reviewed scope;
it does not approve the complete customer-intelligence output.

Change this decision to GO after a bounded end-to-end canary demonstrates:

1. Useful cited summaries include the approved municipal passages and relevant
   constraints, including properties with low opportunity scores.
2. Event labels and filters agree with those passages, with proposed and
   confirmed dates/stages distinguished correctly.
3. Twenty representative cases retain their material facts, dates, conditions
   and property relationships without unsupported consequential claims. Assess
   the summaries in the UI, not only their JSON and citation syntax.
4. The resulting pipeline has an updated cost estimate and a working cumulative
   spending limit covering the passes actually selected for the run.

The owner-date defect should be corrected before customer release. New permit
sources, richer acquisition history, utility coverage, broader narratives and
visual polish are later improvements; they are not prerequisites for this
backfill. Preserve reusable accepted extraction outputs while validating the
missing explanation path. No backfill is launched by this assessment.

CountyIQ is useful for investigating a known property and verifying a municipal
record. It is less effective at helping a customer quickly discover an important
change, understand its significance, and decide what to follow next.

I would use the current product as a research aid. I would not yet rely on the
reviewed instance as a comprehensive daily development monitor. This is a
product judgment, not a claim about demand or willingness to pay.

The layout is clean and readable. The larger weakness is editorial: the product
often displays the inputs and asks the customer to work out the answer. A concise,
grounded LLM explanation should be a primary product feature. Minimizing inference
cost is not an adequate substitute for reducing customer effort.

## What I actually inspected

In a real browser: the new workspace, default Activity feed and expanded event,
Hearing filter, Radar, the top-ranked Radar property, church and restaurant
property reports, York Township, an owner profile, property search, the highlighted
parcel map, and the empty guest Watches view. Desktop was 1440 pixels wide;
the restaurant report was also inspected at 390 pixels, with no horizontal
overflow. Existing authenticated watch implementation was inspected in code;
account sign-in and notification delivery were not retested in this assessment.

The local serving dataset matters to the conclusions:

- 60 municipal events across five municipalities; ten have property links;
  none has a project key.
- The current event view also contains 269 parcel delinquency changes. The
  default 90-day discovery request returns the 60 municipal events.
- No stored Pass 2 evidence rows, parcel briefs, or owner briefs are present.
- York Township displays one reviewed record out of 95 known records;
  Heidelberg displays two out of 51.

These are counts from the deliberately limited local review dataset. They do
not establish production coverage or how the product will look after a backfill.
They do establish which capabilities a customer can experience here today.

## Customer findings

| Customer task | What works | What gets in the way |
| --- | --- | --- |
| Find a known property | Search for Hanover Community Church puts its organization and three exact owner/property matches first. Property links and parcel highlighting work. | Search does not immediately communicate which matching property has relevant municipal activity. The fresh workspace gives little preview of useful intelligence. |
| Discover a lead | Radar explains why a property ranked. The first result identifies two touching parcels under the same recorded owner and a recent acquisition. | Three score concepts require interpretation. The top-level acquisition claim omits the date and which adjoining parcel changed hands. Static geography, nearby plans and actual changes compete for attention. |
| Understand a municipal record | Original wording, document type, property match and source document are accessible. The church source opens to page 2. | The “Record summary” repeats the agenda excerpt. It then asks what stage, conditions and dates the passage establishes, although much of that can already be explained. |
| Find something time-sensitive | The restaurant passage preserves a proposed September 8, 2026, 6 pm hearing date. | The default feed puts several time extensions above it. Its card is dated August 11 and labeled “Municipal record”; the proposed hearing date has no separate treatment. |
| Filter by the work I care about | Municipality and broad category filters exist. | The Hearing filter returns zero results despite hearing requests in the general feed. The explicit Development matter filter also returns zero. Current municipal events lack the structured tags/category details those filters need. |
| Follow a project over time | Project case-file code already supports status, decisions, conditions, milestones and a timeline. | None of the 60 currently served municipal events has a project key. Named plans in the feed therefore do not lead into that existing project experience. |
| Check an owner | Portfolio acreage, municipalities and linked parcels are useful. | BARLEY FARMS 2 LLC incorrectly shows January 3, 2024 as its latest sale even though its linked 2934 Cape Horn Road record has December 1, 2025 and $869,116. The UI compares non-ISO date strings lexically. |
| Understand coverage | Municipality-level reviewed/known counts and source dates are explicit. | The Activity page does not make the sampled coverage prominent. A large number of cards can feel like county coverage even when many came from one agenda. |

The feed also mixes rezoning and restaurant activity with parking-space approval,
tree work, roof replacement, payments and budget items under the same Development
badge. Those records can have value, but the customer needs relevance controls.
Preserve the records while distinguishing substantive development, routine
administration, infrastructure and procurement stages.

Repeated caveats occupy substantial space. Preserve the material uncertainty in
the main explanation—such as “proposed hearing; scheduling unconfirmed”—and keep
methodological detail in the source expansion. Feed property links should show
addresses without requiring expansion; a PIDN alone is a poor customer label.

The map is a useful spatial foundation and fits the selected parcel clearly.
Showing the named nearby plan and the same-owner adjoining parcel would better
explain the top Radar finding. The current report requires the customer to piece
together text, ownership and geography.

## Would LLM Passes 2–3 improve the product?

**Yes to customer-facing summaries. Selectively yes to interpretation of complex
signal combinations. Simply switching on the old pipeline would not deliver the
experience needed.**

| Work | Recommended role |
| --- | --- |
| Dates, arithmetic, parcel joins, source freshness, watch matching | Keep deterministic. The owner-profile date bug needs a deterministic correction. |
| A clear single municipal passage | A short LLM explanation can translate procedural language, identify the stated action and retain qualifications. It should not require a high opportunity score or two signals. |
| Several related records or conflicting signals | Pass 2 can assess relationships and limits: which parcel a plan concerns, whether a newer record changes the stage, and whether ownership evidence supports only a transfer or an accumulating parcel pattern. |
| Property/project explanation | Pass 3 should combine relevant source passages, structured facts, material constraints and unresolved questions into a concise cited account. |
| Opportunity recommendations | Treat these as a separate quality problem. A readable explanation is useful even when it cannot justify an investment or acquisition recommendation. |

The present pipeline has four product mismatches:

1. `municipal_record` is context-only. Pass 2's ordinary selection requires at
   least two interpretive signals. A single valuable hearing passage can be
   excluded.
2. Pass 3 selects from top-ranked eligible parcels with medium/high serving
   interpretive evidence. The restaurant's opportunity score is nine; the
   church's is zero. Neither score measures whether its record deserves a plain
   explanation.
3. Pass 3's signal context is restricted to interpretive evidence. It does not
   directly include the new literal municipal passages or the full set of
   mapped constraints. For example, the top Radar property's septic limitation
   belongs in a useful site explanation even though it is not an interpretive
   signal.
4. The generated Research brief is rendered far down the property report, after
   numerous factual sections. A useful explanation should appear near the top,
   with original evidence one click away, rather than duplicate a second long
   summary lower down.

I would allow a source-summary path independent of Pass 2 significance. Use the
more involved interpretation path when the evidence requires it. Cache accepted
summaries by the underlying evidence and regenerate when it changes; reserve
extra model work for cases where it changes understanding. Do not require two
LLM calls to paraphrase one straightforward passage.

Existing evaluations support caution about completeness, not rejection of LLM
summaries. The reviewed Pass 2 subset reported 59/59 grounded signal decisions
after targeted corrections. That is an AI-reviewed rubric result, not customer
outcome validation. The September 5 four-case Pass 3 artifact passed structural,
citation and production checks in all four cases, with no prohibited claims,
but passed the complete gold checks in only one. The other three failed
required-fact retention; their recorded recommendation checks passed. This tiny
sample identifies a completeness problem and does not establish a general model
accuracy rate or justify dismissing summarization.

## What a better explanation could say

These are assessment drafts written from the inspected evidence, not outputs
from a newly tested or deployed Pass 3 prompt.

**Hanover Community Church — final plan on the agenda**

> The August 5 agenda placed the church's final land-development and reverse
> subdivision plan up for consideration. It says the Planning Commission
> recommended approval in October 2025, the supervisors approved waivers in
> November, and DEP-required stormwater revisions are complete. The agenda does
> not establish whether final approval was granted. Check the meeting's minutes
> for the decision.

Support: the [August 5 agenda, page 2](https://heidelbergtwpmunicipal.com/wp-content/uploads/August-2026-BOS-Agenda-1.pdf#page=2).

**2861 East Prospect Road — restaurant liquor-license hearing requested**

> The August 11 agenda requests a hearing on transferring a liquor license to a
> restaurant at this address and recommends September 8 at 6 pm. That is a
> proposed hearing date; this record does not confirm the hearing was scheduled
> or the transfer approved.

Support: the [York Township August 11 agenda](https://yorktownshippa.gov/wp-content/uploads/BOC_2026-08-11-Agenda.pdf).

**495 Chapel Church Road — ownership activity, with unresolved site questions**

> This 62.7-acre property shares recorded ownership with an adjoining parcel
> acquired in December 2025. Current mapped zoning is low-density residential;
> the future-use map suggests mixed commercial and industrial uses but does not
> change today's zoning. Mapped soils show extensive septic limitations, making
> sewer availability a key unresolved question. The nearby Thornton plan does
> not establish a project on this property.

Support: the inspected property report and its acquisition, zoning, nearby-plan
and soil evidence. The recent acquisition is the adjoining parcel; the subject
parcel's last recorded sale is January 2024 for $1.

These explanations answer an actual question, preserve the distinction between
recorded facts and implications, and direct the next investigation. Avoid
generic “this may indicate an opportunity” prose.

## Ranked opportunities

| Priority | Opportunity | Customer benefit and required work |
| --- | --- | --- |
| 1 | Concise record and property explanations | Make the main action, stage, date and uncertainty immediately understandable. Extend the evidence context and place the summary prominently. Add structured topic/stage/date fields so the feed's labels, ranking and filters agree with its content. |
| 2 | Project continuity and a meaningful change summary | Connect successive agendas, minutes, revisions and scoped decisions to the existing case files. Explain what changed since the last record, what remains unresolved and which body acted. Distinguish a newly collected old agenda from new project activity. |
| 3 | Reliable upcoming dates and watch digests | Elevate proposed versus confirmed hearings, application deadlines, scheduled votes and explicit completion targets. The private inbox already exists; the additional value is a concise meaningful-change digest, deadline treatment and optional delivery outside an open app. |
| 4 | Buyer activity and adjoining acquisitions | Show the parcel, date and consideration behind an ownership signal; aggregate documented acquisitions by verified owner and municipality, without double-counting multi-parcel transactions. Current portfolios are a starting point, not a complete transaction history. |
| 5 | Site feasibility tied to the proposed use | Bring current zoning, future land use, soils, flood, access and documented water/sewer information together. Make missing utility capacity explicit. Existing mapped layers support screening; they do not answer service availability, capacity or permitted use on their own. |
| 6 | Permit progress, construction and occupancy | Connect planning activity to later environmental/building permits, inspections and documented occupancy. This would help customers distinguish a proposal from work moving toward execution. Availability varies by source and municipality. |

For new source work, Pennsylvania's official [DEP permit tracker](https://www.pa.gov/services/dep/track-an-environmental-permit-application)
supports searches and filtering by applicant, county, permit type, status and
submission date, plus review-stage history. This is a concrete investigation
candidate beyond the nearby DEP screening points already shown.

The [York County Recorder of Deeds](https://yorkcountypa.gov/539/Recorder-of-Deeds)
provides access to recorded real-estate documents. It is a source candidate for
transaction history; this review did not establish bulk access or product reuse
rights. [YCPC's reports directory](https://ycpc.org/198/Reports-Documents) lists
building-permit and subdivision-activity reports. Those may support coverage
checks or municipality trends; their listing alone does not establish an
address-level permit feed. York Township's [Building and Zoning department](https://yorktownshippa.gov/departments/)
is another local source to investigate for permitting information.

Additional promising uses of the existing records include ordinance changes
affecting specific uses or corridors, infrastructure projects by actual stage,
and named applicant/engineer/decision-body roles. These should expand from the
core property/project workflow. Procurement leads serve a somewhat different
customer and should not dilute a developer's default feed.

## Acceptance before broader rollout

Evaluate 20 real cases against the existing UI: a simple hearing, a routine
extension, a conditional decision, several meetings on one project, a nominal
transfer, a nearby-only plan, a soil/utility limitation and sparse coverage.
Require retained material dates/amounts/conditions and supported citations.
Have customers answer what happened, whether it is proposed or completed,
which property is involved and what remains unknown. Compare reading time,
correct answers and usefulness of the next step. Measure summary completeness
separately from recommendation quality.

Recommended order: correct the demonstrated date and filtering problems; ship
the concise explanation and structured record understanding; populate project
continuity and meaningful watches; then add acquisition and permit/utility
coverage. The first release should make existing evidence more useful before
adding broad county narratives or further scoring systems.

## Evidence and screenshots

- Summary selection and repeated generic questions: [record_briefs.py](../../api/lib/record_briefs.py).
- Feed ordering and filters: [feed.py](../../api/routes/feed.py).
- Owner date comparison defect: [OwnerRecordSummary.tsx](../../frontend/src/components/OwnerRecordSummary.tsx), `latestRecordedSale`.
- Existing project capability: [ProjectCaseFile.tsx](../../frontend/src/pages/ProjectCaseFile.tsx) and [case_files.py](../../api/routes/case_files.py).
- Signal eligibility: [signal_policy.py](../../pipelines/countyiq/lib/signal_policy.py).
- Pass 3 context: [pass3_brief_generation.py](../../pipelines/countyiq/lib/pass3_brief_generation.py), `gather_brief_context`.
- Pass 3 selection: [brief_generation.py](../../pipelines/countyiq/assets/enrichment/brief_generation.py).
- Existing evaluation: [Pass 2 rubric review](pass2-rubric-review-2026-09-04.md) and [Pass 3 four-case artifact](../../pipelines/eval/results/challenger_openai_gpt-5.6-luna_frozen_gold_20260905T155648Z.json).
- Browser evidence: `output/playwright/customer-review-*.txt` and `.png`.

![Default feed](/home/jdaws/countyiq/output/playwright/customer-review-feed.png)

![Top Radar property](/home/jdaws/countyiq/output/playwright/customer-review-top-property.png)

![Restaurant report on mobile](/home/jdaws/countyiq/output/playwright/customer-review-restaurant-mobile.png)
