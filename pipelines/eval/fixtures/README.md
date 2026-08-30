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
  deterministic, de-identified contexts from the 7,214 currently eligible
  parcels: 54 two-signal, 29 three-signal, and all 17 observed four-signal
  cases, covering all 24 observed interaction shapes. Its accepted outcomes,
  required facts, and prohibited claims are generated from explicit evidence
  rules and carry `rubric_generated_requires_human_confirmation`; they are
  diagnostic labels, not human-reviewed promotion gold. The companion
  `p2_expanded_stability20.json` is the deterministic 20-case disagreement
  subset used for repeatability testing and inherits the same limitation.
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
