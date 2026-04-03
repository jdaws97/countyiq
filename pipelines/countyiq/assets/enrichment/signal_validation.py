"""Pass 2 — Signal Validation Dagster Asset.

Interrogates each development signal on each parcel to determine if it is
actually meaningful.  For each unvalidated signal, gathers full context,
builds a validation prompt using the signal-specific template, invokes the
LLM, parses the response, and upserts results to public.evidence.

The asset is controlled by the COUNTYIQ_TEXT_MODEL environment variable.
If that variable is not set, the asset returns immediately with
status="skipped", allowing it to exist in the Dagster graph without
failing on machines that have no model configured.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dagster import (
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
)

from countyiq.lib.intelligence_common import compute_input_hash
from countyiq.lib.pass2_signal_validation import (
    build_signal_validation_prompt,
    gather_signal_context,
    parse_signal_validation_output,
)
from countyiq.resources.database import DatabaseResource


# ---------------------------------------------------------------------------
# SQL constants
# ---------------------------------------------------------------------------

UNVALIDATED_SIGNALS_QUERY = """
    SELECT
        ds.pidn,
        ds.signal_key,
        ds.signal_weight,
        ds.source_table,
        ds.source_id,
        ds.distance_m,
        ds.evidence
    FROM public.development_signals ds
    LEFT JOIN public.evidence e
        ON e.pidn = ds.pidn AND e.signal_key = ds.signal_key
    WHERE e.id IS NULL
    ORDER BY ds.signal_weight DESC
"""

UPSERT_EVIDENCE_QUERY = """
    INSERT INTO public.evidence
        (pidn, signal_key, claim, evidence_data, source_url, internal_url,
         validation_status, adjusted_significance, validation_reasoning,
         cross_references, validated_at)
    VALUES
        (%(pidn)s, %(signal_key)s, %(claim)s, %(evidence_data)s::jsonb,
         %(source_url)s, %(internal_url)s,
         %(validation_status)s, %(adjusted_significance)s,
         %(validation_reasoning)s, %(cross_references)s::jsonb,
         %(validated_at)s)
    ON CONFLICT (pidn, signal_key)
    DO UPDATE SET
        claim = EXCLUDED.claim,
        evidence_data = EXCLUDED.evidence_data,
        source_url = EXCLUDED.source_url,
        internal_url = EXCLUDED.internal_url,
        validation_status = EXCLUDED.validation_status,
        adjusted_significance = EXCLUDED.adjusted_significance,
        validation_reasoning = EXCLUDED.validation_reasoning,
        cross_references = EXCLUDED.cross_references,
        validated_at = EXCLUDED.validated_at
