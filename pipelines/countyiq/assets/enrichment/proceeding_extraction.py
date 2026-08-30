"""Pass 0 — extract structured proceeding records from meeting-minute PDFs."""

import json
import os
from pathlib import Path
from urllib.parse import urlparse

import requests
from dagster import AssetExecutionContext, MaterializeResult, MetadataValue, asset

from countyiq.lib.county_config import get_county_config, municipality_source_key
from countyiq.lib.error_budget import check_error_budget
from countyiq.lib.intelligence_events import normalize_development_tags
from countyiq.lib.pass_llm_config import (
    PassItemBudget,
    PassHarnessUnavailable,
    resolve_pass_harness,
)
from countyiq.lib.pass0_templates import EXTRACTION_USER_TEMPLATE, PASS0_SYSTEM_PROMPT
from countyiq.lib.pass_schemas import PASS0_EXTRACTION_SCHEMA
from countyiq.lib.robots import RobotsPolicy
from countyiq.lib.source_rights import (
    authorize_municipality_sources,
    authorize_source,
    require_source_use,
)
from countyiq.resources.database import DatabaseResource

_CONFIDENCE_MAP = {"high": 0.9, "medium": 0.6, "low": 0.3}
# Below this many extracted characters, treat raw_text as a failed/scanned
# extraction and fall back to sending the PDF itself.
_MIN_RAW_TEXT_CHARS = 200
# Municipal minutes are short; this cap (~35K tokens) only guards pathological
# documents from blowing up the context window.
_MAX_RAW_TEXT_CHARS = 140_000
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CountyIQ/1.0; +https://countyiq.app)"}

