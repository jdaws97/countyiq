# Action occurrence contract experiment

Adding an explicit action-occurrence distinction eliminates the targeted York
agenda-state error in both runs, but this version is **not an overall reader
improvement**. Discovery falls and Willis attribution remains unsafe. The result
supports retaining the distinction as a design requirement while continuing to
evaluate the reader separately for omissions.

This follows the [hard-document canary](pass0-hard-pdf-canary.md). No production
pipeline code or database state was changed.

## Controlled change

The sixteen jobs use exactly the same model, low reasoning effort, 8,192-token
output limit, provider routing, source bytes, document metadata, input modality,
reference and weights as v106. This means twelve first-run documents and four
preselected repeats. Ten sources are original PDFs with 53 reference topics;
two are the same archived-text controls with eighteen topics. The baseline is
frozen prior responses, not a simultaneous randomized control.

Only the action contract changes:

- Add `occurrence`: `occurred`, `proposed`, or `unclear`.
- Permit null `outcome`.
- Explain that proposed/unclear actions must have null outcome and decision date;
  agenda recommendations are proposed; `recommended` requires an actual issued
  recommendation; waiting for review or a signature does not establish tabling.
- Require agreement among the action description, occurrence, outcome and evidence.

The unchanged discovery prompt is retained and the new action guidance appended.
No source-specific example, missing-topic list, prior answer or expected count is
provided to the model. Scope, property separation and attribution instructions
are unchanged. There is no extra omission-recovery call or local record deletion.
An occurred action can have null outcome when no existing outcome category fits;
the rule prohibits non-null outcomes for actions that have not occurred, rather
than requiring a categorical outcome for every actual activity.

## Results

| Measure | Frozen baseline | Revised action contract |
| --- | ---: | ---: |
| York agenda records with misleading current recommendation state, both runs | 14 of 14 | **0 of 14** |
| First-run topics mentioned | 67/71 | **61/71** |
| First-run topics separately represented | 65/71 | **61/71** |
| First-run source-weighted separate-topic recall | 241/253 (95.3%) | **229/253 (90.5%)** |
| Matched four-document first run, mentioned / separate | 36 / 34 of 40 | **31 / 31 of 40** |
| Matched four-document second run, mentioned / separate | 35 / 33 of 40 | **33 / 31 of 40** |
| Second-run weighted separate-topic recall | 113/134 (84.3%) | **109/134 (81.3%)** |

On the ten PDF sources, first-run coverage falls from 51 mentions / 49 separate
subjects to 47 / 47 of 53. On the two text controls it falls from 16 / 16 to
14 / 14 of eighteen. These are discovery measures, not accurate-record rates.
No best-of-repeats union is used.

York recommendations are now explicitly proposed with null outcomes and decision
dates. This improvement does not arise from stripping all actual actions:
Gran-U-Lawn and Willis retain their actual current plan/modification
recommendations in both runs; the Institute retains actual tabling; Walters Farm
retains all three actual recommendations. Spring Grove's driveway waiver, SCADA
purchase and authorization to pursue open-space funding survive. East Manchester
retains the actual HOP-application authorization, surety release, easement-work
authorization, equipment-only playground approval and conditional Hillwood
approval in both runs.

There is nevertheless action-detail loss: Gran-U-Lawn and Willis untabling are
absent in the revised first run and present in its second. York's prior Park
Street tabling remains in the second-run narrative but is absent from that run's
structured action list. Preserving the main decision does not demonstrate full
action recall.

## Omissions and remaining errors

The revised first run misses ten reference topics:

- Shrewsbury: all five minor subjects covering compliant properties at 40 and 44
  East Tolna Road, 6 Covington Drive and 34 South Main Street, plus the removed
  wall at East Tolna/Crosswind. It recovers the sand-volleyball proposal.
- Spring Grove: the adopted clothing-bin ordinance.
- East Manchester: IGA/537 planning, LERTA preparation, Canal/East Locust Point,
  and Saginaw/Mt. Wolf capacity.

