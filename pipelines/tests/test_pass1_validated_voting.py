"""Exercise Pass 1 publication with real parsing, source validation and voting."""

import json
from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from countyiq.assets.enrichment import entity_verification as pass1
from countyiq.lib.llm_harness import HarnessConfig, HarnessResult
from countyiq.lib.pass1_entity_verification import ENTITY_CANDIDATE_PAIRS_READY_QUERY

NAMES = ["ALPHA LLC", "BETA LLC"]
RECORDS = {
    "candidate_names": NAMES,
    "parcels": [
        {"pidn": "P1", "owner_full": "ALPHA LLC"},
        {"pidn": "P2", "owner_full": "BETA LLC"},
    ],
    "tax_claims": [],
    "plcb_licenses": [],
    "corporate_entities": [],
    "proceedings": [],
}


def _entity(names, parcels):
    return {
        "canonical_name": names[0],
        "member_names": names,
        "entity_type": "llc",
        "confidence": 0.9,
        "reasoning": f"Recorded name reviewed [Evidence: candidate:{names[0]}].",
        "linked_records": {"parcels": parcels},
        "relationships": [],
    }


def _partition(*, merged):
    entities = (
        [_entity(NAMES, ["P1", "P2"])]
        if merged
        else [_entity([NAMES[0]], ["P1"]), _entity([NAMES[1]], ["P2"])]
    )
    return {"entities": entities, "rejected_matches": [], "abstentions": []}


def _response(parsed, provider):
    return HarnessResult(
        raw_output=json.dumps(parsed),
        parsed=parsed,
        success=True,
        metadata={"provider": provider, "served_model": f"{provider}/served-model"},
    )


class _Database:
    def __init__(self, names, records=None):
        self.names = names
        self.records = records or {}

    def execute(self, sql, params=None):
        if sql == ENTITY_CANDIDATE_PAIRS_READY_QUERY:
            return [(True,)]
        if sql == pass1.CANDIDATE_CLUSTERS_QUERY:
            return [tuple(self.names)]
        if sql == pass1.ENTITY_REGISTRATION_ROWS_QUERY:
            return self.records.get("corporate_entities", [])
        raise AssertionError(f"Unexpected database query: {sql}")

    def dict_cursor(self):
        return nullcontext(object())


def _run(
    monkeypatch, responses, *, records=None, escalation=False, paid_available=True
):
    records = deepcopy(RECORDS if records is None else records)
    calls = {
        "invoke": [],
        "inferences": [],
        "rejections": [],
        "graphs": [],
        "status": [],
    }
    pending = iter(responses)

    def invoke(config, prompt, **kwargs):
        calls["invoke"].append(kwargs["archive_key"])
        return next(pending)

    def record_inference(database, **kwargs):
        calls["inferences"].append(kwargs)
        return SimpleNamespace(accepted=True, inference_id=42)

    def replace_graph(database, entities, cluster_names, **kwargs):
        calls["graphs"].append(entities)
        return len(entities)

    def record_status(database, subject, number, status, input_hash, error=None):
        calls["status"].append({"status": status, "error": error})

    monkeypatch.setenv("COUNTYIQ_PASS1_TRIALS", "3")
    monkeypatch.setenv("COUNTYIQ_PASS1_SCOPE", "all")
    monkeypatch.setenv("COUNTYIQ_PASS1_ADAPTIVE_VOTING", "true")

    def resolve_harness(*args, **kwargs):
        if not paid_available:
            raise pass1.PassHarnessUnavailable("paid inference is disabled")
        return HarnessConfig(model_path="test/primary"), invoke

    monkeypatch.setattr(pass1, "resolve_pass_harness", resolve_harness)
    monkeypatch.setattr(
        pass1,
        "resolve_escalation_config",
        lambda *args, **kwargs: (
            HarnessConfig(model_path="test/escalation") if escalation else None
        ),
    )
    monkeypatch.setattr(pass1, "gather_cluster_records", lambda *args: records)
    monkeypatch.setattr(pass1, "fetch_reusable_pass_hashes", lambda *args, **kwargs: {})
    monkeypatch.setattr(pass1, "fetch_prior_pass_attempts", lambda *args, **kwargs: {})
    monkeypatch.setattr(pass1, "check_error_budget", lambda *args, **kwargs: None)
    monkeypatch.setattr(pass1, "record_inference_decision", record_inference)
    monkeypatch.setattr(
        pass1,
        "record_validation_rejection",
        lambda database, **kwargs: calls["rejections"].append(kwargs),
    )
    monkeypatch.setattr(pass1, "_replace_cluster_entities", replace_graph)
    monkeypatch.setattr(pass1, "_update_pass_status", record_status)

    result = pass1.entity_verification.op.compute_fn.decorated_fn(
        SimpleNamespace(log=Mock()), _Database(records["candidate_names"], records)
    )
    return calls, result


def test_invalid_trial_cannot_vote_or_supply_selected_provider_metadata(monkeypatch):
    merged = _partition(merged=True)
    invalid = deepcopy(merged)
    invalid["entities"][0]["linked_records"]["parcels"].append("MADE-UP")
    split = _partition(merged=False)
    calls, result = _run(
        monkeypatch,
        [
            _response(merged, "first"),
            _response(invalid, "second"),
            _response(split, "third"),
        ],
    )

    assert len(calls["invoke"]) == 3
    assert calls["graphs"] == [split["entities"]]
    assert calls["inferences"][0]["provider"] == "third"
    assert calls["inferences"][0]["served_model"] == "third/served-model"
    assert calls["inferences"][0]["payload"]["trial_stats"]["target_trials"] == 3
    assert calls["inferences"][0]["payload"]["trial_stats"]["n_trials"] == 2
    assert "trial 2:" in calls["rejections"][0]["errors"][0]
    assert result.metadata["trial_validation_rejections"].value == 1
    assert result.metadata["voting_early_stops"].value == 0


