"""Replay accepted subscription Pass 0 receipts through the current binder.

This operator tool never invokes a model, CLI, or API. It validates the final
receipt named by accepted inference provenance, then binds that raw response to
the currently governed source. ``--apply`` is deliberately required for writes.
"""

from __future__ import annotations

import argparse
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from countyiq.assets.enrichment.proceeding_extraction import PENDING_PROCEEDINGS_QUERY
from countyiq.lib.intelligence_integrity import content_hash
from countyiq.lib.llm_harness import HarnessConfig
from countyiq.lib.municipal_evidence import (
    REVIEW_SCHEMA,
    REVIEW_SYSTEM_PROMPT,
    REVIEW_VERSION,
    bind_review,
    review_prompt,
    source_document,
)
from countyiq.lib.municipal_evidence_pipeline import (
    persist_evidence,
    record_snapshot,
)
from countyiq.resources.database import make_database_resource

CORRECTION_SUFFIX = (
    "\nThe previous complete response failed source attribution validation: "
)
CORRECTION_END = (
    ". Re-read the original source and return the complete corrected set. "
    "Separate each case's substantive passages from shared context; do not "
    "drop a case, its outcome or conditions just to remove an overlap. "
    "Only this case's literal subject-property references can create links."
)


def safe_artifact_path(directory: Path, artifact: str) -> Path:
    """Resolve one provenance artifact without allowing traversal outside it."""
    if (
        not artifact
        or Path(artifact).name != artifact
        or not artifact.endswith(".json")
    ):
        raise ValueError("Receipt artifact name is invalid")
    root = directory.resolve(strict=True)
    path = (root / artifact).resolve(strict=True)
    if path.parent != root:
        raise ValueError("Receipt artifact escapes the configured directory")
    return path


def final_receipt(directory: Path, provenance: dict[str, Any]) -> tuple[Path, dict]:
    artifacts = provenance.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("Accepted inference has no subscription receipt provenance")
    final = artifacts[-1]
    if not isinstance(final, dict) or not isinstance(final.get("artifact"), str):
        raise TypeError("Final subscription receipt provenance is malformed")
    path = safe_artifact_path(directory, final["artifact"])
    receipt = json.loads(path.read_text())
    if (
        not isinstance(receipt, dict)
        or "request" not in receipt
        or "response" not in receipt
    ):
        raise ValueError("Subscription receipt is malformed")
    if receipt.get("response_hash") != content_hash(receipt["response"]):
        raise ValueError("Receipt response hash does not match its raw response")
    if final.get("response_hash") != receipt["response_hash"]:
        raise ValueError("Receipt response hash does not match provenance")
    if path.name != f"{content_hash(receipt['request'])}.json":
        raise ValueError("Receipt filename does not match its request hash")
    if (
        provenance.get("provider") != "codex_subscription"
        or receipt.get("provider") != "codex_subscription"
        or receipt.get("billing") != "chatgpt_subscription"
        or receipt["request"].get("model") != provenance.get("author_model")
    ):
        raise ValueError("Receipt author does not match subscription provenance")
    return path, receipt


def validate_request(receipt: dict, document) -> None:
    """Accept the canonical first prompt or its bounded validation correction."""
    request = receipt["request"]
    if (
        request.get("system") != REVIEW_SYSTEM_PROMPT
        or request.get("schema") != REVIEW_SCHEMA
    ):
        raise ValueError("Receipt system prompt or schema is not current")
    prompt = request.get("prompt")
    expected = review_prompt([], document)
    if not isinstance(prompt, str) or not prompt.startswith(expected):
        raise ValueError(
            "Receipt prompt does not begin with the canonical review prompt"
        )
    suffix = prompt[len(expected) :]
    if suffix and not suffix.startswith(CORRECTION_SUFFIX):
        raise ValueError("Receipt prompt has an unrecognized suffix")
    if suffix and (
        not suffix.endswith(CORRECTION_END)
        or len(suffix) > len(CORRECTION_SUFFIX) + 2000 + len(CORRECTION_END)
    ):
        raise ValueError("Receipt correction suffix is incomplete")


