"""Pass 2 (batched) — Dagster Asset.

Validates all development signals for each parcel in a single LLM call,
rather than one call per signal. Shares parcel context across signals and
lets the LLM reason about cross-signal patterns.

This is the production-recommended asset. The per-signal version
(signal_validation.py) is retained for A/B comparison.

The asset requires ``COUNTYIQ_PASS2_ENABLED=true``; model selection is independent.
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

from countyiq.lib.intelligence_common import (
    compute_input_hash,
    fetch_prior_pass_hashes,
)
from countyiq.lib.error_budget import check_error_budget
from countyiq.lib.pass_llm_config import (
    PassItemBudget,
    PassHarnessUnavailable,
    resolve_pass_harness,
)
from countyiq.lib.pass_schemas import PASS2_BATCHED_VALIDATION_SCHEMA
from countyiq.lib.pass2_batched_validation import (
    BATCHED_VALIDATION_SYSTEM_PROMPT,
    PROMPT_VERSION,
    build_batched_signal_prompt,
    gather_parcel_batch_context,
    merge_trial_validations,
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

PARCELS_NEEDING_VALIDATION_QUERY = r"""
    -- Selects parcels that need (re-)validation for any of these reasons:
    --   1. Has at least one signal with no corresponding evidence row (new signal)
    --   2. Upstream context changed since last validation (tax claims, entity
    --      graph, parcels, or proceedings updated more recently than the pass record)
    --
    -- Selection gate: also requires either a high-alpha signal or a
    -- plausibly-real active_subdivision (prop_du > 0, pt_land_dev = 'YES').
    -- Parcels with only context signals (growth area, overlays, traffic and
    -- physical constraints) or penndot_project alone are skipped — prior
    -- 0% actionable validations. See the hybrid-LLM decision in docs/decisions.md.
    --
    -- Data-hygiene gate: degenerate parcels (no acres, no value, no owner)
    -- produce "correct but worthless" briefs so we drop them upstream.

    WITH candidates AS (
        -- Reason 1: new/unmatched signal
        SELECT DISTINCT ds.pidn
        FROM public.development_signals ds
        WHERE NOT EXISTS (
            SELECT 1 FROM public.evidence e
            WHERE e.pidn = ds.pidn AND e.signal_key = ds.signal_key
        )

        UNION

        -- Reason 2: upstream data changed since last validation
        SELECT DISTINCT ip.pidn
        FROM meta.intelligence_passes ip
        WHERE ip.pass_number = 2 AND ip.status = 'complete'
          AND (
              -- Tax claims changed
              EXISTS (
                  SELECT 1 FROM staging.tax_claims tc
                  WHERE tc.pidn = ip.pidn AND tc.valid_from > ip.last_run_at
              )
              -- Parcel record changed (sale, owner, assessment)
              OR EXISTS (
                  SELECT 1 FROM staging.parcels p
                  WHERE p.pidn = ip.pidn AND p.valid_from > ip.last_run_at
              )
              -- Entity graph updated
              OR EXISTS (
                  SELECT 1 FROM public.entity_graph eg
                  WHERE eg.verified_at > ip.last_run_at
                    AND (
                        eg.canonical_name IN (
                            SELECT owner_full FROM staging.parcels
                            WHERE pidn = ip.pidn AND valid_to IS NULL
                        )
                        OR EXISTS (
                            SELECT 1 FROM staging.parcels sp
                            WHERE sp.pidn = ip.pidn AND sp.valid_to IS NULL
                              AND sp.owner_full = ANY(eg.linked_names)
                        )
                    )
              )
              -- Subdivision plan near this parcel changed. active_subdivision
              -- signals link by proximity (not PIDN), so a plan update or
              -- withdrawal would otherwise keep multiplying old evidence into
              -- the momentum score forever. Radius matches development_signals.
              OR EXISTS (
                  SELECT 1
                  FROM staging.planning_subdivisions s
                  JOIN staging.parcels pp
                      ON pp.pidn = ip.pidn AND pp.valid_to IS NULL
                  WHERE s.valid_from > ip.last_run_at
                    AND ST_DWithin(
                        ST_Centroid(pp.geom)::geography, s.geom::geography, 250)
              )
              -- New proceeding extractions mentioning this parcel (by PIDN or address).
              -- Use extraction timestamp, not public_proceedings.valid_from, so
              -- backfilled or retried extractions on older meeting records still
              -- trigger revalidation.
              OR EXISTS (
                  SELECT 1 FROM staging.proceeding_extractions pe
                  JOIN staging.public_proceedings pp ON pp.id = pe.proceeding_id
                  WHERE pe.extraction_type NOT IN ('_complete', '_no_extractions')
                    AND pp.valid_to IS NULL
                    AND pe.extracted_at > ip.last_run_at
                    AND (
                        pe.parcel_reference = ip.pidn
                        OR pe.parcel_reference IN (
                            SELECT propadr FROM staging.parcels
                            WHERE pidn = ip.pidn AND valid_to IS NULL AND propadr IS NOT NULL
                        )
                    )
              )
          )
    )
    -- LLM gate: Pass 2 exists for cross-signal ambiguity, not for validating
    -- deterministic GIS or public-record facts. A parcel needs at least two
    -- genuinely interpretive signals before it can consume a model call.
    SELECT pidn
    FROM candidates c
    WHERE 2 <= (
        SELECT COUNT(*) FROM public.development_signals ds
        WHERE ds.pidn = c.pidn
          AND ds.signal_key IN (
              'active_subdivision', 'ownership_change', 'vacancy',
              'assemblage', 'zoning_mismatch'
          )
    )
    ORDER BY pidn
