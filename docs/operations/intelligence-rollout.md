# Intelligence Canary and Backfill Gate

This is the operator contract for paid Passes 0–3. It separates a bounded
canary from the later full York backfill. No paid pass is scheduled; an API key
alone cannot enable one.

## What the controls prove

- Exact quotes, explicit entity membership/source identifiers, machine-readable
  evidence references, and inline brief citations fail closed before serving.
- Accepted, quarantined, legacy-unverified, and human-resolved decisions are
  append-versioned. A same-evidence semantic flip cannot replace the incumbent.
- The resolver recomputes current source evidence, verifies the exact reviewed
  source hash, and changes the projection and audit ledgers in one transaction.
- Finite item, dollar, and provider-price limits bound dispatch. Missing cost
  telemetry or a provider failure after dispatch charges the full conservative
  reservation and stops subsequent calls.

These controls prove provenance, citation resolution, and internal consistency.
They do not prove that a model's interpretation is factually correct. Human
gold labels and review of consequential canary outputs remain the truth oracle.

## 1. Deploy the boundary without enabling inference

Deploy the reviewed commit through the normal quiesced release path, which
creates and verifies the rollback backup before applying Alembic to the
repository's current head. Revision 040 archives old model-backed projections lacking
accepted provenance as `legacy_unverified` and retracts them. It does not delete
source records or accepted inference history.

```bash
cd /opt/countyiq
export COUNTYIQ_DEPLOY_REF=<reviewed-40-character-commit-sha>
git checkout --detach "$COUNTYIQ_DEPLOY_REF"
env COUNTYIQ_DEPLOY_REF="$COUNTYIQ_DEPLOY_REF" \
  COUNTYIQ_ENV_FILE=/opt/countyiq/.env docker/deploy.sh --check
sudo env COUNTYIQ_DEPLOY_REF="$COUNTYIQ_DEPLOY_REF" \
  COUNTYIQ_ENV_FILE=/opt/countyiq/.env docker/deploy.sh
```

Verify `/api/ready`, `/api/ops/health`, and that the database matches the
checked-out repository's Alembic head. All `COUNTYIQ_PASS{0-4}_ENABLED` values
must remain false during this deployment.

## 2. Complete the remaining human label review

Pass 2 requires review of all 20 release-review cases in
`pipelines/eval/fixtures/p2_expanded_stability20.json`. Inspect the source
evidence, every accepted status/significance range, required fact, and forbidden
claim. Do not approve a rubric merely because Luna agreed with it.

Copy `docs/operations/pass2-human-review-receipt.example.json` outside the
repository or to a separately reviewed release artifact. Fill the reviewer,
timestamp, fixture SHA-256, and one `"approved"` decision for each case ID. If a
rubric is wrong, correct and review the frozen promotion corpus before approval;
the receipt must not paper over a bad label.

The Pass 2 preflight validates that all 20 IDs are approved and that the receipt
matches the exact fixture bytes. The product owner may delegate this review to
an AI reviewer; the receipt must then name the reviewer as such and link the
written case-by-case record (the current 2026-09-04 review is in
`docs/research/pass2-rubric-review-2026-09-04.md`).

This receipt is a first-run gate only. Once a pass has accepted model runs in
the ledger, the preflight replaces it with the live deterministic-gate pass
rate over the last 30 days: accepted outputs divided by accepted plus rejected,
required to stay at or above `COUNTYIQ_PASS{N}_MIN_GATE_PASS_RATE` (default
0.8) once 20 outputs exist. A prompt or model change that starts failing the
quote, citation, or membership gates therefore blocks the next run without a
person re-labelling anything.

## 3. Produce a fresh no-spend estimate

Run the deterministic refresh first so candidate materialized views and source
contexts are current. Then run the estimator; it performs SELECTs only and does
not import the provider harness.

```bash
cd /opt/countyiq/pipelines
.venv/bin/python scripts/estimate_llm_backfill.py \
  --sample-size 50 \
  --output /opt/countyiq/receipts/intelligence-estimate.json
```

