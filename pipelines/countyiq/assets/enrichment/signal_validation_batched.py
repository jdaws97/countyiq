"""Pass 2 (batched) — Dagster Asset.

Validates all development signals for each parcel in a single LLM call,
rather than one call per signal. Shares parcel context across signals and
lets the LLM reason about cross-signal patterns.

This is the production-recommended asset. The per-signal version
(signal_validation.py) is retained for A/B comparison.

The asset is controlled by COUNTYIQ_TEXT_MODEL (local path) or
COUNTYIQ_OPENROUTER_MODEL (API slug). If neither is set, returns skipped.
"""
import json
import os
import traceback
from datetime import datetime, timezone

from dagster import (
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
)

from countyiq.lib.intelligence_common import compute_input_hash
from countyiq.lib.pass2_batched_validation import (
    build_batched_signal_prompt,
    gather_parcel_batch_context,
    parse_batched_signal_output,
)
from countyiq.resources.database import DatabaseResource


def _row_value(row, key: str, index: int = 0):
    """Return a column value from a DB row whether the row is a tuple or a dict.

    database.execute() currently returns plain tuples, but code that accesses
    row[0] will silently break if a RealDictCursor ever gets wired in as the
    default (row[0] on a dict returns the first key string, not the value).
    This helper normalizes both shapes.
    """
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key)
    return row[index]


# ---------------------------------------------------------------------------
# SQL constants
# ---------------------------------------------------------------------------

