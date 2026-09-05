# Revised municipal LLM evaluation — September 4, 2026

**Keep the project, public-works and municipal-policy features. Do not start the
full LLM backfill.** The approved 40-document evaluation completed for **$0.14069727**.
The revised prompt recovers useful information, but is not reliable enough to
publish. Its more complicated evidence contract rejects nearly all nonempty
documents. A confirmed date-parser defect has now been corrected and replayed
without additional model calls; substantial failures remain.

## Execution and isolation

- Local real database countyiq at localhost:5433 upgraded from 058 through 061.
- Original frozen 30 documents: 30 calls, $0.10741412 against a $1 cap.
- Held-out 10 documents: 10 calls, $0.03328315 against a $1 cap.
- All 40 responses reported OpenAI serving openai/gpt-5.6-luna. Costs reconcile
  with the durable authorization ledgers; no semantic retries.
- Both runs used the same prompt/configuration/code identity, verified against
  the workspace before the subsequent date-parser-only correction.
- Full source texts, requests, responses, costs and source hashes are archived.
  No responses were edited, no extractions or aliases were published, and no
  quality approval receipt was issued.
- Final real-data check: migration 061, 175,928 current parcels, zero proceeding
  extractions, zero proceeding project aliases. Synthetic data stayed isolated.

The machine-readable [results and all 40 document reviews](municipal-llm-v2-results-2026-09-04.json)
include hashes and artifact locations. This is a Codex qualitative source review,
not independent human adjudication or a formal precision/recall gold set. The
original sample is enriched for relevant matters; the ten-document held-out sample
is small and stratified. Neither predicts countywide yield.

## What passed

| Measure | Original 30, revised prompt | Held-out 10 |
| --- | ---: | ---: |
| Successful / schema-valid responses | 30 / 30 | 10 / 10 |
| Extracted matters before gates | 111 | 33 |
| Documents passing the evaluated contract | 4 | 1 |
| Nonempty documents passing that contract | 0 | 1 |
| Matters surviving the whole-document gate | 0 | 3 |
| Independently quoted passages | 233 | 59 |
| Passages absent from source after whitespace normalization | 15 | 0 |
| Documents passing after offline date-parser correction | 5 | 1 |
| Matters surviving after that correction | 2 | 3 |

Four passing original documents were empty controls. After the date correction,
only **two nonempty documents and five matters** survive across the forty.
These are structural acceptance counts, not customer-approved useful projects.
Even the passing held-out document classifies an existing-tower lot subdivision
as development despite no stated new construction.

The earlier baseline passed 13 documents and retained 32 matters under its older,
less demanding contract. The revised contract catches additional problems but
currently makes the serving yield worse. We should fix that contract, not waive it.

## Useful progress

The same source data supports worthwhile customer workflows:

- Prosper's approximately 73-unit proposal, Raising Cane's redevelopment,
  The Learning Experience daycare/office plan, BAE's new office and the Long Level
  boathouse are concrete investigation leads. Pending applications and denied relief
  remain useful when accurately labeled.
- All four notable baseline omissions were recovered: Goodwill's proposed
  $350,000 social-hall remodel, Dillsburg conditional-use fees, North Sherman Street
  bidding and East Hopewell road-paving bids.
- The false CUH 2026-10 project inferred from a next-case footer disappeared.
  CUH 2026-8/9 no longer received the generic submission-calendar deadline.
- Hanover's July decisions and Jacobus's June event retain the earlier event date
  instead of the containing meeting date. The Warrington historical date still uses
  a two-digit source year and needs explicit anchoring or an unresolved date.
- Read-only SQL replay leaves Game Club Road, street intersections and ambiguous
  127 N. West Street unlinked. Explicit Cardinal Lane IDs resolve two parcels;
  Long Level IDs resolve the two existing matches without inventing a third.
- Candidate identity replay joins Sprich across three documents, Washington's
  subdivision across meetings, and Prosper/Kuhar across boards. These candidates
  were rejected by document gates and were not stored as customer projects.

## Remaining customer risks

