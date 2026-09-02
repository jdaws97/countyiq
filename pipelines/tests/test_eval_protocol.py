"""Production/eval fidelity, frozen scoring, and paid-eval budget tests."""

import json
from pathlib import Path

import pytest

from countyiq.lib.llm_harness import HarnessResult
from countyiq.lib.pass1_entity_verification import ENTITY_VERIFICATION_SYSTEM_PROMPT
from countyiq.lib.pass2_batched_validation import BATCHED_VALIDATION_SYSTEM_PROMPT
from countyiq.lib.pass_schemas import (
    PASS0_EXTRACTION_SCHEMA,
    PASS2_BATCHED_VALIDATION_SCHEMA,
    PASS3_BRIEF_SCHEMA,
)
from eval.protocol import (
    EvalCostLedger,
    EvalCostLimitExceeded,
    EvalCostUnavailable,
    build_production_eval_config,
    estimate_max_call_cost,
)
from eval.fixture_io import load_frozen_cases
from eval.scoring import (
    enforce_production_gate,
    score_pass0,
    score_pass1,
    score_pass2,
    score_pass3,
)
from eval.challenger import (
    RECOMMENDED_JUDGE,
    _fixture_cluster_names,
    _is_default_pass2_fixture,
    _mk_judge_config,
)


FIXTURES = Path(__file__).parents[1] / "eval" / "fixtures"


def test_pass0_eval_uses_production_schema_system_and_native_pdf():
    config = build_production_eval_config(
        "openai/gpt-5.6-luna", 0, archive_label="test"
    )
    assert config.json_schema == PASS0_EXTRACTION_SCHEMA
    assert config.system_prompt
    assert config.pdf_engine == "native"


def test_production_gate_is_required_for_eval_promotion():
    accepted = enforce_production_gate({"gold_pass": True}, [])
    rejected = enforce_production_gate(
        {"gold_pass": True},
        ["unknown signal citation"],
    )
    assert accepted["gold_pass"] is True
    assert accepted["production_gate_pass"] is True
    assert rejected["gold_pass"] is False
    assert rejected["production_gate_errors"] == ["unknown signal citation"]


def test_pass1_eval_uses_production_system_and_effort():
    config = build_production_eval_config(
        "openai/gpt-5.6-luna", 1, archive_label="test"
    )
    assert config.system_prompt == ENTITY_VERIFICATION_SYSTEM_PROMPT
    assert config.reasoning_effort == "high"
    assert config.thinking is True


def test_pass2_eval_uses_production_schema_system_and_effort():
    config = build_production_eval_config(
        "deepseek/deepseek-v4-flash-0731", 2, archive_label="test"
    )
    assert config.json_schema == PASS2_BATCHED_VALIDATION_SCHEMA
    assert config.system_prompt == BATCHED_VALIDATION_SYSTEM_PROMPT
    assert config.reasoning_effort == "low"
    assert config.thinking is True


def test_only_the_committed_default_pass2_fixture_is_labeled_gold(tmp_path):
    default = FIXTURES / "p2_frozen.json"
    assert _is_default_pass2_fixture(default)
    assert _is_default_pass2_fixture(default.resolve())
    assert not _is_default_pass2_fixture(tmp_path / "p2_frozen.json")


def test_pass3_eval_uses_production_schema():
    config = build_production_eval_config(
        "openai/gpt-5.6-luna", 3, archive_label="test"
    )
    assert config.json_schema == PASS3_BRIEF_SCHEMA
    assert config.system_prompt


def test_eval_config_respects_strict_schema_kill_switch(monkeypatch):
    monkeypatch.setenv("COUNTYIQ_STRICT_SCHEMA", "false")
    config = build_production_eval_config(
        "openai/gpt-5.6-luna", 2, archive_label="test"
    )
    assert config.json_schema is None


def test_pass0_gold_corpus_has_three_negative_controls_and_five_matters():
    corpus = json.loads((FIXTURES / "p0_expected.json").read_text())
    assert len(corpus["documents"]) == 6
    assert sum(not doc["expected_records"] for doc in corpus["documents"]) == 3
    assert sum(len(doc["expected_records"]) for doc in corpus["documents"]) == 5


