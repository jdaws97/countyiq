# Hard-document PDF canary

The [action-contract follow-up](pass0-action-contract.md) fixes the York agenda
state error at the same model level, but loses topics and retains Willis
attribution errors. It is not an overall replacement for this reader.

The unchanged v105 reader does **not** reach 71/71 on the harder cohort. Its first
complete run mentions 67 of 71 reference topics and represents 65 separately.
The repeat subset remains unstable, and materially unsafe attribution and action
fields survive even when topic coverage and literal-source checks look good.

This is a diagnostic of the proposed reader, not a production deployment. The
[previous modality trial](pass0-pdf-modalities.md) found all eighteen topics in
four easier documents; that result does not generalize to this cohort.

## Frozen comparison

The twelve source documents and 71-topic reference are unchanged from the
[broader discovery audit](pass0-discovery.md). The reference is model-assisted
source review, not independent human gold. The same Luna model, low reasoning,
8,192-token output limit, prompt and schema from v105 are used. No reference,
weights, old response, expected count or locator inventory enters inference.

Ten original PDFs were recovered, and every PDF hash matches the original cohort's
content hash. They contain 53 reference topics. Two sources use archived full-text
controls: Shrewsbury's November 2022 agenda downloads as DOCX, and the East
Manchester December 2020 PDF returns HTTP 403. These controls contain eighteen
topics. Their page 1 denotes a synthetic text container, not physical pagination.
No converted text PDF is passed off as an original.

All twelve documents run once. York April 2025, Fairview November 2015,
Shrewsbury September 2011 and East Manchester December 2020 receive a preselected
second run. No generation retries or selection of the better answer occur. The
sixteen-call protocol was frozen before dispatch. An initial undispatched
24-call draft exceeded the conservative reservation allowance; its files were
retained, and the final sixteen-call protocol fit the remaining authorization.

| First run | Earlier reader: mentioned / separate | Current reader: mentioned / separate |
| --- | ---: | ---: |
| Hallam December 2023 | 2 / 2 | 2 / 2 |
| York April 2025 | 7 / 7 | 7 / 7 |
| Shrewsbury November 2022, text control | 3 / 3 | 3 / 3 |
| Fairview November 2015 | 4 / 4 | 4 / 4 |
| Fairview April 2016 | 4 / 4 | 4 / 4 |
| Fairview February 2016 | 1 / 1 | 1 / 1 |
| Spring Grove August 2021 | 14 / 14 | 14 / 14 |
| Shrewsbury September 2011 | 13 / 6 | 12 / 10 |
| New Salem September 2020 | 2 / 2 | 2 / 2 |
| East Manchester December 2020, text control | 9 / 9 | 13 / 13 |
| Hallam January 2024 | 2 / 2 | 2 / 2 |
| West Manchester April 2023 | 3 / 3 | 3 / 3 |
| **All twelve** | **64 / 57 of 71** | **67 / 65 of 71** |
| **Ten sources now supplied as PDFs** | **52 / 45 of 53** | **51 / 49 of 53** |
| **Two text controls** | **12 / 12 of 18** | **16 / 16 of 18** |

These are raw topic discovery counts, before citation rejection, and do not mean
correct-record counts. The earlier reader used a different prompt/schema and
text input. The full-cohort recall improvement comes from the East Manchester
text control; it cannot be attributed to native PDF. PDF subject separation
improved, while PDF topic recall fell by one on the first run.

## Missing and combined subjects

The first run omits:

- Shrewsbury: retaining-wall removal at East Tolna/Crosswind; proposed Eagle Scout
  sand-volleyball court.
- East Manchester: Sewer Authority intermunicipal agreement and 537 planning;
  Canal/East Locust Point progress.

Shrewsbury still combines 40 and 44 East Tolna Road into one record despite the
instruction to separate properties. It does correctly separate the other code
subjects and restrict solicitor/magistrate authorization to the two noncompliant
properties. East Manchester recovers Keystone's sewer/building restriction, DHL,
Saginaw/Mt. Wolf capacity and Core 5 blasting from the earlier omissions.

| Repeated source | First run: mentioned / separate | Second run: mentioned / separate |
| --- | ---: | ---: |
| York | 7 / 7 of 7 | 7 / 7 of 7 |
| Fairview November | 4 / 4 of 4 | 4 / 4 of 4 |
| Shrewsbury September | 12 / 10 of 14 | 13 / 11 of 14 |
| East Manchester, text | 13 / 13 of 15 | 11 / 11 of 15 |
| **Matched subset** | **36 / 34 of 40** | **35 / 33 of 40** |

