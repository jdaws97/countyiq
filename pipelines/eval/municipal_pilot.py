"""Run a manifest-bound Pass 0 evaluation without publishing extracted records.

Default: validate inputs and write a frozen experiment directory. --run invokes
the configured production-shaped model under a durable dollar cap. This is an
evaluation path; it does not approve a quality receipt or enable runtime passes.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor
from jsonschema import Draft202012Validator

from countyiq.assets.enrichment.proceeding_extraction import (
    PENDING_PROCEEDINGS_QUERY, has_landuse_vocabulary,
)
from countyiq.lib.backfill_authorization import BackfillAuthorization, create_backfill_authorization
from countyiq.lib.intelligence_integrity import validate_pass0_extractions
from countyiq.lib.pass0_templates import EXTRACTION_USER_TEMPLATE, PROMPT_VERSION
from countyiq.lib.pass_llm_config import resolve_pass_model
from countyiq.lib.proceeding_claims import PASS0_CLAIMS_SCHEMA, review_claims
from countyiq.lib.pass0_templates import document_prompt
from countyiq.lib.llm_harness import probe_llm_archive_destination
from countyiq.lib.quality_release import release_identity
from eval.protocol import build_production_eval_config, estimate_max_call_cost, EvalCostLedger, invoke_tracked

REPO = Path(__file__).resolve().parents[2]


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def prompt_for(row: dict) -> str:
    return document_prompt(row["raw_text"], body_name=row["body_name"], county_name="York County",
                           state="PA", proceeding_type=row["proceeding_type"], meeting_date=row["meeting_date"])


def validate_manifest_record(record: dict, row: dict, eligible: set[int]) -> None:
    if row["id"] not in eligible:
        raise ValueError(f"Source {row['id']} is no longer eligible")
    for field in ("body_name", "meeting_date", "proceeding_type", "document_url", "content_hash"):
        if str(record.get(field)) != str(row.get(field)):
            raise ValueError(f"Source {row['id']} changed {field}")
    if digest(row.get("raw_text") or "") != record["raw_text_sha256"]:
        raise ValueError(f"Source {row['id']} text changed")
    if len(row["raw_text"]) > 140_000:
        raise ValueError("Pilot must review whole documents; source exceeds runtime text cap")


def load_sources(manifest: dict) -> list[dict]:
    records = manifest["records"]
    ids = [r["id"] for r in records]
    if not 1 <= len(ids) <= 30 or len(ids) != len(set(ids)):
        raise ValueError("Pilot requires 1–30 distinct manifest records")
    with psycopg2.connect(os.environ["DATABASE_URL"]) as conn:
        conn.set_session(readonly=True)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(PENDING_PROCEEDINGS_QUERY)
            eligible = {r["id"] for r in cur.fetchall()}
            cur.execute("SELECT * FROM staging.public_proceedings WHERE id = ANY(%s)", (ids,))
            by_id = {r["id"]: dict(r) for r in cur.fetchall()}
    result = []
    for record in records:
        row = by_id.get(record["id"])
        if row is None:
            raise ValueError(f"Source {record['id']} missing")
        validate_manifest_record(record, row, eligible)
        result.append(row)
    return result


def evaluate_format(parsed: dict | None, source_text: str, meeting_date=None) -> dict:
    schema_errors = [e.message for e in Draft202012Validator(PASS0_CLAIMS_SCHEMA).iter_errors(parsed)]
    extractions, evidence_errors, rejected_items = [], [], []
    citation_repairs, field_rejections, coverage = [], [], None
    try:
        review = review_claims(parsed, source_text, meeting_date=meeting_date)
        extractions, rejected_items = review["extractions"], review["rejected_items"]
        citation_repairs, coverage = review["citation_repairs"], review["coverage"]
        field_rejections = review["field_rejections"]
        evidence_errors = validate_pass0_extractions(extractions, source_text, meeting_date=meeting_date)
    except ValueError as exc:
        evidence_errors = [str(exc)]
    publishable = not evidence_errors and (bool(extractions) or not rejected_items)
    # Item-level shape errors do not invalidate good siblings. Report them,
    # distinguishing partial acceptance from an entirely clean document.
    return {"schema_errors": schema_errors, "evidence_errors": evidence_errors,
            "runtime_gate_passed": publishable,
            "complete_document_gate_passed": publishable and not rejected_items and not field_rejections and not schema_errors,
            "rejected_items": rejected_items, "citation_repairs": citation_repairs, "field_rejections": field_rejections, "coverage": coverage,
            "extraction_count": len(extractions) if publishable else 0,
            "semantic_review_complete": False,
            "hydrated_extractions": extractions if publishable else []}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-cost-usd", type=float, required=True)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if not math.isfinite(args.max_cost_usd) or not 0 < args.max_cost_usd <= 2:
        parser.error("This pilot is capped at $2")
    manifest = json.loads(args.manifest.read_text())
    rows = load_sources(manifest)
    model = resolve_pass_model(0)
    config = build_production_eval_config(model, 0, archive_label="municipal_pilot")
    maximum = sum(estimate_max_call_cost(config, prompt_for(row), retries=0) for row in rows)
    if maximum > args.max_cost_usd:
        parser.error("Worst-case reservation exceeds the cap")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    output = args.output_dir
    os.environ["COUNTYIQ_ARCHIVE_DIR"] = str(output / "transcripts")
    os.environ["COUNTYIQ_ARCHIVE_STRICT"] = "1"
    protocol = dict(
        started_at=datetime.now(timezone.utc).isoformat(), manifest_sha256=digest(args.manifest.read_text()),
        model=model, config=asdict(config), production_quality_identity=release_identity(0),
        prompt_version=PROMPT_VERSION, max_cost_usd=args.max_cost_usd,
        maximum_reservation_usd=maximum, retries=0, document_count=len(rows),
        publication="evaluation_only", semantic_reviewer="Codex source-by-source review pending",
        criteria=["source-supported matter", "correct decision stage and scope", "verbatim supporting quote",
                  "correct property identity", "project relevance", "distinct matter recall",
                  "duplicate project risk", "prefilter false negatives", "provider-reported cost"],
    )
    (output / "protocol.json").write_text(json.dumps(protocol, indent=2))
    (output / "sources.json").write_text(json.dumps(rows, default=str, indent=2))
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2))
    if not args.run:
        print(json.dumps({"prepared": str(output), "maximum_reservation_usd": maximum}))
        return 0
    if not os.environ.get("OPENROUTER_API_KEY"):
        key_path = Path("~/.config/openrouter/key").expanduser()
        if not key_path.is_file():
            raise RuntimeError("OPENROUTER_API_KEY unavailable")
        os.environ["OPENROUTER_API_KEY"] = key_path.read_text().strip()
    probe = probe_llm_archive_destination()
    if not probe["ok"]:
        raise RuntimeError(probe["reason"])
    auth_path = output / "spend-authorization.json"
    authorization_settings = dict(pass_number=0, model=model, max_cost_usd=args.max_cost_usd,
                                  max_price_prompt=config.max_price_prompt,
                                  max_price_completion=config.max_price_completion)
    create_backfill_authorization(auth_path, **authorization_settings)
    authorization = BackfillAuthorization(auth_path, **authorization_settings)
    ledger = EvalCostLedger(args.max_cost_usd)
    report = {"status": "running", "responses": {}, "max_cost_usd": args.max_cost_usd}
    records = {r["id"]: r for r in manifest["records"]}
    for row in rows:
        key = str(row["id"])
        reservation = authorization.reserve(estimate_max_call_cost(config, prompt_for(row), retries=0))
        try:
            result = invoke_tracked(ledger, config, prompt_for(row), retries=0, archive_key=key)
            authorization.settle(reservation, result.metadata["cost"])
        except Exception as exc:
            authorization.forfeit(reservation)
            report.update(status="stopped", error=str(exc), stopped_at_source=row["id"])
            (output / "results.json").write_text(json.dumps(report, indent=2))
            print(json.dumps({"status": "stopped", "id": row["id"], "error": str(exc)}), flush=True)
            return 1
        report["responses"][key] = dict(
            parsed=result.parsed, raw_output=result.raw_output, success=result.success, error=result.error,
            usage=result.metadata, source=records[row["id"]],
            would_pass_prefilter=has_landuse_vocabulary(row["raw_text"]),
            format_review=evaluate_format(result.parsed, row["raw_text"], row["meeting_date"]),
        )
        report["ledger"] = ledger.summary()
        (output / "results.json").write_text(json.dumps(report, indent=2))
        print(json.dumps({"id": row["id"], "success": result.success,
                         "count": report["responses"][key]["format_review"]["extraction_count"],
                         "runtime_gate": report["responses"][key]["format_review"]["runtime_gate_passed"],
                         "spend_usd": ledger.spent_usd}), flush=True)
    report["status"] = "completed"
    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    (output / "results.json").write_text(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
