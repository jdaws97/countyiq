"""Generate parcel briefs from validated signals."""

import json
import os
from dataclasses import replace
from datetime import datetime, timezone

from dagster import (
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
)

from countyiq.lib.intelligence_common import compute_input_hash
from countyiq.lib.pass_llm_config import PassHarnessUnavailable, resolve_pass_harness
from countyiq.lib.pass3_brief_generation import (
    build_brief_generation_prompt,
    gather_brief_context,
    parse_brief_output,
    should_generate_brief,
)
from countyiq.resources.database import DatabaseResource

PARCELS_NEEDING_BRIEFS_QUERY = """
    -- Selects parcels that need a brief for any of these reasons:
    --   1. Has medium/high evidence but no brief yet
    --   2. Has evidence that was validated MORE RECENTLY than the current brief
    --      (upstream Pass 2 produced new/updated evidence since the brief was written)
    SELECT DISTINCT e.pidn
    FROM public.evidence e
    LEFT JOIN public.parcel_briefs pb
        ON pb.pidn = e.pidn
    WHERE e.adjusted_significance IN ('high', 'medium')
      AND (
          pb.pidn IS NULL                              -- Reason 1: no brief
          OR e.validated_at > pb.generated_at           -- Reason 2: evidence is fresher than brief
      )
    ORDER BY e.pidn
"""

UPSERT_BRIEF_QUERY = """
    INSERT INTO public.parcel_briefs
        (pidn, brief_text, assessment, assessment_reasoning,
         key_questions, signal_count, citations, brief_version,
         pass_metadata, generated_at)
    VALUES
        (%(pidn)s, %(brief_text)s, %(assessment)s, %(assessment_reasoning)s,
         %(key_questions)s::text[], %(signal_count)s, %(citations)s::jsonb, 1,
         %(pass_metadata)s::jsonb, %(generated_at)s)
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
        generated_at = EXCLUDED.generated_at
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

    try:
        config, invoke_with_retry = resolve_pass_harness(
            log,
            pass_number=3,
            archive_label="pass3_briefs",
            default_max_tokens=2048,
        )
    except PassHarnessUnavailable as exc:
        return _skipped_result(exc.reason)
    config = replace(config, temperature=min(config.temperature, 0.3))

    log.info("Querying parcels eligible for brief generation")
    rows = database.execute(PARCELS_NEEDING_BRIEFS_QUERY)

    if not rows:
        log.info("No parcels eligible for brief generation.")
        return MaterializeResult(
            metadata={
                "status": MetadataValue.text("complete"),
                "parcels_eligible": MetadataValue.int(0),
                "briefs_created": MetadataValue.int(0),
                "skipped": MetadataValue.int(0),
                "errors": MetadataValue.int(0),
            }
        )

    parcels_eligible = len(rows)
    briefs_created = 0
    skipped = 0
    errors = 0

    log.info("Found %d parcels eligible for briefs", parcels_eligible)

    for row in rows:
        pidn = row[0] if isinstance(row, (tuple, list)) else row.get("pidn", row)
        input_hash: str | None = None

        try:
            with database.dict_cursor() as cur:
                ctx = gather_brief_context(cur, pidn)

            validated_signals = ctx.get("validated_signals", [])
            if not should_generate_brief(validated_signals):
                log.debug("Parcel %s has no medium+ signals after context gather, skipping", pidn)
                skipped += 1
                continue

            input_hash = compute_input_hash(ctx)

            existing = database.execute(
                """
                SELECT input_hash FROM meta.intelligence_passes
                WHERE pidn = %(pidn)s
                  AND pass_number = 3
                  AND status = 'complete'
                """,
                {"pidn": pidn},
            )
            prior_hash = existing[0][0] if existing and not isinstance(existing[0], dict) else (existing[0].get("input_hash") if existing else None)
            if prior_hash == input_hash:
                log.debug("Parcel %s context unchanged, skipping brief generation", pidn)
                skipped += 1
                continue

            prompt = build_brief_generation_prompt(ctx)
            result = invoke_with_retry(config, prompt, retries=1, archive_key=pidn)

            if not result.success:
                log.warning(
                    "LLM failed for brief on %s: %s", pidn, result.error,
                )
                _update_pass_status(
                    database, pidn, 3, "error", input_hash, result.error,
                )
                errors += 1
                continue

            parsed = parse_brief_output(result.parsed or {})
            if "error" in parsed:
                log.warning(
                    "Invalid LLM brief output for %s: %s", pidn, parsed["error"],
                )
                _update_pass_status(
                    database, pidn, 3, "error", input_hash, parsed["error"],
                )
                errors += 1
                continue

            now = datetime.now(timezone.utc).isoformat()
            pass_metadata = {
                "model": os.path.basename(config.model_path),
                "pass_version": "3.0",
                "temperature": config.temperature,
                "thinking": config.thinking,
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
                },
            )

            _update_pass_status(database, pidn, 3, "complete", input_hash)
            briefs_created += 1

            log.info(
                "Generated brief for %s: assessment=%s",
                pidn, parsed["assessment"],
            )

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
        parcels_eligible, briefs_created, skipped, errors,
    )

    return MaterializeResult(
        metadata={
            "status": MetadataValue.text("complete"),
            "parcels_eligible": MetadataValue.int(parcels_eligible),
            "briefs_created": MetadataValue.int(briefs_created),
            "skipped": MetadataValue.int(skipped),
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


def _skipped_result(reason: str) -> MaterializeResult:
    """Return a MaterializeResult indicating the asset was skipped."""
    return MaterializeResult(
        metadata={
            "status": MetadataValue.text("skipped"),
            "reason": MetadataValue.text(reason),
            "parcels_eligible": MetadataValue.int(0),
            "briefs_created": MetadataValue.int(0),
            "skipped": MetadataValue.int(0),
            "errors": MetadataValue.int(0),
        }
    )
