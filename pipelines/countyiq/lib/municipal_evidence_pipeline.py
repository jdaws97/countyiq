"""Read each municipal source once and retain source selections in history."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import requests
from dagster import MaterializeResult

from countyiq.lib.county_config import municipality_source_key
from countyiq.lib.error_budget import check_error_budget
from countyiq.lib.intelligence_integrity import content_hash, record_inference_decision
from countyiq.lib.municipal_evidence import (
    DEFAULT_EVIDENCE_MODEL,
    READER_POLICY_VERSION,
    REVIEW_SCHEMA,
    REVIEW_SYSTEM_PROMPT,
    REVIEW_VERSION,
    bind_review,
    review_prompt,
    source_document,
    source_kind,
)
from countyiq.lib.municipal_subjects import validate_subject_cards
from countyiq.lib.municipal_value import VALUE_POLICY_VERSION, source_value
from countyiq.lib.pass0_documents import MAX_BYTES, read_pdf_source
from countyiq.lib.pass_llm_config import (
    PassHarnessUnavailable,
    PassItemBudget,
    PassSpendLimitExceeded,
    resolve_pass_harness,
)
from countyiq.lib.pass_subscription import (
    start_subscription_item,
    subscription_provenance,
)
from countyiq.lib.robots import RobotsPolicy, get_with_robots
from countyiq.lib.source_rights import require_source_use


def record_snapshot(row: dict) -> dict:
    """Source identity is independent of model, prompt and selected cards."""
    return {
        "content_hash": row["content_hash"],
        "raw_text_sha256": hashlib.sha256((row["raw_text"] or "").encode()).hexdigest(),
        "body_name": row["body_name"],
        "meeting_date": str(row["meeting_date"]),
        "proceeding_type": row["proceeding_type"],
        "document_url": row["document_url"],
    }


def reader_identity(config) -> str:
    return content_hash(
        {
            "config": config.__dict__,
            "reader": REVIEW_VERSION,
            "reader_policy": READER_POLICY_VERSION,
            "value_policy": VALUE_POLICY_VERSION,
            "method": "direct",
        }
    )


def read_evidence(document, config, invoke) -> dict:
    """Read the complete source, with one bounded attribution correction."""
    value = source_value(document)
    if value.skip_reason:
        return {
            "status": "complete",
            "cards": [],
            "errors": [],
            "warnings": [],
            "value_decision": value.skip_reason,
            "requested_model": None,
        }
    model = config.model_path
    ceilings = {
        DEFAULT_EVIDENCE_MODEL: (0.16, 0.55),
        "deepseek/deepseek-v4-flash-0731": (0.16, 0.32),
    }
    json_contract = model.startswith("deepseek/deepseek-v4")
    prompt_ceiling, completion_ceiling = ceilings.get(
        model, (config.max_price_prompt, config.max_price_completion)
    )
    review_config = replace(
        config,
        model_path=model,
        thinking=False,
        reasoning_effort=config.reasoning_effort
        or ("high" if model == DEFAULT_EVIDENCE_MODEL else "low"),
        provider_quantizations=("fp8",)
        if model == DEFAULT_EVIDENCE_MODEL or model.startswith("deepseek/deepseek-v4")
        else None,
        max_price_prompt=min(config.max_price_prompt, prompt_ceiling)
        if config.max_price_prompt is not None
        else None,
        max_price_completion=min(config.max_price_completion, completion_ceiling)
        if config.max_price_completion is not None
        else None,
        json_schema=None if json_contract else REVIEW_SCHEMA,
        schema_name="municipal_evidence_review",
        system_prompt=REVIEW_SYSTEM_PROMPT,
    )
    prompt = review_prompt([], document)
    if json_contract:
        prompt += "\nRequired output JSON schema:\n" + json.dumps(
            REVIEW_SCHEMA, separators=(",", ":")
        )
    original_prompt = prompt
    for attempt in (1, 2):
        response = invoke(
            review_config,
            prompt,
            retries=0,
            archive_key=f"municipal-source:{document.sha256}:attempt:{attempt}",
        )
        if not response.success:
            raise ValueError(response.error or "Source review failed")
        reviewed = bind_review(response.parsed, [], document)
        if reviewed["status"] == "complete":
            break
        rejection = "; ".join(reviewed["errors"])
        if attempt == 2:
            raise ValueError(rejection)
        prompt = original_prompt + (
            "\nThe previous complete response failed source attribution validation: "
            + rejection[:2000]
            + ". Re-read the original source and return the complete corrected set. "
            "Separate each case's substantive passages from shared context; do not "
            "drop a case, its outcome or conditions just to remove an overlap. "
            "Only this case's literal subject-property references can create links."
        )
    reviewed["validation_attempts"] = attempt
    reviewed["requested_model"] = model
    reviewed["value_decision"] = "read_non_accounting_source"
    return reviewed


def persist_evidence(
    database, row, document, page_spans, reviewed, config, *, provenance=None
):
    """Preserve every original span; source changes invalidate serving immediately."""
    if reviewed["status"] != "complete":
        raise ValueError("Only complete reviewed reads may be published")
    validate_subject_cards(reviewed["cards"], document)
    for card in reviewed["cards"]:
        for span in [card["subject"], *card["passages"]]:
            if (
                span["source_text_sha256"] != document.sha256
                or document.text[span["start"] : span["end"]] != span["text"]
            ):
                raise ValueError("Evidence changed after source binding")
        if card["title"] != " ".join(card["subject"]["text"].split()):
            raise ValueError("Evidence title changed after source binding")
    snapshot = record_snapshot(row)
    payload = {
        "record_snapshot": snapshot,
        "source_text_sha256": document.sha256,
        "pages": page_spans,
        "cards": reviewed["cards"],
        "warnings": reviewed.get("warnings", []),
        "reader_identity": reader_identity(config),
        "reader_policy": READER_POLICY_VERSION,
        "coverage": "value_filtered_source_read",
        "value_policy": VALUE_POLICY_VERSION,
        "excluded_accounting_sections": source_value(document).excluded_sections,
        "value_decision": reviewed.get("value_decision", "read_non_accounting_source"),
        "document_kind": source_kind(document),
        "requested_model": reviewed.get("requested_model", config.model_path),
        "validation_attempts": reviewed.get("validation_attempts", 0),
    }
    if provenance is not None:
        payload["provenance"] = provenance
    # Selection differences on unchanged evidence are reviewable contradictions,
    # even though no approval, parcel or ownership claim is being generated.
    return record_inference_decision(
        database,
        subject_key=f"proceeding:{row['id']}",
        pass_number=0,
        output_kind="municipal_evidence",
        decision_key="source_selection",
        source_hash=content_hash({"record": snapshot, "text": document.sha256}),
        input_hash=content_hash(
            {"record": snapshot, "reader": reader_identity(config)}
        ),
        requested_model=reviewed.get("requested_model", config.model_path)
        or "deterministic-value-gate",
        prompt_version=REVIEW_VERSION,
        payload=payload,
        semantic_decision=reviewed["cards"],
        evidence_refs=[str(row["document_url"])],
        provider=provenance.get("provider") if provenance else None,
    )


def prepare_source(row: dict, authorizations: dict, robots):
    """Use retained text, or locally read a hash-matching governed PDF."""
    authorization = authorizations.get(municipality_source_key(row["body_name"]))
    if authorization is None:
        raise ValueError("Municipal source has no current authorization")
    require_source_use(authorization, "derived_product")
    if row["raw_text"] and len(row["raw_text"].strip()) >= 200:
        return source_document([{"page": None, "text": row["raw_text"]}])
    with get_with_robots(
        row["document_url"],
        robots=robots,
        allowed_origins=authorization.allowed_origins,
        headers={"User-Agent": "CountyIQ/1.0 (+https://countyiq.app)"},
        timeout=45,
        stream=True,
    ) as response:
        response.raise_for_status()
        chunks = []
        size = 0
        for chunk in response.iter_content(64 * 1024):
            size += len(chunk)
            if size > MAX_BYTES:
                raise ValueError(
                    "Municipal PDF exceeds the local preparation byte limit"
                )
            chunks.append(chunk)
    pdf_bytes = b"".join(chunks)
    if hashlib.sha256(pdf_bytes).hexdigest() != row["content_hash"]:
        raise ValueError(
            "Municipal PDF changed; refresh the source record before reading"
        )
    prepared = read_pdf_source(pdf_bytes)
    return source_document(
        [
            {"page": page.page, "text": prepared.text[page.start : page.end]}
            for page in prepared.pages
        ]
    )


def select_proceedings(
    rows: list[dict], proceeding_ids: list[int] | None
) -> list[dict]:
    """Pin a canary to eligible documents without silently widening its scope."""
    if not proceeding_ids:
        return rows
    if any(
        type(identifier) is not int or identifier <= 0 for identifier in proceeding_ids
    ):
        raise ValueError("Proceeding IDs must be positive integers")
    selected_ids = set(proceeding_ids)
    missing = selected_ids - {row["id"] for row in rows}
    if missing:
        raise ValueError(f"Requested proceedings are not eligible: {sorted(missing)}")
    return [row for row in rows if row["id"] in selected_ids]


def run_municipal_evidence(
    context,
    database,
    pending_query: str,
    authorizations: dict,
    *,
    proceeding_ids: list[int] | None = None,
) -> MaterializeResult:
    """Incremental native-text reader under the existing durable spend gate.

    Scanned inputs use the locked local OCR runtime. Preparation failures remain
    pending; they never become an empty completed read or paid parser fallback.
    """
    from countyiq.assets.enrichment.proceeding_extraction import _update_pass_status

    try:
        config, invoke = resolve_pass_harness(
            context.log,
            pass_number=0,
            archive_label="municipal_evidence",
            reasoning_task=False,
            default_max_tokens=8192,
            json_schema=REVIEW_SCHEMA,
            schema_name="municipal_evidence_review",
            system_prompt=REVIEW_SYSTEM_PROMPT,
        )
    except PassHarnessUnavailable as error:
        return MaterializeResult(metadata={"status": "skipped", "reason": error.reason})
    # Match the evaluated deterministic sampling settings, retaining budget,
    # provider price ceilings and model chosen by the ordinary pass gate.
    config = replace(config, temperature=0, top_k=0, top_p=1, require_parameters=True)
    with database.dict_cursor() as cur:
        cur.execute(pending_query)
        rows = select_proceedings([dict(row) for row in cur.fetchall()], proceeding_ids)
        cur.execute("""
            SELECT DISTINCT ON (subject_key)
                subject_key, input_hash, provider, prompt_version, payload
            FROM meta.intelligence_inference_history
            WHERE output_kind = 'municipal_evidence' AND disposition = 'accepted'
            ORDER BY subject_key, inference_id DESC
        """)
        previous = {row["subject_key"]: row for row in cur.fetchall()}
    budget = PassItemBudget(0)
    robots = RobotsPolicy(
        "CountyIQ/1.0 (+https://countyiq.app)", product_token="CountyIQ"
    )
    counts = {
        "eligible_in_scope": len(rows),
        "processed": 0,
        "unchanged": 0,
        "needs_text": 0,
        "errors": 0,
        "quarantined": 0,
    }
    stop_reason = "scope_exhausted"
    for row in rows:
        fingerprint = content_hash(
            {"record": record_snapshot(row), "reader": reader_identity(config)}
        )
        prior = previous.get(f"proceeding:{row['id']}", {})
        payload = prior.get("payload") or {}
        subscription_current = (
            prior.get("provider") == "codex_subscription"
            and prior.get("prompt_version") == REVIEW_VERSION
            and payload.get("reader_policy") == READER_POLICY_VERSION
            and payload.get("value_policy") == VALUE_POLICY_VERSION
            and payload.get("record_snapshot") == record_snapshot(row)
        )
        if prior.get("input_hash") == fingerprint or subscription_current:
            counts["unchanged"] += 1
            continue
        if not budget.claim(context.log, label="municipal source reads"):
            stop_reason = "item_limit"
            break
        try:
            document, pages = prepare_source(row, authorizations, robots)
        except (ValueError, RuntimeError, requests.RequestException):
            context.log.exception(
                "Municipal source %s needs text preparation", row["id"]
            )
            counts["needs_text"] += 1
            _update_pass_status(
                database,
                row["id"],
                "error",
                fingerprint,
                "Source text preparation failed",
            )
            continue
        try:
            start_subscription_item(invoke)
            reviewed = read_evidence(document, config, invoke)
            gate = persist_evidence(
                database,
                row,
                document,
                pages,
                reviewed,
                config,
                provenance=subscription_provenance(invoke),
            )
            counts["processed" if gate.accepted else "quarantined"] += 1
            _update_pass_status(
                database,
                row["id"],
                "complete" if gate.accepted else "error",
                fingerprint,
                None
                if gate.accepted
                else "New selection awaits contradiction resolution",
            )
        except PassSpendLimitExceeded as error:
            stop_reason = getattr(error, "stop_reason", "spend_limit")
            break
        except ValueError:
            context.log.exception("Municipal source %s was not published", row["id"])
            counts["errors"] += 1
            _update_pass_status(
                database,
                row["id"],
                "error",
                fingerprint,
                "Source read failed validation",
            )
    check_error_budget(
        context.log,
        label="Municipal source reads",
        errors=counts["needs_text"] + counts["errors"],
        total=sum(
            counts[key] for key in ("processed", "needs_text", "errors", "quarantined")
        ),
    )
    remaining = len(rows) - counts["processed"] - counts["unchanged"]
    return MaterializeResult(
        metadata={
            "status": "partial" if remaining else "complete",
            "mode": "evidence",
            "stop_reason": stop_reason,
            "remaining": remaining,
            **counts,
        }
    )