Shrewsbury's second run recovers the wall but still misses the court and combines
the same two properties. East Manchester's second run also loses LERTA and the
Saginaw/Mt. Wolf capacity topic. Both repeats still miss the IGA/537 and Canal/East
Locust topics. No combined best-of-two score is presented. All sixteen responses
return empty unresolved-fragment and unreadable-page arrays despite the omissions
and Fairview's attribution uncertainty.

## Errors that topic recall hides

**Fairview / Willis, both runs:** the reader confidently attaches the intervening
Schoolhouse Lane/Ridge Road section and its modification motions to Willis. The
original PDF itself has the unlabeled intervening material, restarting numbered
lists and a repeated table fragment. Physical pages 4–6 require unresolved
attribution; page 6 was visually rechecked. The current 14-lot Willis plan and its
clearly headed later actions remain identifiable, but the extra road location and
modifications cannot safely be attached. First-run `denied` also turns a negative
recommendation into a denial; second-run `recommended` corrects that distinction
without resolving subject attribution. Both records still count as discovering
Willis. Neither is a qualified factual record.

**York agenda, all seven records in both runs:** prose correctly says the
`[approve/deny]` alternatives are unresolved. Nevertheless, the action outcome
field says `recommended` with current timing. Those are proposed agenda actions,
not recorded recommendations. A consumer reading the enum alone could invent
an advancement event. Literal quotations and correct property identities do not
make that action field safe.

**Other retained limitations:** Shrewsbury sometimes turns planned referrals into
completed referrals or `recommended`, and pending signature/adoption into `tabled`.
The underlying no-plan-approval prose is usually retained. Plasterer's conflicting
historical waiver dates remain unflagged. East Manchester's first LERTA record
omits the actual authorization to prepare extension paperwork; both Hillwood
records preserve conditional approval but omit the explicit two-building scope.
Both DHL records use the complainant's address to construct a nearby facility
location without an explicit source location relationship. West Manchester adds
the meeting-header postal context to subject addresses without separate support.
These are further reasons not to equate discovery counts with complete usable
intelligence.

Useful distinctions also survive: no Keystone permission to keep building,
no unconditional Hillwood approval, equipment-only playground purchase,
HOP-application authorization rather than an issued permit, KS security release
rather than funding, and reverse subdivision rather than seven new lots.

The literal-text/page diagnostic flags nine required records in the first run
and four in the repeat subset. These flags are not thirteen false findings:
some reflect line-wrap normalization, while others involve ellipses, omitted
words or wrong pages. For example, Willis's Final Plan cover-sheet sentence is
on physical page 9, not 10; Gran-U-Lawn's streetlight and road-widening passages
are on page 2, not 3. The audit preserves all candidates and flags separately.
A matching quotation also cannot settle the Willis attachment error.

Extras include routine maintenance, parking, snow-plow/franchise business and
other out-of-scope or optional topics. They are not credited as recovered required
subjects. Their source grounding does not make them relevant to the frozen scope.

## Weighting silent misses

Weights were assigned from the frozen source reference before dispatch:

| Weight | Intended priority |
| --- | --- |
| 5 | Development/subdivision, rezoning, material capacity constraints, or substantial new infrastructure/acquisition proposals |
| 3 | Other material project advancement, financial/legal/enforcement matters, policy or property relief |
| 1 | Minor compliance, small property relief or bare low-information topics |

These are illustrative ordinal product priorities, not measured economic losses
or customer-validated weights. They are retained per topic in `weights.json`.

The denominator includes **every source-reference topic**, including those for
which the reader emits nothing. Weighted separate-topic recall is the sum of
weights of separately represented subjects divided by the sum of all reference
weights. It rises from 217/253 (85.8%) in the earlier reader to 241/253 (95.3%) in
this first run. On the matched repeat subset it falls from 122/134 (91.0%) to
113/134 (84.3%). The second East Manchester answer loses two weight-5 topics.
These percentages measure discovery only and do not subtract wrong facts.

A useful scorecard needs distinct measures for weighted omissions, merged
subjects, wrong identity/attribution, wrong action/state, missing material scope,
and evidence repair. A dangerous false approval or wrong-property action should
be surfaced independently; many correct minor records should not cancel it.
Retain source-supported discovery candidates while withholding unsupported
fields, rather than deleting an entire development because one quote needs repair.

For unseen documents, the system cannot directly count subjects it never noticed.
A source-first audit supplies that denominator on an evaluation sample. Independent
inventories and deterministic checks can nominate production revisits, but they
also miss things. Periodic audits must include apparently clean and empty-output
documents, not just flagged documents, to measure silent loss. Another model's
agreement alone is insufficient independent ground truth.

## What the current pipeline checks

Repository code has two separate deterministic mechanisms:

1. `has_landuse_vocabulary` is a prefilter before extraction. It can skip a
   document with none of its terms. It does not reconcile extracted records
   against every occurrence of those terms.
