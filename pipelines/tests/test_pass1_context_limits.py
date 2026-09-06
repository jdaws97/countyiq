"""Pass 1 must defer oversized candidate components before any decision work."""

from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace

from countyiq.assets.enrichment import entity_verification as pass1
from countyiq.lib.pass1_entity_verification import (
    ENTITY_CANDIDATE_PAIRS_READY_QUERY,
    stable_cluster_key,
)


class _Log:
    def debug(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass


class _Database:
    def __init__(self, pairs):
        self.pairs = pairs

    def execute(self, sql, params=None):
        if sql == ENTITY_CANDIDATE_PAIRS_READY_QUERY:
            return [(True,)]
        if sql == pass1.CANDIDATE_CLUSTERS_QUERY:
            return self.pairs
        raise AssertionError(f"unexpected database query: {sql}")

    def dict_cursor(self):
        return nullcontext(object())


def _pairs(count: int) -> list[tuple[str, str]]:
    return [(f"NAME {index}", f"NAME {index + 1}") for index in range(count - 1)]


def _run_asset(monkeypatch, pairs, *, prompt, prior=None):
    calls = {"gather": 0, "invoke": 0, "record": 0, "replace": 0, "status": []}
    prior_hashes = (
        {
            stable_cluster_key(cluster): "accepted-input-hash"
            for cluster in pass1._build_clusters(pairs)
        }
        if prior
        else {}
    )
    monkeypatch.setattr(
        pass1, "inference_input_hash", lambda *args, **kwargs: "accepted-input-hash"
    )
    monkeypatch.setenv("COUNTYIQ_PASS1_TRIALS", "1")
    monkeypatch.setattr(
        pass1,
        "resolve_pass_harness",
        lambda *args, **kwargs: (
            SimpleNamespace(model_path="test/model", thinking=False),
            lambda *args, **kwargs: (
                calls.__setitem__("invoke", calls["invoke"] + 1)
                or SimpleNamespace(success=True, parsed={}, metadata={})
            ),
        ),
    )
    monkeypatch.setattr(
        pass1, "resolve_escalation_config", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        pass1, "fetch_reusable_pass_hashes", lambda *args, **kwargs: prior_hashes
    )
    monkeypatch.setattr(pass1, "fetch_prior_pass_attempts", lambda *args, **kwargs: {})
    monkeypatch.setattr(pass1, "check_error_budget", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        pass1,
        "gather_cluster_records",
        lambda *args: (
            calls.__setitem__("gather", calls["gather"] + 1)
            or {
                "candidate_names": [],
                "parcels": [],
                "tax_claims": [],
                "corporate_entities": [],
            }
        ),
    )
    monkeypatch.setattr(pass1, "build_entity_cluster_prompt", lambda records: prompt)
    monkeypatch.setattr(
        pass1, "build_deterministic_entity_resolution", lambda *args: None
    )
    monkeypatch.setattr(
        pass1,
        "parse_entity_verification_output",
        lambda output: {"entities": [], "rejected_matches": [], "abstentions": []},
    )
    monkeypatch.setattr(
        pass1,
        "merge_entity_trial_partitions",
        lambda parsed, names, **kwargs: {
            **parsed[0],
            "trial_stats": {"representative_trial_index": 0},
        },
    )
    monkeypatch.setattr(pass1, "validate_entity_membership", lambda *args: [])
    monkeypatch.setattr(
        pass1,
        "record_inference_decision",
        lambda *args, **kwargs: (
            calls.__setitem__("record", calls["record"] + 1)
            or SimpleNamespace(accepted=True, inference_id=1)
        ),
    )
    monkeypatch.setattr(
        pass1,
        "_replace_cluster_entities",
        lambda *args, **kwargs: calls.__setitem__("replace", calls["replace"] + 1) or 0,
    )
    monkeypatch.setattr(
        pass1,
        "_update_pass_status",
        lambda *args: calls["status"].append(args),
    )

    result = pass1.entity_verification.op.compute_fn.decorated_fn(
        SimpleNamespace(log=_Log()), _Database(pairs)
    )
    return calls, result


def test_over_name_limit_defers_before_gather_or_prior_hash_skip(monkeypatch):
    names = 41
    calls, result = _run_asset(monkeypatch, _pairs(names), prompt="unused", prior=True)

    assert (
        calls["gather"] == calls["invoke"] == calls["record"] == calls["replace"] == 0
    )
    assert len(calls["status"]) == 1
    assert calls["status"][0][1:] == (
        stable_cluster_key([f"NAME {index}" for index in range(names)]),
        1,
        "error",
        "",
        "deferred: context exceeds reviewed limits: candidate_names=41 limit=40",
    )
    assert result.metadata["clusters_deferred_context"].value == 1
    assert result.metadata["items_claimed"].value == 0


def test_over_character_limit_defers_before_prior_hash_skip_or_publication(monkeypatch):
    calls, result = _run_asset(
        monkeypatch,
        _pairs(2),
        prompt="x" * (pass1.MAX_DYNAMIC_PROMPT_CHARACTERS + 1),
        prior=True,
    )

    assert calls["gather"] == 1
    assert calls["invoke"] == calls["record"] == calls["replace"] == 0
    assert result.metadata["items_claimed"].value == 0
    assert calls["status"][0][3:] == (
        "error",
        "",
        "deferred: context exceeds reviewed limits: dynamic_prompt_characters=64001 limit=64000",
    )
    assert result.metadata["clusters_deferred_context"].value == 1


def test_context_limits_are_inclusive_at_the_boundary(monkeypatch):
    calls, result = _run_asset(
        monkeypatch,
        _pairs(pass1.MAX_CANDIDATE_NAMES_PER_CONTEXT),
        prompt="x" * pass1.MAX_DYNAMIC_PROMPT_CHARACTERS,
    )

    assert (
        calls["gather"] == calls["invoke"] == calls["record"] == calls["replace"] == 1
    )
    assert result.metadata["clusters_deferred_context"].value == 0
