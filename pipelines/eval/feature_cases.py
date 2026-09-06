"""Evaluate municipal-action and owner-summary cases using production contracts.

Default is no-spend prompt export. --responses scores archived JSON keyed by case
ID. Paid runs require --run, --model, --max-cost-usd, and a new --output file.
"""

import argparse
from dataclasses import replace
import json
import math
from pathlib import Path

from eval.fixture_io import load_frozen_cases
from eval.scoring import _contains_any, _forbidden_assertions
from countyiq.lib.pass2_batched_validation import (
    build_batched_signal_prompt,
    parse_batched_signal_output,
)
from countyiq.lib.pass3_owner_briefs import (
    build_owner_rollup_prompt,
    parse_owner_brief_output,
    OWNER_ROLLUP_SYSTEM_PROMPT,
)
from countyiq.lib.pass_schemas import PASS3B_OWNER_BRIEF_SCHEMA
from countyiq.lib.intelligence_integrity import validate_owner_brief_citations

FIXTURE = Path(__file__).with_name("fixtures") / "feature_cases.json"


def prompt_for(case):
    ctx = case["context"]
    return (
        build_batched_signal_prompt(ctx)
        if case["pass"] == "2"
        else build_owner_rollup_prompt(ctx["owner"], ctx["evidence"])
    )


def score(case, raw):
    ctx, expected = case["context"], case["expectations"]
    errors = []
    if case["pass"] == "2":
        from countyiq.lib.intelligence_integrity import validate_pass2_evidence_refs

        parsed = parse_batched_signal_output(raw, ctx["signals"])
        errors.extend(
            validate_pass2_evidence_refs(
                parsed.get("validations", []),
                ctx["signals"],
                ctx.get("context_signals", []),
                parsed.get("cross_signal_insight"),
            )
        )
    else:
        parsed = parse_owner_brief_output(raw)
        errors.extend(
            validate_owner_brief_citations(
                parsed,
                {r["signal_key"] for r in ctx["evidence"]},
                ctx["owner"]["pidns"],
            )
        )
        if parsed.get("portfolio_strategy") not in expected["allowed_strategies"]:
            errors.append("Unsupported portfolio strategy")
        if parsed.get("recommendation") not in {
            "investigate",
            "watch",
            "insufficient_evidence",
        }:
            errors.append("Unsupported recommendation")
    if parsed.get("error"):
        errors.append(parsed["error"])
    text = json.dumps(raw)
    errors.extend(
        "Unsupported claim: " + claim
        for claim in _forbidden_assertions(text, expected["forbidden_claims"])
    )
    for alternatives in expected.get("required_fact_groups", []):
        if not _contains_any(text, alternatives):
            errors.append("Missing fact: " + " / ".join(alternatives))
    return {"passed": not errors, "errors": errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--responses", type=Path)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--model")
    parser.add_argument("--max-cost-usd", type=float)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.run and args.responses:
        parser.error("Choose a paid run or archived responses, not both")
    cases = load_frozen_cases(FIXTURE)
    if args.run and (
        not args.model
        or not args.max_cost_usd
        or not math.isfinite(args.max_cost_usd)
        or args.max_cost_usd <= 0
        or not args.output
    ):
        parser.error(
            "Paid runs require a model, positive finite budget, and output path"
        )
    if args.output and args.output.exists():
        parser.error(
            "Output already exists; score archived responses instead of overwriting"
        )
    responses = json.loads(args.responses.read_text()) if args.responses else {}
    if not isinstance(responses, dict):
        parser.error("Responses must be an object keyed by case ID")
    responses = responses.get("responses", responses)
    if not isinstance(responses, dict):
        parser.error("Responses must be an object keyed by case ID")
    report = {
        "cases": {},
        "responses": responses,
        "paid": bool(args.run),
        "model": args.model,
    }
    if args.run:
        from eval.protocol import (
            build_production_eval_config,
            EvalCostLedger,
            invoke_tracked,
        )

        ledger = EvalCostLedger(args.max_cost_usd)
    for case in cases:
        if args.run:
            config = build_production_eval_config(
                args.model,
                2 if case["pass"] == "2" else 3,
                archive_label="feature_evaluation",
            )
            if case["pass"] == "3b":
                config = replace(
                    config,
                    system_prompt=OWNER_ROLLUP_SYSTEM_PROMPT,
                    json_schema=PASS3B_OWNER_BRIEF_SCHEMA,
                )
            try:
                result = invoke_tracked(
                    ledger, config, prompt_for(case), retries=0, archive_key=case["id"]
                )
            except Exception as exc:
                report["stopped"] = {"case": case["id"], "reason": str(exc)}
                report["ledger"] = ledger.summary()
                args.output.write_text(json.dumps(report, indent=2))
                print(json.dumps(report, indent=2))
                return 1
            responses[case["id"]] = result.parsed or {}
            report["cost_usd"] = ledger.spent_usd
            report.setdefault("usage", {})[case["id"]] = result.metadata
        raw = responses.get(case["id"])
        if args.responses and raw is None:
            report["cases"][case["id"]] = {
                "passed": False,
                "errors": ["Missing archived response"],
            }
            continue
        report["cases"][case["id"]] = (
            score(case, raw)
            if raw is not None
            else {"prompt": prompt_for(case), "evaluated": False}
        )
        if args.output:
            args.output.write_text(json.dumps(report, indent=2))
    if args.output:
        args.output.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return int(any(item.get("passed") is False for item in report["cases"].values()))


if __name__ == "__main__":
    raise SystemExit(main())
