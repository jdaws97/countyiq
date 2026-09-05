"""Pass 0 — extract structured proceeding records from meeting-minute PDFs."""

import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlparse

import requests
from dagster import AssetExecutionContext, MaterializeResult, MetadataValue, asset

from countyiq.lib.intelligence_common import PROCEEDING_USE_ALLOWED_SQL
from countyiq.lib.county_config import get_county_config, municipality_source_key
from countyiq.lib.doc_text import extract_text_from_pdf_bytes
from countyiq.lib.error_budget import check_error_budget
from countyiq.lib.intelligence_common import (
    fetch_prior_pass_attempts,
    pass_attempt_priority,
)
from countyiq.lib.intelligence_events import normalize_development_tags
from countyiq.lib.intelligence_autoresolve import auto_resolve_contradiction
from countyiq.lib.intelligence_integrity import (
    content_hash,
    inference_input_hash,
    pass0_semantic_decision,
    record_inference_decision,
    record_validation_rejection,
    validate_pass0_extractions,
)
from countyiq.lib.proceeding_contract import details_for
from countyiq.lib.proceeding_quality import VERSION as METADATA_REVIEW_VERSION
from countyiq.lib.pass0_templates import (
    EXTRACTION_USER_TEMPLATE,
    PASS0_SYSTEM_PROMPT,
    PROMPT_VERSION,
)
from countyiq.lib.pass_llm_config import (
    PassHarnessUnavailable,
    PassItemBudget,
    PassSpendLimitExceeded,
    resolve_pass_harness,
)
from countyiq.lib.proceeding_claims import PASS0_MODEL_SCHEMA, bind_model_claims, review_claims
from countyiq.lib.pass0_templates import document_prompt
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
_ROBOTS_PRODUCT_TOKEN = "CountyIQ"

PENDING_PROCEEDINGS_QUERY = f"""
    SELECT pp.id,
        pp.body_name,
        pp.meeting_date,
        pp.proceeding_type,
        pp.document_url,
        pp.raw_text,
        pp.content_hash
    FROM staging.public_proceedings pp
    WHERE pp.valid_to IS NULL
      AND {PROCEEDING_USE_ALLOWED_SQL}
      AND pp.document_url IS NOT NULL
      AND pp.metadata_quality->>'status' = 'ready'
      AND pp.metadata_quality->>'version' = '{METADATA_REVIEW_VERSION}'
      AND pp.meeting_date <= CURRENT_DATE
    ORDER BY pp.meeting_date DESC
"""

PRIOR_ACCEPTED_PROJECTIONS_QUERY = """
    WITH latest AS (
        SELECT DISTINCT ON (subject_key)
            subject_key, input_hash, inference_id
        FROM meta.intelligence_inference_history
        WHERE pass_number = 0
          AND output_kind = 'proceeding_extraction'
          AND disposition = 'accepted'
        ORDER BY subject_key, inference_id DESC
    )
    SELECT DISTINCT latest.subject_key, latest.input_hash
    FROM latest
    JOIN staging.proceeding_extractions pe
      ON latest.subject_key = 'proceeding:' || pe.proceeding_id::text
     AND pe.active_inference_id = latest.inference_id
"""


# Deterministic pre-filter. A document with none of these land-use terms in
# its text has never produced a property extraction in the reviewed corpus
# (water-authority minutes, budget hearings, personnel sessions). Skipping it
# costs nothing and records an explicit marker instead of a paid empty call.
LANDUSE_TERMS = (
    "subdivision",
    "land development",
    "rezon",
    "zoning",
    "variance",
    "special exception",
    "conditional use",
    "site plan",
    "sketch plan",
    "preliminary plan",
    "final plan",
    "planning commission",
    "zoning hearing",
    "lot line",
    "lot consolidation",
    "curative amendment",
    "waiver",
    "sewage facilities",
    "planning module",
    "developer",
    "parcel",
    "tax map",
    # Municipality-wide policy actions (ordinance_action extractions).
    "ordinance",
    "comprehensive plan",
    "act 537",
    "official map",
    "moratori",
    "lerta",
    "keystone opportunity",
    "tax increment",
    # Explicit public capital work, including the pilot's prefilter misses.
    "capital project",
    "construction bid",
    "park project",
    "play equipment",
    "social hall",
    "substation",
    "storm drain",
    "solar project",
    "roof",
    "public bid",
    "bridge project",
    "bridge work",
    "pedestrian improvements",
    "energy storage",
    "office addition",
)

