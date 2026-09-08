# Subscription-authored examples for Luna, passes 0–3

I produced ten source-based outputs in this Codex subscription task and supplied
them as demonstrations to Luna. The mechanism works, but this first example set
is not a general quality improvement. It helped some entity grouping and evidence
formatting, while introducing other errors and increasing overall inference cost.
These remain evaluation artifacts; no production prompt or stored intelligence
output was changed.

## What was tested

- Two authored demonstrations for each of five contracts: Pass 0 municipal source
  selection, Pass 1 entity verification, Pass 2 signal validation, Pass 3
  investigation briefs, and Pass 3 municipal record explanations.
- Seventeen different student cases: 3 municipal documents, 4 entity clusters,
  4 parcel signal bundles, 2 investigation briefs, and 4 municipal explanations.
- Two trials per case per arm: unchanged production prompt versus that same
  prompt plus the two matching input/output examples. This produced 68 calls.
- Same Luna effort in both arms: high for Pass 1, low elsewhere. Both arms had
  128,000 output-token capacity and a 600-second response timeout. Calls used
  OpenRouter with OpenAI pinned as the provider. No strong-model teacher API
  calls, batch API, automatic retries, or production imports were involved.
- A further 8 calls repeated the Pass 2 example arm after correcting two defects
  in my teacher outputs. The original baseline was retained. This correction is
  a development-set iteration, not a fresh independent validation.

All ten initial teacher outputs passed production schema and citation validation.
All ten outputs in the corrected pack also pass. All **76 student responses**
finished and passed those structural validators, without truncation or retries.
That does not establish factual completeness or semantic correctness.

Inputs, examples and behavior expectations were frozen before the first dispatch.
Each student's test case was excluded from its demonstrations. These are previously
examined evaluation sources, however, not sources unseen by the experimenter. The
same assistant authored and reviewed the examples and results; this is a small
diagnostic experiment, not an independent estimate of teacher accuracy.

