# Intelligence gaps after the cost optimization

Implementation follow-up: [product completion and remaining limits](pass03-product-completion.md).
The diagnosis below is retained as the before-state assessment.

September 7, 2026. Follow-up diagnosis only: reviewed archived source text and
model outputs, inspected current code, and queried local records without changing
production behavior or making further paid model calls.

## Judgment

The single-reader GLM approach and summaries assembled from source records are a
good inexpensive foundation. The current implementation is **not yet an optimal
replacement for the development-intelligence workflow**. Some savings remove
useful connections, and the existing extraction score understates that loss.
The next work should restore precise source associations and broaden a narrowly
defined priority queue, rather than restore paid interpretation everywhere.

## Concrete missed information

These examples were checked against the original retained source text and final
GLM selections. Commercial significance below is a new assessment; it does not
retroactively rewrite the frozen evaluation labels.

| Source | Omission or context loss | Significance |
| --- | --- | --- |
| York Township, August 11 agenda, source 10688 | Request for a restaurant liquor-license transfer hearing at **2861 East Prospect Road**, with September 8 at 6 pm recommended | A named commercial-property lead with a next date. Worth recovering. The source requests a hearing; it does not establish approval or that the hearing ultimately occurred. |
| Spring Grove, July 20 minutes, source 8766 | YMCA reported on track to open August 3, with tours available | A useful facility-completion/occupancy milestone. More valuable for tracking project stages than identifying a new construction bid. |
| Loganville, August 31 agenda, source 9659 | **$230,000 Westridge Drive/Ferndale Road repaving estimate** retained without its enclosing **Budget Planning for 2027** heading | Important context defect: a potential future work item becomes less clearly distinguished from current or funded work. Two other selected infrastructure passages lose that heading too. |
| Newberry, July 28 reports, source 6414, PDF page 11 | Valve pit ordered from Monarch to relocate the influent pump-station flowmeter | A real utility/equipment project update, though the named order is already placed. Potential supporting work, not an established open procurement. |
| Hopewell, July 2 minutes, source 1884, PDF page 4 | Armstrong Cable conditionally allowed approximately four months of temporary truck/trailer parking while working in the area | A local infrastructure-work clue. No precise construction boundary or customer is established. More relevant to equipment/service intelligence than land acquisition. |
| West Manchester, August manager report, source 9481, PDF pages 5–6 | York Fair representatives expected fairgrounds refinancing approval in early September; township payment was expected afterward | A useful financing/stage clue for an identifiable property. This is a reported expectation, not proof of completed financing or distress. |
| Hopewell expenses, source 1884, PDF page 8 | $1,347 Act 537 legal charge; $712 BV Lot 3 engineering charge; other named legal matters | Weak but potentially useful corroboration. They establish recorded expenses, not a new project, funding award, approval or procurement opportunity. Do not restore a main-feed card for every invoice. |

Not every omission is consequential. Mount Wolf's Emerson Flats reference asks
for an updated valuation for budget millage calculations; it does not report a
transaction or a new development action. The omitted PA American Water rate
increase specifically says the township's residents are exempt. Newberry's
MESB grant references concern monitoring, reimbursement and close-out; they are
less actionable than a new funding award. New stone bins appear to involve
municipal work using an acquired barrier wall, not an announced construction bid.

Several dense PDF examples above have `review_required` source metadata in the
local database, so the API currently withholds the whole record. Those examples
describe reader quality conditional on source clearance, not solely new losses
caused by this optimization. York, Spring Grove and Loganville examples have
ready metadata. Source readiness/OCR is a separate coverage problem.

The selected run misses 17 of 291 in-scope reference topics, plus seven expenses
excluded by policy. Six missed references were labeled material. However, the
liquor-license hearing and fairgrounds refinancing were labeled nonmaterial in
the frozen rubric. For the broader commercial-intelligence goal, that rubric is
too forgiving. The earlier **97.2% material-topic coverage is not a measurement
of retained end-to-end business value**.

