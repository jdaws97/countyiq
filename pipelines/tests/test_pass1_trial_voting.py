"""Pass 1 N-trial partition voting, escalation config, and hash prefetch.

Covers the 2026-08-06 decision (docs/decisions.md): run Pass 1 with N-trial
voting — majority pair verdicts win, disagreement demotes to abstention —
plus the COUNTYIQ_PASS1_ESCALATION_MODEL cascade from docs/open-items.md.
"""

import pytest

from countyiq.lib.intelligence_common import fetch_prior_pass_hashes
from countyiq.lib.llm_harness import HarnessConfig
from countyiq.lib.pass_llm_config import resolve_escalation_config
from countyiq.lib.pass1_entity_verification import (
    entity_trial_majority_decided,
    merge_entity_trial_partitions,
)


def _entity(canonical, corporate=(), proceedings=()):
    return {
        "canonical_name": canonical,
        "entity_type": "llc",
        "confidence": 0.9,
        "reasoning": "r",
        "linked_records": {
            "corporate_entities": list(corporate),
            "proceedings": list(proceedings),
        },
        "relationships": [],
        "portfolio_summary": {},
    }


def _parsed(entities, rejected=(), abstentions=()):
    return {
        "entities": entities,
        "rejected_matches": list(rejected),
        "abstentions": list(abstentions),
    }


NAMES = ["ALPHA LLC", "BETA LLC", "GAMMA LLC"]


class TestMergeEntityTrialPartitions:
    @pytest.mark.parametrize(("valid", "target"), [(1, 3), (2, 5)])
    def test_failed_trials_cannot_reduce_publication_quorum(self, valid, target):
        grouped = _parsed([_entity("ALPHA LLC", corporate=["BETA LLC"])])
        with pytest.raises(ValueError, match="Insufficient validated trials"):
            merge_entity_trial_partitions(
                [grouped] * valid, ["ALPHA LLC", "BETA LLC"], target_trials=target
            )

    def test_failed_trials_cannot_turn_two_votes_into_five_trial_majority(self):
        grouped = _parsed([_entity("ALPHA LLC", corporate=["BETA LLC"])])
        split = _parsed([_entity("ALPHA LLC"), _entity("BETA LLC")])
        result = merge_entity_trial_partitions(
            [grouped, grouped, split],
            ["ALPHA LLC", "BETA LLC"],
            target_trials=5,
        )
        assert result["entities"] == split["entities"]
        assert result["trial_stats"]["representative_trial_index"] == 2
        assert result["trial_stats"]["target_trials"] == 5
        assert result["trial_stats"]["n_trials"] == 3

    def test_three_valid_merge_votes_are_enough_for_five_trial_quorum(self):
        grouped = _parsed([_entity("ALPHA LLC", corporate=["BETA LLC"])])
        result = merge_entity_trial_partitions(
            [grouped] * 3, ["ALPHA LLC", "BETA LLC"], target_trials=5
        )
        assert result["entities"] == grouped["entities"]
        assert result["trial_stats"]["target_trials"] == 5

    def test_single_trial_passthrough(self):
        t = _parsed([_entity("ALPHA LLC", corporate=["BETA LLC"])])
        merged = merge_entity_trial_partitions([t], NAMES)
        assert merged["entities"] == t["entities"]
        assert merged["trial_stats"]["n_trials"] == 1
        assert merged["trial_stats"]["demoted_entities"] == 0

    def test_majority_merge_survives(self):
        # 2 of 3 trials group ALPHA+BETA; the merge survives.
        grouped = _parsed(
            [
                _entity("ALPHA LLC", corporate=["BETA LLC"]),
                _entity("GAMMA LLC"),
            ]
        )
        split = _parsed(
            [
                _entity("ALPHA LLC"),
                _entity("BETA LLC"),
                _entity("GAMMA LLC"),
            ]
        )
        merged = merge_entity_trial_partitions([grouped, grouped, split], NAMES)
        canonicals = {e["canonical_name"] for e in merged["entities"]}
        assert "ALPHA LLC" in canonicals
        assert merged["trial_stats"]["n_trials"] == 3
        assert merged["trial_stats"]["demoted_entities"] == 0

    def test_minority_merge_demoted_to_abstention(self):
        # Non-transitive majority: (A,B) and (A,C) each 2/3, (B,C) only 1/3.
        # The representative all-three grouping contains the unsupported
        # (B,C) pair, so it must be demoted to an abstention.
        t1 = _parsed([_entity("ALPHA LLC", corporate=["BETA LLC", "GAMMA LLC"])])
        t2 = _parsed(
            [
                _entity("ALPHA LLC", corporate=["BETA LLC"]),
                _entity("GAMMA LLC"),
            ]
        )
        t3 = _parsed(
            [
                _entity("ALPHA LLC", corporate=["GAMMA LLC"]),
                _entity("BETA LLC"),
            ]
        )
        merged = merge_entity_trial_partitions([t1, t2, t3], NAMES)
        assert merged["trial_stats"]["demoted_entities"] == 1
        assert any(
            "disagreement" in (a.get("reason") or "") for a in merged["abstentions"]
        )

    def test_two_trial_disagreement_is_not_majority(self):
        # Strict majority: 1 of 2 trials grouping a pair is NOT enough,
        # and the split trial is the majority-consistent representative.
        grouped = _parsed([_entity("ALPHA LLC", corporate=["BETA LLC"])])
        split = _parsed([_entity("ALPHA LLC"), _entity("BETA LLC")])
        merged = merge_entity_trial_partitions(
            [grouped, split], ["ALPHA LLC", "BETA LLC"]
        )
        for entity in merged["entities"]:
            linked = entity["linked_records"]["corporate_entities"]
            assert not (
                entity["canonical_name"] == "ALPHA LLC" and "BETA LLC" in linked
            )

    def test_rejections_and_abstentions_carry_through(self):
        t = _parsed(
            [_entity("ALPHA LLC")],
            rejected=[{"name_a": "ALPHA LLC", "name_b": "BETA LLC", "reason": "x"}],
            abstentions=[{"names": ["GAMMA LLC"], "reason": "thin evidence"}],
        )
        merged = merge_entity_trial_partitions([t, t, t], NAMES)
        assert merged["rejected_matches"]
        assert any(a.get("names") == ["GAMMA LLC"] for a in merged["abstentions"])


