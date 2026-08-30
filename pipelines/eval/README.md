# LLM evaluation

Production does not import this directory. Evaluation has two deliberately
separate lanes; see `fixtures/README.md` for provenance and remaining coverage
limits.

## Frozen regression

The default challenger lane uses byte-identical, fingerprinted inputs and human
labels for Passes 0-3:

- Pass 0: six rendered PDFs, five positive matters, three negative controls,
  and field-level applicant/parcel/decision/content checks.
- Pass 1: eight de-identified entity-partition cases spanning merges, hard
  negatives, a borderline acceptable alternative, government/authority
  boundaries, and a five-source organization link.
- Pass 2: ten de-identified contexts, one for every exact pair of the five
  production interpretive signals, with accepted calibration ranges, required
  evidence facts, and prohibited unsupported claims.
- Pass 3: four production-shaped decision/citation cases covering pursue,
  watchlist, and pass outcomes.

Every call uses the production system prompt, schema, reasoning contract, and
dynamic prompt builder. Human labels—not an LLM judge—determine gold results.
Pass 2 reports status, significance, joint calibration, grounded decisions,
prohibited claims, required-fact recall, strict signal passes, and perfect cases
separately so one omitted fact does not hide the rest of a model's behavior.

```bash
cd pipelines
.venv/bin/python -m eval.challenger \
  --model z-ai/glm-5.3-flash \
  --passes 2 \
  --quantizations fp8 \
  --max-cost-usd 0.25
```

For broader diagnostic coverage, `p2_expanded_frozen.json` contains 100
deterministically selected, de-identified contexts across all 24 signal
interaction shapes observed in the current database. Its expected outcomes are
evidence-derived rubrics and explicitly require human confirmation; this is not
promotion gold until adjudicated.

```bash
cd pipelines
.venv/bin/python -m eval.build_expanded_pass2 --check
.venv/bin/python -m eval.challenger \
  --model z-ai/glm-5.3-flash \
  --passes 2 \
  --pass2-fixture eval/fixtures/p2_expanded_frozen.json \
  --workers 8 \
  --quantizations fp8 \
  --max-cost-usd 0.25
```

`--workers` enables bounded concurrent Pass 2 calls while preserving the shared
pre-dispatch spend ledger. The result records `frozen_rubric` as its dataset so
it cannot be confused with human-reviewed gold.

## Live drift

Pass 1's committed names and Pass 2's `p2_pidns.txt` are live selectors, not
frozen evidence. Both gather mutable context from the current PostgreSQL database.
They are useful after a backfill for coverage, prompt-shape, latency,
abstention, stability, and drift checks, but are not comparable across database
snapshots. The CLI requires `--live` so this distinction cannot be missed.

```bash
cd pipelines
.venv/bin/python -m eval.challenger \
  --model z-ai/glm-5.3-flash \
  --passes 1,2 \
  --live \
  --quantizations fp8 \
  --reasoning-effort low \
  --max-cost-usd 0.50
```

Pass 2 stores challenger and incumbent outputs without an automated judge by
default. A paid pairwise judge is available with `--judge-model`, but its
verdict is diagnostic only—not a label or promotion oracle. In the 2026-08-30
probe, the judge cost more than all candidate calls, two of three judgments
truncated, and the surviving judgment rewarded schema shape while overlooking
unsupported factual certainty.

The evaluated optional replacement is `x-ai/grok-4.6`. With the tightened
evidence-auditor prompt, strict schema, and ZDR routing, it matched the human
winner and identified the decisive unsupported claims on all three bakeoff
cases for $0.025872 total. Use
`--judge-model x-ai/grok-4.6`; still retain human labels as the acceptance gate.

`eval_runner.py` remains an operational Pass 2/3 live smoke/latency/cost tool,
not a model-quality report. It now reserves provider-price-bounded maximum
charges before calls and checkpoints after every case. `--pidns-file` pins
selectors but still does not pin gathered context; its default SQL sample is
random.

## Fixture refresh

The builder makes no model calls. It refreshes one md5-stable live parcel for
each exact two-signal combination, de-identifies direct identifiers in the
frozen copy, fingerprints every context, and derives the reviewed Pass 3 cases.

```bash
cd pipelines
.venv/bin/python -m eval.build_fixtures
.venv/bin/python -m eval.build_fixtures --check
```

Do not refresh frozen evidence merely because live data changed. Review the
diff and labels as a corpus version change. Refresh the separate live shadow
after deterministic source/backfill changes.

When only labels or deterministic scoring change, re-score saved outputs for
free. The command refuses a context-hash mismatch and writes a new result. Pass
the matching custom fixture for expanded results:

```bash
cd pipelines
.venv/bin/python -m eval.rescore eval/results/<frozen-result>.json
.venv/bin/python -m eval.rescore \
  eval/results/<expanded-result>.json \
  --fixture eval/fixtures/p2_expanded_frozen.json
```

`eval.select_pass2_stability` deterministically extracts the highest-disagreement
paired cases for repeat trials. `eval.complete_pass2_result` can reconstruct a
partially checkpointed concurrent run from its archives and dispatch only
genuinely missing outputs; it is a recovery tool, not part of a normal run.

## Files

| File | Purpose |
|---|---|
| `challenger.py` | Frozen Pass 0-3 regression plus explicit live Pass 1/2 drift probes |
| `protocol.py` | Production-equivalent configuration, provider price ceilings, and pre-call spend reservations |
| `scoring.py` | Deterministic frozen-fixture scoring |
| `rescore.py` | Hash-checked offline rescoring of saved frozen Pass 2 outputs |
| `build_fixtures.py` | Deterministic de-identification, fingerprinting, and live-shadow refresh |
| `build_expanded_pass2.py` | Stratified 100-case Pass 2 diagnostic corpus builder and integrity check |
| `select_pass2_stability.py` | Paired-disagreement subset selection for repeated trials |
| `complete_pass2_result.py` | Archive-backed recovery of interrupted concurrent Pass 2 runs |
| `fixture_io.py` | Canonical context hashes and tamper/staleness checks |
| `eval_runner.py` | Ad hoc live Pass 2/3 database sampling |
| `eval_report.py` | Compare generated result files |
| `fixtures/` | Fixture data and provenance; read its README before interpreting a result |

One-off scripts and raw outputs belong in the gitignored `results/` and
`archives/` directories. Durable conclusions and current defaults belong in
`docs/decisions.md`.
