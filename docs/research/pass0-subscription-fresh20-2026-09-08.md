# Pass 0: subscription drafts versus Luna on 20 fresh documents

The primary assistant's drafts handled passage boundaries and relevance filtering better in this sample. Luna preserved most major projects and complex conditions, but repeatedly selected neighboring subjects or irrelevant administrative material. The primary was also fallible: its Jacobus bakery card includes the neighboring tattoo-parlor listing. These findings support testing selective source review; they do not establish an independently measured model accuracy advantage or a working automatic review-routing system.

## Design and limits

Twenty retained municipal documents were selected by deterministic hash rank from 736 eligible records, excluding document IDs and URLs identified in 1,862 earlier source/evaluation artifacts. The sample contains four long, eight medium and eight short documents, one per recorded body name and no duplicate source text, with meeting dates from January through July 2026. This is a stratified diagnostic sample, not a population-weighted estimate. “Fresh” means excluded by that recorded prior-artifact inventory; it cannot prove absence from every earlier conversation or training data.

The primary read the numbered sources and archived all 20 outputs and source-based notes before any Luna dispatch. Luna received the same complete numbered source, unchanged production selection prompt and schema, at **low reasoning**, twice per document. No teacher examples were supplied in this stage. Each request allowed 128,000 output tokens and a 600-second timeout; there were no retries or truncated responses.

The primary then reviewed all outputs against the source. A separate Terra reviewer, shown only sources and primary drafts, critiqued the four longest drafts. The primary checked every claim and did not adopt that review wholesale. This was not blinded independent adjudication or equal-compute testing: the primary used tools and extended reading time, while each Luna trial was one API request. Retained source text was the common input; PDF/OCR fidelity and downstream parcel matching were not tested.

## Results

| Measure | Result |
|---|---:|
| Primary drafts / Luna calls | 20 / 40 |
| Schema and source binding | All 60 outputs passed |
| Luna outputs needing literal-title fallback | 4 of 40 |
| Documents with a documented Luna issue in either trial | 14 of 20 |
| Luna outputs with a documented issue | 27 of 40 |
| Primary documents with a confirmed avoidable contamination error | 1 of 20 |
| API cost for this experiment | **$0.03468856** |
| Cumulative spend under the existing $5 authorization | **$3.099197816** |

The issue counts are a **post-output diagnostic inventory**, not accuracy, precision or recall. They combine omissions, missing context, contamination, incorrect subject labels, fragmentation and irrelevant selections. They do not count every questionable boundary choice as an error. “One confirmed primary error” does not certify the other drafts as gold. Card counts—126 primary cards and 290 across both Luna trials—are not quality scores.

The strongest repeatable differences were:

- **Neighboring properties:** In both Hanover Shade Tree reads, Luna's 141 Broadway, 391 Grant Drive and 501 McCosh Street cards started at shared heading line 104 and swept in earlier properties' cases. The primary used separate heading and property ranges. Shrewsbury trial 2 repeated this pattern across development, enforcement, utility and road listings.
- **A missed hearing:** Both Franklin reads omitted the separately identified **CUH 2026-7, May 26 at 5:45 pm**, at line 106. They retained the larger data-center hearing and other projects. Red Lion trial 1 also omitted the tabled school safety-light agreement.
- **A real address in the wrong role:** Both Lower Windsor reads titled the Barshinger Road truck-hours ordinance with the speaker's **1505 Snyder Corner Road** address. Exact source binding validates the words but does not establish that they identify the affected property.
- **Incomplete continuation:** Both Jacobus gas-line cards stopped mid-paragraph. Trial 1 ended at “A motion was made”; trial 2 at “generator.” They preserved installation but dropped the servicing authorization and vote. The primary retained the complete passage.
- **Irrelevant selections:** Both York Township reads selected a grant for a rescue pumper despite the vehicle exclusion. Other repeated additions included anonymous hotel concerns, generic inspection/ordinance reports, routine tree removals without identified hazards, and supply bids.

Luna also performed well on difficult material. All three readers preserved Hanover's halfway-house denial and the absolute prohibition on renting the approved in-law quarters. They preserved Apple Hill's opening conditions, Rita's ten waivers, the 90-day Holly Meadows extension, conflicting Springwood hearing dates, and Fairview's eventual approvals/denials and six extension dates. Length alone did not identify the weak cases.

## Primary errors and source limitations

The primary bakery card selected Jacobus lines 201–204, unnecessarily including the tattoo property's address at 202. The independent reviewer caught this. Its proposed repair—select only 204—would lose the special-exception wording beginning at 203, so that repair was not applied.

The source itself puts the tattoo date and beginning of the bakery request in the same numbered unit, 203. Unit 211 similarly joins common discussion with the start of the tattoo-only motion. A model limited to whole source-line ranges cannot perfectly separate these clauses. This is distinct from unnecessarily selecting the entire neighboring address at 202. The original drafts remain frozen; this document does not present a silently corrected teacher pack.

Several primary selections remain debatable: CDBG program opt-in/awareness, small electrical repairs, proposed tree wells, and preliminary traffic/parking discussion. The reviewer called Red Lion's CDBG selection a definite error, but the prompt explicitly allows identified community-development funding, so this was retained as a policy-boundary question. Luna trial 2 separated East Hopewell's STR and family-housing topics more clearly than the primary's combined housing card. These qualifications matter before converting drafts into training examples.

