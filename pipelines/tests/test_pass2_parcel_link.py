"""Regressions for nearby proposals promoted despite unknown parcel linkage."""

import pytest
from countyiq.lib.intelligence_integrity import validate_pass2_evidence_refs


def check_plan(location, distance, status="confirmed", significance="medium"):
    return validate_pass2_evidence_refs(
        [
            {
                "signal_key": "active_subdivision",
                "validation_status": status,
                "adjusted_significance": significance,
                "reasoning": (
                    "The proposal is nearby; exact parcel coverage is unconfirmed. "
                    "[Evidence: signal:active_subdivision]"
                ),
                "cross_references": ["signal:active_subdivision"],
            }
        ],
        [
            {
                "signal_key": "active_subdivision",
                "distance_m": distance,
                "evidence": {"plan_location": location},
            }
        ],
    )


@pytest.mark.parametrize(
    ("location", "distance"),
    [
        ("within_30m_of_parcel", 1),  # p2x-089
        ("within_30m_of_parcel", 0),  # p2x-051: rounded zero cannot resolve linkage
        ("nearby", 0),
        (None, 0),
        ("unknown", 0),
        ("point_on_parcel", 36.4),
        ("point_on_parcel", -1),
        ("point_on_parcel", "unavailable"),
        ("point_on_parcel", float("nan")),
        ("point_on_parcel", float("inf")),
        ("point_on_parcel", False),
    ],
)
def test_a_prose_caveat_does_not_allow_confirming_an_unlinked_plan(location, distance):
    assert any(
        "lacks a consistent" in error for error in check_plan(location, distance)
    )


@pytest.mark.parametrize(
    ("status", "significance"),
    [("confirmed", "low"), ("upgraded", "low"), ("downgraded", "medium")],
)
def test_unlinked_plans_cannot_retain_confirmation_or_actionable_priority(
    status, significance
):
    assert check_plan("within_30m_of_parcel", 1, status, significance)


@pytest.mark.parametrize(
    ("status", "significance"),
    [("downgraded", "low"), ("downgraded", "none"), ("stale", "none")],
)
def test_uncertain_plan_can_be_retained_without_becoming_actionable(
    status, significance
):
    assert check_plan("within_30m_of_parcel", 1, status, significance) == []


@pytest.mark.parametrize("distance", [0, "0", None])
def test_consistent_mapped_point_supports_a_parcel_relevant_proposal(distance):
    assert check_plan("point_on_parcel", distance) == []
