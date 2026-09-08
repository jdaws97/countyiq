# Structural alternatives to full-document extraction

The strongest result is a change in what supplies the inventory: use official
plan-review records directly and retain searchable source passages alongside
them. Generated interpretations still make material errors. These experiments
support building around source evidence; they do not establish an unattended
replacement extractor.

The user authorized substantially different designs, new tools and complete
rewrites if experiments support them, and rejected a human-review service.
This work tests six alternatives in research artifacts. No production pipeline,
schema, API, frontend or deployment was changed.

## Results

| Alternative | Actual experiment | Result and decision |
| --- | --- | --- |
| Official records supply the inventory | Parse three county reports; independently query the configured county GIS layer by received month | Strongest candidate. 62 report rows recovered. July GIS query independently returned 30 rows, including all 28 PDF rows and two additional records. These are review cases, not necessarily distinct projects or approvals. |
| Preserve and search every captured passage; interpret questions on demand | Index 436 DOCX body paragraphs; 11 positive and two negative queries; 13 question-answer calls | All 11 positive questions retrieved their required evidence within three results. Both negative questions received correct abstentions. One answer reversed a responsible actor; two had incomplete citation coverage. Keep evidence search; do not promote generated answers to authoritative facts. |
| Source-specific deterministic parsing | County table parser plus municipal heading selector trained on two earlier minutes | Table rows work in this format. Municipal selector retained only 7/11 topics and missed the warehouse in the fire report. Reject it as a discovery gate. |
| Task-specific learned relevance | Fixed-vocabulary multinomial Naive Bayes trained on 132 paragraphs, with three positive examples | Retained context for only 1/11 topics, without its complete key evidence. This tiny experiment fails as a usable filter. It does **not** adequately test a well-trained domain model; that avenue remains inconclusive. |
| Cross-document histories and corroboration | Exact-name passage histories, exact-ID PDF/GIS agreement, and same-name/location collision checks | Useful evidence timelines and 28/28 cross-source row matches. Shared names, dates and map points do not establish a single project or revision. Keep source-case identities and candidate links separate. |
| Literal decision evidence instead of generated event fields | Deterministically retain paragraphs containing a motion and “Motion carried” | Retains all six reference decision passages, along with 21 other motion passages. No invented action enum, but substantial noise and no automatic project interpretation. A useful evidence layer, not a finished event extractor. |

## Corpus and comparison limits

The fresh municipal corpus is six Dillsburg Borough DOCX files. January and
February 2025 are development sources for the local selectors. March through
June 2026 are a temporal test set: 304 body paragraphs containing 11 required
topics. The complete corpus contains 436 nonempty body paragraphs.

The reference was established by primary-agent reading of the complete sources
before the paid calls. It is model-assisted source review, **not independent
human gold**. Queries were designed after reading those sources; they are not
customer questions. The municipal results concern one municipality and four
test meetings. The county reports cover multiple municipalities but test a
different, tabular task. There is no combined accuracy percentage across them.

The corpus reader preserves native `word/document.xml` body text with original
paragraph indices. Those indices are not physical pages. Preserving all 436
captured paragraphs does not prove that an arbitrary PDF or scanned document
was read correctly. Header/footer, tracked-change and other document-format
handling are not general capabilities established here.

Eighteen paid calls used the same Luna model, low reasoning, OpenAI-only routing,
8,192-token output ceiling and existing cumulative authorization ledger. Five
calls read complete documents: four tests and February's empty-topic control.
Thirteen answered fixed queries from the three highest-ranked source passages.
The full-document baseline retains the v105 discovery/action contract, with
only the adaptation from PDF page citations to DOCX paragraph IDs. It does not
include the v107 action-occurrence change.

Requests, references, source hashes and settings were frozen before dispatch.
No expected answers, reference topic inventory, expected count or scoring fields
entered model input. No generation retries, repeated-answer selection or prompt
tuning occurred after the first response. Comparing the two readers changes the
task as intended: exhaustive extraction versus answering a supplied question.

