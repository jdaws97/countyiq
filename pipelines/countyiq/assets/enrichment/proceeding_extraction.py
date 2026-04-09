"""Pass 0 — Document Extraction via native PDF input.

For each unprocessed proceeding in staging.public_proceedings:
  1. Download the PDF (via the document_url stored at ingest time)
  2. Send the entire PDF to the LLM via OpenRouter's native PDF support
  3. Store extracted records in staging.proceeding_extractions

Uses models with native PDF input (e.g., Grok 4.1 Fast via OpenRouter).
The PDF is sent as a base64-encoded file content block — no pdf2image
or OCR conversion needed.

The asset is controlled by COUNTYIQ_OPENROUTER_MODEL (preferred) or
COUNTYIQ_MULTIMODAL_MODEL / COUNTYIQ_TEXT_MODEL environment variables.
If none are set, the asset returns immediately with status="skipped".
"""

import json
from pathlib import Path

from dagster import (
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
)

from countyiq.lib.pass0_templates import EXTRACTION_PROMPT
from countyiq.resources.database import DatabaseResource

# Confidence label → numeric float for storage
_CONFIDENCE_MAP = {"high": 0.9, "medium": 0.6, "low": 0.3}


@asset(
    group_name="enrichment",
    description=(
        "Pass 0: extract rezoning/variance/subdivision records from "
        "meeting minute PDFs using a multimodal LLM"
    ),
    deps=["public_proceedings_scrape"],
    kinds={"postgres", "llm"},
)
def proceeding_extraction(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> MaterializeResult:
    log = context.log

    # ------------------------------------------------------------------
    # Resolve backend and model (same pattern as Pass 1/2/3/4)
    # ------------------------------------------------------------------
    openrouter_model = os.environ.get("COUNTYIQ_OPENROUTER_MODEL")
    local_model = os.environ.get("COUNTYIQ_MULTIMODAL_MODEL") or os.environ.get("COUNTYIQ_TEXT_MODEL")

    if openrouter_model:
        backend = "openrouter"
        model_path = openrouter_model
    elif local_model:
        backend = "llama_cpp"
        model_path = local_model
    else:
        log.info(
            "No model configured — skipping Pass 0 extraction. "
            "Set COUNTYIQ_OPENROUTER_MODEL or COUNTYIQ_MULTIMODAL_MODEL."
        )
        return MaterializeResult(
            metadata={
                "status": MetadataValue.text("skipped"),
                "reason": MetadataValue.text("no model configured"),
                "proceedings_processed": MetadataValue.int(0),
                "extractions_inserted": MetadataValue.int(0),
                "errors": MetadataValue.int(0),
            }
        )

    log.info(f"Pass 0: backend={backend} model={model_path}")

    # ------------------------------------------------------------------
    # Guard: optional dependencies must be importable
    # ------------------------------------------------------------------
    try:
        from countyiq.lib.llm_harness import (
            HarnessConfig, get_preset_for_model, invoke_with_retry,
        )
    except ImportError as exc:
        log.warning("llm_harness import failed (%s) — skipping", exc)
        return _skipped_result("llm_harness import failed")

    import requests

    preset = get_preset_for_model(model_path, thinking=False, reasoning_task=False)
    config = HarnessConfig(
        model_path=model_path,
        backend=backend,
        archive_label="pass0_extraction",
        **preset,
    )

    # ------------------------------------------------------------------
    # Find unprocessed proceedings
    # ------------------------------------------------------------------
    rows = database.execute(
        """
        SELECT pp.id, pp.body_name, pp.meeting_date, pp.proceeding_type, pp.document_url
        FROM staging.public_proceedings pp
        WHERE pp.valid_to IS NULL
          AND pp.document_url IS NOT NULL
          AND NOT EXISTS (
              -- Only skip proceedings that have been FULLY extracted.
              -- A proceeding is fully extracted when it has a sentinel row
              -- with extraction_type = '_complete'. Partial extractions
              -- (some pages succeeded, others failed) will be retried.
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
                "proceedings_processed": MetadataValue.int(0),
                "extractions_inserted": MetadataValue.int(0),
                "errors": MetadataValue.int(0),
            }
        )

    log.info("Found %d unprocessed proceedings", len(rows))

    proceedings_processed = 0
    extractions_inserted = 0
    errors = 0

    _HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CountyIQ/1.0; +https://countyiq.app)"}

    for proceeding_id, body_name, meeting_date, proceeding_type, document_url in rows:
        log.info(
            "Processing proceeding %d: %s / %s / %s",
            proceeding_id, body_name, meeting_date, proceeding_type,
        )

        # Download the PDF
        try:
            resp = requests.get(document_url, headers=_HEADERS, timeout=60)
            resp.raise_for_status()
            pdf_bytes = resp.content
        except Exception as exc:
            log.warning("Failed to download PDF for proceeding %d (%s): %s", proceeding_id, document_url, exc)
            errors += 1
            continue

        pdf_size_kb = len(pdf_bytes) // 1024
        log.info("Proceeding %d: downloaded %d KB PDF", proceeding_id, pdf_size_kb)

        # Clear any partial extraction rows from a prior failed attempt
        existing_rows = database.execute(
            "SELECT COUNT(*) FROM staging.proceeding_extractions WHERE proceeding_id = %s",
            (proceeding_id,),
        ) or []
        existing_count = existing_rows[0][0] if existing_rows else 0
        if existing_count:
            database.execute(
                "DELETE FROM staging.proceeding_extractions WHERE proceeding_id = %s",
                (proceeding_id,),
            )
            log.info("Proceeding %d: cleared %d partial row(s) before retry", proceeding_id, existing_count)

        _prior_inserted = extractions_inserted

        # Build prompt — handle nullable meeting_date
        date_clause = f" dated {meeting_date}" if meeting_date else ""
        prompt = EXTRACTION_PROMPT.format(
            body_name=body_name,
            proceeding_type=proceeding_type,
            date_clause=date_clause,
        )

        # Send entire PDF to the LLM in one call
        result = invoke_with_retry(
            config,
            prompt,
            pdf_bytes=pdf_bytes,
            retries=1,
            archive_key=f"{proceeding_id}",
        )

        if not result.success:
            log.warning(
                "LLM failed on proceeding %d: %s",
                proceeding_id, result.error,
            )
            errors += 1
            # Don't insert sentinel — eligible for retry next run
            continue

        extractions = (result.parsed or {}).get("extractions", [])

        for extraction in extractions:
            try:
                confidence_label = extraction.get("confidence", "low")
                confidence_float = _CONFIDENCE_MAP.get(confidence_label, 0.3)

                conditions = extraction.get("conditions")
                conditions_json = json.dumps(conditions) if conditions else None

                database.execute(
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
                        Path(model_path).name,
                        None,  # page_number not applicable for whole-document extraction
                    ),
                )
                extractions_inserted += 1
            except Exception as exc:
                log.warning(
                    "DB insert failed for proceeding %d extraction: %s",
                    proceeding_id, exc,
                )
                errors += 1

        # Sentinel logic
        proceeding_extraction_count = extractions_inserted - _prior_inserted
        sentinel_type = "_complete" if proceeding_extraction_count > 0 else "_no_extractions"

        if proceeding_extraction_count == 0:
            try:
                database.execute(
                    """
                    INSERT INTO staging.proceeding_extractions
                        (proceeding_id, extraction_type, extraction_confidence, model_used, page_number)
                    VALUES (%s, '_no_extractions', 0.0, %s, 0)
                    ON CONFLICT DO NOTHING
                    """,
                    (proceeding_id, Path(model_path).name),
                )
            except Exception as exc:
                log.warning("Failed to insert no-extractions sentinel for %d: %s", proceeding_id, exc)

        try:
            database.execute(
                """
                INSERT INTO staging.proceeding_extractions
                    (proceeding_id, extraction_type, extraction_confidence, model_used, page_number)
                VALUES (%s, '_complete', 1.0, %s, 0)
                ON CONFLICT DO NOTHING
                """,
                (proceeding_id, Path(model_path).name),
            )
        except Exception as exc:
            log.warning("Failed to insert completion sentinel for %d: %s", proceeding_id, exc)

        proceedings_processed += 1
        log.info(
            "Proceeding %d complete: %d extractions (total so far: %d)",
            proceeding_id, proceeding_extraction_count, extractions_inserted,
        )

    log.info(
        "Pass 0 complete: %d proceedings, %d extractions, %d errors",
        proceedings_processed, extractions_inserted, errors,
    )

    return MaterializeResult(
        metadata={
            "status": MetadataValue.text("complete"),
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