The design follows the input/output demonstration approach described in
[OpenAI's prompting guidance](https://developers.openai.com/api/docs/guides/prompt-engineering).
The example sets were fixed per contract; no retrieval system or fine-tuning was
implemented.

## Results

The counts below measure specific frozen behaviors. They are different units
across rows and must not be pooled into a single accuracy percentage.

| Contract | Baseline | Initial examples | Interpretation |
| --- | ---: | ---: | --- |
| Pass 0: selected coverage, exclusion and separation checks | 39/48 | 44/48 | Some coverage improvement, but source review found additional mixing and omissions |
| Pass 1: expected grouping/abstention outcome | 7/8 | 8/8 | More consistent useful grouping; the baseline's remaining result was a safe abstention |
| Pass 2: significance and missing-footprint checks | 13/18 | 10/18 | No general improvement; corrected examples also scored 10/18 |
| Pass 3 briefs: expected recommendation | 4/4 | 3/4 | One example-assisted run contradicted its own monitoring language |
| Pass 3 municipal explanations: primary event classification | 8/8 | 7/8 | One routine extension became an upcoming-decision event instead of a continuance |

**Pass 0:** On Newberry document 6414, examples consolidated the generator punch
list and its later installed/in-service update in both trials; baseline did so in
one. Examples also included the controlling new-submissions heading with the
Sheetz and recreation-facility cards. However, those baseline cards already named
their plan types, so the heading score is not equivalent to discovering two missed
projects. One example-assisted trial selected intervening neighboring plans along
with that heading, violating subject separation. That trial also omitted the
Comprehensive Plan steering-meeting item, which both baseline trials retained.

On Loganville document 9659, all four responses retained anonymous plan feedback
that the current prompt says to exclude. Examples sometimes added routine radar
signs or broader neighboring material. The frozen park-budget check required the
park heading as well as the 2027 budget heading; both arms failed that check.
Production's existing binding logic adds missing budget-year context, so a failed
raw selection must not automatically be described as a missing year in the final
bound evidence. Both arms preserved the named road estimate and gas replacement.
On document 10415, both arms retained the central generator, UV, road and ordinance
actions; examples did not create a clear overall improvement.

**Pass 1:** The HART names were grouped into the Taylor variants while keeping the
Colby owner group separate in both example trials. Baseline did that once and
abstained on the cluster once. Abstention is allowed by the current contract, so
this is improved resolution consistency, not evidence that baseline made a false
identity claim. Both arms abstained on the conflicting Kelley initials and handled
the corporate and township/authority name groups. No unsupported control or
beneficial-ownership relationship was emitted in these cases.

**Pass 2:** Both arms correctly avoided treating missing mapped footprints as
confirmed vacancy, and both downgraded fragmented adjacency. Examples did not
reliably reduce the significance of nearby plans without parcel inclusion or
ambiguous current/future land-use differences. Those significance thresholds are
reviewer expectations, not independently established truth; this result supports
“no consistent improvement,” not a precise model accuracy ranking. All plan
responses retained both proposed-lot and proposed-unit counts, including zero.

My own initial examples had two defects missed by structural validation. The
Taylor Brooks example used the backing JSON's 73.5m distance although the actual
student prompt prints 74m. The water-company example omitted the mandatory
precomputed 3.624-acre neighboring total. I corrected the first to the printed
distance and added the second with its all-intersecting-neighbor population.
The corrected example arm preserved the required acreage and population in
**4/4 applicable responses**, compared with **3/4 baseline responses**. That is a
small, concrete transfer of a desired behavior. Its significance-check score still
remained 10/18, with some individual decisions changing between trials.

**Pass 3 briefs:** Both baseline runs recommended watching the documented farm
sale. One example-assisted run instead returned `insufficient_evidence`, despite
saying the records support monitoring. The other returned `watch`. Both arms
watched the school-authority purchase, but neither consistently preserved the
exact March 9 date and the current-zoning versus future-policy distinction.
The two demonstrations covered a named-plan investigation and a static-screen
rejection; they did not include a `watch` example. That imbalance is a plausible
explanation to test, not a demonstrated cause of the regression.

**Municipal explanations:** Both arms preserved the church agenda's proposed
approval, historical waiver approval and completed stormwater revisions. Both
kept the speed-limit ordinance proposed without inventing a speed. Both preserved
the liquor hearing's proposed September 8 date and 6:00 p.m. time. Examples made
some summaries shorter, but one Village Walk response mislabeled the 90-day
extension as `upcoming_decision`. One liquor-hearing example response also omitted
the `upcoming_decision` secondary tag that the other three responses included.
The frozen primary-event score does not capture that secondary-tag difference.

## Cost and practical use

| Initial matched arm | Calls | Actual API cost | Input tokens | Reasoning tokens |
| --- | ---: | ---: | ---: | ---: |
| Baseline | 34 | $0.03828196 | 94,714 | 14,825 |
| With examples | 34 | $0.05120750 | 162,058 | 16,675 |

The initial example arm cost **34% more** overall. Prompt caching varied across
requests, so that exact multiplier is not a production forecast. At the same
observed token counts and ordinary uncached Luna rates, the estimates are
$0.05134 versus $0.06671, about 30% more with examples. These estimates exclude
cache-write premiums. Actual charged costs above include the reported provider
accounting. Rates are documented on the
[official Luna model page](https://developers.openai.com/api/docs/models/gpt-5.6-luna).

The correction run cost $0.00905054. **Total new API spend was $0.09854**, taking
the shared authorization from $2.965969256 to **$3.064509256 of $5**. All
reservations are settled. Teacher drafting and review happened in this subscription
task; the API cost does not price that subscription usage or review time.

This proves that I can author candidate outputs through the subscription and
that Luna can consume them as examples. It does not yet justify attaching this
example pack to every production request. The strongest observed use was narrowly
teaching an evidence-format requirement or an entity-name pattern. A production
candidate should use reviewed examples that cover the relevant decision types,
then earn its place on a new set of source cases. Property-bundle explanations,
owner rollups and an end-to-end subscription backfill were outside this pilot.

## Review artifacts and validation

- [Corrected ten-example pack](../../output/subscription-teacher-examples-2026-09-07/pass2-repair/teacher-examples.json): full inputs, authored outputs, provenance and validation results.
- [Original frozen example pack](../../output/subscription-teacher-examples-2026-09-07/teacher-examples.json): preserved with its two disclosed defects.
- [Initial results and costs](../../output/subscription-teacher-examples-2026-09-07/summary.json).
- [Corrected Pass 2 results](../../output/subscription-teacher-examples-2026-09-07/pass2-repair/summary.json).
- [Frozen behavior expectations](../../output/subscription-teacher-examples-2026-09-07/rubric.json).
- [Experiment helper](../../output/subscription-teacher-examples-2026-09-07/experiment.py), [audit/scoring helper](../../output/subscription-teacher-examples-2026-09-07/score.py), and [correction helper](../../output/subscription-teacher-examples-2026-09-07/repair_pass2.py).

The audit reconstructed all actual request payloads, checked frozen input/example/
rubric hashes, verified model/provider and response accounting, re-ran production
output validators, and reconciled every new charge with the shared ledger. The
four evaluation Python files pass Ruff formatting and lint. No application code,
production validators, configuration, database records or release state changed.