"""

UPSERT_EVIDENCE_QUERY = """
    INSERT INTO public.evidence
        (pidn, signal_key, claim, evidence_data, source_url, internal_url,
         validation_status, adjusted_significance, validation_reasoning,
         cross_references, validated_at,
         model_version, prompt_version, n_trials, trial_agreement, confidence)
    VALUES
        (%(pidn)s, %(signal_key)s, %(claim)s, %(evidence_data)s::jsonb,
         %(source_url)s, %(internal_url)s,
         %(validation_status)s, %(adjusted_significance)s,
         %(validation_reasoning)s, %(cross_references)s::jsonb,
         %(validated_at)s,
         %(model_version)s, %(prompt_version)s,
         %(n_trials)s, %(trial_agreement)s, %(confidence)s)
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
        validated_at = EXCLUDED.validated_at,
        model_version = EXCLUDED.model_version,
        prompt_version = EXCLUDED.prompt_version,
        n_trials = EXCLUDED.n_trials,
        trial_agreement = EXCLUDED.trial_agreement,
        confidence = EXCLUDED.confidence
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

    try:
        config, invoke_with_retry = resolve_pass_harness(
            log,
            pass_number=2,
            archive_label="pass2_batched",
            json_schema=PASS2_BATCHED_VALIDATION_SCHEMA,
            schema_name="pass2_validations",
            default_max_tokens=4096,
            default_thinking=True,
            # Static block goes out as a byte-identical system message so
            # providers with implicit prompt caching can reuse it per parcel.
            system_prompt=BATCHED_VALIDATION_SYSTEM_PROMPT,
        )
    except PassHarnessUnavailable as exc:
        return _skipped_result(exc.reason)
    item_budget = PassItemBudget(2)

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

    # One upfront fetch of prior input hashes replaces a per-parcel SELECT
    # inside the loop (thousands of round trips on a full run).
    prior_hashes = fetch_prior_pass_hashes(database, pass_number=2)

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
            if prior_hashes.get(pidn) == input_hash:
                parcels_skipped += 1
                continue

            if not item_budget.claim(log, label="changed parcels"):
                break

            # Build prompt and invoke LLM N times (N=1 by default for
            # backward compat; N>1 enables trial voting — see experiment A
            # in the evaluation summarized by docs/decisions.md). Temperature=0 is not
            # deterministic across trials on shared APIs, so agreement
            # across N trials becomes the persisted confidence score.
            n_trials = max(1, int(os.environ.get("COUNTYIQ_PASS2_TRIALS", "1")))
            prompt = build_batched_signal_prompt(ctx)

            trial_parses: list[dict] = []
            trial_result = None
            for trial_idx in range(n_trials):
                archive_key = pidn if n_trials == 1 else f"{pidn}:trial-{trial_idx}"
                trial_result = invoke_with_retry(
                    config, prompt, archive_key=archive_key, retries=1
                )
                if not trial_result.success:
                    log.warning(
                        f"LLM failed for {pidn} (trial {trial_idx + 1}/{n_trials}): "
                        f"{trial_result.error}"
                    )
                    continue
                tp = parse_batched_signal_output(trial_result.parsed or {}, ctx["signals"])
                if tp.get("parse_error"):
                    log.warning(
                        f"Parse error on {pidn} trial {trial_idx + 1}/{n_trials}: "
                        f"{tp['parse_error']}"
                    )
                    continue
                trial_parses.append(tp)

            if not trial_parses:
                # All N trials failed — escalate as a parcel-level error.
                err_msg = trial_result.error if trial_result else "all trials failed"
                _update_pass_status(database, pidn, 2, "error", input_hash, err_msg)
                errors += 1
                continue

            # Merge trials into single set with trial_agreement + confidence.
            if n_trials == 1:
                # Single-trial mode: preserve legacy shape, annotate metadata.
                parsed = trial_parses[0]
                for v in parsed.get("validations", []):
                    v.setdefault("n_trials", 1)
                    v.setdefault("trial_agreement", 1.0)
                    v.setdefault("confidence", None)
            else:
                parsed = merge_trial_validations(trial_parses, ctx["signals"])

            all_validations = list(parsed["validations"])
            unresolved_error_keys = set(parsed.get("errors") or [])

            # Retry path: if any signals were missing or failed to parse,
            # make a second call with just those signals to recover them.
            retry_keys = set(parsed.get("missing", [])) | set(parsed.get("errors", []))
            if retry_keys:
                retry_signals = [
                    s for s in ctx["signals"] if s["signal_key"] in retry_keys
                ]
                log.info(
                    f"{pidn}: retrying {len(retry_signals)} dropped signal(s): "
                    f"{sorted(retry_keys)}"
                )

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
                    recovered_retry_keys = {
                        v["signal_key"] for v in retry_parsed.get("validations", [])
                    }
                    unresolved_error_keys = (
                        (unresolved_error_keys - retry_keys)
                        | set(retry_parsed.get("errors", []))
                    ) - recovered_retry_keys
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
                        "model_version": config.model_path,
                        "prompt_version": PROMPT_VERSION,
                        "n_trials": validation.get("n_trials"),
                        "trial_agreement": validation.get("trial_agreement"),
                        "confidence": validation.get("confidence"),
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
                error_signal_keys=sorted(unresolved_error_keys) or None,
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
    check_error_budget(
        log, label="pass2_signal_validation",
        errors=errors, total=parcels_validated + errors,
    )

    return MaterializeResult(
        metadata={
            "status": MetadataValue.text("complete"),
            "model": MetadataValue.text(config.model_path),
            "thinking": MetadataValue.bool(config.thinking),
            "parcels_total": MetadataValue.int(total_parcels),
            "parcels_validated": MetadataValue.int(parcels_validated),
            "signals_validated": MetadataValue.int(signals_validated),
            "parcels_skipped": MetadataValue.int(parcels_skipped),
            "item_limit": MetadataValue.int(item_budget.limit),
            "items_claimed": MetadataValue.int(item_budget.claimed),
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