2. `proceeding_coverage.review_coverage`, called by `review_claims`, builds a
   source inventory of address patterns, application-number patterns and selected
   named headings. It checks them against explicit legacy extraction identities
   and narrative fields, excluding supporting quotations. Unmatched anchors set
   `needs_review`; the stored list is bounded to forty with a truncation flag.

The extraction asset persists coverage findings and emits a review-document
count, but still marks a successfully persisted document `complete`. Coverage
findings do not trigger a paid reread or recover a missing record. A repository
search found no downstream consumer of this flag implementing such a reread.
This describes current checked-out code, not verified deployed behavior.

An offline adapter applied that same check to this experiment's label, identifiers,
location and narrative fields; it does not wire the new schema into production.
Shrewsbury passes with **zero unmatched anchors in both runs**, even though the
court is missing and properties are combined; the first run also misses the wall.
The check only sees `44 East Tolna Road` from the shared-address wording, misses
`6 Covington Drive` split across source lines, and has no qualifying court/wall
heading. A nearby subject name can also match while its action is wrong: York and
Fairview November both pass. East Manchester is flagged, but its unmatched list
includes generic headings and unrelated material and does not enumerate all its
missing subjects. False alarms include `Rd` versus `Road` and consultant addresses.

The research-only locator separately named five of seven earlier whole-topic
misses. That was an additional model call in the previous experiment, not an
automatic rescue stage demonstrated in this pipeline. Native PDF alone, the
current heuristic, and the reader's own uncertainty flags do not close this gap.

## Likely causes, and what has not been isolated

The evidence supports several interacting causes rather than a single model or
PDF-reader explanation. The following is diagnosis from observed behavior, not a
controlled allocation of error rates to individual components.

- **Action contract and model instruction-following:** `recommended` does not
  explicitly encode whether a recommendation actually occurred or is proposed
  agenda business. The prompt says to distinguish them, but the schema accepts
  the inconsistent output. All fourteen York observations show this systematic
  prose/enum disagreement. Separate action occurrence from its substance and
  validate contradictory fields before allowing an advancement event downstream.
- **Scope and omission behavior:** short reports compete with detailed development
  items; exclusion of routine maintenance/community events also leaves borderline
  subjects such as a removed retaining wall or Scout court exposed to relevance
  judgments. The unexplained loss of LERTA and capacity between identical-input
  repeats also shows model instability beyond a fixed scope definition. More
  output space alone would not address these runs: all finished normally, and
  completion usage ranged from 793 to 3,772 tokens against an 8,192-token ceiling.
- **Source ambiguity and overconfident attribution:** Fairview's problematic
  section is ambiguous in the original PDF, not merely damaged extracted text.
  The model attaches it despite instructions to retain unresolved fragments. A
  source boundary/conflict check and an actionable unresolved state matter here;
  changing PDF input modality did not settle the attachment.
- **Coverage implementation:** the regex inventory is incomplete and matches
  names rather than a complete subject/action inventory. Passing it is compatible
  with omissions, merged properties and false action fields. It requests review
  without implementing recovery. This is a known detection limitation, separate
  from the model behavior that produces the omission.

Literal-quote and page-generation slips are an additional evidence-handling issue,
often repairable without losing the discovered subject. They should not be
combined with wrong-property attachment under one accuracy label. The harness
supplied the full inputs and retained the raw answers; the four first-run topic
omissions are already absent in those raw answers, before any citation rejection.

A discriminating next comparison would keep the model and input fixed, change
only action occurrence/consistency handling, and evaluate discovery separately
from action correctness. A separate coverage/revisit comparison can then measure
recovered source topics, new false facts, extra calls and review load. A model
upgrade should be judged under the same contract and sources; this experiment
does not establish that a different model would remove these problems.

## Evidence, cost and verification

Artifacts are under `output/pass0-redesign-2026-09-06/hard-pdf-v106/`:
originals and receipts, archived controls, frozen prompt/protocol/reference/weights,
all sixteen requests and responses, settled charges, explicit record-to-topic
mappings, quote diagnostics and coverage replays. `hard_pdf_v106.py` imports the
unchanged v105 reader. `audit_hard_v106.py` reproduces the comparison and verifies
request reconstruction, source/code hashes, schema validity and native routing.

All sixteen calls completed without API/schema failures for **$0.06779163**.
The first twelve cost $0.05486745; the four repeats cost $0.01292418. This includes
provider caching and excludes local preparation and review labor. Known ledger
spending is $5.109140164696; three older unresolved reservations remain unchanged
at $1.079594964. **$1.811264871304 remains uncommitted under the approved $8 cap.**

The focused existing proceeding-accuracy suite passes 26 tests. Ruff format and
lint pass for all three new experiment helpers; the offline audit reproduces all
sixteen calls. No maintained pipeline implementation or database state changed.
