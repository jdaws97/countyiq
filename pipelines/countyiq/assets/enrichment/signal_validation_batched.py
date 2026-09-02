"""Pass 2 (batched) — Dagster Asset.

Validates all development signals for each parcel in a single LLM call,
rather than one call per signal. Shares parcel context across signals and
lets the LLM reason about cross-signal patterns.

This is the production-recommended asset. The per-signal version
(signal_validation.py) is retained for A/B comparison.

The asset requires ``COUNTYIQ_PASS2_ENABLED=true``; model selection is independent.
"""
import hashlib
import json
import os
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime

from dagster import (
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
)

from countyiq.lib.error_budget import check_error_budget
from countyiq.lib.intelligence_autoresolve import auto_resolve_contradiction
from countyiq.lib.intelligence_common import (
    compute_input_hash,
    fetch_prior_pass_attempts,
    fetch_reusable_pass_hashes,
    pass_attempt_priority,
)
from countyiq.lib.intelligence_integrity import (
    inference_input_hash,
    pass2_semantic_decision,
    record_inference_decision,
    record_validation_rejection,
    validate_pass2_evidence_refs,
)
from countyiq.lib.pass2_batched_validation import (
    BATCHED_VALIDATION_SYSTEM_PROMPT,
    PROMPT_VERSION,
    build_batched_signal_prompt,
    gather_parcel_batch_context,
    merge_trial_validations,
    parse_batched_signal_output,
)
from countyiq.lib.pass_llm_config import (
    PassHarnessUnavailable,
    PassItemBudget,
    PassSpendLimitExceeded,
    resolve_pass_harness,
)
from countyiq.lib.pass_schemas import PASS2_BATCHED_VALIDATION_SCHEMA
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

_FULL_SCAN_BRANCH = """
        UNION

        -- Hash-based change detection is the correctness gate. This branch
        -- makes every signalled parcel a candidate so a model or prompt-version
        -- change reaches all of them. It is skipped when the stored
        -- model/prompt fingerprint matches the current one (fast path).
        SELECT DISTINCT ds.pidn
        FROM public.development_signals ds
"""

RETRACT_STALE_EVIDENCE_QUERY = """
    DELETE FROM public.evidence e
    WHERE NOT EXISTS (
        SELECT 1
        FROM public.development_signals ds
        WHERE ds.pidn = e.pidn
          AND ds.signal_key = e.signal_key
          AND ds.evidence IS NOT DISTINCT FROM e.evidence_data
    )
    RETURNING e.pidn, e.signal_key
"""

_CANDIDATE_QUERY_TEMPLATE = r"""
    -- Selects parcels eligible for validation. The Python source/model/prompt
    -- hash skips unchanged work; including every eligible parcel ensures a
    -- prompt or model change can trigger a deliberate new version.
    -- Fast-path candidates include parcels that need (re-)validation because:
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
                  WHERE LEFT(pe.extraction_type, 1) <> '_'
                    AND pp.valid_to IS NULL
                    AND pe.extracted_at > ip.last_run_at
                    AND (
                        REGEXP_REPLACE(pe.parcel_reference, '[^0-9]', '', 'g') = ip.pidn
                        OR EXISTS (
                            SELECT 1
                            FROM staging.parcels parcel
                            WHERE parcel.pidn = ip.pidn
                              AND parcel.valid_to IS NULL
                              AND parcel.propadr IS NOT NULL
                              AND public.normalize_street_address(parcel.propadr)
                                  = public.normalize_street_address(pe.parcel_reference)
                              AND EXISTS (
                                  SELECT 1
                                  FROM meta.municipality_source_rights msr
                                  WHERE msr.body_name = pp.body_name
                                    AND msr.municipality_name = parcel.municipality
                                    AND msr.derived_product_allowed = TRUE
                              )
                        )
                    )
              )
          )

        UNION

        -- Reason 3: a prior attempt errored. The fast path must still retry
        -- these even though evidence rows may exist from an earlier success.
        SELECT ip.pidn
        FROM meta.intelligence_passes ip
        WHERE ip.pass_number = 2 AND ip.status = 'error'
{full_scan_branch}
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
              'active_subdivision', 'municipal_action', 'ownership_change',
              'vacancy', 'assemblage', 'entity_assemblage', 'zoning_mismatch'
          )
    )
    ORDER BY pidn
"""

