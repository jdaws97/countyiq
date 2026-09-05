# Municipal accuracy pass — September 5, 2026

Implemented the requested conversion relevance, conservative citation repair and omitted-matter detection changes, then completed a fresh twelve-document evaluation. The frozen candidate does not meet the predeclared thresholds for an additional review-only backfill. No backfill, quality receipt or customer publication followed the evaluation.

The strongest finding is that the model mentioned all 22 useful reference topics. Our validation and discovery rules account for the main losses. This gives the next work a bounded scope; it does not justify an open-ended sequence of prompt changes and paid canaries.

## Implemented changes

- Source-supported conversion to multifamily housing, apartments or additional dwelling units can be discoverable inside an existing building. The override requires the conversion and housing use in the same source clause. Model rationale alone, a historical conversion, a neighboring apartment building or an explicit denial of conversion cannot promote a minor matter.
- One unique exact relevance excerpt can be relocated to an adjacent passage when that passage is already cited by the same item's narrative and literal identity. The original model output remains unchanged; the repaired projection and reason are recorded separately. Unknown IDs, repeated excerpts, missing identity and distant text stay quarantined. Decisions are not repaired by searching for another vote.
- A deterministic inventory checks application IDs, addresses and named headings against extracted identities and narratives. Unmatched anchors are kept in the inference payload, operator status and evaluation results, including when the model returns an empty list. Lists are bounded with explicit truncation. Broad paragraph citations do not count as coverage. The check flags possible omissions and can produce false positives; it never manufactures projects or starts paid retries.
- Static instructions now distinguish existing-building conversions and require checking every named matter before returning.

An offline replay of the prior ten saved responses retains 47 matters and 18 discovery candidates, compared with 46 and 15 before this pass, with no new calls. It recovers the 701 Wallace conversion through a logged citation repair. The coverage check flags both SolAmerica and Baker. This replay is regression evidence, not fresh accuracy evidence.

## Fresh evaluation and stopping rule

Twelve documents were selected from 2,844 eligible source IDs not present in the previous forty-document evaluation. Selection was purposive, limited to 300–14,000 characters, and included agendas, minutes, property relief, draft policies, public works and a routine refuse-contract document. Some municipalities and ongoing cases recur. This is a small agent-reviewed sample, not a random estimate or independent human gold set.

Before generation, a hashed reference recorded 42 expected matters, including 22 useful discovery topics. The frozen criteria required zero unsupported decisions or wrong-property associations, at least 90% useful-matter retention and at least 90% discovery precision. The code and reference were unchanged during generation and scoring.

| Result | Count |
| --- | ---: |
| Useful reference topics mentioned in raw output | 22 / 22 |
| Useful matters retained through runtime gates | 18 / 22 — 81.8% |
| Useful matters reaching discovery | 16 / 22 — 72.7% |
| Discovery candidates supported by reference scope | 16 / 18 — 88.9% |
| Raw matters / validation survivors | 41 / 33 |
| Survivors after the normal vocabulary prefilter | 32 |
| Unsupported approvals / wrong-property claims observed | 0 / 0 |
| Deferred case incorrectly labeled removed | 1 |

The vocabulary prefilter would suppress one document's scope-uncertain road-project output. The evaluation intentionally called the model on every sample document to check such exclusions. One output covers two reference topics, so reference coverage and extraction counts differ.

Ruhlman's new-lot discovery classification is a borderline scope judgment. Counting it as useful would improve precision, but would not resolve the failed retention threshold. The reference remains unchanged. The twelve-document results are retained as evidence even though the candidate failed.

## Bounded findings

1. **Validation loses useful supported matters.** Slash-form votes such as 2/0, authority abbreviations and referral recipients expose limits in the current checks. “Currently approved” describing an existing three-unit conversion incorrectly rejects a scheduled fourth-unit request. Other rejections correctly withhold nonliteral citations. Four useful reference matters are lost at validation.
2. **Discovery classification loses context.** An existing-tower split is promoted, while a municipality-wide Agricultural Security Area review and a tabled hotel are hidden. These need scope and lifecycle handling with explicit tests.
3. **A deferred agenda item is mislabeled removed.** The Franklin Street case says it will be in August meetings pending details. Its closed-looking status is misleading.
4. **Lower-impact backlog:** omitted Colonial Sewer context, verbose/ambiguous review anchors, narrative date expansion, and waiver requests placed in a conditions list.

Further work should address those repeatable rule categories against saved outputs. Keep individual low-impact misses in the backlog. After those corrections, any new canary must have a finite sample, budget and decision rule. This turn stops at the predeclared no-go; it does not launch an additional sample to seek a passing result.

## Cost, verification and evidence

Twelve successful calls through OpenRouter, served by OpenAI using openai/gpt-5.6-luna, cost **$0.03945302** against a $0.30 cap, with zero retries and no open reservations. Conservatively accounted cumulative spend is **$0.28520645** under the original $1 ceiling, including prior uncertain failed-request debits.

Fresh checks passed: **1,194 pipeline tests**, **15 attribution integration tests** against the isolated countyiq_test database with rollback, Dagster definitions import, scoped diff/whitespace checks, and all 73 retained evidence spans against exact source offsets and hashes. There were no frontend/API changes or live database writes.

See the [source-scored review](municipal-accuracy-2026-09-05.json), [frozen reference](../../output/municipal-accuracy-2026-09-05/reference.json), [archived results](../../output/municipal-accuracy-2026-09-05/fresh12/results.json), [review queue](../../output/municipal-accuracy-2026-09-05/review-queue.md), and [verification record](../../output/municipal-accuracy-2026-09-05/verification.json).
