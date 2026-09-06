"""Policy tests for rule-first, judge-assisted contradiction resolution."""

from countyiq.lib.intelligence_autoresolve import classify_flip, decide
from countyiq.lib.intelligence_judge import build_judge_prompt, parse_judge_output


def _entities(*groups):
    return {
        "entities": [
            {"canonical_name": sorted(g)[0], "member_names": sorted(g)} for g in groups
        ]
    }


def test_person_merged_with_organization_is_consequential():
    prior = _entities({"SMITH JOHN A"}, {"SMITH HOLDINGS LLC"})
    challenger = _entities({"SMITH JOHN A", "SMITH HOLDINGS LLC"})
    assessment = classify_flip(
        output_kind="entity_verification",
        prior_payload=prior,
        challenger_payload=challenger,
        prior_input_hash="a",
        challenger_input_hash="a",
    )
    assert assessment.consequential
    assert "identity membership" in assessment.reasons[0]


def test_organization_to_organization_merge_requires_review():
    prior = _entities({"ACME PROPERTIES LLC"}, {"ACME PROPERTIES L.L.C."})
    challenger = _entities({"ACME PROPERTIES LLC", "ACME PROPERTIES L.L.C."})
    assessment = classify_flip(
        output_kind="entity_verification",
        prior_payload=prior,
        challenger_payload=challenger,
        prior_input_hash="a",
        challenger_input_hash="b",
    )
    assert assessment.consequential
    assert decide(assessment, "challenger", True) == "queued_consequential"
    assert assessment.version_upgrade
    assert assessment.rule_default == "accept_challenger"


def test_proceeding_approval_denial_flip_is_consequential_but_tabling_is_not():
    matter = {
        "extraction_type": "variance_request",
        "applicant_name": "Acme",
        "parcel_reference": "P1",
        "project_name": None,
    }
    approved = {"extractions": [{**matter, "decision": "approved"}]}
    denied = {"extractions": [{**matter, "decision": "denied"}]}
    tabled = {"extractions": [{**matter, "decision": "tabled"}]}
    assert classify_flip(
        output_kind="proceeding_extraction",
        prior_payload=approved,
        challenger_payload=denied,
        prior_input_hash="a",
        challenger_input_hash="a",
    ).consequential
    assert not classify_flip(
        output_kind="proceeding_extraction",
        prior_payload=approved,
        challenger_payload=tabled,
        prior_input_hash="a",
        challenger_input_hash="a",
    ).consequential


def test_signal_crossing_brief_eligibility_is_consequential():
    def validations(sig):
        return {
            "validations": [
                {
                    "signal_key": "vacancy",
                    "validation_status": "confirmed",
                    "adjusted_significance": sig,
                }
            ]
        }

    assert classify_flip(
        output_kind="signal_validation",
        prior_payload=validations("high"),
        challenger_payload=validations("none"),
        prior_input_hash="a",
        challenger_input_hash="a",
    ).consequential
    assert classify_flip(
        output_kind="signal_validation",
        prior_payload=validations("medium"),
        challenger_payload=validations("none"),
        prior_input_hash="a",
        challenger_input_hash="a",
    ).consequential
    assert not classify_flip(
        output_kind="signal_validation",
        prior_payload=validations("high"),
        challenger_payload=validations("medium"),
        prior_input_hash="a",
        challenger_input_hash="a",
    ).consequential


def test_signal_non_serving_status_is_non_actionable_even_with_legacy_high_band():
    confirmed = {
        "validations": [
            {
                "signal_key": "vacancy",
                "validation_status": "confirmed",
                "adjusted_significance": "medium",
            }
        ]
    }
    irrelevant = {
        "validations": [
            {
                "signal_key": "vacancy",
                "validation_status": "irrelevant",
                "adjusted_significance": "high",
            }
        ]
    }

    assert classify_flip(
        output_kind="signal_validation",
        prior_payload=confirmed,
        challenger_payload=irrelevant,
        prior_input_hash="a",
        challenger_input_hash="a",
    ).consequential


def test_brief_recommendation_extremes_are_consequential():
    assert classify_flip(
        output_kind="parcel_brief",
        prior_payload={"recommendation": "pursue_now"},
        challenger_payload={"recommendation": "pass"},
        prior_input_hash="a",
        challenger_input_hash="a",
    ).consequential
    assert not classify_flip(
        output_kind="parcel_brief",
        prior_payload={"recommendation": "watchlist"},
        challenger_payload={"recommendation": "pass"},
        prior_input_hash="a",
        challenger_input_hash="a",
    ).consequential
    assert classify_flip(
        output_kind="owner_brief",
        prior_payload={"recommendation": "pursue_acquisition"},
        challenger_payload={"recommendation": "none"},
        prior_input_hash="a",
        challenger_input_hash="a",
    ).consequential


def test_same_version_flip_defaults_to_incumbent():
    assessment = classify_flip(
        output_kind="parcel_brief",
        prior_payload={"recommendation": "watchlist"},
        challenger_payload={"recommendation": "pass"},
        prior_input_hash="same",
        challenger_input_hash="same",
    )
    assert assessment.rule_default == "accept_prior"


def test_decision_matrix():
    routine_upgrade = classify_flip(
        output_kind="parcel_brief",
        prior_payload={"recommendation": "watchlist"},
        challenger_payload={"recommendation": "pass"},
        prior_input_hash="a",
        challenger_input_hash="b",
    )
    consequential = classify_flip(
        output_kind="parcel_brief",
        prior_payload={"recommendation": "pursue_now"},
        challenger_payload={"recommendation": "pass"},
        prior_input_hash="a",
        challenger_input_hash="b",
    )

    # Consequential always waits for a person, whatever the judge says.
    assert decide(consequential, "challenger", True) == "queued_consequential"
    # No judge configured: the rule decides alone.
    assert decide(routine_upgrade, None, False) == "auto_resolved"
    # Judge agrees or is unclear: resolve. Judge disagrees: a person looks.
    assert decide(routine_upgrade, "challenger", True) == "auto_resolved"
    assert decide(routine_upgrade, "unclear", True) == "auto_resolved"
    assert decide(routine_upgrade, "prior", True) == "queued_disagreement"
    # Judge configured but failed: never resolve on a missing opinion.
    assert decide(routine_upgrade, None, True) == "queued_judge_unavailable"


def test_judge_prompt_and_parser():
    prompt = build_judge_prompt(
        output_kind="signal_validation",
        evidence_text="PARCEL: 1\nSignal 1: vacancy",
        prior_decision={
            "validations": [{"signal_key": "vacancy", "adjusted_significance": "high"}]
        },
        challenger_decision={
            "validations": [
                {"signal_key": "vacancy", "adjusted_significance": "medium"}
            ]
        },
    )
    assert (
        "SOURCE EVIDENCE" in prompt and "PRIOR DECISION" in prompt and "JSON" in prompt
    )
    assert parse_judge_output(
        {"winner": "Prior", "confidence": 1.7, "reason": "x"}
    ) == ("prior", 1.0, "x")
    assert parse_judge_output({"winner": "maybe"}) is None
    assert parse_judge_output("nope") is None


def test_person_to_person_merge_requires_review_even_on_new_version():
    assessment = classify_flip(
        output_kind="entity_verification",
        prior_payload=_entities({"ALEX RIVER"}, {"JORDAN RIVER"}),
        challenger_payload=_entities({"ALEX RIVER", "JORDAN RIVER"}),
        prior_input_hash="old",
        challenger_input_hash="new",
    )
    assert decide(assessment, None, False) == "queued_consequential"