## Official records: a concrete architectural alternative

The [YCPC reports catalogue](https://ycpc.org/233/Subdivision-Activity-Reports)
provides monthly lists of reviewed plans. A coordinate parser developed from May
2026 recovered 21 May rows, 13 June rows and 28 July rows. July's four rendered
pages contain 9, 7, 9 and 3 rows; primary review rechecked all four pages. The
parser retains first-line ID, received date, municipality and title cells with
word coordinates. It does not yet normalize the full multiline location,
parcel, use or quantity fields.

More usefully, CountyIQ **already configures and ingests** the county's
`OPEN_DATA/PLANNING_Subdivisions/FeatureServer/0` layer. The new idea is making
these source records the discovery inventory, rather than treating them only
as a supporting signal for other records. This is not a newly discovered data
feed or a missing geometry ingestion fix: the existing asset already attaches
the point geometry separately from its attribute parser.

Two checks were run against that public layer:

1. An exact-ID lookup returned all 28 July PDF records. IDs, titles and received
   dates agreed, and all rows had point geometry.
2. An independent query used only `DATE_RCVD` from July 1 through August 1,
   with no PDF IDs or titles. Its count and bounded row response both returned
   30. Nothing from the PDF was missing. The additional records were `26-0146`,
   **177 South Harrison Street**, and `26-0147`, **Bobcat of York**, both with
   July 31 received dates. No date-window adjustment was made to force agreement.

The difference demonstrates why the PDF is not a complete oracle for the current
month-based GIS inventory. It does not establish why the records differ or that
the feed contains every county project. The server used its declared fixed EST
time reference for the query. This is a captured September 6 observation of July
records, not a freshness SLA.

The layer provides review IDs, titles, received dates, plan flags, development
metrics, notes and point geometry. It has no explicit approval/lifecycle field,
parcel-string field or plan-location text field. The PDF retains additional
parcel/location evidence. The related [building-permit page](https://ycpc.org/226/Building-Permit-Reports)
describes incomplete municipal reporting and directs individual-permit questions
to municipalities; it does not supply the missing complete lifecycle inventory.

The catalogue's old web-map item was inaccessible through two public metadata
endpoints. That blocked map does not make the separately configured public
FeatureServer unavailable; its successful receipts are retained separately.

## Evidence search and interpretation

The source index uses SQLite FTS5 with Porter stemming, fixed stop words,
BM25 ranking and a three-paragraph result limit. Every captured body paragraph
enters the index without relevance filtering. Test queries are restricted to
their requested meeting. This is not a test of unconstrained county-wide search,
semantic embeddings or automatic question generation.

The full-document reader found all 11 topics. That headline hides errors:

- It emitted two separate records for the single Pheasant Ridge/Windy Heights
  traffic study, each carrying the same Borough payment cap.
- In the April Logan Park dispute, it labeled an unresolved insurance request
  `tabled` and a planned meeting `recommended`, despite no such source actions.
- It returned one equipment-related scope extra. The empty February control
  correctly returned no records.

The source-question reader kept the shared study together, retained conditional
Impala driveway relief, distinguished audit authorization from missing audit
materials, and rejected both nonexistent-subdivision and data-center-approval
claims. But its warehouse answer changed “DAA is making them” modify a hydrant
into **DAA being required to modify it**. A valid source ID did not prevent a
wrong responsible actor.

Two other answers need citation repair: the Logan Park premium increase relies
on supplied paragraph 25, which the answer failed to cite; the Senior Center
answer cites the work description but omits the supplied paragraph establishing
the speaker's organization. The Impala source also has inconsistent ordinance
and memo labels that neither reader explicitly flags. These issues prevent a
claim of uniformly reliable answers.

The literal quotation diagnostic found four distinct baseline mismatches:
three capitalization-only differences and one insertion of “If” into an
Impala quotation. Those are separate from wrong actions or missing topics.

## Selectors and histories

The municipal template selects 91/304 test paragraphs and retains the key
passages for 7/11 topics. It drops Logan Park's April discussion, Senior Center
entrance work, the conditional-use fee amendment and the warehouse update.
These occur in community, administrative and fire-report sections outside its
selected headings. Sixteen unfamiliar-heading flags do not rescue those misses.

The learned classifier has only three positive training paragraphs. Its corrected
fixed-vocabulary version selects two test paragraphs from the Impala discussion,
retaining 2/26 relevant paragraphs and none of the eleven topics' complete key
evidence sets. The first implementation mishandled unseen vocabulary; primary
review caught it, preserved that run, and required a separate corrected run.
Only the corrected result is used here. No threshold tuning followed scoring.
A serious supervised-model comparison needs a much larger, independently
reviewed training set; this result cannot justify rejecting that entire approach.

Exact-name histories retain Logan Park's April dispute, May audit authorization
and June missing-materials update. They also retain incidental agenda mentions.
Pheasant Ridge matches both a 2025 Stoney Run road/drain decision and the 2026
shared traffic study. They are useful candidate passages, not resolved project
histories. An absent later Winfield match cannot mean no subsequent activity.

The county collision is stronger evidence against automatic merging:
`26-0119` and `26-0121` have identical municipality, title, received date and
point geometry, but different subdivision/land-development flags and other
attributes. Both remain separate official review cases. Neither a shared name
nor a shared parcel/point proves that one is a later revision of the other.

## What a replacement would change

The evidence favors a prototype with two independent inputs: official review
cases and all captured municipal passages. A project should not disappear from
search because a generative extractor omitted it. A narrative matter should not
disappear merely because it lacks a review-case ID.

Keep source snapshots, provenance, source-use controls and PIDN identity. Add
source-native case records and a passage index as first-class data. Use exact
case IDs for demonstrated joins; retain uncertain title/location matches as
candidates. Keep generated explanations attached to their evidence rather than
allowing them to overwrite official states. The current parcel-proximity signal
is not a substitute for an exact case-to-parcel identity relationship.

This can require replacing the extraction-centered storage and API contract,
adding source/case search and changing how watches obtain evidence. It is more
than a prompt patch. The present experiments justify that design direction,
but do not establish county-wide retrieval quality, complete lifecycle linking,
customer utility or error-free generated explanations. No production rewrite
has been promoted on that evidence.

## Artifacts, cost and verification

Artifacts are under `output/pass0-redesign-2026-09-06/structural-v108/`:
`corpus/`, `registry/`, `selection/`, the frozen reader requests/responses,
`reference.json`, `semantic_review.json`, `audit.json` and replay scripts.

From the repository root:

```bash
PYTHONPATH=pipelines pipelines/.venv/bin/python output/pass0-redesign-2026-09-06/structural-v108/audit.py
PYTHONPATH=pipelines pipelines/.venv/bin/python output/pass0-redesign-2026-09-06/structural-v108/audit_registry.py
```

Both offline audits pass. They verify source hashes, raw-passage preservation,
deterministic replays, all eighteen requests and schemas, supplied citation IDs,
source-reviewed topic mappings, and the independent GIS/PDF reconciliation.
These checks replay adjudication; they do not manufacture independent semantic
ground truth. The project formatter passes for all new Python artifacts.
Focused lint passes for the corpus, dispatch and audit helpers. A blanket lint
check also reports five cosmetic findings in already frozen evidence scripts
(stop-word literal, regex aliases and import spacing); those original bytes
remain preserved for reproduction.

API cost was **$0.0194854**: $0.015839 for five full-document calls and
$0.0036464 for thirteen question calls. This is the actual selected workload,
not a projected customer cost or a fair per-record accuracy/cost ratio. Query
volume, caching and retrieval scope would change production economics.
The cumulative ledger commits $6.274828828696 of the authorized $8, including
unchanged unresolved reservations from older work, leaving **$1.725171171304**.