def latest_accepted(cursor, proceeding_id: int) -> dict | None:
    cursor.execute(
        """
        SELECT inference_id, payload, requested_model, provider, prompt_version
        FROM meta.intelligence_inference_history
        WHERE subject_key = %s AND output_kind = 'municipal_evidence'
          AND pass_number = 0 AND decision_key = 'source_selection'
          AND disposition = 'accepted'
        ORDER BY inference_id DESC LIMIT 1
        """,
        (f"proceeding:{proceeding_id}",),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def eligible_row(cursor, proceeding_id: int) -> dict | None:
    cursor.execute(
        f"SELECT * FROM ({PENDING_PROCEEDINGS_QUERY}) eligible WHERE id = %s",
        (proceeding_id,),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


class CurrentTransaction:
    """Let the ordinary integrity writer share the locked outer transaction."""

    def __init__(self, connection):
        self.connection = connection

    @contextmanager
    def transaction(self):
        with self.connection.cursor() as cursor:
            yield cursor


def rebind_one(database, proceeding_id: int, directory: Path, apply: bool) -> dict:
    """Validate and optionally persist a single replay, without authoring work."""
    with database.read_snapshot() as cursor:
        prior = latest_accepted(cursor, proceeding_id)
        row = eligible_row(cursor, proceeding_id)
    if prior is None or row is None:
        raise ValueError("Proceeding is not currently eligible with an accepted read")
    payload = prior["payload"] or {}
    if prior["prompt_version"] != REVIEW_VERSION:
        raise ValueError(
            "Accepted inference was not produced by the current review version"
        )
    if payload.get("record_snapshot") != record_snapshot(row):
        raise ValueError("Current source snapshot differs from accepted inference")

    # Eligibility above checks current derived-use governance. This operation
    # reads retained text only; a missing source cannot trigger an acquisition.
    if not row["raw_text"] or len(row["raw_text"].strip()) < 200:
        raise ValueError("Receipt replay requires complete retained source text")
    document, pages = source_document([{"page": None, "text": row["raw_text"]}])
    if payload.get("source_text_sha256") != document.sha256:
        raise ValueError("Current source text hash differs from accepted inference")
    receipt_path, receipt = final_receipt(directory, payload.get("provenance") or {})
    validate_request(receipt, document)
    reviewed = bind_review(receipt["response"], [], document)
    if reviewed["status"] != "complete":
        raise ValueError(
            "Rebound receipt failed validation: " + "; ".join(reviewed["errors"])
        )
    old_cards = payload.get("cards", [])
    report = {
        "proceeding_id": proceeding_id,
        "prior_inference_id": prior["inference_id"],
        "source_text_sha256": document.sha256,
        "receipt": {
            "path": str(receipt_path),
            "response_hash": receipt["response_hash"],
        },
        "old_payload": payload,
        "old_cards": old_cards,
        "new_cards": reviewed["cards"],
        "changed": old_cards != reviewed["cards"],
    }
    if not apply or not report["changed"]:
        return report

    provenance = dict(payload.get("provenance") or {})
    provenance["binding_repair"] = {
        "prior_inference_id": prior["inference_id"],
        "receipt_response_hash": receipt["response_hash"],
        "binder_sha256": content_hash(
            Path(bind_review.__code__.co_filename).read_text()
        ),
    }
    config = HarnessConfig(
        model_path=prior["requested_model"],
        system_prompt=REVIEW_SYSTEM_PROMPT,
        json_schema=REVIEW_SCHEMA,
        reasoning_effort=receipt["request"].get("effort"),
    )
    with database.transaction(dict_rows=True) as cursor:
        lock_key = (
            f"0\x1fmunicipal_evidence\x1fproceeding:{proceeding_id}\x1fsource_selection"
        )
        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (lock_key,)
        )
        cursor.execute(
            "SELECT id FROM staging.public_proceedings WHERE id = %s FOR SHARE",
            (proceeding_id,),
        )
        current = latest_accepted(cursor, proceeding_id)
        current_row = eligible_row(cursor, proceeding_id)
        if current is None or current["inference_id"] != prior["inference_id"]:
            raise ValueError("Accepted inference changed during replay; refusing write")
        if current_row is None or record_snapshot(current_row) != record_snapshot(row):
            raise ValueError("Source changed during replay; refusing write")
        gate = persist_evidence(
            CurrentTransaction(cursor.connection),
            current_row,
            document,
            pages,
            replace_result(reviewed, prior["requested_model"]),
            config,
            provenance=provenance,
        )
    report["write"] = {
        "inference_id": gate.inference_id,
        "accepted": gate.accepted,
        "contradiction_id": gate.contradiction_id,
    }
    return report


def replace_result(reviewed: dict, requested_model: str) -> dict:
    """Keep the raw author's model and mark a deterministic binding repair."""
    result = dict(reviewed)
    result["requested_model"] = requested_model
    result["validation_attempts"] = 0
    result["value_decision"] = "read_non_accounting_source"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids", nargs="+", type=int, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if any(identifier <= 0 for identifier in args.ids):
        parser.error("--ids must contain positive proceeding IDs")
    if args.report.resolve() == args.directory.resolve():
        parser.error("--report must name an output file")
    database = make_database_resource()
    database.setup_for_execution(None)
    try:
        report = {"apply": args.apply, "results": [], "errors": []}
        for proceeding_id in args.ids:
            try:
                report["results"].append(
                    rebind_one(database, proceeding_id, args.directory, args.apply)
                )
            except (ValueError, TypeError, OSError) as error:
                report["errors"].append(
                    {"proceeding_id": proceeding_id, "error": str(error)}
                )
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2, default=str) + "\n")
    finally:
        database.teardown_after_execution(None)
    unresolved = any(
        not item.get("write", {}).get("accepted", True) for item in report["results"]
    )
    return 2 if report["errors"] or unresolved else 0


if __name__ == "__main__":
    raise SystemExit(main())
