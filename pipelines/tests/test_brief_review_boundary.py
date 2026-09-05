"""Recommendation vocabulary migrations must preserve consequential review."""
import pytest

from countyiq.lib.intelligence_autoresolve import classify_flip, decide


@pytest.mark.parametrize("kind,positive,negative", [
    ("parcel_brief", positive, negative)
    for positive in ("pursue_now", "investigate")
    for negative in ("pass", "insufficient_evidence")
] + [
    ("owner_brief", positive, negative)
    for positive in ("pursue_acquisition", "investigate")
    for negative in ("none", "insufficient_evidence")
])
@pytest.mark.parametrize("reverse", [False, True])
def test_current_and_historical_extremes_always_require_review(kind, positive, negative, reverse):
    before, after = (negative, positive) if reverse else (positive, negative)
    assessment = classify_flip(
        output_kind=kind,
        prior_payload={"recommendation": before},
        challenger_payload={"recommendation": after},
        prior_input_hash="old-version",
        challenger_input_hash="new-version",
    )
    assert assessment.consequential
    assert decide(assessment, "challenger", True) == "queued_consequential"
    assert decide(assessment, None, False) == "queued_consequential"


@pytest.mark.parametrize("kind,before,after", [
    ("parcel_brief", "pursue_now", "investigate"),
    ("owner_brief", "pursue_acquisition", "investigate"),
    ("parcel_brief", "pass", "insufficient_evidence"),
    ("owner_brief", "none", "insufficient_evidence"),
    ("parcel_brief", "watch", "insufficient_evidence"),
    ("owner_brief", "investigate", "investigate"),
])
def test_renaming_within_a_group_is_not_an_extreme_reversal(kind, before, after):
    assessment = classify_flip(
        output_kind=kind,
        prior_payload={"recommendation": before},
        challenger_payload={"recommendation": after},
        prior_input_hash="old-version",
        challenger_input_hash="new-version",
    )
    assert not assessment.consequential