class TestEntityTrialMajorityDecided:
    def test_two_matching_partitions_decide_three_trial_vote(self):
        grouped = _parsed([_entity("ALPHA LLC", corporate=("BETA LLC",))])
        assert entity_trial_majority_decided([grouped, grouped], NAMES, target_trials=3)

    def test_disagreement_requires_deciding_trial(self):
        grouped = _parsed([_entity("ALPHA LLC", corporate=("BETA LLC",))])
        split = _parsed([_entity("ALPHA LLC"), _entity("BETA LLC")])
        assert not entity_trial_majority_decided(
            [grouped, split], NAMES, target_trials=3
        )

    def test_deciding_trial_resolves_disagreement(self):
        grouped = _parsed([_entity("ALPHA LLC", corporate=("BETA LLC",))])
        split = _parsed([_entity("ALPHA LLC"), _entity("BETA LLC")])
        assert entity_trial_majority_decided(
            [grouped, split, split], NAMES, target_trials=3
        )

    def test_single_name_cluster_has_no_ambiguous_pairs(self):
        one = _parsed([_entity("ALPHA LLC")])
        assert not entity_trial_majority_decided([one], ["ALPHA LLC"], target_trials=3)
        assert entity_trial_majority_decided([one, one], ["ALPHA LLC"], target_trials=3)


class TestResolveEscalationConfig:
    def test_unset_returns_none(self, monkeypatch):
        monkeypatch.delenv("COUNTYIQ_PASS1_ESCALATION_MODEL", raising=False)
        base = HarnessConfig(model_path="inception/mercury-2")
        assert resolve_escalation_config(base, pass_number=1) is None

    def test_escalation_carries_base_knobs(self, monkeypatch):
        monkeypatch.setenv("COUNTYIQ_PASS1_ESCALATION_MODEL", "z-ai/glm-5.2")
        base = HarnessConfig(
            model_path="inception/mercury-2",
            archive_label="pass1_entity",
            max_tokens=8192,
            system_prompt="static block",
            max_price_prompt=2.0,
        )
        esc = resolve_escalation_config(base, pass_number=1)
        assert esc.model_path == "z-ai/glm-5.2"
        assert esc.archive_label == "pass1_entity"
        assert esc.max_tokens == 8192
        assert esc.system_prompt == "static block"
        assert esc.max_price_prompt == 2.0

    def test_escalation_effort_override(self, monkeypatch):
        monkeypatch.setenv("COUNTYIQ_PASS1_ESCALATION_MODEL", "openai/gpt-5.6-luna")
        monkeypatch.setenv("COUNTYIQ_PASS1_ESCALATION_REASONING_EFFORT", "HIGH")
        base = HarnessConfig(model_path="inception/mercury-2", reasoning_effort="low")
        esc = resolve_escalation_config(base, pass_number=1)
        assert esc.reasoning_effort == "high"


class _FakeDatabase:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((query, params))
        return self.rows


class TestFetchPriorPassHashes:
    def test_tuple_rows(self):
        db = _FakeDatabase([("PIDN1", "hash1"), ("PIDN2", "hash2")])
        hashes = fetch_prior_pass_hashes(db, pass_number=2)
        assert hashes == {"PIDN1": "hash1", "PIDN2": "hash2"}
        assert db.calls[0][1] == {"pass_number": 2}

    def test_dict_rows_and_empty(self):
        db = _FakeDatabase([{"pidn": "K", "input_hash": "h"}])
        assert fetch_prior_pass_hashes(db, pass_number=1) == {"K": "h"}
        assert fetch_prior_pass_hashes(_FakeDatabase(None), pass_number=3) == {}
