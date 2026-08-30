#!/usr/bin/env python3
"""Validate and summarize CountyIQ delegated-agent outcome records."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


HERE = Path(__file__).resolve().parent
DEFAULT_POLICY = HERE / "policy.json"
DEFAULT_RUNS = HERE / "runs.jsonl"
DEFAULT_CASES = HERE / "eval_cases.json"

MODELS = {"luna", "terra", "root"}
TASK_CLASSES = {
    "atomic_change",
    "bounded_extraction",
    "discovery",
    "failure_triage",
    "scoped_implementation",
    "checklist_review",
    "other",
}
RISKS = {"low", "medium", "high"}
VERIFIER_TYPES = {"deterministic", "sampled", "manual"}
REGRESSION_RESULTS = {"pass", "fail", "not_required", "not_run"}
ROOT_REVIEWS = {"none", "receipt", "targeted", "full"}
EXPECTED_ROUTES = {"direct_tool", "luna", "terra", "root"}
WORK_KINDS = {"read_only", "code", "docs", "policy"}
PRE_RUN_VERDICTS = {"probation", "trusted", "suspended"}

REQUIRED_FIELDS = {
    "schema_version",
    "id",
    "timestamp",
    "model",
    "task_class",
    "work_kind",
    "changed_files",
    "pre_run_verdict",
    "risk",
    "claimed_success",
    "contract_pass",
    "scope_pass",
    "verifier_type",
    "verifier_pass",
    "regression",
    "accepted",
    "rework_required",
    "escaped_defect",
    "root_review",
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: root must be an object")
    return value


def parse_timestamp(value: str) -> datetime:
    if "T" not in value:
        raise ValueError("timestamp must be RFC 3339 with a T separator")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("timestamp must be valid RFC 3339") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone offset")
    return parsed


def load_runs(path: Path) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    seen: set[str] = set()
    previous_timestamp: datetime | None = None
    with path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                continue
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: {exc.msg}") from exc
            errors = validate_run(record)
            if errors:
                raise ValueError(f"{path}:{line_number}: {'; '.join(errors)}")
            if record["id"] in seen:
                raise ValueError(f"{path}:{line_number}: duplicate id {record['id']!r}")
            parsed_timestamp = parse_timestamp(record["timestamp"])
            if previous_timestamp is not None and parsed_timestamp < previous_timestamp:
                raise ValueError(f"{path}:{line_number}: timestamps must be append-ordered")
            previous_timestamp = parsed_timestamp
            seen.add(record["id"])
            runs.append(record)
    return runs


def validate_run(record: Any) -> list[str]:
    if not isinstance(record, dict):
        return ["record must be an object"]

    errors: list[str] = []
    missing = sorted(REQUIRED_FIELDS - record.keys())
    if missing:
        errors.append(f"missing fields: {', '.join(missing)}")
        return errors

    if record["schema_version"] != 1:
        errors.append("schema_version must be 1")
    for field in ("id", "timestamp"):
        if not isinstance(record[field], str) or not record[field].strip():
            errors.append(f"{field} must be a non-empty string")
    if isinstance(record["timestamp"], str) and record["timestamp"].strip():
        try:
            parse_timestamp(record["timestamp"])
        except ValueError as exc:
            errors.append(str(exc))
    if not isinstance(record["model"], str) or record["model"] not in MODELS:
        errors.append(f"model must be one of {sorted(MODELS)}")
    if not isinstance(record["task_class"], str) or record["task_class"] not in TASK_CLASSES:
        errors.append(f"task_class must be one of {sorted(TASK_CLASSES)}")
    if not isinstance(record["work_kind"], str) or record["work_kind"] not in WORK_KINDS:
        errors.append(f"work_kind must be one of {sorted(WORK_KINDS)}")
    if not isinstance(record["pre_run_verdict"], str) or record["pre_run_verdict"] not in PRE_RUN_VERDICTS:
        errors.append(f"pre_run_verdict must be one of {sorted(PRE_RUN_VERDICTS)}")
    if not isinstance(record["risk"], str) or record["risk"] not in RISKS:
        errors.append(f"risk must be one of {sorted(RISKS)}")
    if not isinstance(record["verifier_type"], str) or record["verifier_type"] not in VERIFIER_TYPES:
        errors.append(f"verifier_type must be one of {sorted(VERIFIER_TYPES)}")
    if not isinstance(record["regression"], str) or record["regression"] not in REGRESSION_RESULTS:
        errors.append(f"regression must be one of {sorted(REGRESSION_RESULTS)}")
    if not isinstance(record["root_review"], str) or record["root_review"] not in ROOT_REVIEWS:
        errors.append(f"root_review must be one of {sorted(ROOT_REVIEWS)}")

    boolean_fields = {
        "claimed_success",
        "contract_pass",
        "scope_pass",
        "verifier_pass",
        "accepted",
        "rework_required",
        "escaped_defect",
    }
    for field in boolean_fields:
        if not isinstance(record[field], bool):
            errors.append(f"{field} must be boolean")

    changed_files = record["changed_files"]
    if not isinstance(changed_files, list) or any(
        not isinstance(path, str) or not path.strip() for path in changed_files
    ):
        errors.append("changed_files must be an array of non-empty paths")
    elif len(changed_files) != len(set(changed_files)):
        errors.append("changed_files must not contain duplicates")
    elif record["work_kind"] == "code" and not changed_files:
        errors.append("code work requires at least one changed file")
    elif record["work_kind"] == "read_only" and changed_files:
        errors.append("read_only work cannot list changed files")

    if record["accepted"] is True and record["verifier_pass"] is not True:
        errors.append("accepted work requires verifier_pass=true")
    if record["accepted"] is True and record["regression"] in ("fail", "not_run"):
        errors.append("accepted work requires regression pass or not_required")
    if record["accepted"] is True and record["root_review"] == "none" and record["verifier_type"] != "deterministic":
        errors.append("acceptance without root review requires a deterministic verifier")
    if record["accepted"] is True and record["work_kind"] == "code" and record["regression"] != "pass":
        errors.append("accepted code work requires regression=pass")
    if (
        record["accepted"] is True
        and record["verifier_type"] == "sampled"
        and record["pre_run_verdict"] != "trusted"
        and record["root_review"] != "full"
    ):
        errors.append("sampled work on probation or suspension requires full root review")
    if record["escaped_defect"] is True and record["accepted"] is not True:
        errors.append("an escaped defect requires accepted=true")

    tokens = record.get("tokens")
    if tokens is not None:
        if not isinstance(tokens, dict):
            errors.append("tokens must be an object when present")
        else:
            allowed = {"agent_prompt", "agent_output", "root_verification", "root_solo_estimate"}
            unknown = sorted(str(field) for field in tokens if not isinstance(field, str) or field not in allowed)
            if unknown:
                errors.append(f"unknown token fields: {', '.join(unknown)}")
            for field, value in tokens.items():
                if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                    errors.append(f"tokens.{field} must be a non-negative integer or null")

    output_chars = record.get("agent_output_chars")
    if output_chars is not None and (
        not isinstance(output_chars, int) or isinstance(output_chars, bool) or output_chars < 0
    ):
        errors.append("agent_output_chars must be a non-negative integer")
    return errors


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    window = policy.get("rolling_window")
    if not isinstance(window, int) or isinstance(window, bool) or window <= 0:
        errors.append("rolling_window must be a positive integer")
    work_kinds = policy.get("work_kinds")
    if not isinstance(work_kinds, list) or any(not isinstance(value, str) for value in work_kinds) or set(work_kinds) != WORK_KINDS:
        errors.append(f"work_kinds must equal {sorted(WORK_KINDS)}")
    verdicts = policy.get("pre_run_verdicts")
    if not isinstance(verdicts, list) or any(not isinstance(value, str) for value in verdicts) or set(verdicts) != PRE_RUN_VERDICTS:
        errors.append(f"pre_run_verdicts must equal {sorted(PRE_RUN_VERDICTS)}")

    threshold_names = {
        "min_samples",
        "min_wilson_lower_bound",
        "min_claim_precision",
        "min_scope_rate",
        "max_rework_rate",
        "max_escape_rate",
    }
    thresholds = policy.get("trust_thresholds")
    if not isinstance(thresholds, dict) or set(thresholds) != threshold_names:
        errors.append(f"trust_thresholds must contain exactly {sorted(threshold_names)}")
    else:
        samples = thresholds["min_samples"]
        if not isinstance(samples, int) or isinstance(samples, bool) or samples <= 0:
            errors.append("min_samples must be a positive integer")
        for name in threshold_names - {"min_samples"}:
            value = thresholds[name]
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 1:
                errors.append(f"{name} must be a number in [0, 1]")

    routes = policy.get("routes")
    if not isinstance(routes, dict) or set(routes) != EXPECTED_ROUTES:
        errors.append(f"routes must contain exactly {sorted(EXPECTED_ROUTES)}")
    else:
        for route_name in ("luna", "terra"):
            route = routes[route_name]
            task_classes = route.get("task_classes") if isinstance(route, dict) else None
            if (
                not isinstance(task_classes, list)
                or not task_classes
                or any(not isinstance(value, str) for value in task_classes)
                or not set(task_classes) <= TASK_CLASSES
            ):
                errors.append(f"routes.{route_name}.task_classes must be known task classes")
    domains = policy.get("hard_root_domains")
    if not isinstance(domains, list) or not domains or any(
        not isinstance(domain, str) or not domain.strip() for domain in domains
    ):
        errors.append("hard_root_domains must be a non-empty string array")
    return errors


def validate_cases(path: Path, expected_routes: set[str] = EXPECTED_ROUTES) -> list[dict[str, Any]]:
    payload = load_json(path)
    if payload.get("schema_version") != 1:
        raise ValueError(f"{path}: schema_version must be 1")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"{path}: cases must be a non-empty array")

    seen: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"{path}: case {index} must be an object")
        missing = {"id", "prompt", "expected_route", "risk", "oracle"} - case.keys()
        if missing:
            raise ValueError(f"{path}: case {index} missing {sorted(missing)}")
        for field in ("id", "prompt", "oracle"):
            if not isinstance(case[field], str) or not case[field].strip():
                raise ValueError(f"{path}: case {index} field {field} must be non-empty")
        if case["id"] in seen:
            raise ValueError(f"{path}: duplicate case id {case['id']!r}")
        seen.add(case["id"])
        if not isinstance(case["expected_route"], str) or case["expected_route"] not in expected_routes:
            raise ValueError(f"{path}: case {case['id']} has invalid expected_route")
        if not isinstance(case["risk"], str) or case["risk"] not in RISKS:
            raise ValueError(f"{path}: case {case['id']} has invalid risk")
    return cases


def verified_success(record: dict[str, Any]) -> bool:
    return bool(
        record["claimed_success"]
        and record["contract_pass"]
        and record["scope_pass"]
        and record["verifier_pass"]
        and record["regression"] in {"pass", "not_required"}
        and record["accepted"]
        and not record["rework_required"]
        and not record["escaped_defect"]
    )


def wilson_lower_bound(successes: int, total: int, z: float = 1.96) -> float:
    if total == 0:
        return 0.0
    proportion = successes / total
    denominator = 1 + z * z / total
    centre = proportion + z * z / (2 * total)
    adjustment = z * math.sqrt((proportion * (1 - proportion) + z * z / (4 * total)) / total)
    return (centre - adjustment) / denominator


def safe_rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def token_savings(record: dict[str, Any]) -> int | None:
    tokens = record.get("tokens")
    if not isinstance(tokens, dict):
        return None
    required = ("agent_prompt", "agent_output", "root_verification", "root_solo_estimate")
    if any(not isinstance(tokens.get(field), int) for field in required):
        return None
    return tokens["root_solo_estimate"] - (
        tokens["agent_prompt"] + tokens["agent_output"] + tokens["root_verification"]
    )


def summarize(records: Iterable[dict[str, Any]], policy: dict[str, Any]) -> dict[str, Any]:
    ordered = sorted(records, key=lambda item: parse_timestamp(item["timestamp"]))
    window = int(policy["rolling_window"])
    recent = ordered[-window:]
    total = len(recent)
    successes = sum(verified_success(record) for record in recent)
    claimed = [record for record in recent if record["claimed_success"]]
    claims_upheld = sum(verified_success(record) for record in claimed)
    scope_passes = sum(record["scope_pass"] for record in recent)
    reworks = sum(record["rework_required"] for record in recent)
    escapes = sum(record["escaped_defect"] for record in recent)
    no_full_review = sum(record["root_review"] != "full" for record in recent if record["accepted"])
    accepted = sum(record["accepted"] for record in recent)

    output_sizes = [record["agent_output_chars"] for record in recent if "agent_output_chars" in record]
    savings = [value for record in recent if (value := token_savings(record)) is not None]

    result = {
        "n": total,
        "pass_rate": safe_rate(successes, total),
        "wilson_lb": wilson_lower_bound(successes, total),
        "claim_precision": safe_rate(claims_upheld, len(claimed)),
        "scope_rate": safe_rate(scope_passes, total),
        "rework_rate": safe_rate(reworks, total),
        "escape_rate": safe_rate(escapes, total),
        "accepted_without_full_review_rate": safe_rate(no_full_review, accepted),
        "median_output_chars": statistics.median(output_sizes) if output_sizes else None,
        "median_token_savings": statistics.median(savings) if savings else None,
    }
    result["verdict"] = trust_verdict(result, policy["trust_thresholds"])
    return result


def trust_verdict(summary: dict[str, Any], thresholds: dict[str, Any]) -> str:
    if summary["n"] < thresholds["min_samples"]:
        return "probation"
    trusted = (
        summary["wilson_lb"] >= thresholds["min_wilson_lower_bound"]
        and summary["claim_precision"] >= thresholds["min_claim_precision"]
        and summary["scope_rate"] >= thresholds["min_scope_rate"]
        and summary["rework_rate"] <= thresholds["max_rework_rate"]
        and summary["escape_rate"] <= thresholds["max_escape_rate"]
    )
    return "trusted" if trusted else "suspended"


def grouped_summaries(runs: list[dict[str, Any]], policy: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        groups[(run["model"], run["task_class"])].append(run)
    return {key: summarize(records, policy) for key, records in sorted(groups.items())}


def percentage(value: float) -> str:
    return f"{value * 100:.1f}%"


def print_report(runs: list[dict[str, Any]], policy: dict[str, Any]) -> None:
    print("| Model | Task class | n | Pass | Wilson LB | Claim precision | Scope | Rework | Escape | Verdict |")
    print("|---|---|---:|---:|---:|---:|---:|---:|---:|---|")
    for (model, task_class), summary in grouped_summaries(runs, policy).items():
        print(
            f"| {model} | {task_class} | {summary['n']} | {percentage(summary['pass_rate'])} "
            f"| {percentage(summary['wilson_lb'])} | {percentage(summary['claim_precision'])} "
            f"| {percentage(summary['scope_rate'])} | {percentage(summary['rework_rate'])} "
            f"| {percentage(summary['escape_rate'])} | {summary['verdict']} |"
        )

    savings = [value for run in runs if (value := token_savings(run)) is not None]
    print()
    if savings:
        print(f"Token savings coverage: {len(savings)}/{len(runs)} runs; median {statistics.median(savings):g} tokens.")
    else:
        print(f"Token savings coverage: 0/{len(runs)} runs (quality metrics remain valid).")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate", help="Validate policy, run ledger, and eval cases")
    subparsers.add_parser("report", help="Print model/task-class trust metrics")
    gate = subparsers.add_parser("gate", help="Exit 0 only when a model/task class is trusted")
    gate.add_argument("--model", choices=sorted(MODELS), required=True)
    gate.add_argument("--task-class", choices=sorted(TASK_CLASSES), required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        policy = load_json(args.policy)
        policy_errors = validate_policy(policy)
        if policy_errors:
            raise ValueError(f"{args.policy}: {'; '.join(policy_errors)}")
        runs = load_runs(args.runs)
        cases = validate_cases(args.cases, set(policy["routes"]))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.command == "validate":
        print(f"OK: {len(runs)} runs, {len(cases)} eval cases, policy schema v1")
        return 0
    if args.command == "report":
        print_report(runs, policy)
        return 0

    matching = [
        run for run in runs if run["model"] == args.model and run["task_class"] == args.task_class
    ]
    summary = summarize(matching, policy)
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary["verdict"] == "trusted" else 1


if __name__ == "__main__":
    raise SystemExit(main())
