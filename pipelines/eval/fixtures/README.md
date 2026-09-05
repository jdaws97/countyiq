# Evaluation fixture provenance

CountyIQ uses two evaluation lanes because reproducibility and production drift
answer different questions.

## Frozen regression lane

Inputs, source evidence, and expected outcomes must all be committed and
versioned. Every model sees byte-identical context. This lane is the only one
that can support a model-promotion regression gate.

- **Pass 0:** `p0_pdfs/` plus `p0_expected.json`. All 17 PDF pages were rendered
  and visually reviewed on 2026-08-30. The gold set contains five positive
  property matters and three zero-extraction negative controls across six
  documents. Gold includes field-level applicant, parcel, decision/status,
  content, and supporting-text checks where the source supports them.
- **Pass 1:** `p1_frozen.json` contains eight de-identified production-shaped
  contexts and reviewed acceptable partitions. It includes hard negatives,
  one explicitly borderline case, government/authority boundaries, and
  parcel/tax/PLCB/corporate/proceeding linkage.
- **Pass 2:** `p2_frozen.json` contains ten de-identified contexts selected as
  one case for every exact pair of the five production interpretive signals.
  Labels define acceptable status/significance ranges, required evidence facts,
  and prohibited unsupported claims. Stable realistic aliases preserve repeated
  owners and decision-relevant types such as utility or school authority; do
  not replace them with visibly patterned placeholders that can bias entity
  reasoning.
- **Pass 2 expanded diagnostic:** `p2_expanded_frozen.json` contains 100
  deterministic, de-identified current-evidence contexts: 42 two-signal, 38
  three-signal, and 20 four-signal cases covering 46 observed interaction
  shapes across all six production interpretive signals. Selection takes up to
  two cases per observed shape, then fills deterministically to 100. The
  builder fails if selected, gathered, and labeled signal keys differ. Its
  accepted outcomes, required facts, and prohibited claims come from explicit
  evidence rules (`build_expanded_pass2.py`, rubric `pass2_expanded_v5`). The
  companion `p2_expanded_stability20.json` is a deterministic,
  cardinality-balanced 20-case release-review subset. All 20 were reviewed
  case-by-case on 2026-09-04
  (`docs/research/pass2-rubric-review-2026-09-04.md`) and carry
  `rubric_reviewed`; `--relabel` rewrites labels from stored contexts without
  touching contexts or their hashes. The other 80 cases remain
  `rubric_generated_requires_human_confirmation`.
- **Pass 3:** `p3_frozen.json` contains four reviewed contexts derived from the
  Pass 2 evidence and covers pursue, watchlist, and pass decisions plus strict
  signal citations.
- **Pass 4:** no current LLM promotion corpus; the pass remains disabled.

## Live drift lane

`p1_clusters.json` contains only name selectors. `p2_pidns.txt` contains only
parcel identifiers. The actual evidence for both is gathered from the current
PostgreSQL database, so it can change after every ingest, backfill, schema
change, or entity-resolution run. `p2_live_shadow.json` records the selected
combination for audit; regenerate it after deterministic source/backfill changes.

Use live data to measure current coverage, prompt shape, latency, abstention,
stability, and distribution drift. Save the complete gathered context with the
run before adjudication. Do not call selector-only runs “frozen,” and do not
compare models run on different database snapshots.

## Corpus maintenance

Run `python -m eval.build_fixtures --check` in verification. A context hash
mismatch is a hard failure. Regenerating the frozen files is a reviewed corpus
change, not routine drift maintenance. Keep widening the corpus when a real
failure reveals a missing class, and refresh the separate live shadow after the
York backfill so drift/cost measurements represent the eventual workload.

## Investigation contract and feature coverage (2026-09-04)

p3_investigation_frozen.json retains the original Pass 3 source contexts and
updates recommendation/urgency labels for investigation briefs. The original
p3_frozen.json remains unchanged for historical comparisons. feature_cases.json
adds four municipal-action and three owner-summary supplemental cases. These
synthetic cases have not yet been run against a paid model. See
docs/operations/llm-product-release.md for scoring and release requirements.
