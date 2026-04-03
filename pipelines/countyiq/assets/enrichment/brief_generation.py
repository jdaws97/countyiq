"""Pass 3 — Brief Generation Dagster Asset.

Synthesizes validated signals into intelligence briefs for parcels that have
at least one medium- or high-significance validated signal.  For each
eligible parcel, gathers full context, builds a brief generation prompt,
invokes the LLM, parses the response, and upserts results to
public.parcel_briefs.

The asset is controlled by the COUNTYIQ_TEXT_MODEL environment variable.
If that variable is not set, the asset returns immediately with
status="skipped", allowing it to exist in the Dagster graph without
failing on machines that have no model configured.
"""

import json
import os
from datetime import datetime, timezone

from dagster import (
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
)

from countyiq.lib.intelligence_common import compute_input_hash
from countyiq.lib.pass3_brief_generation import (
    build_brief_generation_prompt,
    gather_brief_context,
    parse_brief_output,
    should_generate_brief,
)
from countyiq.resources.database import DatabaseResource


# ---------------------------------------------------------------------------
# SQL constants
# ---------------------------------------------------------------------------

ELIGIBLE_PARCELS_QUERY = """
    SELECT DISTINCT e.pidn
    FROM public.evidence e
    LEFT JOIN public.parcel_briefs pb
        ON pb.pidn = e.pidn
    WHERE e.adjusted_significance IN ('high', 'medium')
      AND pb.pidn IS NULL
    ORDER BY e.pidn
"""

UPSERT_BRIEF_QUERY = """
    INSERT INTO public.parcel_briefs
        (pidn, brief, assessment, assessment_reasoning,
         key_questions, citations, brief_version,
         pass_metadata, generated_at)
    VALUES
        (%(pidn)s, %(brief)s, %(assessment)s, %(assessment_reasoning)s,
         %(key_questions)s::jsonb, %(citations)s::jsonb, 1,
         %(pass_metadata)s::jsonb, %(generated_at)s)
    ON CONFLICT (pidn)
    DO UPDATE SET
        brief = EXCLUDED.brief,
        assessment = EXCLUDED.assessment,
        assessment_reasoning = EXCLUDED.assessment_reasoning,
        key_questions = EXCLUDED.key_questions,
        citations = EXCLUDED.citations,
        brief_version = public.parcel_briefs.brief_version + 1,
        pass_metadata = EXCLUDED.pass_metadata,
        generated_at = EXCLUDED.generated_at
"""


# ---------------------------------------------------------------------------
# Dagster Asset
# ---------------------------------------------------------------------------

@asset(
    group_name="enrichment",
    description=(
        "Pass 3: synthesize validated signals into intelligence briefs "
        "for parcels with medium or high significance signals"
    ),
    deps=["signal_validation"],
    kinds={"postgres", "llm"},
)
def brief_generation(
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
            "COUNTYIQ_TEXT_MODEL is not set — skipping Pass 3 brief generation. "
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

    # Temperature 0.2 for slightly more creative briefs than validation
    config = HarnessConfig(model_path=model_path, max_tokens=2048, temperature=0.2)

    # ------------------------------------------------------------------
    # Find eligible parcels (medium+ signals, no existing brief)
    # ------------------------------------------------------------------
    log.info("Querying parcels eligible for brief generation")
    rows = database.execute(ELIGIBLE_PARCELS_QUERY)

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

    conn = database._get_conn()

    for row in rows:
        pidn = row[0] if isinstance(row, (tuple, list)) else row.get("pidn", row)

        try:
            # Gather full context
            import psycopg2.extras
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                ctx = gather_brief_context(cur, pidn)

            # Check eligibility (should_generate_brief)
            validated_signals = ctx.get("validated_signals", [])
            if not should_generate_brief(validated_signals):
                log.debug("Parcel %s has no medium+ signals after context gather, skipping", pidn)
                skipped += 1
                continue

            # Change detection
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
            if existing and existing[0][0] == input_hash:
                log.debug("Parcel %s context unchanged, skipping brief generation", pidn)
                skipped += 1
                continue

            # Build prompt and invoke LLM
            prompt = build_brief_generation_prompt(ctx)
            result = invoke_with_retry(config, prompt, retries=1)

            if not result.success:
                log.warning(
                    "LLM failed for brief on %s: %s", pidn, result.error,
                )
                _update_pass_status(
                    database, pidn, 3, "error", input_hash, result.error,
                )
                errors += 1
                continue

            # Parse and validate output
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

            # Upsert to public.parcel_briefs
            now = datetime.now(timezone.utc).isoformat()
            pass_metadata = {
                "model": os.path.basename(model_path),
                "pass_version": "3.0",
                "temperature": 0.2,
            }

            database.execute(
                UPSERT_BRIEF_QUERY,
                {
                    "pidn": pidn,
                    "brief": parsed["brief"],
                    "assessment": parsed["assessment"],
                    "assessment_reasoning": parsed.get("assessment_reasoning", ""),
                    "key_questions": json.dumps(parsed.get("key_questions", [])),
                    "citations": json.dumps(parsed.get("citations", [])),
                    "pass_metadata": json.dumps(pass_metadata),
                    "generated_at": now,
                },
            )

            # Update pass tracking
            _update_pass_status(database, pidn, 3, "complete", input_hash)
            briefs_created += 1

            log.info(
                "Generated brief for %s: assessment=%s",
                pidn, parsed["assessment"],
            )

        except Exception as exc:
            log.warning("Error generating brief for %s: %s", pidn, exc)
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