def test_pass0_gold_scoring_matches_records_once_and_penalizes_duplicates():
    fixture = {
        "expected_records": [
            {
                "id": "stanton",
                "accepted_types": ["variance_request"],
                "anchors": [["chris stanton"], ["475 andersontown"]],
            }
        ]
    }
    extraction = {
        "extraction_type": "variance_request",
        "applicant_name": "Chris Stanton",
        "parcel_reference": "475 Andersontown Rd",
    }
    exact = score_pass0({"extractions": [extraction]}, fixture)
    assert exact["gold_pass"] is True
    assert exact["matched_records"] == ["stanton"]

    duplicate = score_pass0({"extractions": [extraction, extraction]}, fixture)
    assert duplicate["gold_pass"] is False
    assert duplicate["extra_extractions"] == 1


def test_pass0_field_gold_penalizes_wrong_decision():
    fixture = {
        "expected_records": [
            {
                "id": "case",
                "accepted_types": ["variance_request"],
                "anchors": [["applicant"], ["example road"]],
                "field_expectations": {"decision": ["continued"]},
                "required_nonempty_fields": ["supporting_text"],
            }
        ]
    }
    extraction = {
        "extraction_type": "variance_request",
        "applicant_name": "Applicant",
        "parcel_reference": "1 Example Road",
        "decision": "approved",
        "supporting_text": "The hearing was continued.",
    }
    score = score_pass0({"extractions": [extraction]}, fixture)
    assert score["matched_records"] == ["case"]
    assert score["fields_pass"] is False
    assert score["gold_pass"] is False


def test_pass0_negative_control_fails_on_any_extraction():
    score = score_pass0(
        {"extractions": [{"extraction_type": "development_proposal"}]},
        {"expected_records": []},
    )
    assert score["expected_count"] == 0
    assert score["extra_extractions"] == 1
    assert score["gold_pass"] is False


def test_recommended_judge_uses_strict_grounding_contract_and_zdr():
    config = _mk_judge_config(RECOMMENDED_JUDGE)
    assert config.model_path == "x-ai/grok-4.6"
    assert config.json_schema is not None
    assert config.system_prompt and "strict evidence auditor" in config.system_prompt
    assert config.reasoning_effort == "low"
    assert config.zdr is True
    assert config.max_price_prompt == 2.5
    assert config.max_price_completion == 8.0


def test_cost_ledger_sums_provider_reported_cost():
    ledger = EvalCostLedger(max_cost_usd=0.25)
    ledger.record(HarnessResult("{}", {}, True, metadata={"cost": 0.01}))
    ledger.record(HarnessResult("{}", {}, True, metadata={"cost": 0.02}))
    assert ledger.summary() == {
        "calls": 2,
        "spend_usd": 0.03,
        "reserved_usd": 0.0,
        "max_cost_usd": 0.25,
    }


def test_cost_ledger_fails_closed_when_cost_is_missing():
    ledger = EvalCostLedger(max_cost_usd=0.25)
    with pytest.raises(EvalCostUnavailable):
        ledger.record(HarnessResult("{}", {}, True))


def test_cost_ledger_stops_over_limit():
    ledger = EvalCostLedger(max_cost_usd=0.01)
    with pytest.raises(EvalCostLimitExceeded):
        ledger.record(HarnessResult("{}", {}, True, metadata={"cost": 0.011}))


def test_cost_ledger_reserves_before_dispatch_and_releases_actual_cost():
    ledger = EvalCostLedger(max_cost_usd=0.05)
    reservation = ledger.reserve(0.04)
    with pytest.raises(EvalCostLimitExceeded):
        ledger.reserve(0.02)
    ledger.record(HarnessResult("{}", {}, True, metadata={"cost": 0.003}), reservation)
    assert ledger.summary()["spend_usd"] == 0.003
    assert ledger.summary()["reserved_usd"] == 0.0


