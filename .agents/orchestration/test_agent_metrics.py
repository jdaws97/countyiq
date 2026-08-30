#!/usr/bin/env python3
"""Unit tests for the dependency-free agent metrics checker."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import agent_metrics


def passing_run(index: int) -> dict[str, object]:
    return {
        "schema_version": 1,
        "id": f"run-{index}",
        "timestamp": f"2026-08-{index + 1:02d}T00:00:00-04:00",
        "model": "luna",
        "task_class": "atomic_change",
        "work_kind": "code",
        "changed_files": ["pipelines/countyiq/example.py"],
        "pre_run_verdict": "probation",
        "risk": "low",
        "claimed_success": True,
        "contract_pass": True,
        "scope_pass": True,
        "verifier_type": "deterministic",
        "verifier_pass": True,
        "regression": "pass",
        "accepted": True,
        "rework_required": False,
        "escaped_defect": False,
        "root_review": "none",
    }


class ValidationTests(unittest.TestCase):
    def test_rejects_unverified_acceptance(self) -> None:
        record = passing_run(0)
        record["verifier_pass"] = False
        self.assertIn("accepted work requires verifier_pass=true", agent_metrics.validate_run(record))

    def test_rejects_sampled_acceptance_without_review(self) -> None:
        record = passing_run(0)
        record["verifier_type"] = "sampled"
        record["root_review"] = "targeted"
        self.assertTrue(any("full root review" in error for error in agent_metrics.validate_run(record)))

    def test_trusted_sampled_acceptance_allows_targeted_review(self) -> None:
        record = passing_run(0)
        record["verifier_type"] = "sampled"
        record["pre_run_verdict"] = "trusted"
        record["root_review"] = "targeted"
        self.assertEqual(agent_metrics.validate_run(record), [])

    def test_code_work_requires_regression_pass(self) -> None:
        record = passing_run(0)
        record["regression"] = "not_required"
        self.assertTrue(any("accepted code work" in error for error in agent_metrics.validate_run(record)))

    def test_timestamp_requires_timezone(self) -> None:
        record = passing_run(0)
        record["timestamp"] = "2026-08-01T00:00:00"
        self.assertTrue(any("timezone" in error for error in agent_metrics.validate_run(record)))

    def test_ledger_rejects_backdated_append(self) -> None:
        first = passing_run(1)
        second = passing_run(0)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runs.jsonl"
            path.write_text(json.dumps(first) + "\n" + json.dumps(second) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "append-ordered"):
                agent_metrics.load_runs(path)

    def test_token_savings(self) -> None:
        record = passing_run(0)
        record["tokens"] = {
            "agent_prompt": 100,
            "agent_output": 200,
            "root_verification": 150,
            "root_solo_estimate": 1000,
        }
        self.assertEqual(agent_metrics.token_savings(record), 550)

    def test_policy_thresholds_are_validated(self) -> None:
        policy = agent_metrics.load_json(agent_metrics.DEFAULT_POLICY)
        policy["trust_thresholds"]["min_claim_precision"] = 1.5
        self.assertTrue(any("min_claim_precision" in error for error in agent_metrics.validate_policy(policy)))

    def test_malformed_policy_returns_errors_instead_of_crashing(self) -> None:
        policy = agent_metrics.load_json(agent_metrics.DEFAULT_POLICY)
        policy["work_kinds"] = None
        policy["routes"]["luna"]["task_classes"] = [{}]
        errors = agent_metrics.validate_policy(policy)
        self.assertTrue(any("work_kinds" in error for error in errors))
        self.assertTrue(any("task_classes" in error for error in errors))


class TrustTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = agent_metrics.load_json(agent_metrics.DEFAULT_POLICY)

    def test_ten_perfect_runs_become_trusted(self) -> None:
        summary = agent_metrics.summarize([passing_run(index) for index in range(10)], self.policy)
        self.assertEqual(summary["verdict"], "trusted")

    def test_one_false_claim_suspends_small_sample(self) -> None:
        records = [passing_run(index) for index in range(10)]
        records[-1]["verifier_pass"] = False
        records[-1]["accepted"] = False
        records[-1]["rework_required"] = True
        summary = agent_metrics.summarize(records, self.policy)
        self.assertEqual(summary["verdict"], "suspended")

    def test_fewer_than_ten_runs_remain_on_probation(self) -> None:
        summary = agent_metrics.summarize([passing_run(index) for index in range(9)], self.policy)
        self.assertEqual(summary["verdict"], "probation")


if __name__ == "__main__":
    unittest.main()
