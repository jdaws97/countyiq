"""Compare native subscription models on frozen Pass 1/2 fixtures.

Uses the production prompts, schemas, parsers and deterministic scorers. Model
responses remain local evaluation artifacts; this module performs no database
writes and never dispatches an API fallback.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from countyiq.lib.intelligence_integrity import (
    validate_entity_membership,
    validate_pass2_evidence_refs,
)
from countyiq.lib.llm_harness import HarnessConfig
from countyiq.lib.pass1_entity_verification import (
    build_entity_cluster_prompt,
    parse_entity_verification_output,
)
from countyiq.lib.pass2_batched_validation import (
    build_batched_signal_prompt,
    parse_batched_signal_output,
)
from countyiq.lib.subscription_backfill import SubscriptionAuthor

from eval.challenger import _fixture_cluster_names
from eval.feature_cases import score as score_feature
from eval.fixture_io import load_frozen_cases
from eval.protocol import PASS_EVAL_PROTOCOLS
from eval.scoring import enforce_production_gate, score_pass1, score_pass2

FIXTURES = Path(__file__).with_name("fixtures")
MODELS = ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol", "gpt-6-astra")


def prepare_cases(pass_number: int, *, expanded: bool = False) -> list[dict]:
    if pass_number == 1:
        paths = [FIXTURES / "p1_frozen.json"]
    else:
        paths = [FIXTURES / "p2_frozen.json"]
        if expanded:
            paths.extend(
                [
                    FIXTURES / "p2_expanded_stability20.json",
                    FIXTURES / "feature_cases.json",
                ]
            )
    prepared = []
    for path in paths:
        for case in load_frozen_cases(path):
            if path.name == "feature_cases.json" and case["pass"] != "2":
                continue
            context = case["context"]
            if pass_number == 1:
                names = _fixture_cluster_names(case)
                context = {**context, "candidate_names": names}
                prompt = build_entity_cluster_prompt(context)
            else:
                prompt = build_batched_signal_prompt(context)
            prepared.append(
                {
                    "case": case,
                    "context": context,
                    "prompt": prompt,
                    "fixture": path.name,
                }
            )
    return prepared


def score_response(pass_number: int, item: dict, raw: dict) -> tuple[dict, dict]:
    case, context = item["case"], item["context"]
    if pass_number == 1:
        parsed = parse_entity_verification_output(raw)
        errors = validate_entity_membership(parsed, context, context["candidate_names"])
        score = score_pass1(parsed, {"records": case["context"], **case})
    else:
        parsed = parse_batched_signal_output(raw, context["signals"])
        errors = validate_pass2_evidence_refs(
            parsed.get("validations", []),
            context["signals"],
            context.get("context_signals", []),
            parsed.get("cross_signal_insight"),
        )
        if item["fixture"] == "feature_cases.json":
            feature = score_feature(case, raw)
            score = {
                "gold_pass": feature["passed"],
                "feature_errors": feature["errors"],
            }
        else:
            score = score_pass2(parsed, case)
    return parsed, enforce_production_gate(score, errors)


def run(args) -> dict:
    protocol = PASS_EVAL_PROTOCOLS[args.pass_number]
    config = HarnessConfig(
        model_path="codex/subscription:" + args.model,
        max_tokens=protocol.max_tokens,
        reasoning_effort=args.effort,
        json_schema=protocol.json_schema,
        system_prompt=protocol.system_prompt,
    )
    author = SubscriptionAuthor(
        args.output / "receipts", model=args.model, timeout=1800
    )
    items = prepare_cases(args.pass_number, expanded=args.expanded)
    for item in items:
        case = item["case"]
        item["prompt"] += (
            "\nIndependent review identifier: subscription-eval:"
            f"{case['context_sha256']}:{case['id']}:trial{args.trial}"
        )
    report = {
        "pass_number": args.pass_number,
        "model": args.model,
        "effort": args.effort,
        "trial": args.trial,
        "api_calls": 0,
        "billing": "chatgpt_subscription",
        "cases": [],
        "batch_failures": [],
    }
    started = time.monotonic()
    for start in range(0, len(items), args.batch_size):
        batch = items[start : start + args.batch_size]
        try:
            author.prefetch(config, [item["prompt"] for item in batch])
        except ValueError as error:
            report["batch_failures"].append(str(error))
            print(json.dumps({"batch_split_reason": str(error)}), flush=True)
        for item in batch:
            author.receipts.clear()
            result = author(config, item["prompt"])
            parsed, score = score_response(args.pass_number, item, result.parsed or {})
            row = {
                "case_id": item["case"]["id"],
                "fixture": item["fixture"],
                "context_sha256": item["case"]["context_sha256"],
                "success": result.success,
                "raw": result.parsed,
                "parsed": parsed,
                "score": score,
                "provenance": author.provenance(),
            }
            report["cases"].append(row)
            report["elapsed_seconds"] = round(time.monotonic() - started, 3)
            (args.output / "results.json").write_text(json.dumps(report, indent=2))
            print(
                json.dumps(
                    {"case_id": row["case_id"], "gold_pass": score["gold_pass"]}
                ),
                flush=True,
            )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=MODELS, required=True)
    parser.add_argument("--pass-number", type=int, choices=(1, 2), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--effort", choices=("low", "medium", "high"), default="medium")
    parser.add_argument("--batch-size", type=int, choices=range(1, 9), default=8)
    parser.add_argument("--trial", type=int, default=1)
    parser.add_argument("--expanded", action="store_true")
    args = parser.parse_args()
    if args.trial < 1:
        parser.error("--trial must be positive")
    report = run(args)
    print(
        json.dumps(
            {
                "cases": len(report["cases"]),
                "passed": sum(row["score"]["gold_pass"] for row in report["cases"]),
                "elapsed_seconds": report["elapsed_seconds"],
            }
        )
    )


if __name__ == "__main__":
    main()