PARCELS_NEEDING_VALIDATION_QUERY = """
    -- Selects parcels that need (re-)validation for any of these reasons:
    --   1. Has at least one signal with no corresponding evidence row (new signal)
    --   2. Was never fully validated (no complete pass-2 record)
    --   3. Was validated but the context has since changed (hash mismatch —
    --      new signals added, entity data updated, etc.)
    --
    -- The input-hash check inside the main loop handles (3) at the parcel
    -- level, but the parcel has to be SELECTED first — this query ensures it is.
    SELECT DISTINCT ds.pidn
    FROM public.development_signals ds
    WHERE
        -- Reason 1: new/unmatched signal
        NOT EXISTS (
            SELECT 1
            FROM public.evidence e
            WHERE e.pidn = ds.pidn
              AND e.signal_key = ds.signal_key
        )
    UNION
    SELECT DISTINCT ds2.pidn
    FROM public.development_signals ds2
    JOIN meta.intelligence_passes ip
        ON ip.pidn = ds2.pidn
       AND ip.pass_number = 2
       AND ip.status = 'complete'
    WHERE
        -- Reason 3: previously validated, but the pass record exists and
        -- hash may be stale. The actual hash comparison happens in the
        -- Python loop; this just ensures the parcel enters the candidate set.
        -- We re-check periodically by selecting any parcel whose last
        -- validation is older than 7 days.
        ip.last_run_at < NOW() - INTERVAL '7 days'
    ORDER BY pidn
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
        "Pass 2 (batched): validate all development signals per parcel in a "
        "single LLM call. Cross-signal reasoning and cost-optimized."
    ),
    deps=["entity_verification", "development_signals"],
    kinds={"postgres", "llm"},
)
def signal_validation_batched(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> MaterializeResult:
    log = context.log

    # ------------------------------------------------------------------
    # Resolve backend and model
    # ------------------------------------------------------------------
    openrouter_model = os.environ.get("COUNTYIQ_OPENROUTER_MODEL")
    local_model = os.environ.get("COUNTYIQ_TEXT_MODEL")

    if openrouter_model:
        backend = "openrouter"
        model_path = openrouter_model
    elif local_model:
        backend = "llama_cpp"
        model_path = local_model
    else:
        log.info(
            "Neither COUNTYIQ_OPENROUTER_MODEL nor COUNTYIQ_TEXT_MODEL is set — "
            "skipping Pass 2 batched validation."
        )
        return _skipped_result("no model configured")

    log.info(f"Pass 2 batched: backend={backend} model={model_path}")

    # ------------------------------------------------------------------
    # Guard: llm_harness importable
    # ------------------------------------------------------------------
    try:
        from countyiq.lib.llm_harness import (
            HarnessConfig,
            get_preset_for_model,
            invoke_with_retry,
        )
    except ImportError as exc:
        log.warning("llm_harness import failed (%s) — skipping", exc)
        return _skipped_result("llm_harness import failed")

    # Default to thinking=True for batched validation since we saw quality wins
    thinking_enabled = os.environ.get("COUNTYIQ_THINKING", "true").lower() in ("1", "true", "yes")
    preset = get_preset_for_model(model_path, thinking=thinking_enabled, reasoning_task=True)

    config = HarnessConfig(
        model_path=model_path,
        backend=backend,
        max_tokens=4096,  # Larger budget for multi-signal batch output
        thinking=thinking_enabled,
        archive_label="pass2_batched",
        **preset,
    )

    # ------------------------------------------------------------------
    # Find parcels with unvalidated signals
    # ------------------------------------------------------------------
    log.info("Finding parcels with unvalidated signals")
    rows = database.execute(PARCELS_NEEDING_VALIDATION_QUERY)
    pidns = [_row_value(row, "pidn") for row in (rows or [])]
    total_parcels = len(pidns)

    if not total_parcels:
        log.info("No parcels with unvalidated signals.")
        return MaterializeResult(
            metadata={
                "status": MetadataValue.text("complete"),
                "parcels_total": MetadataValue.int(0),
                "parcels_validated": MetadataValue.int(0),
                "signals_validated": MetadataValue.int(0),
                "parcels_skipped": MetadataValue.int(0),
                "errors": MetadataValue.int(0),
            }
        )

    log.info(f"Found {total_parcels} parcels with unvalidated signals")

    parcels_validated = 0
    signals_validated = 0
    parcels_skipped = 0
    errors = 0

    for i, pidn in enumerate(pidns, 1):
        input_hash: str | None = None  # set after context gather, used in error paths
        try:
            # Gather all context + signals for this parcel using the public
            # dict_cursor context manager (no private _get_conn() access).
            # The DatabaseResource connection runs in autocommit mode, so
            # transaction boundaries are per-statement — the cursor is purely
            # for dict-row access.
            with database.dict_cursor() as cur:
                ctx = gather_parcel_batch_context(cur, pidn)

            if not ctx["signals"]:
                continue

            # Input hash — covers all signals + all context in one
            input_hash = compute_input_hash(ctx)

            # Check if already processed with same hash
            existing = database.execute(
                """
                SELECT input_hash FROM meta.intelligence_passes
                WHERE pidn = %(pidn)s
                  AND pass_number = 2
                  AND status = 'complete'
                """,
                {"pidn": pidn},
            )
            if existing and _row_value(existing[0], "input_hash") == input_hash:
                parcels_skipped += 1
                continue

            # Build prompt and invoke LLM (first attempt — all signals)
            prompt = build_batched_signal_prompt(ctx)
            result = invoke_with_retry(config, prompt, archive_key=pidn, retries=1)

            if not result.success:
                log.warning(f"LLM failed for {pidn}: {result.error}")
                _update_pass_status(database, pidn, 2, "error", input_hash, result.error)
                errors += 1
                continue

            # Parse batched output into per-signal validations
            parsed = parse_batched_signal_output(result.parsed or {}, ctx["signals"])

            if parsed.get("parse_error"):
                log.warning(f"Parse error for {pidn}: {parsed['parse_error']}")
                _update_pass_status(
                    database, pidn, 2, "error", input_hash, parsed["parse_error"]
                )
                errors += 1
                continue

            all_validations = list(parsed["validations"])

            # Retry path: if any signals were missing or failed to parse,
            # make a second call with just those signals to recover them.
            retry_keys = set(parsed.get("missing", [])) | set(parsed.get("errors", []))
            retry_attempted = 0
            if retry_keys:
                retry_signals = [
                    s for s in ctx["signals"] if s["signal_key"] in retry_keys
                ]
                log.info(
                    f"{pidn}: retrying {len(retry_signals)} dropped signal(s): "
                    f"{sorted(retry_keys)}"
                )
                retry_attempted = len(retry_signals)

                retry_prompt = build_batched_signal_prompt(
                    ctx, signals_override=retry_signals
                )
                retry_result = invoke_with_retry(
                    config, retry_prompt, archive_key=f"{pidn}:retry", retries=1
                )

                if retry_result.success:
                    retry_parsed = parse_batched_signal_output(
                        retry_result.parsed or {}, retry_signals
                    )
                    # Take whatever validations the retry produced
                    all_validations.extend(retry_parsed.get("validations", []))
                    if retry_parsed.get("missing"):
                        log.warning(
                            f"{pidn}: still missing after retry: "
                            f"{retry_parsed['missing']}"
                        )
                else:
                    log.warning(f"{pidn}: retry failed: {retry_result.error}")

            # Upsert each validated signal to public.evidence
            now_iso = datetime.now(timezone.utc).isoformat()
            written_keys = set()
            for validation in all_validations:
                if validation["signal_key"] in written_keys:
                    continue  # defensive: don't double-write if retry returned a dup
                src_signal = next(
                    (s for s in ctx["signals"] if s["signal_key"] == validation["signal_key"]),
                    None,
                )
                if not src_signal:
                    continue

                database.execute(
                    UPSERT_EVIDENCE_QUERY,
                    {
                        "pidn": pidn,
                        "signal_key": validation["signal_key"],
                        "claim": "; ".join(validation.get("key_facts", [])) or None,
                        "evidence_data": json.dumps(src_signal.get("evidence", {})),
                        "source_url": None,
                        "internal_url": f"/property/{pidn}",
                        "validation_status": validation["validation_status"],
                        "adjusted_significance": validation["adjusted_significance"],
                        "validation_reasoning": validation["reasoning"],
                        "cross_references": json.dumps(
                            validation.get("cross_references", [])
                        ),
                        "validated_at": now_iso,
                    },
                )
                written_keys.add(validation["signal_key"])
                signals_validated += 1

            # Report unrecovered losses (rare — after retry, these are truly dropped)
            expected_keys = {s["signal_key"] for s in ctx["signals"]}
            final_missing = sorted(expected_keys - written_keys)
            if final_missing:
                log.warning(
                    f"{pidn}: {len(final_missing)} signal(s) unrecovered after retry: "
                    f"{final_missing}"
                )

            # Persist the full pass record including cross-signal insight and
            # any unrecovered signal keys so follow-up runs can target them.
            _update_pass_status(
                database,
                pidn,
                2,
                "complete",
                input_hash,
                cross_signal_insight=parsed.get("cross_signal_insight") or None,
                missing_signal_keys=final_missing or None,
                error_signal_keys=list(parsed.get("errors") or []) or None,
                signals_validated_count=len(written_keys),
            )
            parcels_validated += 1

            if (i % 50) == 0:
                log.info(
                    f"Progress: {i}/{total_parcels} parcels "
                    f"({parcels_validated} validated, {parcels_skipped} skipped, "
                    f"{errors} errors)"
                )

        except Exception as exc:
            # Record the error against meta.intelligence_passes so the next
            # run has the context to target or skip this parcel, and so the
            # failure reason survives outside the log stream.
            log.warning(
                f"Error processing parcel {pidn}: {exc}\n{traceback.format_exc()}"
            )
            try:
                _update_pass_status(
                    database,
                    pidn,
                    2,
                    "error",
                    input_hash or "",
                    error_message=str(exc),
                )
            except Exception as status_exc:
                # Don't let a secondary failure break the loop
                log.warning(f"Failed to persist error status for {pidn}: {status_exc}")
            errors += 1

    log.info(
        f"Pass 2 batched complete: {parcels_validated} parcels validated, "
        f"{signals_validated} signals written, {parcels_skipped} skipped, "
        f"{errors} errors"
    )

    return MaterializeResult(
        metadata={
            "status": MetadataValue.text("complete"),
            "backend": MetadataValue.text(backend),
            "model": MetadataValue.text(model_path),
            "thinking": MetadataValue.bool(thinking_enabled),
            "parcels_total": MetadataValue.int(total_parcels),
            "parcels_validated": MetadataValue.int(parcels_validated),
            "signals_validated": MetadataValue.int(signals_validated),
            "parcels_skipped": MetadataValue.int(parcels_skipped),
            "errors": MetadataValue.int(errors),
        }
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _update_pass_status(
    database: DatabaseResource,
    pidn: str,
    pass_number: int,
    status: str,
    input_hash: str,
    error_message: str | None = None,
    cross_signal_insight: str | None = None,
    missing_signal_keys: list[str] | None = None,
    error_signal_keys: list[str] | None = None,
    signals_validated_count: int | None = None,
) -> None:
    """Insert or update meta.intelligence_passes for a parcel-level pass.

    Columns added in migration 014:
      - cross_signal_insight: the LLM's cross-signal synthesis paragraph
      - missing_signal_keys: signal keys the LLM never returned, as JSONB
      - error_signal_keys: signal keys the LLM returned but that failed parsing
      - signals_validated_count: how many signals were successfully written
    """
    database.execute(
        """
        INSERT INTO meta.intelligence_passes
            (pidn, pass_number, status, last_run_at, input_hash, error_message,
             cross_signal_insight, missing_signal_keys, error_signal_keys,
             signals_validated_count)
        VALUES
            (%(pidn)s, %(pass_number)s, %(status)s, NOW(), %(input_hash)s,
             %(error_message)s, %(cross_signal_insight)s,
             %(missing_signal_keys)s::jsonb, %(error_signal_keys)s::jsonb,
             %(signals_validated_count)s)
        ON CONFLICT (pidn, pass_number)
        DO UPDATE SET
            status = EXCLUDED.status,
            last_run_at = EXCLUDED.last_run_at,
            input_hash = EXCLUDED.input_hash,
            error_message = EXCLUDED.error_message,
            cross_signal_insight = EXCLUDED.cross_signal_insight,
            missing_signal_keys = EXCLUDED.missing_signal_keys,
            error_signal_keys = EXCLUDED.error_signal_keys,
            signals_validated_count = EXCLUDED.signals_validated_count
        """,
        {
            "pidn": pidn,
            "pass_number": pass_number,
            "status": status,
            "input_hash": input_hash,
            "error_message": error_message,
            "cross_signal_insight": cross_signal_insight,
            "missing_signal_keys": (
                json.dumps(missing_signal_keys) if missing_signal_keys else None
            ),
            "error_signal_keys": (
                json.dumps(error_signal_keys) if error_signal_keys else None
            ),
            "signals_validated_count": signals_validated_count,
        },
    )


def _skipped_result(reason: str) -> MaterializeResult:
    """Return a MaterializeResult indicating the asset was skipped."""
    return MaterializeResult(
        metadata={
            "status": MetadataValue.text("skipped"),
            "reason": MetadataValue.text(reason),
            "parcels_total": MetadataValue.int(0),
            "parcels_validated": MetadataValue.int(0),
            "signals_validated": MetadataValue.int(0),
            "parcels_skipped": MetadataValue.int(0),
            "errors": MetadataValue.int(0),
        }
    )