PARCELS_NEEDING_VALIDATION_QUERY = _CANDIDATE_QUERY_TEMPLATE.replace(
    "{full_scan_branch}", _FULL_SCAN_BRANCH
)
PARCELS_NEEDING_VALIDATION_FAST_QUERY = _CANDIDATE_QUERY_TEMPLATE.replace(
    "{full_scan_branch}", ""
)

FINGERPRINT_SELECT = """
    SELECT fingerprint FROM meta.pass_config_fingerprints WHERE pass_number = %(pass_number)s
"""
FINGERPRINT_UPSERT = """
    INSERT INTO meta.pass_config_fingerprints (pass_number, fingerprint, updated_at)
    VALUES (%(pass_number)s, %(fingerprint)s, NOW())
    ON CONFLICT (pass_number)
    DO UPDATE SET fingerprint = EXCLUDED.fingerprint, updated_at = EXCLUDED.updated_at
"""


def pass2_config_fingerprint(model_path: str, n_trials: int) -> str:
    """Stable fingerprint of everything that changes a Pass 2 input hash besides data."""
    return hashlib.sha256(
        f"{model_path}|trials={n_trials}|{PROMPT_VERSION}".encode()
    ).hexdigest()[:16]


def resolve_pass2_concurrency() -> int:
    """How many provider calls may be in flight at once (COUNTYIQ_PASS2_CONCURRENCY).

    Database work stays on the single resource connection; only the HTTP
    round trips overlap. Defaults to 4, which cut a sequential ~10 s/parcel
    loop several-fold without changing spend.
    """
    raw = os.environ.get("COUNTYIQ_PASS2_CONCURRENCY", "4")
    try:
        return max(1, min(int(raw), 16))
    except ValueError:
        return 4


@dataclass
class _WorkItem:
    pidn: str
    ctx: dict
    source_hash: str
    input_hash: str
    prompt: str
    n_trials: int
    futures: dict[int, Future] = field(default_factory=dict)


