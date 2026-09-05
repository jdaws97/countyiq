# Municipal LLM fixes and regression — September 5, 2026

The fixes substantially improve usable extraction yield and block several consequential mistakes. Full backfill is still not recommended: the regression retains useful case history, but misses some named matters and underclassifies several housing conversions. No quality receipt was issued, no customer data was published, and no production database was changed.

## What changed

- Validate each matter independently after validating the document envelope and source hash. A bad citation now quarantines that matter while valid siblings survive. Keep original claims, rejected item indexes and reasons in immutable inference payloads and operator telemetry. Entirely rejected output remains a failure rather than a valid empty document.
- Require short, exact source excerpts for decision action and relevance. An agenda choice, uncompleted motion, draft amendment or procedural modification cannot establish completed project or ordinance approval. Decision authority can use the document header when the item's recorded action supports that body; a different body's action cannot borrow that authority.
- Derive relevance from item-specific evidence. Nearby compliance language no longer suppresses a substantive battery-storage proposal. Homeowner accessories, existing-tower splits and single-parcel Agricultural Security Area matters remain minor; substantive draft land-use policy stays discoverable with a procedural status.
- Improve instructions and prefilters for public bids, office additions, permitting and capital milestones. Exclude next-case-number footers from application identity, preserve only source-supported dates, and prevent generic policy names from creating shared project aliases. Typed ordinance/resolution references remain municipality scoped.

The wire contract now requires action and relevance excerpts. Existing quality approvals cannot certify these changed sources/schema. Stored contract version 3 remains compatible with consumers; release identity includes the new semantic validation module.

## Authorized ten-document regression

The user approved reuse of ten frozen municipal sources through OpenRouter, served by OpenAI using openai/gpt-5.6-luna, with a new $0.28 cap inside the original cumulative $1 limit. All ten requests completed, one attempt each.

| Measure | Prior run on the same ten | Fixed candidate, final replay |
| --- | ---: | ---: |
| Raw extracted matters | 51 | 52 |
| Matters surviving validation | 23 | 46 |
| Quarantined candidate matters | — | 6 |
| Candidate discovery-eligible matters | — | 15 |
| Provider cost | $0.03952565 | $0.04428219 |

All ten documents retain output; six are completely clean and four retain valid siblings alongside quarantined items. These are matter counts, not distinct projects or independently verified accuracy scores.

The generated candidate initially retained 44 matters. Subsequent deterministic corrections to header authority, procedural policy relevance and plan-modification scope were tested against the same saved responses, yielding 46 without additional model calls. The generation protocol is preserved unchanged; the final replay records its different code identity. The prompt was unchanged after generation. All 99 retained evidence spans match exact offsets and hashes in the frozen sources.

Cost rose 12.03% per ten-document sample. Cost per validation-surviving matter fell 43.98%; that does not establish cost per accurate customer opportunity. The new run spent $0.04428219, with no outstanding reservations. Cumulative conservative accounting is $0.24575343, including $0.08020906 retained for earlier failed requests without provider cost telemetry. This is below the authorized $1 cumulative cap.

A separate offline diagnostic on all forty old responses retains 100 matters versus 38 under the old whole-document gate. It explicitly enables legacy parsing because those responses lack the new required excerpts. It is diagnostic evidence only and cannot qualify the current candidate for publication.

## Customer value and remaining gaps

The roof public bid, Goodwill social-hall remodeling, Espresso Way permitting and Casella office addition provide useful leads or case updates. The data-center draft remains discoverable without claiming adoption. A garage approval unsupported by a recorded vote is withheld, and a next-case footer no longer creates a fake application.

Six candidate items remain withheld: two incorrectly located relevance excerpts, one incorrectly worded scheduled action, one unsupported garage decision, one related-entity citation mismatch and one nonliteral action excerpt. This protects customers but still loses potentially useful information.

Several York multifamily conversions remain incorrectly relegated to minor-property discovery status. The new generation also omits SolAmerica Orwig Road and Baker removal. Some generic ordinance context has limited customer value. Exact quotations and deterministic counterexamples do not establish that every generated explanation is entailed by its source.

This was a previously reviewed regression sample with targeted agent semantic review, not an unseen benchmark or independent human gold review. Do not infer precision or recall from validation acceptance. The next quality work is conversion classification, omitted named-matter coverage and excerpt selection, followed by source-scored evaluation on a fresh representative sample before deciding on a capped production canary.

## Verification and artifacts

Fresh verification passed: 1,175 pipeline tests, with 101 integration tests deselected; 15 attribution integration tests against countyiq_test with rollback; Dagster definitions import; and scoped whitespace/diff checks. A mocked production-asset regression verifies valid-only persistence, quarantine telemetry and preservation of original claims. No frontend or API behavior changed in this fixes pass.

The [machine-readable review](municipal-llm-v3-fixes-2026-09-05.json) contains per-source notes, exact costs and both release identities. Reproducible local evidence is in [verification.json](../../output/municipal-v3-fixes-2026-09-05/verification.json), [saved candidate responses](../../output/municipal-v3-fixes-2026-09-05/candidate10/results.json), [final production-validator replay](../../output/municipal-v3-fixes-2026-09-05/candidate10-replay.json), and [source review](../../output/municipal-v3-fixes-2026-09-05/source-review.json). The [earlier evaluation](municipal-llm-v3-results-2026-09-04.md) remains unchanged.