PENDING_PROCEEDINGS_QUERY = """
    SELECT
        pp.id,
        pp.body_name,
        pp.meeting_date,
        pp.proceeding_type,
        pp.document_url,
        pp.raw_text
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


def _is_pdf_document(document_url: str) -> bool:
    """True when the URL clearly points at a PDF.

    Guards the download-and-attach fallback: OpenRouter's file-parser only
    accepts PDFs, so Word documents (and extensionless URLs like Google
    Drive's uc?export=download) must never be inlined as file_data. Those
    documents rely on scrape-time raw_text instead.
    """
    return urlparse(document_url).path.lower().endswith(".pdf")


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
            event_tags = normalize_development_tags(
                extraction_type=extraction.get("extraction_type"),
                decision=extraction.get("decision"),
                conditions=conditions or [],
                proposed_tags=extraction.get("event_tags") or [],
                what_happens_next=extraction.get("what_happens_next"),
                upcoming_date=extraction.get("upcoming_date"),
            )
            related_entities = list(
                dict.fromkeys(
                    entity.strip()
                    for entity in [
                        extraction.get("applicant_name"),
                        *(extraction.get("related_entities") or []),
                    ]
                    if isinstance(entity, str) and entity.strip()
                )
            )

            cur.execute(
                """
                INSERT INTO staging.proceeding_extractions
                    (proceeding_id, extraction_type, applicant_name,
                     parcel_reference, current_zoning, proposed_zoning,
                     decision, conditions, supporting_text,
                     extraction_confidence, model_used, page_number,
                     event_tags, project_name, related_entities,
                     what_happened, why_it_matters, what_happens_next,
                     upcoming_date, interpretation_generated_at)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s, %s, %s, NOW())
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
                    event_tags,
                    extraction.get("project_name"),
                    related_entities,
                    extraction.get("what_happened"),
                    extraction.get("why_it_matters"),
                    extraction.get("what_happens_next"),
                    extraction.get("upcoming_date"),
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
    county = get_county_config()
    source_authorization = authorize_source(
        database,
        source_key="public_proceedings",
        acquisition_method="official_document_direct",
        asset_key="proceeding_extraction",
        dagster_run_id=context.run_id,
    )
    require_source_use(source_authorization, "derived_product")
    municipality_authorizations = authorize_municipality_sources(
        database,
        entries=county.municipality_websites,
        acquisition_method="official_document_direct",
        asset_key="proceeding_extraction",
        dagster_run_id=context.run_id,
    )

    try:
        config, invoke_with_retry = resolve_pass_harness(
            log,
            pass_number=0,
            archive_label="pass0_extraction",
            reasoning_task=False,
            default_max_tokens=4096,
            json_schema=PASS0_EXTRACTION_SCHEMA,
            schema_name="pass0_extractions",
            # Static block goes out as a byte-identical system message so
            # providers with implicit prompt caching can reuse it per doc.
            system_prompt=PASS0_SYSTEM_PROMPT,
            # Pin the PDF parser for the inline-PDF fallback path: unpinned
            # uploads can silently route to OCR at ~$2/1,000 pages (see
            # docs/cost.md). "native" uses the model's own file input.
            pdf_engine=os.environ.get("COUNTYIQ_PASS0_PDF_ENGINE", "native"),
        )
    except PassHarnessUnavailable as exc:
        return _skipped_result(exc.reason)
    item_budget = PassItemBudget(0)

    rows = database.execute(PENDING_PROCEEDINGS_QUERY)

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

    unknown_bodies = sorted(
        {
            body_name
            for _, body_name, *_ in rows
            if municipality_source_key(body_name) not in municipality_authorizations
        }
    )
    if unknown_bodies:
        raise RuntimeError(
            "Proceedings reference bodies without active reviewed policies: "
            + ", ".join(unknown_bodies)
        )

    robots = RobotsPolicy(_HEADERS["User-Agent"])
    proceedings_processed = 0
    extractions_inserted = 0
    from_raw_text = 0
    from_pdf = 0
    errors = 0

    for proceeding_id, body_name, meeting_date, proceeding_type, document_url, raw_text in rows:
        log.info(
            "Processing proceeding %d: %s / %s / %s",
            proceeding_id,
            body_name,
            meeting_date,
            proceeding_type,
        )

        # Prefer the text the scraper already extracted (pdfplumber). Sending
        # text instead of an inline PDF avoids OpenRouter file-parser fees
        # (~8x the token cost of a typical minutes doc), cuts input tokens,
        # and removes the runtime dependency on flaky municipal websites.
        pdf_bytes = None
        use_text = bool(raw_text and len(raw_text.strip()) >= _MIN_RAW_TEXT_CHARS)
        if not use_text and not _is_pdf_document(document_url):
            # No usable text and not a PDF (Word doc, extensionless Drive
            # link): OpenRouter can't parse it, so skip rather than upload
            # bytes mislabeled as application/pdf.
            log.warning(
                "Skipping proceeding %d: no raw_text and '%s' is not a PDF",
                proceeding_id,
                document_url,
            )
            errors += 1
            continue
        if not use_text:
            robots_decision = robots.decision(document_url)
            if not robots_decision.allowed:
                log.warning(
                    "Skipping proceeding %d: robots policy blocked PDF fallback (%s)",
                    proceeding_id,
                    robots_decision.reason,
                )
                errors += 1
                continue
            try:
                resp = requests.get(document_url, headers=_HEADERS, timeout=60)
                resp.raise_for_status()
                pdf_bytes = resp.content
                if not pdf_bytes.startswith(b"%PDF-"):
                    raise ValueError("response is not a PDF document")
            except Exception as exc:
                log.warning(
                    "Failed to download PDF for proceeding %d (%s): %s",
                    proceeding_id,
                    document_url,
                    exc,
                )
                errors += 1
                continue

        if not item_budget.claim(log, label="pending proceedings"):
            break

        date_clause = f" dated {meeting_date}" if meeting_date else ""
        prompt = EXTRACTION_USER_TEMPLATE.format(
            body_name=body_name,
            county_name=county.name,
            state=county.state,
            proceeding_type=proceeding_type,
            date_clause=date_clause,
        )
        if use_text:
            prompt += "\n\nDOCUMENT TEXT:\n" + raw_text[:_MAX_RAW_TEXT_CHARS]
            from_raw_text += 1
        else:
            from_pdf += 1

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

    check_error_budget(
        log, label="pass0_proceeding_extraction",
        errors=errors, total=proceedings_processed + errors,
    )

    return MaterializeResult(
        metadata={
            "status": MetadataValue.text("complete"),
            "model": MetadataValue.text(config.model_path),
            "proceedings_processed": MetadataValue.int(proceedings_processed),
            "extractions_inserted": MetadataValue.int(extractions_inserted),
            "from_raw_text": MetadataValue.int(from_raw_text),
            "from_pdf_fallback": MetadataValue.int(from_pdf),
            "item_limit": MetadataValue.int(item_budget.limit),
            "items_claimed": MetadataValue.int(item_budget.claimed),
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
