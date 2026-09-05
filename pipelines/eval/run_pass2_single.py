#!/usr/bin/env python3
"""Run one Pass 2 model once per frozen case without duplicate incumbent calls."""

from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from countyiq.lib.intelligence_integrity import validate_pass2_evidence_refs
from countyiq.lib.pass2_batched_validation import (
    build_batched_signal_prompt,
    parse_batched_signal_output,
)
from countyiq.lib.pass_llm_config import resolve_pass_model
from eval.challenger import (
    FIXTURES,
    RESULTS,
    _mk_config,
    _parse,
    _pass2_prompt_one,
    summarize_pass2_gold,
)
from eval.fixture_io import load_frozen_cases
from eval.protocol import EvalCostLedger
from eval.scoring import enforce_production_gate, score_pass2


def _archive_index(since: str | None) -> dict[tuple[str, str], dict]:
    if not since:
        return {}
    index = {}
    for path in Path("archives/challenger").rglob("*.json"):
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if str(payload.get("archived_at") or "") < since:
            continue
        key = payload.get("key")
        prompt = payload.get("prompt")
        if isinstance(key, str) and isinstance(prompt, str):
            index[(key, prompt)] = payload
    return index


def _archived_result(payload: dict, context: dict) -> dict:
    raw_output = str(payload.get("raw_output") or "")
    parsed = parse_batched_signal_output(_parse(raw_output) or {}, context["signals"])
    errors = validate_pass2_evidence_refs(
        parsed.get("validations", []),
        context["signals"],
        context.get("context_signals", []),
        parsed.get("cross_signal_insight"),
    )
    metadata = payload.get("metadata") or {}
    return {
        "success": not metadata.get("error"),
        "error": metadata.get("error"),
        "usage": {**metadata, "reused_archive": True},
        "parsed": parsed,
        "output": json.dumps(parsed),
        "production_gate_errors": errors,
        "reused_archive": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture",
        type=Path,
        default=FIXTURES / "p2_expanded_frozen.json",
    )
    parser.add_argument("--model", default=resolve_pass_model(2))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-cost-usd", type=float, default=0.15)
    parser.add_argument(
        "--case-id",
        action="append",
        dest="case_ids",
        help="Run only this fixture case ID; repeat for multiple cases.",
    )
    parser.add_argument(
        "--reuse-archives-since",
        default=None,
        help="Reuse matching prompt archives at or after this ISO timestamp.",
    )
    args = parser.parse_args()
    if args.workers <= 0 or args.max_cost_usd <= 0:
        raise SystemExit("workers and max-cost-usd must be positive")
    if not os.environ.get("OPENROUTER_API_KEY"):
        key_file = Path("~/.config/openrouter/key").expanduser()
        if not key_file.exists():
            raise SystemExit("OPENROUTER_API_KEY not set")
        os.environ["OPENROUTER_API_KEY"] = key_file.read_text().strip()

    cases = load_frozen_cases(args.fixture)
    if args.case_ids:
        requested = set(args.case_ids)
        available = {case["id"] for case in cases}
        unknown = sorted(requested - available)
        if unknown:
            raise SystemExit(f"Unknown case IDs: {', '.join(unknown)}")
        cases = [case for case in cases if case["id"] in requested]
    ledger = EvalCostLedger(max_cost_usd=args.max_cost_usd)
    config = _mk_config(args.model, 2, max_tokens=4096, effort="low")
    archives = _archive_index(args.reuse_archives_since)
    rows = []

    def run_case(case):
        context = case["context"]
        prompt = build_batched_signal_prompt(context)
        archive_key = f"chal_p2:{case['id']}:{args.model}"
        archived = archives.get((archive_key, prompt))
        result = (
            _archived_result(archived, context)
            if archived
            else _pass2_prompt_one(config, prompt, context, case["id"], ledger)
        )
        result["score"] = enforce_production_gate(
            score_pass2(result["parsed"], case),
            result["production_gate_errors"],
        )
        return {
            "case_id": case["id"],
            "case_type": case["case_type"],
            "context_sha256": case["context_sha256"],
            "model": result,
        }

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(run_case, case): case["id"] for case in cases}
        for index, future in enumerate(as_completed(futures), 1):
            row = future.result()
            rows.append(row)
            print(
                f"{index:03d}/{len(cases)} {row['case_id']} "
                f"pass={row['model']['score']['gold_pass']}"
            )
    rows.sort(key=lambda row: row["case_id"])

    paired_shape = [
        {
            "challenger": {"score": row["model"]["score"]},
            "incumbent": {"score": row["model"]["score"]},
        }
        for row in rows
    ]
    summary = summarize_pass2_gold(paired_shape)
    summary = {
        key.removeprefix("challenger_"): value
        for key, value in summary.items()
        if key == "n" or key.startswith("challenger_")
    }
    summary["production_gate_passes"] = sum(
        not row["model"]["production_gate_errors"] for row in rows
    )
    summary["spend"] = ledger.summary()
    summary["failed_case_ids"] = [
        row["case_id"] for row in rows if not row["model"]["score"]["gold_pass"]
    ]
    output = {
        "model": args.model,
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "dataset_mode": "frozen_rubric_single_model",
        "fixture_file": str(args.fixture),
        "summary": summary,
        "case_rows": rows,
    }
    RESULTS.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = RESULTS / f"pass2_single_{args.model.replace('/', '_')}_{stamp}.json"
    path.write_text(json.dumps(output, indent=2, default=str))
    print(json.dumps(summary, indent=2))
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
