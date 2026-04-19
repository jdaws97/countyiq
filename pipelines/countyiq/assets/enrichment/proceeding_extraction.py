"""Pass 0 — extract structured proceeding records from meeting-minute PDFs."""

import json
from pathlib import Path

import requests
from dagster import AssetExecutionContext, MaterializeResult, MetadataValue, asset

from countyiq.lib.pass_llm_config import PassHarnessUnavailable, resolve_pass_harness
from countyiq.lib.pass0_templates import EXTRACTION_PROMPT
from countyiq.resources.database import DatabaseResource

_CONFIDENCE_MAP = {"high": 0.9, "medium": 0.6, "low": 0.3}
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CountyIQ/1.0; +https://countyiq.app)"}


def _write_proceeding_extractions(
    database: DatabaseResource,
    *,
    proceeding_id: int,
    extractions: list[dict],
    model_used: str,
) -> tuple[int, int]:
    """Persist one proceeding's extracted rows transactionally.

    Returns ``(existing_count, inserted_count)``. If any insert fails, the
    whole transaction rolls back so the proceeding stays eligible for retry.
    """
    with database.transaction() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM staging.proceeding_extractions WHERE proceeding_id = %s",
            (proceeding_id,),
        )
        existing_row = cur.fetchone()
        existing_count = existing_row[0] if existing_row else 0

        if existing_count:
            cur.execute(
                "DELETE FROM staging.proceeding_extractions WHERE proceeding_id = %s",
                (proceeding_id,),
            )

        inserted_count = 0
        for extraction in extractions:
            confidence_label = extraction.get("confidence", "low")
            confidence_float = _CONFIDENCE_MAP.get(confidence_label, 0.3)
            conditions = extraction.get("conditions")
            conditions_json = json.dumps(conditions) if conditions else None

            cur.execute(
                """
                INSERT INTO staging.proceeding_extractions
                    (proceeding_id, extraction_type, applicant_name,
                     parcel_reference, current_zoning, proposed_zoning,
                     decision, conditions, supporting_text,
                     extraction_confidence, model_used, page_number)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
                """,
                (
                    proceeding_id,
                    extraction.get("extraction_type"),
                    extraction.get("applicant_name"),
                    extraction.get("parcel_reference"),
                    extraction.get("current_zoning"),
                    extraction.get("proposed_zoning"),
                    extraction.get("decision"),
                    conditions_json,
                    extraction.get("supporting_text"),
                    confidence_float,
                    model_used,
                    None,
                ),
            )
            inserted_count += 1

        if inserted_count == 0:
            cur.execute(
                """
                INSERT INTO staging.proceeding_extractions
                    (proceeding_id, extraction_type, extraction_confidence, model_used, page_number)
                VALUES (%s, '_no_extractions', 0.0, %s, 0)
                ON CONFLICT DO NOTHING
                """,
                (proceeding_id, model_used),
            )

        cur.execute(
            """
            INSERT INTO staging.proceeding_extractions
                (proceeding_id, extraction_type, extraction_confidence, model_used, page_number)
            VALUES (%s, '_complete', 1.0, %s, 0)
            ON CONFLICT DO NOTHING
            """,
            (proceeding_id, model_used),
        )

    return existing_count, inserted_count


@asset(
    group_name="enrichment",
    description=(
        "Pass 0: extract rezoning/variance/subdivision records from "
        "meeting minute PDFs using an OpenRouter model"
    ),
    deps=["public_proceedings_scrape"],
    kinds={"postgres", "llm"},
)
def proceeding_extraction(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> MaterializeResult:
    log = context.log

    try:
        config, invoke_with_retry = resolve_pass_harness(
            log,
            pass_number=0,
            archive_label="pass0_extraction",
            reasoning_task=False,
            default_max_tokens=4096,
        )
    except PassHarnessUnavailable as exc:
        return _skipped_result(exc.reason)

    rows = database.execute(
        """
        SELECT
            pp.id,
            pp.body_name,
            pp.meeting_date,
            pp.proceeding_type,
            pp.document_url
        FROM staging.public_proceedings pp
        WHERE pp.valid_to IS NULL
          AND pp.document_url IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM staging.proceeding_extractions pe
              WHERE pe.proceeding_id = pp.id
                AND pe.extraction_type = '_complete'
          )
        ORDER BY pp.meeting_date DESC
        """
    )

    if not rows:
        log.info("No unprocessed proceedings found.")
        return MaterializeResult(
            metadata={
                "status": MetadataValue.text("complete"),
                "model": MetadataValue.text(config.model_path),
                "proceedings_processed": MetadataValue.int(0),
                "extractions_inserted": MetadataValue.int(0),
                "errors": MetadataValue.int(0),
            }
        )

    proceedings_processed = 0
    extractions_inserted = 0
    errors = 0

    for proceeding_id, body_name, meeting_date, proceeding_type, document_url in rows:
        log.info(
            "Processing proceeding %d: %s / %s / %s",
            proceeding_id,
            body_name,
            meeting_date,
            proceeding_type,
        )

        try:
            resp = requests.get(document_url, headers=_HEADERS, timeout=60)
            resp.raise_for_status()
            pdf_bytes = resp.content
        except Exception as exc:
            log.warning(
                "Failed to download PDF for proceeding %d (%s): %s",
                proceeding_id,
                document_url,
                exc,
            )
            errors += 1
            continue

        date_clause = f" dated {meeting_date}" if meeting_date else ""
        prompt = EXTRACTION_PROMPT.format(
            body_name=body_name,
            proceeding_type=proceeding_type,
            date_clause=date_clause,
        )

        result = invoke_with_retry(
            config,
            prompt,
            retries=1,
            archive_key=f"{proceeding_id}",
            pdf_bytes=pdf_bytes,
        )

        if not result.success:
            log.warning("LLM failed on proceeding %d: %s", proceeding_id, result.error)
            errors += 1
            continue

        extractions = (result.parsed or {}).get("extractions", [])
        model_used = Path(config.model_path).name
        try:
            existing_count, inserted_for_proceeding = _write_proceeding_extractions(
                database,
                proceeding_id=proceeding_id,
                extractions=extractions,
                model_used=model_used,
            )
        except Exception as exc:
            log.warning(
                "Failed to persist extractions for proceeding %d: %s",
                proceeding_id,
                exc,
            )
            errors += 1
            continue

        if existing_count:
            log.info(
                "Proceeding %d: cleared %d partial row(s) before retry",
                proceeding_id,
                existing_count,
            )

        extractions_inserted += inserted_for_proceeding
        proceedings_processed += 1
        log.info(
            "Proceeding %d complete: %d extraction(s)",
            proceeding_id,
            inserted_for_proceeding,
        )

    return MaterializeResult(
        metadata={
            "status": MetadataValue.text("complete"),
            "model": MetadataValue.text(config.model_path),
            "proceedings_processed": MetadataValue.int(proceedings_processed),
            "extractions_inserted": MetadataValue.int(extractions_inserted),
            "errors": MetadataValue.int(errors),
        }
    )


def _skipped_result(reason: str) -> MaterializeResult:
    return MaterializeResult(
        metadata={
            "status": MetadataValue.text("skipped"),
            "reason": MetadataValue.text(reason),
            "proceedings_processed": MetadataValue.int(0),
            "extractions_inserted": MetadataValue.int(0),
            "errors": MetadataValue.int(0),
        }
    )
