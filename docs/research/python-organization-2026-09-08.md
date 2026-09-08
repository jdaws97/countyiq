# Python usage and organization audit

The repository has sensible top-level buckets, but experiment lifecycle and
operator discoverability need improvement. File count alone overstates the
maintenance problem. This is a read-only audit of code usage; no source files
were moved or deleted.

## Inventory

At commit `ee50f25`, `git ls-files '*.py'` reports 473 tracked Python files.
Counts include package initializers and test support files.

| Purpose / location | Files | Interpretation |
| --- | ---: | --- |
| `pipelines/countyiq/`, `api/lib/`, `api/routes/`, API entrypoints | 169 | Application namespace; includes some experimental libraries |
| `pipelines/tests/`, `api/tests/`, `api/unit_tests/` | 176 | Tests and test support |
| `pipelines/alembic/` | 76 | Migration history and environment; retain for upgrades |
| `pipelines/eval/` | 27 | Evaluations, fixture tooling, shared evaluation support |
| `pipelines/scripts/` | 12 | Operator commands |
| Infrastructure, orchestration, OCR, benchmark tooling | 13 | Supporting tools outside those buckets |
| **Total tracked** | **473** | These are not 473 independent scripts |

There are also 304 Python files under ignored `output/`. Many are saved source
snapshots, frozen experiment inputs, or unaccepted prototypes. For example,
`output/ux-redesign/baseline/` contains copied API files, and Pass 0 experiment
directories contain snapshots of the same libraries across revisions. Others
are one-off launchers and review helpers. They are not all unique maintained
tools, and Python files should be distinguished from the JSON receipts needed
for backfill resume and inference provenance.

The machine-readable inventory is the local, ignored
`output/python-inventory-2026-09-08.json`. Its untracked monitoring script belongs
to concurrent monitoring work and is not a cleanup candidate.

## What is actually used

Production Dagster starts `countyiq.definitions`; the API starts its application
entrypoint. The application namespace count is a location classification, not
a claim that all 169 files run on every request or pipeline execution.

The running historical source backfill uses
`scripts/subscription_backfill_remote.py`, which invokes
`scripts/subscription_backfill.py`. That command calls maintained source-read,
matter, explanation, validation, and persistence libraries. The same libraries
also support the Dagster assets. It does not execute the experimental Python
files in `output/`.

The operator scripts serve identifiable purposes:

| Purpose | Commands in `pipelines/scripts/` |
| --- | --- |
| Author and resume historical records | `subscription_backfill.py`, `subscription_backfill_remote.py` |
| Replay retained receipts after a binding fix | `rebind_subscription_reads.py` |
| Preflight, authorization, quality evidence, estimates | `verify_intelligence_preflight.py`, `create_intelligence_backfill_authorization.py`, `prepare_quality_receipt.py`, `estimate_llm_backfill.py` |
| Source and contradiction review | `audit_municipal_sources.py`, `review_proceeding_metadata.py`, `review_intelligence_contradictions.py` |
| Subscription login | `codex_login.py`, invoked by `docker/codex-login.sh` |
| Radar calibration | `backtest_radar_weights.py`, retained operational calibration workflow |

Documentation references and test imports establish supported use, not the last
time each command was executed. No standalone tool was established as dead
solely because it lacked a Python import.

Evaluation is not part of the ordinary application import path, but deleting
the directory would still break the current release contract:
`countyiq/lib/quality_release.py` hashes `eval/source_context_cases.py` for
Passes 2 and 3. `pipelines/Dockerfile` copies both `scripts/` and `eval/` into the
runtime image. Evaluation files also have direct test callers. The statement
“production does not import eval” is narrower than “production does not need
any eval files.”

## Concrete organization improvements

1. Add an operator-command index with purpose, entrypoint, inputs, output
   directory, and whether the command writes production data. Keep the twelve
   supported commands discoverable together; adding another generic runner is
   unnecessary.
2. Separate shared evaluation support, fixture preparation, and executable
   experiments inside `pipelines/eval/`. Retain compatibility entrypoints during
   moves so documented commands and tests remain valid.