The archived stronger Luna Pro reader also omitted the restaurant hearing, YMCA
opening, flowmeter/stone-bin/MESB details and fairgrounds refinancing. It retained
Armstrong's parking arrangement and some budget headings, but still omitted the
road item's budget heading. This is evidence against buying a stronger read for
every document as the default remedy; the trials are not a causal experiment
isolating model capability from prompting and selection policy.

## Larger workflow gaps

### Municipal evidence does not populate property signals

`persist_evidence` writes retained municipal selections to inference history.
The property municipal-action signal and linked-proceedings query still read
`staging.proceeding_extractions`. No adapter supplies that path from new evidence
cards. Consequently, a successfully retained municipal finding does not by
itself reach parcel signals, their downstream notifications, or the Pass 1
municipal-activity priority filter.

A concrete example is **Hanover Community Church, 1959 Smith Station Road**.
The accepted August agenda selection retains a final-plan consideration and
completed DEP-required stormwater revisions. The exact address exists as parcel
`30000DE0017L0`. It already has an independent subdivision signal, but no
municipal-action signal for this update; source 10262 has no structured
extraction. Existing information was not deleted. The new update simply does
not flow through the older property path.

Recommended design: associate literal evidence with uniquely matched PIDNs or
addresses inside the correct municipality, preserving document type and date.
An association should say the record mentions the property, and must not infer
that an agenda proposal passed. Ambiguous matches remain municipality-level.
This can plausibly recover substantial value with deterministic code rather
than another general-purpose LLM pass; its accuracy still needs validation.

### Owner priority excludes acquisition activity

Primary re-execution of the production selectors found 6,151 candidate groups,
318 selected and 5,833 deferred. Among deferred groups:

- 439 have an existing recent-sale signal, including **76 organization groups**.
- 1,887 have a sale or one of the two assemblage signals, including 351
  organization groups. These categories overlap and must not be summed.

One deferred D.R. Horton name-variant group has 19 parcels with ownership-change
signals and 17 with entity-assemblage signals. No member is in the selector's
plan/municipal-activity name set. These are candidate associations, not an
accepted identity merge or proof of additional holdings. Nonetheless, describing
all deferred work as merely speculative understates its potential value.

Recommended next scope: prioritize acquisition-active organizations and
user-watched owners as well as plan/municipal activity. Start by evaluating the
76 organization groups with recent sales, rather than reopening all 5,833.
Re-estimate actual eligible calls and measure useful identity recovery before
committing to an ongoing budget. No revised dollar estimate is claimed here.

### Free summaries retain facts but not every connection

The record summary selects at most four findings and three verification questions
from existing signals. Detailed records remain on the property page. Replacing
generated prose is a reasonable saving, but a summary cannot explain a new
municipal development if that evidence never reaches its inputs. Restoring that
connection has higher priority than paying to improve prose.

## Next optimization order

1. Restore exact, source-bound property associations without inventing outcomes.
2. Retain governing year, procedural stage and date headings around excerpts.
3. Expand owner prioritization to high-value acquisition activity.
4. Re-evaluate named commercial hearings, facility milestones and utility work;
   test selective recovery before considering second reads for dense documents.
5. Keep accounting detail available as supporting source evidence. Test whether
   named expense references add novel leads before paying to interpret them.

Keep the one-source GLM reader, free exact-registration tier, early vote stopping
and summaries from existing records. None of this follow-up establishes a global
cost/quality optimum. It identifies concrete gaps worth addressing while keeping
most of the measured savings.

## Evidence

- Prior evaluation and exact selections:
  `output/pass03-optimization/primary-quality-final.json` and `glm-high-full/`.
- Source archives:
  `glm-high-full/sources/<source_id>.json`; PDF links and bytes are retained in
  the accepted-workspace manifest from the prior evaluation.
- Identity inventory and independent primary check:
  `output/pass03-optimization/missing-intelligence/identity-scope.json` and
  `identity-primary-check.json`.
- Relevant code: `municipal_evidence_pipeline.persist_evidence`,
  `development_signals` municipal-action SQL, `api/routes/parcels.py` linked
  proceedings, `ACTIVE_ENTITY_NAMES_QUERY`, and `build_record_brief`.

No new paid inference, identity merge, source-publication change or production
code change was made for this diagnosis.