def test_known_models_have_pre_call_absolute_cost_estimates():
    for model in ("openai/gpt-5.6-luna", "z-ai/glm-5.3-flash"):
        config = build_production_eval_config(model, 2, archive_label="test")
        maximum = estimate_max_call_cost(config, "small prompt", retries=1)
        assert 0 < maximum < 0.1
        assert config.max_price_prompt is not None
        assert config.max_price_completion is not None


def test_unknown_model_without_price_ceiling_fails_closed():
    config = build_production_eval_config("vendor/unknown", 2, archive_label="test")
    with pytest.raises(EvalCostUnavailable):
        estimate_max_call_cost(config, "prompt")


def test_frozen_pass1_to_pass3_corpora_are_hashed_and_cover_required_shapes():
    pass1 = load_frozen_cases(FIXTURES / "p1_frozen.json")
    pass2 = load_frozen_cases(FIXTURES / "p2_frozen.json")
    pass3 = load_frozen_cases(FIXTURES / "p3_frozen.json")
    assert len(pass1) == 8
    assert len(pass2) == 10
    assert len(pass3) == 4
    combinations = {tuple(case["signal_combination"]) for case in pass2}
    assert len(combinations) == 10
    covered = {signal for combination in combinations for signal in combination}
    assert covered == {
        "active_subdivision",
        "assemblage",
        "ownership_change",
        "vacancy",
        "zoning_mismatch",
    }
    decisions = {
        value
        for case in pass3
        for value in case["labels"]["accepted_fields"]["recommendation"]
    }
    assert decisions == {"pursue_now", "watchlist", "pass"}


def test_expanded_pass2_corpus_is_stratified_and_explicitly_diagnostic():
    path = FIXTURES / "p2_expanded_frozen.json"
    payload = json.loads(path.read_text())
    cases = load_frozen_cases(path)
    assert len(cases) == 100
    assert payload["promotion_status"] == "diagnostic_until_human_review"
    assert payload["cardinality_counts"] == {"2": 54, "3": 29, "4": 17}
    assert len({tuple(case["signal_combination"]) for case in cases}) == 24
    for case in cases:
        assert case["review"]["status"] == (
            "rubric_generated_requires_human_confirmation"
        )
        assert len(case["labels"]["signals"]) == len(case["signal_combination"])


def test_pass2_deidentification_preserves_roles_without_synthetic_name_artifacts():
    cases = load_frozen_cases(FIXTURES / "p2_frozen.json")
    serialized = json.dumps(cases).lower()
    assert "owner p2-" not in serialized
    assert "neighbor owner" not in serialized
    assert "water company" in cases[5]["context"]["parcel"]["owner"].lower()
    assert "school authority" in cases[8]["context"]["parcel"]["owner"].lower()
    neighbor_owners = [
        neighbor["owner"] for neighbor in cases[6]["context"]["neighbors"]
    ]
    assert len(set(neighbor_owners)) == 12
    assert len(neighbor_owners) == 13


def test_pass1_partition_scorer_accepts_human_partition_and_rejects_false_merge():
    case = load_frozen_cases(FIXTURES / "p1_frozen.json")[0]
    assert _fixture_cluster_names(case) == [
        "MARTIN MICHAEL L",
        "MARTINSON MICHAEL E",
    ]
    parsed = {
        "entities": [
            {"linked_records": {"parcels": ["P1A001"]}},
            {"linked_records": {"parcels": ["P1A002"]}},
        ]
    }
    assert score_pass1(parsed, {"records": case["context"], **case})["gold_pass"]
    false_merge = {"entities": [{"linked_records": {"parcels": ["P1A001", "P1A002"]}}]}
    assert not score_pass1(false_merge, {"records": case["context"], **case})[
        "gold_pass"
    ]


def test_pass1_cross_source_case_requires_every_labeled_link():
    case = load_frozen_cases(FIXTURES / "p1_frozen.json")[-1]
    linked = {
        "parcels": ["P1H001"],
        "tax_claims": ["P1H001"],
        "plcb_licenses": ["LIC-P1H-01"],
        "corporate_entities": ["EXAMPLE DEVELOPMENT LLC"],
        "proceedings": ["EXAMPLE DEVELOPMENT LLC"],
    }
    parsed = {"entities": [{"linked_records": linked}]}
    assert score_pass1(parsed, {"records": case["context"], **case})["gold_pass"]
    linked["proceedings"] = []
    assert not score_pass1(parsed, {"records": case["context"], **case})["gold_pass"]


