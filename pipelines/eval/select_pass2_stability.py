#!/usr/bin/env python3
"""Select the highest-disagreement expanded Pass 2 cases for repeat trials."""

from __future__ import annotations

import argparse
import json
from hashlib import md5
from pathlib import Path

from eval.fixture_io import load_frozen_cases


def disagreement_score(row: dict) -> int:
    challenger = row["challenger"]["score"]["signal_scores"]
    incumbent = row["incumbent"]["score"]["signal_scores"]
    score = 0
    for key in set(challenger) | set(incumbent):
        left, right = challenger.get(key, {}), incumbent.get(key, {})
        score += 2 * (bool(left.get("pass")) != bool(right.get("pass")))
        score += bool(left.get("decision_pass")) != bool(right.get("decision_pass"))
        score += bool(left.get("required_facts_pass")) != bool(
            right.get("required_facts_pass")
        )
        score += bool(left.get("forbidden_claims_found")) != bool(
            right.get("forbidden_claims_found")
        )
    return score


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=20)
    args = parser.parse_args()

    result = json.loads(args.result.read_text())
    cases = {case["id"]: case for case in load_frozen_cases(args.fixture)}
    rows = result["pass2"]["case_rows"]
    ranked = sorted(
        rows,
        key=lambda row: (
            -disagreement_score(row),
            -len(cases[row["case_id"]]["signal_combination"]),
            md5(row["case_id"].encode()).hexdigest(),
        ),
    )
    selected_ids = [row["case_id"] for row in ranked[: args.count]]
    payload = {
        "version": 1,
        "built_at": "2026-08-30",
        "promotion_status": "diagnostic_stability_subset",
        "source_fixture": str(args.fixture),
        "source_result": str(args.result),
        "selection": "highest paired scoring disagreement, then cardinality and stable hash",
        "cases": [cases[case_id] for case_id in selected_ids],
    }
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"Wrote {args.output} ({len(selected_ids)} cases)")
    print(" ".join(selected_ids))


if __name__ == "__main__":
    main()
