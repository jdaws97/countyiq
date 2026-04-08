"""Pass 0 — Multimodal Document Extraction.

For each unprocessed proceeding in staging.public_proceedings:
  1. Download the PDF from R2 (via the document_url stored at ingest time)
  2. Convert each page to a PNG image using pdf2image
  3. Send each page image to the multimodal LLM using llm_harness
  4. Store extracted records in staging.proceeding_extractions

The asset is controlled by the COUNTYIQ_MULTIMODAL_MODEL environment variable.
If that variable is not set, the asset returns immediately with status="skipped",
allowing it to exist in the Dagster graph without failing on machines that have
no model configured.

llama-cpp-python and pdf2image are lazy-imported. If they are not installed the
asset will also return status="skipped" (with a warning) rather than raise at
module load time.
"""

import json
import os
import tempfile
from datetime import datetime, timezone
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
                "pages_processed": MetadataValue.int(0),
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

    try:
        from pdf2image import convert_from_bytes
    except ImportError as exc:
        log.warning("pdf2image not installed (%s) — skipping", exc)
        return _skipped_result("pdf2image not installed")

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
              SELECT 1
              FROM staging.proceeding_extractions pe
              WHERE pe.proceeding_id = pp.id
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
                "pages_processed": MetadataValue.int(0),
                "errors": MetadataValue.int(0),
            }
        )

    log.info("Found %d unprocessed proceedings", len(rows))

    proceedings_processed = 0
    extractions_inserted = 0
    pages_processed = 0
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

        # Convert PDF pages to images
        try:
            images = convert_from_bytes(pdf_bytes, dpi=150, fmt="png")
        except Exception as exc:
            log.warning("pdf2image failed for proceeding %d: %s", proceeding_id, exc)
            errors += 1
            continue

        total_pages = len(images)
        log.info("Proceeding %d: %d pages", proceeding_id, total_pages)
        _prior_inserted = extractions_inserted  # track per-proceeding count

        # Process each page
        with tempfile.TemporaryDirectory() as tmpdir:
            for page_num, page_image in enumerate(images, start=1):
                img_path = os.path.join(tmpdir, f"page_{page_num:04d}.png")
                page_image.save(img_path, format="PNG")

                prompt = EXTRACTION_PROMPT.format(
                    body_name=body_name,
                    page_num=page_num,
                    total_pages=total_pages,
                    proceeding_type=proceeding_type,
                    meeting_date=str(meeting_date),
                )

                result = invoke_with_retry(config, prompt, image_path=img_path, retries=1)
                pages_processed += 1

                if not result.success:
                    log.warning(
                        "LLM failed on proceeding %d page %d: %s",
                        proceeding_id, page_num, result.error,
                    )
                    errors += 1
                    continue

                extractions = (result.parsed or {}).get("extractions", [])
                if not extractions:
                    continue

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
                                page_num,
                            ),
                        )
                        extractions_inserted += 1
                    except Exception as exc:
                        log.warning(
                            "DB insert failed for proceeding %d page %d extraction: %s",
                            proceeding_id, page_num, exc,
                        )
                        errors += 1

        # If no extractions were found across all pages, insert a sentinel
        # row so the NOT EXISTS check stops re-selecting this proceeding on
        # subsequent runs.  extraction_type='_no_extractions' marks this as a
        # deliberate zero-result marker, not a real extraction.
        proceeding_extraction_count = extractions_inserted - _prior_inserted
        if proceeding_extraction_count == 0:
            try:
                database.execute(
                    """
                    INSERT INTO staging.proceeding_extractions
                        (proceeding_id, extraction_type, extraction_confidence,
                         model_used, page_number)
                    VALUES (%s, '_no_extractions', 0.0, %s, 0)
                    ON CONFLICT DO NOTHING
                    """,
                    (proceeding_id, Path(model_path).name),
                )
                log.info(
                    "Proceeding %d: zero extractions across %d pages, sentinel inserted",
                    proceeding_id, total_pages,
                )
            except Exception as exc:
                log.warning(
                    "Failed to insert sentinel for proceeding %d: %s",
                    proceeding_id, exc,
                )

        proceedings_processed += 1
        log.info(
            "Proceeding %d complete: %d pages, %d extractions so far",
            proceeding_id, total_pages, extractions_inserted,
        )

    log.info(
        "Pass 0 complete: %d proceedings, %d pages, %d extractions, %d errors",
        proceedings_processed, pages_processed, extractions_inserted, errors,
    )

    return MaterializeResult(
        metadata={
            "status": MetadataValue.text("complete"),
            "proceedings_processed": MetadataValue.int(proceedings_processed),
            "pages_processed": MetadataValue.int(pages_processed),
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
            "pages_processed": MetadataValue.int(0),
            "errors": MetadataValue.int(0),
        }
    )