def test_pass2_scorer_requires_calibration_facts_and_blocks_unsupported_claims():
    case = load_frozen_cases(FIXTURES / "p2_frozen.json")[0]
    validations = []
    for label in case["labels"]["signals"]:
        facts = [group[0] for group in label["required_fact_groups"]]
        validations.append(
            {
                "signal_key": label["signal_key"],
                "validation_status": label["accepted_statuses"][0],
                "adjusted_significance": label["accepted_significance"][0],
                "reasoning": "; ".join(facts),
                "key_facts": facts,
                "cross_references": [],
            }
        )
    parsed = {"validations": validations}
    assert score_pass2(parsed, case)["gold_pass"]
    parsed["validations"][0]["reasoning"] += " Approved development intent."
    assert not score_pass2(parsed, case)["gold_pass"]


def test_pass2_fact_matching_allows_modifiers_and_simple_plurals():
    fixture = {
        "labels": {
            "signals": [
                {
                    "signal_key": "active_subdivision",
                    "accepted_statuses": ["confirmed"],
                    "accepted_significance": ["medium"],
                    "required_fact_groups": [
                        ["3 unit"],
                        ["zero lot"],
                        ["no structure"],
                    ],
                    "forbidden_claims": [],
                }
            ]
        }
    }
    parsed = {
        "validations": [
            {
                "signal_key": "active_subdivision",
                "validation_status": "confirmed",
                "adjusted_significance": "medium",
                "reasoning": (
                    "The plan has 3 proposed dwelling units, zero proposed lots, "
                    "and no recorded structures."
                ),
            }
        ]
    }
    score = score_pass2(parsed, fixture)
    signal = score["signal_scores"]["active_subdivision"]
    assert signal["matched_required_fact_groups"] == 3
    assert signal["required_fact_recall"] == 1.0
    assert score["gold_pass"]


def test_pass2_forbidden_claims_ignore_explicit_disclaimers_only():
    fixture = {
        "labels": {
            "signals": [
                {
                    "signal_key": "ownership_change",
                    "accepted_statuses": ["confirmed"],
                    "accepted_significance": ["low"],
                    "required_fact_groups": [],
                    "forbidden_claims": ["distressed", "rezoning"],
                }
            ]
        }
    }
    validation = {
        "signal_key": "ownership_change",
        "validation_status": "confirmed",
        "adjusted_significance": "low",
        "reasoning": (
            "The price does not establish whether the sale was distressed. "
            "There is no evidence of rezoning."
        ),
    }
    clean = score_pass2({"validations": [validation]}, fixture)
    assert clean["gold_pass"]
    validation["reasoning"] += " The buyer completed a distressed acquisition."
    asserted = score_pass2({"validations": [validation]}, fixture)
    assert asserted["signal_scores"]["ownership_change"]["forbidden_claims_found"] == [
        "distressed"
    ]


def test_pass3_scorer_requires_structured_decision_and_grounded_citations():
    case = load_frozen_cases(FIXTURES / "p3_frozen.json")[0]
    labels = case["labels"]
    citations = labels["required_citations"]
    facts = [group[0] for group in labels["required_fact_groups"]]
    parsed = {
        field: accepted[0] for field, accepted in labels["accepted_fields"].items()
    }
    parsed.update(
        {
            "top_signal_key": citations[0],
            "assessment_reasoning": f"Grounded case [Signal: {citations[0]}].",
            "brief": (
                "; ".join(facts)
                + " "
                + " ".join(f"[Signal: {citation}]" for citation in citations)
            ),
            "citations": citations,
        }
    )
    assert score_pass3(parsed, case)["gold_pass"]
    parsed["brief"] = "An uncited factual paragraph with no signal marker."
    assert not score_pass3(parsed, case)["gold_pass"]
