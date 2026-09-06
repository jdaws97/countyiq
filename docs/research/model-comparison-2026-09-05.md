# Lower-cost model review — September 5, 2026

**Decision: qualify the best route on the user's existing OpenRouter account;
do not switch every pass yet.** Direct Luna Batch remains an untested option
requiring a separate account and key, not a prerequisite for this work. GLM 5.3 Flash is the stronger
current alternative model, with entity verification the first pass to qualify.
DeepSeek V4 Flash 0731 needs more work on provider routing, reasoning allocation
and the output contract before it is a dependable default.
This review does not approve a quality receipt or a backfill.

## Controlled comparison

The user reopened model choice after correctly identifying that earlier failures
could arise from prompts, input formatting and the harness. We fixed omitted
neighbor tax-claim years, a balance-only delinquency count, evidence-wrapper
parsing, municipal scope rules and several scorer defects before this comparison.

The request audit found additional confounds:

- GLM inherited generic temperature 0.1/top-k 40. Its publisher/OpenRouter defaults
  are temperature 1/top-p .95, and its mandatory reasoning defaults to maximum
  when effort is absent. The harness now uses those sampling defaults and an
  explicit low reasoning default instead of silently requesting maximum.
- DeepSeek V4 now uses OpenRouter's provider-independent reasoning control and
  omits ignored sampling parameters in thinking mode. Earlier output truncation
  had already been traced to insufficient reasoning/output allowance.
- The mixed-pass README example forced low effort on Pass 1, unlike the high
  effort selected for Luna. That override was removed.