NO_LANDUSE_MARKER = "_no_landuse_terms"
PREFILTER_MODEL = "deterministic-prefilter"
PREFILTER_VERSION = content_hash(
    {"marker": NO_LANDUSE_MARKER, "landuse_terms": LANDUSE_TERMS}
)[:12]


def has_landuse_vocabulary(text: str | None) -> bool:
    """True when the document mentions at least one land-use / planning term."""
    if not text:
        return False
    lowered = text.casefold()
    return any(term in lowered for term in LANDUSE_TERMS)


def _persist_prefilter_skip(
    database: DatabaseResource,
    proceeding_id: int,
    *,
    inference_id: int,
) -> None:
    """Record a deterministic pre-filter skip so downstream readers see an explicit absence."""
    with database.transaction() as cur:
        cur.execute(
            "DELETE FROM staging.proceeding_extractions WHERE proceeding_id = %s",
            (proceeding_id,),
        )
        cur.execute(
            """
            INSERT INTO staging.proceeding_extractions
                (proceeding_id, extraction_type, extraction_confidence,
                 model_used, page_number, active_inference_id)
            VALUES (%s, %s, 1.0, 'deterministic-prefilter', 0, %s)
            ON CONFLICT DO NOTHING
            """,
            (proceeding_id, NO_LANDUSE_MARKER, inference_id),
        )


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
    inference_id: int,
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
                record_status=extraction.get("record_status"),
                decision_scope=extraction.get("decision_scope"),
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
                     upcoming_date, interpretation_generated_at,
                     active_inference_id, extraction_details)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s::jsonb)
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
                    inference_id,
                    json.dumps(details_for(extraction)),
                ),
            )
            inserted_count += 1

        if inserted_count == 0:
            cur.execute(
                """
                INSERT INTO staging.proceeding_extractions
                    (proceeding_id, extraction_type, extraction_confidence,
                     model_used, page_number, active_inference_id)
                VALUES (%s, '_no_extractions', 0.0, %s, 0, %s)
                ON CONFLICT DO NOTHING
                """,
                (proceeding_id, model_used, inference_id),
            )

        cur.execute(
            """
            INSERT INTO staging.proceeding_extractions
                (proceeding_id, extraction_type, extraction_confidence,
                 model_used, page_number, active_inference_id)
            VALUES (%s, '_complete', 1.0, %s, 0, %s)
            ON CONFLICT DO NOTHING
            """,
            (proceeding_id, model_used, inference_id),
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
            default_max_tokens=8192,
            json_schema=PASS0_MODEL_SCHEMA,
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

    prior_rows = database.execute(PRIOR_ACCEPTED_PROJECTIONS_QUERY) or []
    prior_hashes = {
        (row.get("subject_key") if isinstance(row, dict) else row[0]):
        (row.get("input_hash") if isinstance(row, dict) else row[1])
        for row in prior_rows
    }

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

    prior_attempts = fetch_prior_pass_attempts(database, pass_number=0)
    rows = sorted(
        rows,
        key=lambda row: pass_attempt_priority(
            f"proceeding:{row[0] if isinstance(row, (tuple, list)) else row['id']}",
            prior_attempts,
        ),
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

    robots = RobotsPolicy(
        _HEADERS["User-Agent"],
        product_token=_ROBOTS_PRODUCT_TOKEN,
    )
    proceedings_processed = 0
    extractions_inserted = 0
    from_raw_text = 0
    from_pdf = 0
    skipped_unchanged = 0
    skipped_prefilter = 0
    errors = 0
    quarantined_items_count = 0
    partial_documents = 0
    coverage_review_documents = 0
    citation_repairs_count = 0
    withheld_entity_claims = 0
    spend_limit_reached = False

    for (
        proceeding_id,
        body_name,
        meeting_date,
        proceeding_type,
        document_url,
        raw_text,
        proceeding_content_hash,
    ) in rows:
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
        verification_text = (
            raw_text if use_text else ""
        )
        source_version = (
            content_hash({
                "document_content_hash": proceeding_content_hash,
                "raw_text_hash": content_hash(verification_text),
            })
            if use_text
            else proceeding_content_hash
        )
        source_hash = None
        input_hash = None
        if source_version:
            source_hash = content_hash(
                {
                    "proceeding_id": proceeding_id,
                    "body_name": body_name,
                    "meeting_date": meeting_date,
                    "proceeding_type": proceeding_type,
                    "document_url": document_url,
                    "source_version": source_version,
                }
            )
            # An unchanged accepted LLM projection can skip PDF download. Raw
            # text with no land-use vocabulary follows the deterministic path
            # below and uses its own versioned execution identity.
            if not use_text or has_landuse_vocabulary(verification_text):
                input_hash = inference_input_hash(
                    source_hash,
                    requested_model=config.model_path,
                    prompt_version=PROMPT_VERSION,
                )
                if prior_hashes.get(f"proceeding:{proceeding_id}") == input_hash:
                    skipped_unchanged += 1
                    continue
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
                if not source_version:
                    source_version = hashlib.sha256(pdf_bytes).hexdigest()
            except Exception as exc:
                log.warning(
                    "Failed to download PDF for proceeding %d (%s): %s",
                    proceeding_id,
                    document_url,
                    exc,
                )
                errors += 1
                continue

            try:
                verification_text = extract_text_from_pdf_bytes(pdf_bytes)
            except Exception as exc:
                log.warning(
                    "Skipping proceeding %d: local PDF text extraction failed: %s",
                    proceeding_id,
                    exc,
                )
                errors += 1
                continue

        if not verification_text.strip():
            log.warning(
                "Skipping proceeding %d: source text is unavailable for quote verification",
                proceeding_id,
            )
            errors += 1
            continue

        if source_hash is None:
            source_hash = content_hash(
                {
                    "proceeding_id": proceeding_id,
                    "body_name": body_name,
                    "meeting_date": meeting_date,
                    "proceeding_type": proceeding_type,
                    "document_url": document_url,
                    "source_version": source_version,
                }
            )
            input_hash = inference_input_hash(
                source_hash,
                requested_model=config.model_path,
                prompt_version=PROMPT_VERSION,
            )
            if prior_hashes.get(f"proceeding:{proceeding_id}") == input_hash:
                skipped_unchanged += 1
                continue

        if not has_landuse_vocabulary(verification_text):
            input_hash = inference_input_hash(
                source_hash,
                requested_model=PREFILTER_MODEL,
                prompt_version=PREFILTER_VERSION,
            )
            if prior_hashes.get(f"proceeding:{proceeding_id}") == input_hash:
                skipped_unchanged += 1
                continue
            log.info(
                "Skipping proceeding %d: no land-use vocabulary in %d chars of text",
                proceeding_id,
                len(verification_text),
            )
            try:
                gate = record_inference_decision(
                    database,
                    subject_key=f"proceeding:{proceeding_id}",
                    pass_number=0,
                    output_kind="proceeding_extraction",
                    decision_key="document",
                    source_hash=source_hash,
                    input_hash=input_hash,
                    requested_model=PREFILTER_MODEL,
                    served_model=PREFILTER_MODEL,
                    provider="deterministic",
                    prompt_version=PREFILTER_VERSION,
                    payload={
                        "extractions": [],
                        "prefilter": NO_LANDUSE_MARKER,
                    },
                    semantic_decision=pass0_semantic_decision([]),
                    evidence_refs=[f"proceeding:{proceeding_id}"],
                )
                if not gate.accepted:
                    auto = auto_resolve_contradiction(
                        database, gate.contradiction_id, log
                    )
                    if auto.resolved:
                        skipped_prefilter += 1
                        continue
                    message = (
                        f"quarantined contradiction {gate.contradiction_id}: "
                        f"{gate.reason}"
                    )
                    _update_pass_status(
                        database, proceeding_id, "error", input_hash, message
                    )
                    errors += 1
                    continue
                _persist_prefilter_skip(
                    database,
                    proceeding_id,
                    inference_id=gate.inference_id,
                )
                _update_pass_status(
                    database, proceeding_id, "complete", input_hash
                )
            except Exception as exc:
                _update_pass_status(
                    database, proceeding_id, "error", input_hash, str(exc)
                )
                log.warning(
                    "Failed to persist deterministic prefilter for proceeding %d: %s",
                    proceeding_id,
                    exc,
                )
                errors += 1
                continue
            skipped_prefilter += 1
            continue

        if not item_budget.claim(log, label="pending proceedings"):
            break

        try:
            expected_source_sha256 = hashlib.sha256(verification_text.encode("utf-8")).hexdigest()
            prompt = document_prompt(verification_text, body_name=body_name, county_name=county.name,
                                     state=county.state, proceeding_type=proceeding_type, meeting_date=meeting_date)
        except ValueError as exc:
            log.warning("Skipping proceeding %d: %s", proceeding_id, exc)
            errors += 1
            continue
        if use_text:
            from_raw_text += 1
        else:
            from_pdf += 1

        try:
            result = invoke_with_retry(
                config,
                prompt,
                retries=1,
                archive_key=f"{proceeding_id}",
                pdf_bytes=None,  # Indexed local text is the evidence contract, including PDF fallback.
            )
        except PassSpendLimitExceeded as exc:
            spend_limit_reached = True
            log.info(
                "Pass 0 dollar ceiling reached; remaining proceedings are deferred: %s",
                exc,
            )
            break

        if not result.success:
            _update_pass_status(
                database,
                proceeding_id,
                "error",
                input_hash or "",
                result.error,
            )
            log.warning("LLM failed on proceeding %d: %s", proceeding_id, result.error)
            errors += 1
            continue

        extractions, rejected_items = [], []
        model_used = Path(config.model_path).name
        try:
            bound_claims = bind_model_claims(result.parsed, verification_text,
                                            expected_source_sha256=expected_source_sha256)
            review = review_claims(bound_claims, verification_text, meeting_date=meeting_date)
            extractions, rejected_items = review["extractions"], review["rejected_items"]
            validation_errors = validate_pass0_extractions(extractions, verification_text, meeting_date=meeting_date, require_contract=True)
            if rejected_items and not extractions:
                validation_errors.extend(f"item {item['index']}: {'; '.join(item['errors'])}" for item in rejected_items)
        except ValueError as exc:
            validation_errors = [str(exc)]
        if validation_errors:
            _update_pass_status(
                database,
                proceeding_id,
                "error",
                input_hash or "",
                "; ".join(validation_errors),
            )
            record_validation_rejection(
                database,
                subject_key=f"proceeding:{proceeding_id}",
                pass_number=0,
                output_kind="proceeding_extraction",
                source_hash=source_hash,
                input_hash=input_hash,
                requested_model=config.model_path,
                prompt_version=PROMPT_VERSION,
                errors=validation_errors,
            )
            log.warning(
                "Proceeding %d failed evidence validation: %s",
                proceeding_id,
                "; ".join(validation_errors),
            )
            errors += 1
            continue

        try:
            if rejected_items:
                record_validation_rejection(
                    database, subject_key=f"proceeding:{proceeding_id}", pass_number=0,
                    output_kind="proceeding_extraction", source_hash=source_hash, input_hash=input_hash,
                    requested_model=config.model_path, prompt_version=PROMPT_VERSION,
                    errors=[f"item {item['index']}: {'; '.join(item['errors'])}" for item in rejected_items],
                )
                log.warning("Proceeding %d: quarantined %d item(s); retaining %d validated item(s)",
                            proceeding_id, len(rejected_items), len(extractions))
            gate = record_inference_decision(
                database,
                subject_key=f"proceeding:{proceeding_id}",
                pass_number=0,
                output_kind="proceeding_extraction",
                decision_key="document",
                source_hash=source_hash,
                input_hash=input_hash,
                requested_model=config.model_path,
                served_model=result.metadata.get("served_model"),
                provider=result.metadata.get("provider"),
                prompt_version=PROMPT_VERSION,
                payload={"extractions": extractions, "model_claims": result.parsed,
                         "source_sha256": expected_source_sha256,
                         "rejected_items": rejected_items, "accepted_indices": review["accepted_indices"],
                         "citation_repairs": review["citation_repairs"], "coverage": review["coverage"],
                         "field_rejections": review["field_rejections"]},
                semantic_decision=pass0_semantic_decision(extractions),
                citations=[
                    extraction["supporting_text"]
                    for extraction in extractions
                    if extraction.get("supporting_text")
                ],
                evidence_refs=[f"proceeding:{proceeding_id}"],
            )
            if not gate.accepted:
                auto = auto_resolve_contradiction(database, gate.contradiction_id, log)
                if auto.resolved:
                    log.info(
                        "Contradiction %s auto-resolved (%s): %s",
                        gate.contradiction_id, auto.resolution, auto.rationale,
                    )
                    continue
                _update_pass_status(
                    database,
                    proceeding_id,
                    "error",
                    input_hash or "",
                    f"quarantined contradiction {gate.contradiction_id}: {gate.reason}",
                )
                log.warning(
                    "Proceeding %d quarantined as contradiction %s: %s",
                    proceeding_id,
                    gate.contradiction_id,
                    gate.reason,
                )
                errors += 1
                continue

            existing_count, inserted_for_proceeding = _write_proceeding_extractions(
                database,
                proceeding_id=proceeding_id,
                extractions=extractions,
                model_used=model_used,
                inference_id=gate.inference_id,
            )
        except Exception as exc:
            _update_pass_status(
                database,
                proceeding_id,
                "error",
                input_hash or "",
                str(exc),
            )
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
        quarantined_items_count += len(rejected_items)
        partial_documents += int(bool(rejected_items or review["field_rejections"]))
        coverage_review_documents += int(review["coverage"]["needs_review"])
        citation_repairs_count += len(review["citation_repairs"])
        withheld_entity_claims += len(review["field_rejections"])
        proceedings_processed += 1
        _update_pass_status(
            database, proceeding_id, "complete", input_hash or "",
            json.dumps({"quarantined_items": rejected_items, "coverage": review["coverage"],
                        "citation_repairs": review["citation_repairs"], "field_rejections": review["field_rejections"]})
            if rejected_items or review["coverage"]["needs_review"] or review["citation_repairs"] or review["field_rejections"] else None,
        )
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
            "quarantined_items": MetadataValue.int(quarantined_items_count),
            "partial_documents": MetadataValue.int(partial_documents),
            "coverage_review_documents": MetadataValue.int(coverage_review_documents),
            "citation_repairs": MetadataValue.int(citation_repairs_count),
            "withheld_entity_claims": MetadataValue.int(withheld_entity_claims),
            "from_raw_text": MetadataValue.int(from_raw_text),
            "from_pdf_fallback": MetadataValue.int(from_pdf),
            "skipped_unchanged": MetadataValue.int(skipped_unchanged),
            "skipped_prefilter": MetadataValue.int(skipped_prefilter),
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
    proceeding_id: int,
    status: str,
    input_hash: str,
    error_message: str | None = None,
) -> None:
    database.execute(
        """
        INSERT INTO meta.intelligence_passes
            (pidn, pass_number, status, last_run_at, input_hash, error_message)
        VALUES (%(key)s, 0, %(status)s, NOW(), %(hash)s, %(error)s)
        ON CONFLICT (pidn, pass_number)
        DO UPDATE SET
            status = EXCLUDED.status,
            last_run_at = EXCLUDED.last_run_at,
            input_hash = EXCLUDED.input_hash,
            error_message = EXCLUDED.error_message
        """,
        {
            "key": f"proceeding:{proceeding_id}",
            "status": status,
            "hash": input_hash,
            "error": error_message,
        },
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
