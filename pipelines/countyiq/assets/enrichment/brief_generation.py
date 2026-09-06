"""Generate parcel briefs from validated signals."""

import json
import os
from dataclasses import replace
from datetime import UTC, datetime

from dagster import (
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
)

from countyiq.lib.error_budget import check_error_budget
from countyiq.lib.intelligence_common import (
    compute_input_hash,
    fetch_prior_pass_attempts,
    fetch_prior_pass_hashes,
    pass_attempt_priority,
)
from countyiq.lib.intelligence_autoresolve import auto_resolve_contradiction
from countyiq.lib.intelligence_integrity import (
    inference_input_hash,
    parcel_brief_semantic_decision,
    record_inference_decision,
    signal_version_refs,
    record_validation_rejection,
    validate_parcel_brief_citations,
)
from countyiq.lib.pass3_brief_generation import (
    BRIEF_GENERATION_SYSTEM_PROMPT,
    PROMPT_VERSION,
    build_brief_generation_prompt,
    gather_brief_context,
    parse_brief_output,
    should_generate_brief,
)
from countyiq.lib.pass_llm_config import (
    PassHarnessUnavailable,
    PassItemBudget,
    PassSpendLimitExceeded,
    resolve_pass_harness,
)
from countyiq.lib.pass_schemas import PASS3_BRIEF_SCHEMA
from countyiq.lib.signal_policy import INTERPRETIVE_SIGNAL_KEYS_SQL
from countyiq.resources.database import DatabaseResource

PARCELS_NEEDING_BRIEFS_QUERY = f"""
    -- Rank-gated selection. A brief is worth paying for when a user is likely
    -- to open the parcel, which the deterministic radar rank predicts far
    -- better than the model's own significance label did. Candidates are the
    -- top-N eligible parcels by the better of opportunity and momentum that
    -- also carry Pass 2 evidence; the Python source/model/prompt hash still
    -- skips unchanged work within that set.
    WITH ranked AS (
        SELECT dm.pidn
        FROM public.development_momentum dm
        WHERE dm.eligible = TRUE
        ORDER BY GREATEST(dm.opportunity_score, dm.score) DESC, dm.signal_count DESC, dm.pidn
        LIMIT %(rank_limit)s
    )
    SELECT DISTINCT e.pidn
    FROM public.evidence e
    JOIN ranked r ON r.pidn = e.pidn
    WHERE e.validation_status IN ('confirmed', 'upgraded', 'downgraded')
      AND e.signal_key IN ({INTERPRETIVE_SIGNAL_KEYS_SQL})
      AND e.adjusted_significance IN ('high', 'medium')
    ORDER BY e.pidn
"""

RETRACT_UNSERVABLE_BRIEFS_QUERY = f"""
    WITH ranked AS (
        SELECT dm.pidn
        FROM public.development_momentum dm
        WHERE dm.eligible = TRUE
        ORDER BY GREATEST(dm.opportunity_score, dm.score) DESC,
                 dm.signal_count DESC,
                 dm.pidn
        LIMIT %(rank_limit)s
    )
    DELETE FROM public.parcel_briefs pb
    WHERE NOT EXISTS (
        SELECT 1 FROM ranked r WHERE r.pidn = pb.pidn
    )
       OR NOT EXISTS (
        SELECT 1
        FROM public.evidence e
        WHERE e.pidn = pb.pidn
          AND e.signal_key IN ({INTERPRETIVE_SIGNAL_KEYS_SQL})
          AND e.validation_status IN ('confirmed', 'upgraded', 'downgraded')
          AND e.adjusted_significance IN ('high', 'medium')
    )
    RETURNING pb.pidn
"""


def resolve_brief_rank_limit() -> int:
    """How many top-ranked radar parcels are eligible for a cached brief."""
    raw = os.environ.get("COUNTYIQ_PASS3_RANK_LIMIT", "500")
    try:
        return max(1, int(raw))
    except ValueError:
        return 500


def _retract_unservable_briefs(database: DatabaseResource, *, rank_limit: int) -> int:
    rows = (
        database.execute(
            RETRACT_UNSERVABLE_BRIEFS_QUERY,
            {"rank_limit": rank_limit},
        )
        or []
    )
    return len(rows)