In the second Shrewsbury run, the compliant properties return, but 40 and 44 East
Tolna remain combined. The wall and volleyball proposal are missing. In East
Manchester's second run, LERTA returns as a topic, but I-83/Exit 26 and Core 5
blasting disappear; IGA/537, Canal/East Locust and capacity remain missing.
LERTA's actual authorization to prepare paperwork is still absent from the
returned record. Scope selection remains unstable despite unchanged scope rules.

Both Willis records still import Schoolhouse Lane/Ridge Road and requirements
from the ambiguous intervening section. Fewer foreign modification motions are
emitted as actions, but the location/activity attachment remains unsafe. Both
responses return empty unresolved-fragment lists. All sixteen responses return
empty unreadable-page lists.

Plasterer's conflicting historical waiver dates remain unflagged. The second DHL
record still constructs a site vicinity from the complainant's address. The
second Shrewsbury response blurs the Heathcote agreement-review/signing sequence;
source review must precede agreement signing, which precedes preliminary-plan
signing. Hillwood retains conditional approval but still omits the explicit
two-building scope. Its retained conditions do not replace an adequate description
of the development itself.

The new local consistency check finds **three proposed actions with non-null
`reported` outcomes**, concerning Manchester Street in both runs and Core 5 in
the first. These remain in the raw responses and are flagged separately. They
confuse an actual announcement with the future activity being announced. The
nullable schema permits the combination; prompt guidance alone did not enforce
it. There are no such contradictions in the York records. An explicit consumer
check can withhold the inconsistent action interpretation without discarding the
underlying discovery record.

Literal-source diagnostics still find omitted words, shortened quotations and
wrong physical pages. Matching source quotes do not establish subject attachment.
Optional and out-of-scope output remains: for example, the twenty-page Hallam
agenda produces eight records instead of four, including park weed maintenance
and generic grant updates. Its two required subjects are present, but extra output
is not additional credited discovery.

## Interpretation

The action-stage error is responsive to the contract at this same model level.
That is evidence against treating every failure as a model-capability limit.
However, the revised reader loses both minor subjects and higher-priority policy
or capacity information. It is plausible that added emphasis on actions changes
what the reader selects as relevant; this small comparison does not establish that
mechanism or measure its population effect. Ordinary generation variability also
remains visible in the repeats.

A safer next experiment would keep discovery focused on subject, activity, current
state and evidence, then test action verification and omission recovery with their
own acceptance measures. It should measure recovered source topics, preserved
real actions, new false facts, review load and cost. The present result does not
justify promoting this entire prompt as the replacement or claiming completeness.

## Evidence and verification

Artifacts are in `output/pass0-redesign-2026-09-06/action-contract-v107/`.
`action_contract_v107.py` freezes and runs the comparison; `audit_action_v107.py`
reconstructs all sixteen requests, proves identical source/user messages and
unchanged inference settings, and reproduces explicit topic mappings, weighted
counts, source-quote diagnostics and occurrence-consistency flags. Reference and
weights are byte-identical to v106 and excluded from requests. The audit also
verifies input/code hashes, schema validity, OpenAI routing and normal completion.
Source judgments remain model-assisted, not independent human gold.

All sixteen calls settled without API/schema failures for **$0.06660830**. The
first twelve cost $0.05355444 and the four repeats $0.01305386, including provider
caching and excluding preparation/review labor. Completion usage stayed below
3,624 tokens, well below the 8,192-token ceiling; the omissions precede any local
filtering. Known spending is $5.175748464696, with the same three older unresolved
reservations totaling $1.079594964. **$1.744656571304 remains uncommitted under the
approved $8 cap.**

Ruff formatting and lint pass for both new helpers. The offline audit reproduces
all sixteen jobs, and the diff whitespace check passes. No production behavior
was changed or promoted.
