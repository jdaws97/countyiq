# Local intelligence backfill

CountyIQ executes pipeline and native authoring work on the operator PC.
For an existing production database, use the protected session in
[Local pipeline commands](local-pipelines.md). Deploy the reviewed commit first,
then use a clean local checkout of that exact commit. Accepted outputs are
written through the separate pipeline role; source archives remain in R2 and
run history and authoring artifacts remain on the PC.

The former first-host dump/export handoff is retired. Do not restore a local
application database over production to transfer model output. Database backup
and incident restoration are separate procedures in
[Backup and restore](backup-and-restore.md).

## Prepare and preserve state

Install the locked pipeline environment with `uv sync --project pipelines
--locked --extra dev`. The runner creates private state under
`~/.local/state/countyiq/pipeline`, including SQLite run/event history, logs,
model archives, and backfill state. Choose `--state-dir` when a different
durable location is needed, and retain any explicitly selected native artifact
directory alongside it. The VPS database backup does not include these files.

For development only, use the local PostgreSQL service on port 5433 with
explicit `DATABASE_*` settings and `--local`. A governed local raw archive can
use `COUNTYIQ_LOCAL_RAW_ARCHIVE_DIR`; production sessions use strict R2
archival. Keep integration tests on a disposable database because they retain
append-only audit fixtures.

## Refresh evidence before authoring

From `pipelines/`, run the required source job or asset subset through the
protected wrapper, then rebuild deterministic evidence:

```bash
.venv/bin/python scripts/run_pipeline.py \
  --ssh-target ubuntu@YOUR_HOST --identity-file /absolute/path/to/ssh-key \
  --job proceedings_refresh

.venv/bin/python scripts/run_pipeline.py \
  --ssh-target ubuntu@YOUR_HOST --identity-file /absolute/path/to/ssh-key \
  --job deterministic_enrichment_refresh
```

Source policy denials remain denials. A completed command publishes job and
asset health receipts synchronously; no background process is needed.
Production sessions force every inference pass off. Inspect the report and
source health before treating the evidence as ready for authoring.

## Bounded native authoring

Use the same wrapper for the named native scripts:

```bash
.venv/bin/python scripts/run_pipeline.py \
  --ssh-target ubuntu@YOUR_HOST --identity-file /absolute/path/to/ssh-key \
  --script subscription-backfill -- \
  read --directory /absolute/path/to/subscription-artifacts \
  --limit 16 --batch-size 8
```

Follow [Subscription backfill](subscription-backfill.md) for supported stages,
selectors, identity constraints, artifact replay, partial coverage, and source
validation. Keep account authentication on the PC. Preserve request/response
receipts and reuse the same artifact directory for interrupted work. Scripts
retain their own validation receipts; they do not create a Dagster job outcome.

After source reads, rebuild `municipal_evidence_linking` before authoring
municipal matters or property explanations. Then run the appropriate
deterministic projections, including `intelligence_events`, and verify current
coverage, citations, integrity state, and the health API. A bounded batch does
not establish coverage outside its selected scope.

## Paid-pass boundary

The protected production wrapper does not enable paid inference jobs. Existing
quality review, canary, budget, contradiction, and backfill authorization gates
remain in the code; a funded key or completed source refresh does not bypass
them. [Intelligence rollout](intelligence-rollout.md) records those gates, but
its older server-side execution examples are not the local runner procedure.
Pass 4 remains excluded from this backfill workflow.

If integrity preflight finds test fixtures, stale bindings, or unresolved
contradictions, preserve the evidence and resolve the specific issue through
the reviewed workflow. Do not delete append-only history to make a check pass.