UPSERT_BRIEF_QUERY = """
    INSERT INTO public.parcel_briefs
        (pidn, brief_text, assessment, assessment_reasoning,
         key_questions, signal_count, citations, brief_version,
         pass_metadata, generated_at,
         model_version, prompt_version, n_trials, trial_agreement, confidence,
         active_inference_id)
    VALUES
        (%(pidn)s, %(brief_text)s, %(assessment)s, %(assessment_reasoning)s,
         %(key_questions)s::text[], %(signal_count)s, %(citations)s::jsonb, 1,
         %(pass_metadata)s::jsonb, %(generated_at)s,
         %(model_version)s, %(prompt_version)s,
         %(n_trials)s, %(trial_agreement)s, %(confidence)s,
         %(active_inference_id)s)
    ON CONFLICT (pidn)
    DO UPDATE SET
        brief_text = EXCLUDED.brief_text,
        assessment = EXCLUDED.assessment,
        assessment_reasoning = EXCLUDED.assessment_reasoning,
        key_questions = EXCLUDED.key_questions,
        signal_count = EXCLUDED.signal_count,
        citations = EXCLUDED.citations,
        brief_version = public.parcel_briefs.brief_version + 1,
        pass_metadata = EXCLUDED.pass_metadata,
        generated_at = EXCLUDED.generated_at,
        model_version = EXCLUDED.model_version,
        prompt_version = EXCLUDED.prompt_version,
        n_trials = EXCLUDED.n_trials,
        trial_agreement = EXCLUDED.trial_agreement,
        confidence = EXCLUDED.confidence,
        active_inference_id = EXCLUDED.active_inference_id
"""