def test_one_valid_response_and_two_failed_calls_preserve_existing_graph(monkeypatch):
    failed = HarnessResult(raw_output="", parsed=None, success=False, error="HTTP 503")
    calls, result = _run(
        monkeypatch, [_response(_partition(merged=True), "first"), failed, failed]
    )

    assert len(calls["invoke"]) == 3
    assert calls["inferences"] == []
    assert calls["graphs"] == []
    assert calls["status"][0]["status"] == "error"
    assert "Insufficient validated trials" in calls["status"][0]["error"]
    assert result.metadata["errors"].value == 1


def test_two_valid_matching_trials_publish_without_paying_for_the_third(monkeypatch):
    merged = _partition(merged=True)
    calls, result = _run(
        monkeypatch, [_response(merged, "first"), _response(merged, "second")]
    )

    assert len(calls["invoke"]) == 2
    assert calls["graphs"] == [merged["entities"]]
    assert calls["inferences"][0]["provider"] == "first"
    assert calls["inferences"][0]["payload"]["trial_stats"]["target_trials"] == 3
    assert result.metadata["voting_calls_saved"].value == 1
    assert result.metadata["voting_early_stops"].value == 1


def test_self_abstaining_identity_cannot_supply_the_required_trial_quorum(monkeypatch):
    conflicting = _partition(merged=True)
    conflicting["abstentions"] = [
        {
            "names": [NAMES[0]],
            "reason": "Identity within this name is unresolved [Evidence: parcels:P1].",
        }
    ]
    calls, result = _run(
        monkeypatch,
        [
            _response(conflicting, "first"),
            _response(conflicting, "second"),
            _response(_partition(merged=False), "third"),
        ],
    )
    assert len(calls["invoke"]) == 3
    assert calls["inferences"] == []
    assert calls["graphs"] == []
    assert result.metadata["trial_validation_rejections"].value == 2
    assert result.metadata["errors"].value == 1


def test_invalid_escalation_cannot_replace_a_valid_primary_abstention(monkeypatch):
    abstained = {
        "entities": [],
        "rejected_matches": [],
        "abstentions": [
            {
                "names": NAMES,
                "reason": "Insufficient identity evidence [Evidence: candidate:ALPHA LLC].",
            }
        ],
    }
    invalid = _partition(merged=True)
    invalid["entities"][0]["reasoning"] = "Fabricated link [Evidence: parcels:UNKNOWN]."
    calls, result = _run(
        monkeypatch,
        [
            _response(abstained, "primary"),
            _response(abstained, "primary"),
            _response(invalid, "escalated"),
        ],
        escalation=True,
    )

    assert len(calls["invoke"]) == 3
    assert calls["graphs"] == [[]]
    assert calls["inferences"][0]["payload"]["abstentions"] == abstained["abstentions"]
    assert calls["inferences"][0]["requested_model"] == "test/primary"
    assert calls["inferences"][0]["provider"] == "primary"
    assert result.metadata["escalations"].value == 0
    assert calls["rejections"][0]["requested_model"] == "test/escalation"
    assert "escalation:" in calls["rejections"][0]["errors"][0]
    assert result.metadata["escalation_validation_rejections"].value == 1


@pytest.mark.parametrize("paid_available", [True, False])
def test_anchored_deterministic_resolution_needs_no_paid_trial_quorum(
    monkeypatch, paid_available
):
    records = deepcopy(RECORDS)
    records["candidate_names"] = ["ALPHA LLC", "ALPHA, L.L.C."]
    records["parcels"] = [records["parcels"][0]]
    records["parcels"][0]["mail_addr_full"] = "10 MAIN ST, YORK PA 17401"
    records["corporate_entities"] = [
        {
            "entity_name": "ALPHA LLC",
            "entity_number": "123",
            "office_address": "10 Main St, York, PA, 17401",
        }
    ]
    calls, result = _run(
        monkeypatch, [], records=records, paid_available=paid_available
    )

    assert calls["invoke"] == []
    assert calls["graphs"][0][0]["member_names"] == ["ALPHA LLC", "ALPHA, L.L.C."]
    assert calls["inferences"][0]["payload"]["trial_stats"]["target_trials"] == 1
    assert result.metadata["deterministic_clusters"].value == 1
    assert result.metadata["errors"].value == 0


def test_disabled_paid_path_does_not_guess_unanchored_identity(monkeypatch):
    calls, result = _run(monkeypatch, [], paid_available=False)
    assert calls["invoke"] == []
    assert calls["graphs"] == []
    assert result.metadata["clusters_deferred_scope"].value == 1


def test_disabled_paid_path_does_not_attach_unconnected_parcels_to_a_registration(
    monkeypatch,
):
    records = deepcopy(RECORDS)
    records["corporate_entities"] = [
        {"entity_name": "ALPHA LLC", "entity_number": "123"},
        {"entity_name": "BETA LLC", "entity_number": "456"},
    ]
    calls, result = _run(monkeypatch, [], records=records, paid_available=False)
    assert calls["invoke"] == []
    assert calls["graphs"] == []
    assert result.metadata["clusters_deferred_scope"].value == 1
