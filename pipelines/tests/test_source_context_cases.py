"""Source derivations must preserve history and never manufacture evidence."""

from copy import deepcopy

import pytest

from eval.fixture_io import canonical_context_hash, load_frozen_cases
from eval.source_context_cases import (
    FIXTURES,
    derive_pass2_case,
    derive_pass3_case,
    pass2_cases,
    pass3_cases,
)
from countyiq.lib.pass3_brief_generation import build_brief_generation_prompt


def test_demoted_targets_remain_source_context_and_no_call_cases_are_explicit():
    originals = load_frozen_cases(FIXTURES / "p2_expanded_stability20.json")
    before = deepcopy(originals)
    derived = [derive_pass2_case(c) for c in originals]
    assert originals == before
    assert any(not c["call_eligible"] for c in derived)
    for old, new in zip(originals, derived, strict=True):
        old_signals = old["context"]["signals"] + old["context"].get(
            "context_signals", []
        )
        new_signals = new["context"]["signals"] + new["context"]["context_signals"]
        assert sorted(old_signals, key=lambda s: s["signal_key"]) == sorted(
            new_signals, key=lambda s: s["signal_key"]
        )
        assert all(s["signal_key"] != "vacancy" for s in new["context"]["signals"])
        for label in new["labels"]["signals"]:
            assert label in old["labels"]["signals"]
        assert new["context_sha256"] == canonical_context_hash(new["context"])
    assert derived == pass2_cases()


def test_briefs_recover_plan_and_land_use_source_fields_without_prior_prose():
    cases = pass3_cases()
    first = cases[0]
    prompt = build_brief_generation_prompt(first["context"])
    assert "plan_title=Taylor Brooks" in prompt
    assert "prop_lots=4" in prompt
    assert "total_acres=45.5" in prompt
    assert "owner-matched" not in prompt
    assert "vacant component" not in prompt
    assert first["upstream_pass2_eligible"] is False
    assert first["labels"]["required_citations"] == ["active_subdivision"]
    school = build_brief_generation_prompt(cases[2]["context"])
    assert (
        "future_lu=Mixed Use, Non-Residential Office, Retail and Light Industrial"
        in school
    )
    assert "current_zname=Commercial Office" in school
    assert "buyer_is_llc=False" in school


def test_derivation_rejects_damaged_or_mismatched_sources():
    p2 = load_frozen_cases(FIXTURES / "p2_frozen.json")
    p3 = load_frozen_cases(FIXTURES / "p3_investigation_frozen.json")[0]
    with pytest.raises(ValueError, match="does not match"):
        derive_pass3_case(p3, p2[0])
    p2[0]["context"]["parcel"]["owner"] = "tampered"
    with pytest.raises(ValueError, match="Damaged source context"):
        derive_pass2_case(p2[0])