Record the estimate file, database snapshot/backup identifier, model defaults,
provider prices, and the approved maximum for each pass. Do not derive the
dollar limit from the retry ceiling unless that worst case is intentionally
funded.

## 4. Configure exactly one canary pass

For the selected pass, set:

```text
COUNTYIQ_PASS<N>_ENABLED=true
COUNTYIQ_PASS<N>_MAX_ITEMS=<bounded-canary-count-at-or-below-25>
COUNTYIQ_PASS<N>_MAX_COST_USD=<approved-dollar-limit>
COUNTYIQ_MAX_PRICE_PROMPT=<approved-provider-input-price-per-million>
COUNTYIQ_MAX_PRICE_COMPLETION=<approved-provider-output-price-per-million>
COUNTYIQ_PASS<N>_BACKFILL_AUTHORIZATION_FILE=<new-canary-authorization-path>
COUNTYIQ_ARCHIVE_STRICT=true
```

Leave every other paid pass disabled. For Pass 0, retain the native PDF engine
and set a reviewed `COUNTYIQ_PASS0_PDF_TOKEN_CEILING` if 50,000 tokens is not a
safe per-document reservation.

Before enabling the canary, create a new cumulative authorization while the
pass is still disabled:

```bash
.venv/bin/python scripts/create_intelligence_backfill_authorization.py \
  --pass-number <N> \
  --output /opt/countyiq/receipts/pass-<N>-canary-authorization.json
```

The item ceiling remains active for the canary, while this ledger makes its
dollar ceiling cumulative across crashes and accidental reruns.

Run the read-only preflight from the exact environment that will execute the
job:

```bash
cd /opt/countyiq/pipelines
.venv/bin/python scripts/verify_intelligence_preflight.py \
  --target-pass <0|1|2|3> \
  --sample-size 50 \
  --max-canary-items 25 \
  --output /opt/countyiq/receipts/pass-<N>-preflight.json
```

Pass 2 also requires:

```text
--human-review-receipt /secure/path/pass2-human-review-receipt.json
```

The command exits nonzero unless the database matches the repository's single
Alembic head, the integrity queue is clean, every active projection has
accepted provenance, a fresh estimate is available, only the target pass is
enabled, and all spend/archive controls are present. Any deterministic
validation rejection in the prior 24 hours also fails preflight; fix the
model/prompt or evidence issue before proceeding.

## 5. Run and inspect the bounded canary

Use the corresponding manual Dagster job, never `intelligence_full_pipeline`:

| Pass | Manual job |
|---|---|
| 0 | `proceedings_extraction_refresh` |
| 1 | `entity_verification_refresh` |
| 2 | `signal_validation_refresh` |
| 3 | `brief_generation_refresh` |
| 3b | `owner_briefs_refresh` |

After the job, immediately disable the pass. Review provider receipts and raw
archives against the dollar cap and inspect every gate rejection. Do not read
every accepted output: draw the audit sample instead (section 6). Repeat-run
testing must use a separately approved canary budget; do not call a second
stochastic sample "free verification."

For the approved backfill after a clean canary, disable the pass, set
`COUNTYIQ_PASS<N>_BACKFILL_MODE=true`, keep the approved dollar and provider
price ceilings in the environment, point at a new output path, and create a
separate one-time cumulative authorization:

```bash
.venv/bin/python scripts/create_intelligence_backfill_authorization.py \
  --pass-number <N> \
  --output /opt/countyiq/receipts/pass-<N>-authorization.json
```

Set `COUNTYIQ_PASS<N>_BACKFILL_AUTHORIZATION_FILE` to that path, enable only
the target pass, and rerun preflight. The authorization is scoped to the pass,
model, dollar limit, and both provider price ceilings. Reservations are written
before dispatch and survive process restarts; a provider call whose cost cannot
be verified is charged at its full reservation. Never edit or reuse an
authorization for another scope. An orphaned reservation after a crash is an
intentional fail-closed stop: reconcile it against provider receipts and create
a newly approved authorization rather than deleting the reservation.