"""


# ---------------------------------------------------------------------------
# Dagster Asset
# ---------------------------------------------------------------------------

@asset(
    group_name="enrichment",
    description=(
        "Pass 2: validate each development signal against full parcel context "
        "to determine if the signal is meaningful, stale, or irrelevant"
    ),
    deps=["entity_verification", "development_signals"],
    kinds={"postgres", "llm"},
)
def signal_validation(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> MaterializeResult:
    log = context.log

    # ------------------------------------------------------------------
    # Guard: model must be configured
    # ------------------------------------------------------------------
    model_path = os.environ.get("COUNTYIQ_TEXT_MODEL")
    if not model_path:
        log.info(
            "COUNTYIQ_TEXT_MODEL is not set — skipping Pass 2 signal validation. "
            "Set this env var to the path of a GGUF text model to enable."
        )
        return _skipped_result("COUNTYIQ_TEXT_MODEL not set")

    # ------------------------------------------------------------------
    # Guard: llm_harness must be importable
    # ------------------------------------------------------------------
    try:
        from countyiq.lib.llm_harness import HarnessConfig, invoke_with_retry  # noqa: F401
    except ImportError as exc:
        log.warning("llm_harness import failed (%s) — skipping", exc)
        return _skipped_result("llm_harness import failed")

    from countyiq.lib.llm_harness import HarnessConfig, invoke_with_retry

    config = HarnessConfig(model_path=model_path, max_tokens=2048)

    # ------------------------------------------------------------------
    # Find unvalidated signals
    # ------------------------------------------------------------------
    log.info("Querying unvalidated signals")
    rows = database.execute(UNVALIDATED_SIGNALS_QUERY)

    if not rows:
        log.info("No unvalidated signals found.")
        return MaterializeResult(
            metadata={
                "status": MetadataValue.text("complete"),
                "signals_total": MetadataValue.int(0),
                "validated": MetadataValue.int(0),
                "skipped": MetadataValue.int(0),
                "errors": MetadataValue.int(0),
            }
        )

    signals_total = len(rows)
    validated = 0
    skipped = 0
    errors = 0

    log.info("Found %d unvalidated signals", signals_total)

    conn = database._get_conn()

    for row in rows:
        # Unpack row — may be tuple or dict depending on cursor type
        if isinstance(row, dict):
            pidn = row["pidn"]
            signal = {
                "signal_key": row["signal_key"],
                "signal_weight": row["signal_weight"],
                "source_table": row["source_table"],
                "source_id": row["source_id"],
                "distance_m": row["distance_m"],
                "evidence": row["evidence"] if isinstance(row["evidence"], dict) else {},
            }
        else:
            pidn = row[0]
            signal = {
                "signal_key": row[1],
                "signal_weight": row[2],
                "source_table": row[3],
                "source_id": row[4],
                "distance_m": row[5],
                "evidence": row[6] if isinstance(row[6], dict) else {},
            }

        signal_key = signal["signal_key"]

        try:
            # Gather full context
            import psycopg2.extras
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                ctx = gather_signal_context(cur, pidn, signal)

            # Change detection
            input_hash = compute_input_hash(ctx)

            existing = database.execute(
                """
                SELECT input_hash FROM meta.intelligence_passes
                WHERE pidn = %(pidn)s
                  AND pass_number = 2
                  AND status = 'complete'
                """,
                {"pidn": f"{pidn}:{signal_key}"},
            )
            if existing and existing[0][0] == input_hash:
                log.debug("Signal %s on %s unchanged, skipping", signal_key, pidn)
                skipped += 1
                continue

            # Build prompt and invoke LLM
            prompt = build_signal_validation_prompt(ctx)
            result = invoke_with_retry(config, prompt, retries=1)

            if not result.success:
                log.warning(
                    "LLM failed for %s on %s: %s", signal_key, pidn, result.error,
                )
                _update_pass_status(
                    database, f"{pidn}:{signal_key}", 2, "error",
                    input_hash, result.error,
                )
                errors += 1
                continue

            # Parse and validate output
            parsed = parse_signal_validation_output(result.parsed or {})
            if "error" in parsed:
                log.warning(
                    "Invalid LLM output for %s on %s: %s",
                    signal_key, pidn, parsed["error"],
                )
                _update_pass_status(
                    database, f"{pidn}:{signal_key}", 2, "error",
                    input_hash, parsed["error"],
                )
                errors += 1
                continue

            # Upsert to public.evidence
            claim = "; ".join(parsed.get("key_facts", []))
            evidence_data = signal.get("evidence", {})
            source_url = ""
            internal_url = f"/property/{pidn}"
            now = datetime.now(timezone.utc).isoformat()

            database.execute(
                UPSERT_EVIDENCE_QUERY,
                {
                    "pidn": pidn,
                    "signal_key": signal_key,
                    "claim": claim or None,
                    "evidence_data": json.dumps(evidence_data),
                    "source_url": source_url or None,
                    "internal_url": internal_url,
                    "validation_status": parsed["validation_status"],
                    "adjusted_significance": parsed["adjusted_significance"],
                    "validation_reasoning": parsed["reasoning"],
                    "cross_references": json.dumps(parsed.get("cross_references", [])),
                    "validated_at": now,
                },
            )

            # Update pass tracking
            _update_pass_status(
                database, f"{pidn}:{signal_key}", 2, "complete", input_hash,
            )
            validated += 1

            log.info(
                "Validated %s on %s: %s (%s)",
                signal_key, pidn,
                parsed["validation_status"],
                parsed["adjusted_significance"],
            )

        except Exception as exc:
            log.warning(
                "Error processing %s on %s: %s", signal_key, pidn, exc,
            )
            errors += 1

    log.info(
        "Pass 2 complete: %d total, %d validated, %d skipped, %d errors",
        signals_total, validated, skipped, errors,
    )

    return MaterializeResult(
        metadata={
            "status": MetadataValue.text("complete"),
            "signals_total": MetadataValue.int(signals_total),
            "validated": MetadataValue.int(validated),
            "skipped": MetadataValue.int(skipped),
            "errors": MetadataValue.int(errors),
        }
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _update_pass_status(
    database: DatabaseResource,
    pass_key: str,
    pass_number: int,
    status: str,
    input_hash: str,
    error_message: str | None = None,
) -> None:
    """Insert or update meta.intelligence_passes for a signal validation."""
    database.execute(
        """
        INSERT INTO meta.intelligence_passes
            (pidn, pass_number, status, last_run_at, input_hash, error_message)
        VALUES
            (%(pidn)s, %(pass_number)s, %(status)s, NOW(), %(input_hash)s, %(error_message)s)
        ON CONFLICT (pidn, pass_number)
        DO UPDATE SET
            status = EXCLUDED.status,
            last_run_at = EXCLUDED.last_run_at,
            input_hash = EXCLUDED.input_hash,
            error_message = EXCLUDED.error_message
        """,
        {
            "pidn": pass_key,
            "pass_number": pass_number,
            "status": status,
            "input_hash": input_hash,
            "error_message": error_message,
        },
    )


def _skipped_result(reason: str) -> MaterializeResult:
    """Return a MaterializeResult indicating the asset was skipped."""
    return MaterializeResult(
        metadata={
            "status": MetadataValue.text("skipped"),
            "reason": MetadataValue.text(reason),
            "signals_total": MetadataValue.int(0),
            "validated": MetadataValue.int(0),
            "skipped": MetadataValue.int(0),
            "errors": MetadataValue.int(0),
        }
    )