Sources: [GLM publisher model card](https://huggingface.co/zai-org/GLM-5.3-Flash),
[DeepSeek thinking controls](https://api-docs.deepseek.com/guides/thinking_mode/),
[OpenRouter reasoning controls](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens).

A protocol was frozen before dispatch: 12 identical source cases per model,
36 calls total, maximum $1.50. Cases comprise two full municipal documents, two
entity-partition cases, four previously difficult signal contexts and four brief
cases. Every model received the same corrected prompts, explicit low effort for
Passes 0/2/3 and high for Pass 1, and the same output allowance per pass. Both
open models required FP8 routes. There were no generation retries, paid judges,
serving writes or label changes. These are selected regression cases, not an
independent or statistically representative holdout.

| Model | Actual total, 12 calls | Parseable | Parse + reference gate | Median / worst latency | Reasoning tokens |
|---|---:|---:|---:|---:|---:|
| Luna | $0.024388 | 12/12 | 12/12 | 12.9 / 27.6 s | 4,615 |
| GLM 5.3 Flash | $0.011820 | 12/12 | 10/12 | 15.1 / 23.4 s | 1,755 |
| DeepSeek V4 Flash 0731 | $0.009931 | 11/12 | 7/12 | 33.4 / 441.9 s | 47,132 |

**Total: $0.046138529.** Gate counts are diagnostic, not useful-output acceptance:
Pass 0 can pass its envelope while individual items are quarantined or its
extraction list is empty. Every consequential claim still requires source review.
GLM cost 52% less and DeepSeek 59% less in this small run; those are observed
route/cache/usage results, not a forecast for the pass mix in a full backfill.

## What failed, and what it means

**Pass 0:** Luna and GLM retained useful matters but still made some agenda-stage
errors. Guards quarantined individual items, so document-level success conceals
recall loss. A source stating an earlier award or completion can legitimately
appear on an agenda; that is different from inventing a new vote at the listed
meeting. The agent evidence inventory overflags all non-scheduled agenda states;
its warnings must be adjudicated using the actual source wording.

DeepSeek returned an empty extraction list for Dallastown after substantial
reasoning. For Loganville it copied the source fingerprint incorrectly. That is
an interface/transcription failure, not proof that the model read another source.
An offline diagnostic bound the original claims to the trusted input fingerprint:
five items then passed projection and five were rejected for agenda-stage or
literal-reference problems. The original failure is preserved and nothing was
published. Requiring an LLM to reproduce a 64-character source hash deserves
architectural simplification; source binding should be owned by the caller.

**Pass 1:** Luna and GLM pass both difficult partitions and their citation gates.
DeepSeek passes one; the other has uncited reasoning. Two cases are insufficient
to replace identity resolution: run the remaining six frozen partitions and the
supplemental cross-source cases before choosing GLM for this pass.

**Pass 2:** GLM gives useful calibrated explanations and, in the school-property
case, explicitly distinguishes a nearby plan from a plan established on the
subject parcel. Two of four outputs fail citation checks. One copies the example
`context:growth_area` ref even though it is not in the case, and several list
unused refs. DeepSeek omits material acreage/claim facts and a synthesis citation
in one case; another run spends 5,300 reasoning tokens on that small input.
The prompt's global examples and requirement to reproduce the same IDs in prose
and arrays add avoidable opportunities for errors. Keep unknown IDs rejected;
simplify the contract and retest before attributing the whole gap to capability.

Source-supported conservative vacancy dispositions remain disagreements with the
older diagnostic rubric. The p2x-050 fixture also contains different 11/12 neighbor
counting bases. Neither is repaired by changing model labels after seeing output.

**Pass 3:** Luna passes all four frozen cases. GLM passes three; it classifies a
material farm transfer as insufficient evidence rather than watch. That misses the
intended product distinction but invents no acquisition thesis. DeepSeek has an
empty response, corrupted citation IDs on another case, and an overly definite
zoning-density claim in a third. Its route matters: the empty/corrupted responses
came from OpenInference, while its two Baidu briefs were parseable. This tiny
sample does not establish that the provider caused those errors.

## Next qualification steps

1. Qualify GLM on all eight entity partitions and supplemental cases. Promote
   only the exact tested settings and provider constraints, per pass.
2. Remove avoidable prompt/output obligations: example IDs that look like current
   evidence, duplicated citation bookkeeping, and model-generated source hashes.
   Preserve raw responses, exact input binding, unknown-ID rejection and source
   review. Compare revised contracts against Luna on the same frozen cases.
3. Test DeepSeek with a controlled provider and a smaller supported reasoning
   allocation. Count latency, reasoning and rejected/retried output in its price.
4. Use varied new municipal canaries after correcting the remaining stage/recall
   issues. Favorable repeats on documents that drove fixes are regression evidence.

Artifacts are under `output/production-readiness-2026-09-05/fair-model-comparison/`:
frozen protocol/payloads, unmodified responses, actual usage, source evidence,
smoke review and the separate fingerprint diagnostic. The public route snapshot
is `model-route-audit-20260905.json`. Promotional prices and provider offerings
change; route ceilings must be checked again before a funded run. Current listings:
[GLM](https://openrouter.ai/z-ai/glm-5.3-flash),
[DeepSeek 0731](https://openrouter.ai/deepseek/deepseek-v4-flash-0731).

## Follow-up qualification and prompt repeat

Six additional GLM entity cases cost **$0.002455925**. Together with the two
matched cases, GLM produces 8/8 valid, source-cited partitions/abstentions and
7/8 exact gold decisions. The remaining case abstains because the two recorded
names have conflicting middle initials despite a matching address and spouse.
That is a defensible uncertainty, not an invented identity. Keep the frozen
merge label unchanged and adjudicate the ambiguity before choosing a fallback;
forcing a merge to raise a score would be the wrong identity policy.

The citation prefix then lost its concrete example IDs and factual examples;
Passes 2 and 3 received concise checks restating the existing citation contract.
The eight P2/P3 cases were repeated for all three models with unchanged input,
labels, validators, model settings and output ceilings: **24 calls, $0.018893261**.

| Model | Cost for 8 cases | Reference gate | Median / worst latency |
|---|---:|---:|---:|
| Luna | $0.009514 | 8/8 | 7.2 / 11.2 s |
| GLM 5.3 Flash | $0.005410 | 7/8 | 9.9 / 17.0 s |
| DeepSeek V4 Flash 0731 | $0.003970 | 7/8 | 31.3 / 182.1 s |

DeepSeek's four briefs now all parse and pass reference checks. This supports
the user's concern that prior failures partly reflected the interface. It does
not establish semantic equivalence: its school-acquisition brief suggests
development interest from the price/assessment gap; its fragmented-neighbor
brief suggests an assemblage play and a low-density restriction without the
necessary source evidence. An owner-matched nearby plan can reasonably prompt
a question about parcel inclusion, provided inclusion remains unestablished.
Watch itself is valid for a documented transfer and is not an intent claim.

GLM's former invented `context:growth_area` reference disappeared, but one new
output misspells `zoning_mismatch`. DeepSeek adds an invalid `Parcel:` entry to
a P2 evidence-reference array. Both remain rejected. GLM still misses the
watch-versus-static distinction for the large farm transfer. Both models also
need better handling of footprint-screen uncertainty and the ambiguous neighbor
counting bases in p2x-050. No model default or quality receipt was promoted.

Luna's farm brief exposed another scorer defect: explicit "absence of" a
coordinated acquisition was counted as asserting it. Added that negation with
regressions retaining rejection of a separate positive claim. Offline scoring
version 2026-09-05.2 gives Luna 4/4 strict brief cases, GLM 3/4 and DeepSeek 1/4.
The raw scores and responses are preserved; this is not another paid run or a
changed gold label. The full launch ledger is now **156 calls, $0.234389645**.

## Direct OpenAI Batch must be included in the backfill decision

The user identified an omission in the initial cost comparison: the current
OpenRouter harness uses synchronous Chat Completions. Grouping all signals for
a parcel into one Pass 2 request does not receive asynchronous Batch pricing.
[OpenAI's current pricing](https://developers.openai.com/api/docs/pricing) lists
Luna Batch short-context input at $0.10/M, cached input at $0.01/M and output at
$0.60/M. [Batch](https://developers.openai.com/api/docs/guides/batch) processes
uploaded request files within 24 hours at half the direct standard rate.

The eight Luna retest cases used 18,938 input tokens (10,086 cached) and 5,917
output tokens. Repricing those counts yields an illustrative **$0.00453626**,
versus $0.00540953 actually charged for the eight GLM calls. This is not a Batch
invoice: cache behavior, cache-write charges and direct-provider execution must
be tested. Nevertheless, comparing alternative models only against synchronous
Luna overstates their potential backfill savings.

The user currently has only OpenRouter, with no direct OpenAI account. An
eight-request evaluation input is prepared locally, with identical frozen
P2/P3 prompts, source contexts, schemas and labels. Only the provider-specific
transport fields change. Its conservative bound is $0.050425 under a $0.10
cap, including the full output allowance and input cache-write pricing. No
Batch job has been submitted and no account or billing setup is authorized.

Keep synchronous canaries for short feedback cycles. If the user enables
direct OpenAI access, qualify this bounded Batch sample before recommending
that transport for backfill. Compare accepted-output cost, including retries,
rejects, cache effects and dependent-pass turnaround. Otherwise qualify the
best option on the existing OpenRouter account and present the documented
Batch saving as an untested alternative. Batch results must retain frozen
input/model/prompt identity and be revalidated before publication;
asynchronous processing does not relax the evidence or authorization gates.

## Caller-owned source binding and population review

The next 18 calls cost **$0.032608442**, bringing this release review to
**174 calls / $0.266998087**. They are matched diagnostic repeats, not unseen
qualification. Both protocols, all raw outputs and usage remain under
`fair-model-comparison/pass0-caller-binding/` and
`fair-model-comparison/source-population-retest/`. Neither run approved a release.

Pass 0 now asks the model only for cited extractions. The synchronous caller
captures the source fingerprint before the request, verifies the retained text
against it, and constructs the bound review envelope. Stored evidence retains
exact source hashes and offsets; raw responses remain unchanged. A model-supplied
hash is rejected by the new wire schema. Historical responses still undergo their
original hash check and are never silently repaired. This changes the prompt and
quality identity, without changing the stored projection schema.

| Two-document Pass 0 repeat | Actual cost | Median / maximum seconds | Original clean-document gate |
|---|---:|---:|---:|
| Luna | $0.009809390 | 22.2 / 22.3 | 2/2 |
| GLM 5.3 Flash | $0.005597515 | 32.9 / 49.5 | 0/2 |
| DeepSeek 0731 | $0.005220598 | 248.0 / 419.1 | 1/2 |

DeepSeek returned substantive claims for both documents: the former empty output
and hash-copy failure did not recur. That does not qualify the output. In the
Loganville agenda it described a listed Commission expansion as already reviewed
and a listed storage project as already noted. Other items failed literal passage
checks or attached a current meeting date/authority to an earlier reported award.
Luna called the Dallastown deed-execution vote plan approval and described a
scheduled comprehensive-plan RFP report as already reviewed. GLM called bid
advertisement/administration a contract decision and lost a pump purchase to an
incorrect literal project reference.

The source review added narrowly scoped rejections for deed execution labeled
as plan approval, bid administration labeled as a contract award, and completed
review/discussion wording unsupported by an agenda entry. Explicit past awards,
completed work and previously reviewed plans remain valid source facts. The
separate `scope-gate-replay.json` reapplies those checks to the six unchanged
responses without paid reruns. Accepted item counts move from Luna 6/8 to 5/7,
GLM 5/7 to 4/7, and DeepSeek 4/4 to 4/2 for Dallastown/Loganville respectively.
Document success and retained-item counts must not conceal omitted useful matters.
These are rejection/recall findings, not a new semantic quality receipt.

For p2x-050, source code and frozen rows explain the apparent contradiction:
`development_signals.py` counts 11 parcels belonging to 10 other resolved owners;
`NEIGHBORS_QUERY` returns all 12 intersecting neighbors. Their total is 67.838 acres.
The same-owner school parcel accounts for 6.87 acres of that total. No historical
resolved-owner snapshot was recovered, so 60.968 acres computed by excluding the
same raw owner name is a diagnostic, not newly asserted production evidence.
The prompt labels the two populations and forbids attributing all-neighbor acreage
to the other-owner subset. Frozen contexts and gold labels remain unchanged.

| Four-case Pass 2 repeat | Actual cost | Reference gate | Median / maximum seconds |
|---|---:|---:|---:|
| Luna | $0.006847250 | 4/4 | 14.0 / 17.2 |
| GLM 5.3 Flash | $0.003472050 | 4/4 | 12.2 / 19.5 |
| DeepSeek 0731 | $0.001661639 | 2/4 | 15.5 / 160.2 |

Luna and GLM now separate the 11/10 owner counts from the 12-parcel acreage total.
All three acknowledge that a missing mapped footprint does not establish actual
vacancy. Their conservative vacancy downgrades disagree with the frozen rubric's
confirmed/upgraded range; the source evidence supports the conservative reading.
Some required-fact checks also miss explicit machine-key facts such as
`different_owner_neighbors=7`; those scoring limitations are separate from defects.

The reference gates still miss material semantic errors. Luna p2x-086 calls an
$1,800 assessment zero while listing the correct number elsewhere. GLM p2x-049
calls a one-lot plan zero-lot in both reasoning and synthesis. DeepSeek p2x-050
infers a school-site conversion/expansion from an eight-unit plan within 30 meters;
p2x-049 infers development restrictions and a lower approval likelihood from
future land-use labels without ordinance evidence. Its p2x-086 response drops a
required validation and its p2x-050/086 syntheses fail citation checks. None of
these costs can be presented as the price of a qualified replacement.

## Source context and fewer paid judgments

Missing-footprint `vacancy` is now factual context, not a Pass 2 validation target.
The explicit six-key interpretive allowlist also governs parcel and owner brief
eligibility. Source refresh and Pass 2 cleanup retract retired active validation
rows while preserving deterministic signals and immutable inference history.
The database regression covers a matching current footprint source with a retired
high-significance validation, including direct brief gathering before cleanup.
The existing API dependency checks hide briefs after a cited or uncited input
validation is retracted. Cached momentum annotations refresh with the dependent
momentum asset; this change does not claim immediate cleanup of existing caches
merely from deploying code. Pass 4 remains disabled and outside this pilot.

A read-only count on the current local snapshot found **5,548 → 3,404** eligible
Pass 2 parcels: **2,144 fewer calls (38.6%)**, with **2,424** footprint judgments
removed from the previously eligible population. This is a measured snapshot,
not a forecast of counts after future Pass 0/1 backfills. Among the four prior
targeted cases, p2x-040 now requires no call; p2x-049/050/086 still qualify.

Parcel briefs now receive retained source fields without Pass 2 reasoning or
generated reference prose. The format explicitly distinguishes earlier status
and significance judgments from source facts. Missing decisions, project status,
or permitted uses remain unknown; a matching plan title does not establish parcel
inclusion. The existing owner brief formatter already used source data directly.

`eval/source_context_cases.py` derives versioned diagnostic inputs without editing
historical fixtures. For Pass 3 it restores complete signal evidence from the
original Pass 2 snapshots, including plan titles, proposed counts and full land-use
labels. Its lineage records that upstream statuses are synthetic fixture inputs,
and that de-identification can make a surname-associated plan title look like an
exact owner-name match. p3-001 is only a conditional brief-stage test: it no longer
qualifies for a fresh Pass 2 call. Existing recommendation labels remain diagnostic
comparisons, not newly approved gold. Live selectors no longer attach old human
labels to new parcels by ordinal position, and the expanded rubric excludes
municipal-action combinations it does not cover.

The matched **21-call** repeat cost **$0.016668453**, bringing this release review
to **195 calls / $0.283666540**. Exact requests, derived sources, raw outputs,
usage and the separate source review are in
`fair-model-comparison/source-context-retest/`. There were no generation retries,
serving writes, model-default changes or quality approvals.

| Model | Pass 2 cost / original reference gate | Pass 3 cost / original reference gate | Median / maximum seconds, P2; P3 |
|---|---:|---:|---:|
| Luna | $0.005640480 / 3 of 3 | $0.003872820 / 4 of 4 | 10.8 / 11.7; 6.6 / 9.6 |
| GLM 5.3 Flash | $0.002557340 / 3 of 3 | $0.002331780 / 3 of 4 | 11.3 / 17.3; 8.0 / 12.6 |
| DeepSeek 0731 | $0.001292293 / 3 of 3 | $0.000973740 / 4 of 4 | 16.6 / 28.9; 12.4 / 15.4 |

Source review found the earlier one-lot/zero-lot and assessment contradictions did
not recur. Luna's three Pass 2 responses preserved the material source facts.
GLM and DeepSeek still inferred institutional expansion from a nearby eight-unit
plan and a school parcel without a documented relationship. GLM inferred applicant
timing ahead of downzoning pressure; DeepSeek treated an old future designation
as likely no longer reflecting current policy. Conditional generic planning risks
remain separate from falsely asserting a specific permission, decision or intent.

The briefs remain unqualified. Luna p3-002 says to watch the transfer in its text
but returns `insufficient_evidence`; it also omits acreage, while p3-003 omits the
recorded school-authority buyer. GLM p3-001 invents `active_subdecision` and puts a
PIDN in signal citations; p3-002 misses the material transfer's monitoring value.
DeepSeek infers minimal current value and development interest in p3-001,
speculative interest in p3-002, permitted future uses in p3-003, and restrictions
precluding most development in p3-004 without supporting ordinance evidence.

The review also caught a deterministic gate gap: parcel briefs silently accepted
`[Parcel: PIDN]` markers alongside valid signal markers. Those markers belong to
the owner-brief contract. The corrected parcel gate rejects them, including on
unchanged DeepSeek p3-001, reducing its replay result to 3 of 4. Original run
results are preserved; `source-review.json` records the replay and module hash.
Quality receipts now also bind the integrity validator and the source derivation.

Validation: 1,388 pipeline tests passed with integration excluded; four focused
database regressions passed against the disposable migration-065 test database.
After the citation fix and selector cleanup, 65 focused integrity/eval/quality
tests passed and Dagster definitions imported. No production pass was enabled.
The next product decision is how much repeated prose and categorical assessment
the customer actually needs: factual records, one consistent action and a concrete
question should take precedence over preserving redundant generated narratives.

## Full-component ownership canaries

The next Pass 1 review found two harness problems before judging model quality.
The prompt requested per-entity portfolio totals, but most prompts omitted
individual assessments and no serving consumer used the generated totals.
That output field and task are removed; historical transcripts remain intact
and parseable. Large-context source summaries remain factual input.

The actual candidate query includes both name similarity and corporate-office
edges. A pair-only shortlist hid a 1,429-name connected component, with 4,529
parcels and 1,806 tax rows truncated to 50 and 30 while all 1,411 corporate rows
remained. Its dynamic prompt was 409,482 characters. A preliminary independent
audit omitted the office-edge UNION and incorrectly called the A-1 cluster a
three-name deterministic case. Root's execution of the production query found
the full six-name A-1/Otter Creek component; that complete context was used.

Runtime now defers components above 40 names before gathering, or dynamic
prompts above 64,000 characters before hash reuse, item claims or any model,
inference or graph write. Deferrals retain previous graph assignments and are
reported as errors with explicit counts. Components are not split. The cost
estimate excludes the name deferrals and known sampled character deferrals;
unsampled contexts remain an explicit upper-bound uncertainty. Quality receipts
also bind this dispatch code. This guard limits dispatch; it does not establish
adequate evidence coverage or qualify every context below those limits.
A full read-only count finds 20,707 candidate edges and 6,151 components. Three
components (1,429, 86 and 44 names) exceed the name bound, deferring 1,559 names.
This count does not yet measure the character bound across all remaining
contexts. Validation includes 1,396 pipeline unit/regression tests, including
dispatch/retained-projection boundaries and estimate deferrals, plus the Dagster
definitions import. Root corrected the new boundary test's prior-hash setup so
it actually supplies a reusable hash before testing non-bypass.

Nine matched calls on three complete components cost **$0.021047066**,
bringing this review to **204 calls / $0.304713606**. The cases cover 17 similar
person names, six storage/partnership names linked by an office address, and two
Precision organization names sharing a mailing address. Requests use the same
current prompt, high reasoning and 16,384-token output allowance, with no
generation retries; open models require FP8. Source decimal tax amounts were
restored from archived strings for formatting without changing the original
snapshot. No serving write or quality receipt was issued.

| Model | Actual three-call cost | Production reference gate | Median / maximum seconds |
| --- | ---: | ---: | ---: |
| Luna | $0.014253150 | 3/3 | 20.3 / 44.2 |
| GLM 5.3 Flash | $0.003251420 | 3/3 | 30.9 / 33.2 |
| DeepSeek 0731 | $0.003542496 | 0/3 | 89.4 / 160.4 |

Luna and GLM account for all 17 person names and 19 parcels without merging
conflicting middle initials. Both preserve the two separately numbered
organizations in the six-name case and all 21 parcel links; both keep the two
Precision owners of record separate. GLM costs about 77% less than Luna in
these three cases. One GLM sentence repeats a supported co-owner relationship
without its own marker; its field and relationship object are cited, so it
passes the intentionally field-level gate. This prompt/gate difference is not
an invented relationship.

Some corporate prose remains imprecise: a CountyIQ registry lookup with
`not_found_in_current_dos_dataset` is not an affirmative registry record, proof
that a separate legal entity does not exist, or proof of an officer role from
an attention line. The grouping has separate name/address evidence; preserve
this provenance limitation rather than calling every sentence qualified.

DeepSeek exhausts its output allowance on the 17-name case, including 13,860
reasoning tokens. Its other two responses make the same supported groupings
but combine references inside brackets or put evidence-group prefixes into
linked identifier fields. Existing gates reject them. These are output-contract
and budget failures, not evidence that it cannot reason about the records.
Before another broad comparison, examine whether Pass 1 needs to repeat every
singleton explanation and linked-record identifier in model output. The current
results do not establish N=3 voting stability or full-pass quality. Exact sources,
payloads, raw responses and separate reviews are in
`fair-model-comparison/pass1-source-canaries/`.

## Fresh York City minutes: model output versus validator behavior

Three new calls on July 13 planning minutes, source 6712, cost **$0.009826510**.
The cumulative review is **207 calls / $0.314540116**. All models received the
same complete source, current prompt, low reasoning, 16,384-token allowance and
zero generation retries; the open models used FP8. A source-first reference
was frozen before generation. This is a small diagnostic case, not independent
human gold or full-pass qualification.

| Model | Actual cost | Seconds | Accepted records before / after saved-response replay |
| --- | ---: | ---: | ---: |
| Luna | $0.004287350 | 13.6 | 1 / 4 |
| GLM 5.3 Flash | $0.002409000 | 10.3 | 1 / 4 |
| DeepSeek 0731 | $0.003130160 | 236.1 | 1 / 4 |

All three correctly retained the four applications, recognized three actual
advisory recommendations, left final decisions null, and preserved the no-show
application as an update. The validator rejected all three recommendations
because retained `[approve/deny]` text coexisted with a seconded motion followed
by “Unanimous.” A narrow check now recognizes that form inside the cited,
identified application's section. Missing, failed and uncited votes, and the
next application's unanimous vote, cannot use this exception. This does not
turn advisory recommendations into final approvals.

Replay also exposed a discovery-classification miss: “renovate an existing
industrial building into an emergency shelter” established reuse without saying
“redevelopment.” An exact excerpt naming the building and destination use now
supports conversion; routine repairs, negation, historical work and neighboring
building references have negative regression controls. Both fixes reuse the
original responses. No additional model calls or serving writes were made.

All four records now pass the format/evidence gate, but only **two of three**
reference development matters reach discovery. The community-center renovation
still lacks accepted scope in the selected excerpt; all models also put the
staff's explicit UN1-to-UN2 correction into unresolved identity conflicts.
The original source-first reference remains unchanged.

There are model defects too. GLM adds Zoning Hearing Board next steps for the
first two cases without support in their cited passages; only the no-show case
explicitly states that route. DeepSeek's separate-approvals next step is true in
passage p0004 but cites p0005. These narrative entailment errors pass the current
format gate. Luna avoids those extra next steps, but still misses the discovery
recall threshold. No model is qualified by this result. Remove unnecessary
generated narration and distinguish resolved source corrections before the next
matched evaluation. DeepSeek's 11,450 reasoning tokens also make its latency and
real per-document cost materially different from its advertised token price.

Artifacts: `fair-model-comparison/pass0-york-july-canary/` contains the source,
reference, request protocol, original results/transcripts and separate
`replay-and-source-review.json`. The [metadata review](proceeding-metadata-review-2026-09-05.md)
records pre-model selection fixes and preserves unapplied drafts.

## Recorded facts instead of narrative cards

Pass 0 no longer requests `why_it_matters` or `what_happens_next`; retired and
unknown fields remain rejected. Current extraction leaves the historical storage
columns empty. Explicit historical replay validates the old schema without
changing responses or source binding. Event builders no longer fill generic
commentary templates, and the API, project summary, export and UI stop publishing
these fields. Cards show the action once, with stated conditions, milestones and
their own evidence receipts. No table migration or historical-data rewrite is needed.

The prompt now distinguishes an explicit source correction from an unresolved
conflict. Exact evidence of substantive interior renovation can establish
redevelopment without implying expansion or a change from an unstated prior use.
Saved-response replay raises Luna and GLM from two to all three reference
discovery matters in the July minutes. DeepSeek's older excerpt still lacks the
physical scope. Historical conflicts and incorrect narrative citations remain
preserved; replay does not silently repair them.

Three matched calls with the same complete source, unchanged reference, low
reasoning, 16,384-token allowance and FP8 requirements cost **$0.008049745**.
The cumulative review is **210 calls / $0.322589861**. OpenRouter routes/prices
were captured before dispatch. No generation retries were made.

| Model | Actual cost | Seconds | Records accepted | Reference matters discoverable |
| --- | ---: | ---: | ---: | ---: |
| Luna | $0.004117750 | 17.334 | 4/4 | 3/3 |
| GLM 5.3 Flash | $0.002169850 | 48.713 | 4/4 | 3/3 |
| DeepSeek 0731 | $0.001762145 | 75.057 | 0/4 | 0/3 |

Primary source review found no invented next action or numerical scope in the
repeat. Three votes remain advisory recommendations; the no-show remains an
update. **GLM meets this document's source-first criteria.** Luna still lists
the explicit UN1-to-UN2 correction as an unresolved identity conflict, preventing
linking of that matter. Its raw operating-relief `plan_review` label is correctly
demoted by the scope gate. Its generic “proposed emergency shelter” reference
also exposed an alias risk: pure facility descriptions now cannot connect
separate applications; source application IDs and distinctive names remain usable.

DeepSeek repeats `current_zonong` and `proposed_zonong` in every item. The
production schema rejects all four. Its unchanged raw content identifies the
four intended matters and corrected UN2. A separate offline diagnostic changes
only those two object-key spellings: all four records and three discovery matters
then pass the unchanged source validator. This is an interface failure, not
evidence of failed source understanding. Production does not apply this repair;
original responses and zero-acceptance results remain intact. The response used
11,171 reasoning tokens, so latency and rejects remain part of its effective cost.

Artifacts: `fair-model-comparison/pass0-recorded-facts-retest/` retains the exact
source/reference copies, protocol, route snapshot, responses/transcripts,
saved-response replay, semantic review and separate key diagnostic. This is a
matched regression after the findings informed changes, not an unseen source
sample or full-pass qualification. No serving writes, quality receipts, model
default changes or backfill occurred. Metadata version 6 was subsequently
applied and verified locally and in production; it does not qualify these models.

## Varied documents and reasoning control

The next nine matched calls used three previously unused full sources: Hanover
Council minutes of July 22, York City's August 20 zoning agenda and Heidelberg's
September 2 agenda. All passed current dispatch checks. References were frozen
before responses; exact text/hash searches found no match in the earlier release
comparison or committed fixtures. This is selected coverage with primary-agent
labels, not independent human gold or a representative sample. Ambiguous
relevance boundaries were declared before dispatch rather than scored as failures.

The run cost **$0.020810951**, with unchanged low reasoning, 16,384-token output
allowance and FP8 constraints for the open models. Original item acceptance was:

| Model | Cost for three documents | Hanover / York / Heidelberg accepted records |
| --- | ---: | --- |
| Luna | $0.009168230 | 1 / 6 / 1 |
| GLM 5.3 Flash | $0.006732520 | 0 / 6 / 2 |
| DeepSeek 0731 | $0.004910201 | 0 / 0 / 2 |

None passes the complete-document gate. Source review separates the causes:

- All models miss or improperly combine the separate Hanover litigation matter;
  Luna also misses the Mustang Pointe settlement. DeepSeek attaches a court case
  and parties to that settlement without explicit source binding. Its action
  quotations use ellipses. Luna and GLM understand the consent approvals but omit
  the separate carried-vote or authority evidence required by their selected quotes.
- Luna and GLM recognize all seven York applications without manufacturing votes.
  Both put one identifier in the adjacent passage containing the item's body;
  that record is rejected. GLM also misses both clear conversion discovery labels
  by selecting generic use-permission clauses. DeepSeek's OpenInference response
  uses all 16,384 output tokens as reasoning and returns whitespace after 463.412s.
- All three recognize Heidelberg's subjects, but isolated PDF list markers
  interrupt identifiers and exact quotations. The normalized text returned by
  each model fails literal membership. DeepSeek also falsely says committee
  members were appointed; a scheduled status field does not correct that sentence.

Two projection defects are fixed without rewriting responses. Exact evidence of
a signalization upgrade now retains capital scope. A stated formal development
plan remains `plan_review` after an unsupported construction label is removed;
administrative time extensions remain context. Offline replay changes Luna's
accepted Hanover infrastructure item from context to discovery. It does not repair
the consent citations or qualify that document. All **1,453 pipeline unit/regression
tests** pass, including source-scope, invented-scope and administrative boundaries.

A three-call repeat of Heidelberg changed only reasoning from low to high, with
the exact same prompts, source and reference. It cost **$0.013302730**. Luna and
GLM each retain only one record; DeepSeek again exhausts all 16,384 tokens on
reasoning. More reasoning does not solve the representation problems in this test.
The cumulative review is **222 calls / $0.356703542**. All calls are terminal,
with no reserved spend remaining and no generation retries.

Before further paid municipal repeats, improve source representation and the
evidence contract for separated consent votes with offline provenance checks.
Do not silently join ambiguous identifiers, borrow another item's vote, change
reference labels or overwrite failed responses. No model, paid flag, quality
receipt or full-backfill decision changed. Complete artifacts and the detailed
source review are in `fair-model-comparison/pass0-varied-holdout/`; the reasoning
control is in `pass0-reasoning-diagnostic/`.

## Offline source-range interface study

The experimental `pipelines/eval/evidence_ranges.py` lets a caller recover a
continuous original quotation from first/last source-unit IDs. Units follow
original lines, splitting unusually long lines at word boundaries. They preserve
PDF list markers, whitespace, punctuation and Unicode offsets. The caller retains
the original UTF-8 source hash; unknown IDs, different source fingerprints,
reversed ranges and old passage versions fail. This is an evaluation module,
with no production caller, schema replacement or response repair.

A read-only audit of all 6,459 current local proceedings finds 5,399 with text
and 1,060 with null text. All 5,399 text documents reconstruct exactly, totaling
40,612,535 source characters. The current passage JSON totals 42,621,427
characters; the experimental line JSON totals 64,251,822, **50.8% larger**.
The per-document median increase is 53.5%. These are serialized character
measurements, not measured tokenizer usage, latency or model cost.

Five manually selected controls establish representation behavior, not model
accuracy. The broken Heidelberg identifier remains broken, while its interrupted
road sentence can be recovered exactly without asking a model to transcribe the
list marker. A York application heading and body can share a continuous range.
The Hanover signalization motion and result retain their existing semantic pass.
The whole consent range preserves all intervening items but still fails the
current decision gate: nested proposed motions are not independently recorded
votes. Selecting a broader quotation does not establish which decision belongs
to which item. An adversarial neighboring-motion control remains rejected.

The prototype's 16 tests pass. Original responses, source snapshots and frozen
references are unchanged. This study made **zero calls / $0 additional spend**;
the cumulative total remains 222 calls / $0.356703542. Artifacts, the corpus
audit and its read-only runner are in `fair-model-comparison/source-range-study/`.

Do not adopt this representation yet. It removes one copying obligation but
adds substantial input and does not solve consent linkage, malformed identities,
missed matters or unsupported action sentences. The next municipal experiment
must distinguish separately cited item, motion and outcome evidence, explicitly
test excluded/intervening items and retain the original source ranges. Shorter
selector serialization can be measured offline before spending. Qualification
still requires fresh model outputs and source review; hand-selected ranges cannot
stand in for either.