UPSERT_EVIDENCE_QUERY = """
    INSERT INTO public.evidence
        (pidn, signal_key, claim, evidence_data, source_url, internal_url,
         validation_status, adjusted_significance, validation_reasoning,
         cross_references, validated_at,
         model_version, prompt_version, n_trials, trial_agreement, confidence,
         active_inference_id)
    VALUES
        (%(pidn)s, %(signal_key)s, %(claim)s, %(evidence_data)s::jsonb,
         %(source_url)s, %(internal_url)s,
         %(validation_status)s, %(adjusted_significance)s,
         %(validation_reasoning)s, %(cross_references)s::jsonb,
         %(validated_at)s,
         %(model_version)s, %(prompt_version)s,
         %(n_trials)s, %(trial_agreement)s, %(confidence)s,
         %(active_inference_id)s)
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
        confidence = EXCLUDED.confidence,
        active_inference_id = EXCLUDED.active_inference_id
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

    # development_signals is a full replacement snapshot. Retract evidence
    # whose source signal disappeared or changed before deciding whether any
    # paid validation work is eligible; immutable inference history remains.
    evidence_retracted = _retract_stale_evidence(database)
    if evidence_retracted:
        log.info(
            "Retracted %d stale evidence row(s) before Pass 2 selection",
            evidence_retracted,
        )

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
        return _skipped_result(exc.reason, evidence_retracted=evidence_retracted)
    item_budget = PassItemBudget(2)

    # ------------------------------------------------------------------
    # Find parcels with unvalidated signals
    # ------------------------------------------------------------------
    n_trials = max(1, int(os.environ.get("COUNTYIQ_PASS2_TRIALS", "1")))
    fingerprint = pass2_config_fingerprint(config.model_path, n_trials)
    stored_rows = database.execute(FINGERPRINT_SELECT, {"pass_number": 2}) or []
    stored_fingerprint = _row_value(stored_rows[0], "fingerprint") if stored_rows else None
    fast_path = stored_fingerprint == fingerprint
    log.info(
        "Finding parcels with unvalidated signals (%s)",
        "fast path: model/prompt fingerprint unchanged"
        if fast_path
        else "full scan: model/prompt fingerprint changed or never recorded",
    )
    rows = database.execute(
        PARCELS_NEEDING_VALIDATION_FAST_QUERY if fast_path else PARCELS_NEEDING_VALIDATION_QUERY
    )
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
                "evidence_retracted": MetadataValue.int(evidence_retracted),
                "parcels_skipped": MetadataValue.int(0),
                "errors": MetadataValue.int(0),
            }
        )

    log.info(f"Found {total_parcels} parcels with unvalidated signals")

    # One upfront fetch of prior input hashes replaces a per-parcel SELECT
    # inside the loop (thousands of round trips on a full run).
    prior_hashes = fetch_reusable_pass_hashes(database, pass_number=2)
    prior_attempts = fetch_prior_pass_attempts(database, pass_number=2)
    pidns.sort(key=lambda pidn: pass_attempt_priority(pidn, prior_attempts))

    parcels_validated = 0
    signals_validated = 0
    parcels_skipped = 0
    errors = 0
    spend_limit_reached = False

    # ------------------------------------------------------------------
    # Phase A (sequential, single DB connection): gather context, hash,
    # skip unchanged work, claim the item budget, build the prompt.
    # ------------------------------------------------------------------
    work_items: list[_WorkItem] = []
    gather_errors = 0
    item_cap_hit = False
    for pidn in pidns:
        try:
            # Gather all context + signals for this parcel using the public
            # dict_cursor context manager (no private _get_conn() access).
            # The DatabaseResource connection runs in autocommit mode, so
            # transaction boundaries are per-statement — the cursor is purely
            # for dict-row access.
            with database.dict_cursor() as cur:
                ctx = gather_parcel_batch_context(cur, pidn)
        except Exception as exc:
            log.warning(f"Error gathering context for {pidn}: {exc}")
            try:
                _update_pass_status(database, pidn, 2, "error", "", error_message=str(exc))
            except Exception as status_exc:
                log.warning(f"Failed to persist error status for {pidn}: {status_exc}")
            gather_errors += 1
            continue

        if not ctx["signals"]:
            continue

        source_hash = compute_input_hash(ctx)
        input_hash = inference_input_hash(
            source_hash,
            requested_model=f"{config.model_path}|trials={n_trials}",
            prompt_version=PROMPT_VERSION,
        )

        # Check if already processed with same hash
        if prior_hashes.get(pidn) == input_hash:
            parcels_skipped += 1
            continue

        if not item_budget.claim(log, label="changed parcels"):
            item_cap_hit = True
            break

        # Build prompt and invoke LLM N times (N=1 by default for
        # backward compat; N>1 enables trial voting — see experiment A
        # in the evaluation summarized by docs/decisions.md). Temperature=0 is not
        # deterministic across trials on shared APIs, so agreement
        # across N trials becomes the persisted confidence score.
        work_items.append(
            _WorkItem(
                pidn=pidn,
                ctx=ctx,
                source_hash=source_hash,
                input_hash=input_hash,
                prompt=build_batched_signal_prompt(ctx),
                n_trials=n_trials,
            )
        )
    errors += gather_errors

    # ------------------------------------------------------------------
    # Phase B/C: dispatch provider calls for a window of parcels at once,
    # then parse, validate, gate, and persist each result on the main
    # thread in order. Only HTTP round trips overlap; the spend ledger is
    # lock-protected and the database sees one caller.
    # ------------------------------------------------------------------
    concurrency = resolve_pass2_concurrency()
    executor = ThreadPoolExecutor(max_workers=concurrency) if concurrency > 1 else None

    def _dispatch(item: _WorkItem) -> None:
        if executor is None:
            return
        for trial_idx in range(item.n_trials):
            archive_key = item.pidn if item.n_trials == 1 else f"{item.pidn}:trial-{trial_idx}"
            item.futures[trial_idx] = executor.submit(
                invoke_with_retry, config, item.prompt, archive_key=archive_key, retries=1
            )

    def _trial_result(item: _WorkItem, trial_idx: int):
        future = item.futures.pop(trial_idx, None)
        if future is not None:
            return future.result()
        archive_key = item.pidn if item.n_trials == 1 else f"{item.pidn}:trial-{trial_idx}"
        return invoke_with_retry(config, item.prompt, archive_key=archive_key, retries=1)

    dispatched_upto = 0
    try:
      for i, item in enumerate(work_items, 1):
        if spend_limit_reached:
            break
        # Keep `concurrency` parcels in flight ahead of the consumer.
        while dispatched_upto < len(work_items) and dispatched_upto < i - 1 + concurrency:
            _dispatch(work_items[dispatched_upto])
            dispatched_upto += 1

        pidn = item.pidn
        ctx = item.ctx
        source_hash = item.source_hash
        input_hash: str | None = item.input_hash
        n_trials = item.n_trials
        try:
            trial_parses: list[dict] = []
            trial_result = None
            last_success_result = None
            for trial_idx in range(n_trials):
                trial_result = _trial_result(item, trial_idx)
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
                last_success_result = trial_result

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
                    last_success_result = retry_result
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

            validation_errors = validate_pass2_evidence_refs(
                all_validations,
                ctx["signals"],
                ctx.get("context_signals", []),
                parsed.get("cross_signal_insight") or None,
            )
            if validation_errors:
                record_validation_rejection(
                    database,
                    subject_key=pidn,
                    pass_number=2,
                    output_kind="signal_validation",
                    source_hash=source_hash,
                    input_hash=input_hash,
                    requested_model=config.model_path,
                    prompt_version=PROMPT_VERSION,
                    errors=validation_errors,
                )
                message = "; ".join(validation_errors)
                log.warning("%s failed evidence-reference validation: %s", pidn, message)
                _update_pass_status(
                    database, pidn, 2, "error", input_hash, message,
                )
                errors += 1
                continue

            evidence_refs = sorted({
                ref
                for validation in all_validations
                for ref in validation.get("cross_references", [])
            })
            history_payload = {
                "validations": all_validations,
                "cross_signal_insight": parsed.get("cross_signal_insight") or "",
            }
            gate = record_inference_decision(
                database,
                subject_key=pidn,
                pass_number=2,
                output_kind="signal_validation",
                decision_key="signal_batch",
                source_hash=source_hash,
                input_hash=input_hash,
                requested_model=config.model_path,
                served_model=(
                    last_success_result.metadata.get("served_model")
                    if last_success_result else None
                ),
                provider=(
                    last_success_result.metadata.get("provider")
                    if last_success_result else None
                ),
                prompt_version=PROMPT_VERSION,
                payload=history_payload,
                semantic_decision=pass2_semantic_decision(all_validations),
                evidence_refs=evidence_refs,
            )
            if not gate.accepted:
                auto = auto_resolve_contradiction(database, gate.contradiction_id, log)
                if auto.resolved:
                    log.info(
                        "Contradiction %s auto-resolved (%s): %s",
                        gate.contradiction_id, auto.resolution, auto.rationale,
                    )
                    continue
                message = (
                    f"quarantined as contradiction {gate.contradiction_id}: "
                    f"{gate.reason}"
                )
                log.warning("%s %s", pidn, message)
                _update_pass_status(
                    database, pidn, 2, "error", input_hash, message,
                )
                errors += 1
                continue

            # Upsert each gated validation to the active evidence projection.
            now_iso = datetime.now(UTC).isoformat()
            written_keys = set()
            source_by_key = {
                signal["signal_key"]: signal for signal in ctx["signals"]
            }
            with database.transaction() as cur:
                current_keys = [
                    validation["signal_key"] for validation in all_validations
                ]
                cur.execute(
                    """
                    DELETE FROM public.evidence
                    WHERE pidn = %s
                      AND NOT (signal_key = ANY(%s::text[]))
                    """,
                    (pidn, current_keys),
                )
                for validation in all_validations:
                    signal_key = validation["signal_key"]
                    if signal_key in written_keys:
                        continue
                    src_signal = source_by_key[signal_key]
                    cur.execute(
                        UPSERT_EVIDENCE_QUERY,
                        {
                            "pidn": pidn,
                            "signal_key": signal_key,
                            "claim": (
                                f"{signal_key} classified "
                                f"{validation['validation_status']} with "
                                f"{validation['adjusted_significance']} significance"
                            ),
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
                            "active_inference_id": gate.inference_id,
                        },
                    )
                    written_keys.add(signal_key)
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

        except PassSpendLimitExceeded as exc:
            spend_limit_reached = True
            log.info(
                "Pass 2 dollar ceiling reached; remaining parcels are deferred: %s",
                exc,
            )
            break
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

    finally:
        if executor is not None:
            # Do not wait on futures that were dispatched but never consumed
            # after a spend stop; cancel them so no further money is spent.
            for pending in work_items[max(i - 1, 0):] if work_items else []:
                for future in pending.futures.values():
                    future.cancel()
            executor.shutdown(wait=True, cancel_futures=True)

    if not spend_limit_reached and not item_cap_hit:
        # Every candidate was visited under this model/prompt, so the next run
        # can trust the timestamp fast path.
        database.execute(
            FINGERPRINT_UPSERT, {"pass_number": 2, "fingerprint": fingerprint}
        )
    log.info(
        f"Pass 2 batched complete: {parcels_validated} parcels validated, "
        f"{signals_validated} signals written, {parcels_skipped} skipped, "
        f"{errors} errors (concurrency={concurrency}, fast_path={fast_path})"
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
            "evidence_retracted": MetadataValue.int(evidence_retracted),
            "parcels_skipped": MetadataValue.int(parcels_skipped),
            "budget_mode": MetadataValue.text(item_budget.mode),
            "item_limit": (
                MetadataValue.int(item_budget.limit)
                if item_budget.limit is not None
                else MetadataValue.text("cost-only")
            ),
            "items_claimed": MetadataValue.int(item_budget.claimed),
            "spend_limit_reached": MetadataValue.bool(spend_limit_reached),
            "concurrency": MetadataValue.int(concurrency),
            "fast_path": MetadataValue.bool(fast_path),
            "errors": MetadataValue.int(errors),
        }
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _retract_stale_evidence(database: DatabaseResource) -> int:
    rows = database.execute(RETRACT_STALE_EVIDENCE_QUERY) or []
    return len(rows)


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


def _skipped_result(reason: str, *, evidence_retracted: int = 0) -> MaterializeResult:
    """Return a MaterializeResult indicating the asset was skipped."""
    return MaterializeResult(
        metadata={
            "status": MetadataValue.text("skipped"),
            "reason": MetadataValue.text(reason),
            "parcels_total": MetadataValue.int(0),
            "parcels_validated": MetadataValue.int(0),
            "signals_validated": MetadataValue.int(0),
            "evidence_retracted": MetadataValue.int(evidence_retracted),
            "parcels_skipped": MetadataValue.int(0),
            "errors": MetadataValue.int(0),
        }
    )