**Evidence output is too complicated.** Missing field assignments are more common
than fabricated quotes. The original run has 40 missing rationale assignments,
30 missing next-step assignments and 28 missing date assignments. The model also
changes punctuation in structured addresses and sometimes emits a display quote
different from its evidence spans. The held-out run has zero invalid passage
quotes but nine rejected documents. Exact quotations alone do not establish
support for every generated claim.

**Stage and decision scope remain unreliable.** York City agenda templates are
sometimes labeled recommendation even though no recommendation has occurred.
A Fairview item removed from future agendas is labeled continued. A park naming
vote and a bond reduction carry generic approved decisions. Jacobus's source says
the board moved to grant garage relief, without an explicit vote outcome in the
reported passage; approved is too definitive under our stated contract.

**Relevance needs another pass.** Ordinary grate replacement, compliance review,
generic fee schedules and a Horn Farm discussion with unspecified scope still
become public-works, policy or development records. Conversely, Lower Windsor's
substantive zoning rewrite covering data centers and warehouses was omitted.
Several minor subdivisions change category between documents.

**Identity still needs explicit review.** Long Level and carport histories remain
split across boards. A generic title such as Steep Slope or Preliminary Subdivision
Plan must not become a unique municipality-wide project alias. A source conflict
between Resolution 2026-18 and 2026-19 is described correctly in prose but both
numbers become alias candidates. Source layout also fuses SD-03-2026 with address
95 into an apparent application ID. These are reasons to abstain and review.

**Multiple milestones need separate fields.** Advertising, opening, construction
start and completion dates cannot safely share one date value. The source conflict
between November 6, 2025 and November 6, 2026 in February minutes also remains
unflagged in copied conditions.

## Date defect corrected now

The parser previously rejected complete dates wrapped in a weekday, time or
deadline sentence, plus numeric dates such as 1-27-2026. It now recognizes a single
explicit four-digit-year date while retaining the original source wording.
It rejects missing/two-digit years, invalid dates, contradictory weekdays,
date-like docket labels and multiple-date schedules.

Fifteen regression cases were added. Fresh checks passed: **1,047 pipeline unit
tests**, **110 API unit tests**, and git diff --check. The earlier isolated database
tests covered migration 061 and the attribution/persistence paths. No frontend
code changed in this evaluation turn.

Offline revalidation of the unchanged responses makes only source 6302 newly pass.
The replay is recorded separately from the paid run because the code identity
changed. It does not approve a release or demonstrate performance of a new prompt.

## Next implementation order

1. **Use source passage IDs instead of asking the model to reproduce evidence.**
   Segment each document deterministically; return selected passage IDs for claims.
   The server hydrates exact source text and derives the display quote. Keep strict
   bounds, source hashes and claim-to-passage requirements. This removes duplicate
   quoting and field-name bookkeeping without accepting unsupported claims.
2. **Add decision scope and distinct milestones.** Represent the action's subject
   (plan, variance, recommendation, bond, contract, naming) and retain the deciding
   body. Represent removal/withdrawal explicitly. Keep a list of source-backed dates,
   each labeled by purpose; a generic approval cannot set a whole project's status.
3. **Tighten discovery and identity.** Require stated development scope before a
   matter reaches development discovery. Keep unknown-scope/minor matters in property
   history or optional filters. Reject generic names as identity, quarantine
   conflicting IDs, and review cross-board links rather than merging on a parcel.
4. **Evaluate that smaller contract before scaling.** Preserve both completed runs.
   Judge source correctness, material omissions, scope, project continuity and
   cost per usable matter on regression documents plus unseen sources. No broad
   backfill or publication until that evidence supports it.

The revised original sample cost about **55% more** than its baseline, so this
iteration did not demonstrate savings. Completion tokens increased from 45,389
to 76,253. Repeated quote text occupies about 36% of serialized extraction
characters in the new original run; selecting passage IDs is a concrete cost
experiment, not a promised dollar saving. Project browsing, chronology and watch
matching should continue to reuse accepted facts without new model calls.