## Document-by-document review

| ID / source | Principal finding |
|---|---|
| 4119 — Red Lion, June 8 | Luna trial 1 misses safety-light deferral; both add generic hydrant totals; trial 2 adds grant close-out. |
| 9434 — Jacobus, March 4 | Primary bakery contamination; both Luna gas-line passages truncate. Shared source units prevent perfect separation of hearings. |
| 10701 — York Township, January 5 | Core zoning/project conditions retained by all; both Luna reads add excluded rescue-pumper funding. |
| 8128 — Hanover ZHB, May 18 | No clear material issue; denial and no-rental condition preserved. |
| 1618 — Hanover Shade Tree, April 6 | Both Luna reads mix three neighboring property cases and retain three routine removal listings. Retained body metadata incorrectly labels the source as council material. |
| 6700 — Fairview, July 27 | Luna splits Storie modifications and plan approval; trial 1 omits modification vote. Primary consolidates related actions; all retain eventual decisions and extension dates. |
| 6563 — Mount Wolf, June 9 | Luna trial 1 adds baseball use; trial 2 adds anonymous mowing complaint. Primary's CDBG awareness is borderline. |
| 69 — York Haven, February 2 | Luna adds underspecified ordinances and routine marking/sign work; trial 2 crosses curfew into property card. Primary electrical quotes are borderline. |
| 4000 — Yoe, January 5 | Both Luna reads retain generic dam/ordinance reports. All retain fee changes and condemnation follow-up. |
| 10299 — Lower Windsor, June 11 | Both Luna titles use speaker's home instead of affected road; trial 2 adds anonymous bamboo matter. |
| 1166 — Franklin, May 13 | Both Luna reads omit CUH 2026-7 and add stone-supply procurement. Most substantive conditions/dates preserved. |
| 604 — East Hopewell PC, June 11 | Core decisions preserved; Luna omits final next-agenda list, largely repeating retained work. No clear whole-project loss counted. |
| 10542 — Shrewsbury, July 8 | Trial 1 drops development heading; trial 2 imports neighboring subjects to reach headings. |
| 8054 — Manchester, April 14 | Both Luna reads add unidentified hotel concerns; trial 1 duplicates one joint facility-rule listing. |
| 581 — East Hopewell BOS, April 1 | Trial 1 adds supply-bid card; trial 2 attaches supplies to road project. |
| 9875 — Stewartstown authority, June 17 | All preserve potential York Water capacity action; no clear issue. |
| 10464 — Franklintown authority, April 1 | All preserve tentative well exploration and $58,500 generator award; no clear issue. |
| 6422 — Newberry reorganization, January 5 | Primary and trial 1 return empty; trial 2 selects generic fee schedule and neighboring resolution. |
| 10265 — Heidelberg Water Board, May 27 | All preserve feasibility and well-land discussion; no clear issue. |
| 6995 — Monaghan, July 13 | All separate Petrone sewage and Myers stormwater matters; no clear issue. |

## Implication and next test

Use this batch as diagnostic development material. Two focused demonstrations are now justified candidates: separate headings from neighboring property ranges, and retain a project's complete motion plus later update. Review examples for relevance and shared-line limitations before use. Avoid turning every primary judgment into a target.

The next verification should compare unchanged Luna, those focused examples, and selective subscription review on an untouched batch with source checks fixed before outputs. Measure actual omissions, wrong-project context, irrelevant cards and review workload; retain a change only if it improves those outcomes. This experiment alone does not validate an automatic routing rule, show few-shot improvement, or justify a production prompt/model change.

## Artifacts and verification

The frozen [protocol](/home/jdaws/countyiq/output/pass0-subscription-fresh20-2026-09-08/protocol.json), [primary drafts](/home/jdaws/countyiq/output/pass0-subscription-fresh20-2026-09-08/primary-drafts.json), [per-source observations](/home/jdaws/countyiq/output/pass0-subscription-fresh20-2026-09-08/review-observations.json), [independent critique](/home/jdaws/countyiq/output/pass0-subscription-fresh20-2026-09-08/independent-critique.json) and [summary](/home/jdaws/countyiq/output/pass0-subscription-fresh20-2026-09-08/summary.json) accompany the complete sources, requests, responses and accounting receipts in the experiment directory.

All 40 actual requests were reconstructed and hash-checked against frozen plans; all 60 outputs were rebound to their source. Provider/model, unchanged prompts/schema, completion status, pre-dispatch draft ordering and exact budget-ledger delta were verified. Token usage: 121,960 prompt, 18,693 completion, including 11,373 reasoning; 79,248 prompt tokens were cached. API cost excludes subscription usage and primary/reviewer time. The ledger has no outstanding reservations and $1.900802184 remaining.

All four evaluation helpers pass Ruff formatting and lint. The new reviewer ledger entry passes its schema; global orchestration validation remains blocked by an existing row 9 missing `changed_files`, so no trust shortcut was used. Production application files, prompts and database records were not changed. No application test suite was needed for this evaluation-only work.