@asset(
    group_name="enrichment",
    description=(
        "Pass 3: synthesize validated signals into intelligence briefs "
        "for parcels with medium or high significance signals"
    ),
    deps=["signal_validation_batched"],
    kinds={"postgres", "llm"},
)
def brief_generation(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> MaterializeResult:
    log = context.log
    rank_limit = resolve_brief_rank_limit()
    briefs_retracted = _retract_unservable_briefs(database, rank_limit=rank_limit)
    if briefs_retracted:
        log.info(
            "Retracted %d parcel brief(s) outside the current serving set",
            briefs_retracted,
        )

    try:
        config, invoke_with_retry = resolve_pass_harness(
            log,
            pass_number=3,
            archive_label="pass3_briefs",
            default_max_tokens=2048,
            json_schema=PASS3_BRIEF_SCHEMA,
            schema_name="pass3_brief",
            # Static block goes out as a byte-identical system message so
            # providers with implicit prompt caching can reuse it per parcel.
            system_prompt=BRIEF_GENERATION_SYSTEM_PROMPT,
        )
    except PassHarnessUnavailable as exc:
        return _skipped_result(exc.reason, briefs_retracted=briefs_retracted)
    item_budget = PassItemBudget(3)
    config = replace(config, temperature=min(config.temperature, 0.3))

    log.info("Querying parcels eligible for brief generation")
    rows = database.execute(PARCELS_NEEDING_BRIEFS_QUERY, {"rank_limit": rank_limit})

    if not rows:
        log.info("No parcels eligible for brief generation.")
        return MaterializeResult(
            metadata={
                "status": MetadataValue.text("complete"),
                "parcels_eligible": MetadataValue.int(0),
                "briefs_created": MetadataValue.int(0),
                "briefs_retracted": MetadataValue.int(briefs_retracted),
                "skipped": MetadataValue.int(0),
                "errors": MetadataValue.int(0),
            }
        )

    parcels_eligible = len(rows)
    briefs_created = 0
    skipped = 0
    errors = 0
    spend_limit_reached = False

    log.info("Found %d parcels eligible for briefs", parcels_eligible)

    # One upfront fetch of prior input hashes replaces a per-parcel SELECT
    # inside the loop.
    prior_hashes = fetch_prior_pass_hashes(database, pass_number=3)
    prior_attempts = fetch_prior_pass_attempts(database, pass_number=3)
    current_brief_rows = database.execute("SELECT pidn FROM public.parcel_briefs") or []
    current_brief_pidns = {
        (row.get("pidn") if isinstance(row, dict) else row[0])
        for row in current_brief_rows
    }
    rows = sorted(
        rows,
        key=lambda row: pass_attempt_priority(
            row[0] if isinstance(row, (tuple, list)) else row.get("pidn", row),
            prior_attempts,
        ),
    )

    for row in rows:
        pidn = row[0] if isinstance(row, (tuple, list)) else row.get("pidn", row)
        input_hash: str | None = None

        try:
            with database.read_snapshot() as cur:
                ctx = gather_brief_context(cur, pidn)

            validated_signals = ctx.get("validated_signals", [])
            if not should_generate_brief(validated_signals):
                log.debug(
                    "Parcel %s has no medium+ signals after context gather, skipping",
                    pidn,
                )
                skipped += 1
                continue

            signal_dependencies = signal_version_refs(validated_signals, pidn=pidn)
            source_hash = compute_input_hash(ctx)
            input_hash = inference_input_hash(
                source_hash,
                requested_model=config.model_path,
                prompt_version=PROMPT_VERSION,
            )

            if pidn in current_brief_pidns and prior_hashes.get(pidn) == input_hash:
                log.debug(
                    "Parcel %s context unchanged, skipping brief generation", pidn
                )
                skipped += 1
                continue

            if not item_budget.claim(log, label="changed parcel briefs"):
                break

            prompt = build_brief_generation_prompt(ctx)
            result = invoke_with_retry(config, prompt, retries=1, archive_key=pidn)

            if not result.success:
                log.warning(
                    "LLM failed for brief on %s: %s",
                    pidn,
                    result.error,
                )
                _update_pass_status(
                    database,
                    pidn,
                    3,
                    "error",
                    input_hash,
                    result.error,
                )
                errors += 1
                continue

            parsed = parse_brief_output(result.parsed or {})
            if "error" in parsed:
                log.warning(
                    "Invalid LLM brief output for %s: %s",
                    pidn,
                    parsed["error"],
                )
                _update_pass_status(
                    database,
                    pidn,
                    3,
                    "error",
                    input_hash,
                    parsed["error"],
                )
                errors += 1
                continue

            allowed_signal_keys = {
                signal["signal_key"]
                for signal in validated_signals
                if signal.get("signal_key")
            }
            citation_errors = validate_parcel_brief_citations(
                parsed,
                allowed_signal_keys,
            )
            if citation_errors:
                record_validation_rejection(
                    database,
                    subject_key=pidn,
                    pass_number=3,
                    output_kind="parcel_brief",
                    source_hash=source_hash,
                    input_hash=input_hash,
                    requested_model=config.model_path,
                    prompt_version=PROMPT_VERSION,
                    errors=citation_errors,
                )
                message = "; ".join(citation_errors)
                log.warning(
                    "Brief for %s failed citation validation: %s", pidn, message
                )
                _update_pass_status(
                    database,
                    pidn,
                    3,
                    "error",
                    input_hash,
                    message,
                )
                errors += 1
                continue

            gate = record_inference_decision(
                database,
                subject_key=pidn,
                pass_number=3,
                output_kind="parcel_brief",
                decision_key="brief",
                source_hash=source_hash,
                input_hash=input_hash,
                requested_model=config.model_path,
                served_model=result.metadata.get("served_model"),
                provider=result.metadata.get("provider"),
                prompt_version=PROMPT_VERSION,
                payload=parsed,
                semantic_decision=parcel_brief_semantic_decision(parsed),
                citations=parsed.get("citations", []),
                evidence_refs=[f"signal:{key}" for key in parsed.get("citations", [])]
                + signal_dependencies
                + ["parcel-context:v1:" + ctx["source_fingerprint"]],
            )
            if not gate.accepted:
                auto = auto_resolve_contradiction(database, gate.contradiction_id, log)
                if auto.resolved:
                    log.info(
                        "Contradiction %s auto-resolved (%s): %s",
                        gate.contradiction_id,
                        auto.resolution,
                        auto.rationale,
                    )
                    continue
                message = (
                    f"quarantined as contradiction {gate.contradiction_id}: "
                    f"{gate.reason}"
                )
                log.warning("Brief for %s %s", pidn, message)
                _update_pass_status(
                    database,
                    pidn,
                    3,
                    "error",
                    input_hash,
                    message,
                )
                errors += 1
                continue

            now = datetime.now(UTC).isoformat()
            pass_metadata = {
                "model": os.path.basename(config.model_path),
                "pass_version": "3.1-structured",
                "temperature": config.temperature,
                "thinking": config.thinking,
                # Structured-first fields (experiment C). Persisted in JSONB
                # so the front-end can render recommendation + urgency
                # badges without a schema change per new field.
                "recommendation": parsed.get("recommendation"),
                "urgency": parsed.get("urgency"),
                "evidence_strength": parsed.get("evidence_strength"),
                "top_signal_key": parsed.get("top_signal_key"),
                "top_risk": parsed.get("top_risk"),
            }

            # Postgres accepts Python lists directly for text[] parameters.
            key_questions_raw = parsed.get("key_questions", [])
            if isinstance(key_questions_raw, str):
                try:
                    key_questions_raw = json.loads(key_questions_raw)
                except (json.JSONDecodeError, TypeError):
                    key_questions_raw = [key_questions_raw]
            if not isinstance(key_questions_raw, list):
                key_questions_raw = []

            validated_signals = ctx.get("validated_signals", [])

            database.execute(
                UPSERT_BRIEF_QUERY,
                {
                    "pidn": pidn,
                    "brief_text": parsed["brief"],
                    "assessment": parsed["assessment"],
                    "assessment_reasoning": parsed.get("assessment_reasoning", ""),
                    "key_questions": key_questions_raw,
                    "signal_count": len(validated_signals),
                    "citations": json.dumps(parsed.get("citations", [])),
                    "pass_metadata": json.dumps(pass_metadata),
                    "generated_at": now,
                    "model_version": config.model_path,
                    "prompt_version": PROMPT_VERSION,
                    # A single unvoted sample has no agreement measurement;
                    # writing 1.0 here would read as "3/3 unanimous" in any UI.
                    "n_trials": 1,
                    "trial_agreement": None,
                    "confidence": parsed.get("confidence"),
                    "active_inference_id": gate.inference_id,
                },
            )

            _update_pass_status(database, pidn, 3, "complete", input_hash)
            briefs_created += 1

            log.info(
                "Generated brief for %s: assessment=%s",
                pidn,
                parsed["assessment"],
            )

        except PassSpendLimitExceeded as exc:
            spend_limit_reached = True
            log.info(
                "Pass 3 dollar ceiling reached; remaining parcel briefs are deferred: %s",
                exc,
            )
            break
        except Exception as exc:
            log.warning("Error generating brief for %s: %s", pidn, exc)
            _update_pass_status(
                database,
                pidn,
                3,
                "error",
                input_hash or "",
                str(exc),
            )
            errors += 1

    log.info(
        "Pass 3 complete: %d eligible, %d briefs created, %d skipped, %d errors",
        parcels_eligible,
        briefs_created,
        skipped,
        errors,
    )
    check_error_budget(
        log,
        label="pass3_brief_generation",
        errors=errors,
        total=briefs_created + errors,
    )

    return MaterializeResult(
        metadata={
            "status": MetadataValue.text("complete"),
            "parcels_eligible": MetadataValue.int(parcels_eligible),
            "briefs_created": MetadataValue.int(briefs_created),
            "briefs_retracted": MetadataValue.int(briefs_retracted),
            "skipped": MetadataValue.int(skipped),
            "budget_mode": MetadataValue.text(item_budget.mode),
            "item_limit": (
                MetadataValue.int(item_budget.limit)
                if item_budget.limit is not None
                else MetadataValue.text("cost-only")
            ),
            "items_claimed": MetadataValue.int(item_budget.claimed),
            "spend_limit_reached": MetadataValue.bool(spend_limit_reached),
            "errors": MetadataValue.int(errors),
        }
    )


def _update_pass_status(
    database: DatabaseResource,
    pidn: str,
    pass_number: int,
    status: str,
    input_hash: str,
    error_message: str | None = None,
) -> None:
    """Insert or update meta.intelligence_passes for a brief generation run."""
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
            "pidn": pidn,
            "pass_number": pass_number,
            "status": status,
            "input_hash": input_hash,
            "error_message": error_message,
        },
    )


def _skipped_result(reason: str, *, briefs_retracted: int = 0) -> MaterializeResult:
    """Return a MaterializeResult indicating the asset was skipped."""
    return MaterializeResult(
        metadata={
            "status": MetadataValue.text("skipped"),
            "reason": MetadataValue.text(reason),
            "parcels_eligible": MetadataValue.int(0),
            "briefs_created": MetadataValue.int(0),
            "briefs_retracted": MetadataValue.int(briefs_retracted),
            "skipped": MetadataValue.int(0),
            "errors": MetadataValue.int(0),
        }
    )