3. Move research-only Pass 0 libraries out of the application namespace after
   confirming their callers. `pass0_facts`, `pass0_locator`, and
   `pass0_packet_facts` are concrete leads: their inspected non-test callers are
   evaluation code and each other. Keep the active `pass0_templates`, shared
   source binding, and current evidence pipeline in application code.
4. Give each retained experiment a status: active evaluation, historical replay,
   or retired prototype. Several Pass 2 result helpers have no established
   current execution history; that is an unknown lifecycle, not proof that
   they can be deleted.
5. Consolidate completed `output/` experiment folders into dated archives with
   a small manifest. Preserve the original files, receipt hashes, source
   snapshots, and the paths referenced by live backfill provenance. Keep active
   backfill directories in place until completion and verified backup.
6. Decide explicitly whether historical evaluation branches and the currently
   unserved Pass 4 feature remain supported. Those are product/replay decisions,
   not routine file cleanup. Preserve stored history and migration compatibility.

The earlier [test/code simplification review](test-code-simplification-2026-09-08.md)
contains narrower, independently testable cleanup findings. This audit does not
convert those recommendations into deletion authorization.

## Backfill throughput evidence

The resumed source run uses four model workers, batches of up to sixteen whole
documents, and the unchanged `gpt-6-astra` medium configuration. Around
16:28 UTC, 278 documents had been accepted in about fourteen minutes; source
reading was roughly twenty documents per minute. This is a stage-specific
observation, not an end-to-end completion estimate.

The first observed portion of this run produced seventeen combined model calls
covering 191 source receipts, plus eight individual calls. Combined prompts were
often around 110–127 thousand characters including their JSON envelope. The
120,000-character source batching threshold applies before that envelope, so
the configured sixteen-document batch size is often limited by complete source
size. Increasing that limit is not a free throughput improvement.

The current scheduler can wait on an earlier batch while later batches have
finished, and individual correction calls run in the consumer. This creates a
possible utilization gap. The code structure establishes that possibility;
the current measurements do not establish how much a scheduler rewrite would
save. Increasing concurrency or changing models requires a measured trial,
not a promised linear speedup.

A supported way to overlap useful work already exists: stages have separate
operator locks and independent model workers. After refreshing evidence links,
single-record selection bundles from fully read recent years can be authored
while older source documents continue. Property and case bundles still need
their complete source history. Every result retains the ordinary current-source
check, and final coverage must be measured again after all reads and links finish.

The first sixteen overlapping matter imports exposed a larger database cost:
`EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)` measured 16.036 seconds to check one
bundle. The materialized candidate view processed 16,213 records and discarded
16,212 after filtering to the requested key. The operator then repeated the
check inside matter persistence.

The subsequent focused implementation reconstructs isolated selections directly
from their current governed evidence and removes the operator's duplicate matter
check. A read-only production comparison found exact source equality for all
500 deterministically sampled single-record selection bundles. Median direct
lookup time was 5.17 ms; the 95th percentile was 7.23 ms. This is a comparison
of source checks, not a measured end-to-end speedup. Property, address, and case
bundles retain canonical full-scope resolution. Regression coverage includes
changed text, local/global rights revocation, and promotion of a selection to
case, address, or uniquely linked property scope.

The individual-record explanation path had the same county-wide lookup cost:
16.48 seconds for one municipal record. Adding the proceeding-ID predicate while
retaining the complete key and all governing predicates reproduced all 512
exported recent sources exactly. Median lookup time was 10.84 ms and the 95th
percentile was 19.31 ms. Property context preparation was measured separately
at 2.50 seconds for one existing sample property; that is not a population
benchmark.

The subsequent scheduler change consumes completed batches as they become ready,
prefetches singleton batches in their worker, and supports an explicit maximum
of eight workers. Regression checks cover a slow first batch, replacement work
starting before it finishes, bounded dispatch, early-stop caching, and unchanged
receipt reuse. Model, reasoning effort, and source/identity acceptance rules
remain unchanged. End-to-end gains still depend on model response time and the
distribution of source sizes.

The 3,506 eligible documents span February 9, 2000 through September 8, 2026,
covering 1,791 distinct meeting dates. There are 578 documents from 2025 and
490 from 2026. January–July 2026 contains 446 documents, about 64 per month in
this collection. This is uneven historical coverage, not a measured future
arrival rate or a complete census of every municipal document.