## 6. Review queue and sampled audit

Contradictions no longer wait for a person one by one. When a pass quarantines
a same-evidence flip, the policy in `countyiq/lib/intelligence_autoresolve.py`
runs immediately:

| Situation | Outcome |
|---|---|
| Consequential flip: any entity membership merge or split, approved <-> denied, a signal crossing medium-or-high brief eligibility, investigate <-> insufficient evidence (including historical pursue/pass/none labels) | Stays in the queue for a person |
| Routine flip from a newer model or prompt version | Challenger accepted automatically |
| Routine flip on the same model, prompt and evidence | Incumbent kept automatically |
| `COUNTYIQ_JUDGE_MODEL` set and the judge disagrees with the rule default | Stays in the queue with the judge's reasoning |

Every assessment is recorded in `meta.intelligence_auto_resolutions`; every
automatic resolution goes through the same atomic path as a human one and is
marked `auto_resolution` in the ledger. Set
`COUNTYIQ_AUTO_RESOLVE_CONTRADICTIONS=false` to quarantine everything.

What is left for a person:

```bash
cd /opt/countyiq/pipelines
.venv/bin/python scripts/review_intelligence_contradictions.py list      # queue with reasons
.venv/bin/python scripts/review_intelligence_contradictions.py show <id>
.venv/bin/python scripts/review_intelligence_contradictions.py resolve <id>   --decision <accept_prior|accept_challenger|discard_both>   --resolved-by '<reviewer>'   --rationale '<source-based rationale>'   --expected-source-hash '<hash from the latest show output>'   --confirm-projection-change
.venv/bin/python scripts/review_intelligence_contradictions.py auto      # re-run the policy on a backlog
```

Person/organization merge questions are expected to be the bulk of the queue
after the first Pass 1 backfill; review them as a batch rather than blocking
the pipeline on them. `resolve` refuses an already-resolved, superseded,
hash-mismatched, or source-changed contradiction. There is no API write
endpoint.

The weekly audit replaces line-by-line reading. It samples auto-resolutions
the judge was unsure about, low-agreement Pass 2 rows, then random accepted
outputs; every verdict is recorded and written out as a gold candidate for the
eval corpus:

```bash
.venv/bin/python scripts/review_intelligence_contradictions.py sample --size 20
.venv/bin/python scripts/review_intelligence_contradictions.py approve <inference_id> --reviewer '<name>'
.venv/bin/python scripts/review_intelligence_contradictions.py reject <inference_id> --reviewer '<name>' --notes '<what was wrong>'
```

Candidates land in `pipelines/eval/fixtures/candidates/` (gitignored, see
`COUNTYIQ_GOLD_CANDIDATE_DIR`); de-identify and label them with
`eval.build_fixtures` before promoting any to the frozen corpus.

## 7. Canary acceptance

The canary is acceptable only when:

- the preflight returns `ready: true` before dispatch;
- item and actual provider spend stay inside the signed limits;
- no citation, evidence-reference, identity-membership, or schema failure is
  waived;
- every contradiction is either resolved by the recorded policy or adjudicated
  by a person, and the integrity view is green;
- the deterministic gate pass rate is at or above its threshold (or fewer than
  20 outputs exist yet);
- no deterministic gate rejection occurred in the preceding 24 hours;
- sampled factual interpretations meet the human gold acceptance threshold;
- no catastrophic identity merge or unsupported buyer-actionability claim is
  present; and
- a rerun of the no-spend preflight is clean.

Only then prepare a separate full-backfill authorization. This runbook does not
authorize or execute that backfill.

## Version-bound product release gate

See [LLM product release](llm-product-release.md) for the mandatory quality receipt,
private-watch migration, frozen rubric checks, and isolated local test setup.
A structural gate pass rate does not approve a model/prompt release.
