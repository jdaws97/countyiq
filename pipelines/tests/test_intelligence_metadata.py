"""Tests for round-2 intelligence shipping: N-trial voting, structured-first
parser, selection gate wiring. Deterministic — no LLM calls.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Pass 2 N-trial merger
# ---------------------------------------------------------------------------


def _trial(*entries):
    return {"validations": list(entries), "cross_signal_insight": ""}


def _val(key, status, sig, reason="r"):
    return {
        "signal_key": key,
        "validation_status": status,
        "adjusted_significance": sig,
        "reasoning": reason,
    }


def test_merge_all_trials_agree():
    from countyiq.lib.pass2_batched_validation import merge_trial_validations

    trials = [
        _trial(_val("tax_distress", "confirmed", "high")),
        _trial(_val("tax_distress", "confirmed", "high")),
        _trial(_val("tax_distress", "confirmed", "high")),
    ]
    merged = merge_trial_validations(trials, [{"signal_key": "tax_distress"}])
    v = merged["validations"][0]
    assert v["validation_status"] == "confirmed"
    assert v["adjusted_significance"] == "high"
    assert v["trial_agreement"] == 1.0
    assert v["confidence"] == 1.0
    assert v["n_trials"] == 3


def test_merge_majority_vote():
    from countyiq.lib.pass2_batched_validation import merge_trial_validations

    trials = [
        _trial(_val("growth_area", "irrelevant", "none")),
        _trial(_val("growth_area", "irrelevant", "none")),
        _trial(_val("growth_area", "confirmed", "low")),
    ]
    merged = merge_trial_validations(trials, [{"signal_key": "growth_area"}])
    v = merged["validations"][0]
    assert v["validation_status"] == "irrelevant"
    assert v["trial_agreement"] == 0.67
    # confidence = 0.67 × 0.50 (weight for "none") = 0.34
    assert 0.30 <= v["confidence"] <= 0.36


def test_merge_missing_signal_reported():
    from countyiq.lib.pass2_batched_validation import merge_trial_validations

    trials = [
        _trial(_val("tax_distress", "confirmed", "high")),
        _trial(_val("tax_distress", "confirmed", "high")),
        _trial(),  # empty trial — signal absent
    ]
    merged = merge_trial_validations(
        trials,
        [{"signal_key": "tax_distress"}, {"signal_key": "vacancy"}],
    )
    assert merged["missing"] == ["vacancy"]
    # tax_distress returned in 2 of 3 trials — n_trials should be 2, not 3
    v = merged["validations"][0]
    assert v["n_trials"] == 2
    assert v["trial_agreement"] == 1.0


def test_merge_picks_modal_significance_independently():
    from countyiq.lib.pass2_batched_validation import merge_trial_validations

    trials = [
        _trial(_val("assemblage", "confirmed", "high")),
        _trial(_val("assemblage", "confirmed", "medium")),
        _trial(_val("assemblage", "confirmed", "medium")),
    ]
    merged = merge_trial_validations(trials, [{"signal_key": "assemblage"}])
    v = merged["validations"][0]
    assert v["validation_status"] == "confirmed"  # unanimous status
    assert v["adjusted_significance"] == "medium"  # 2 of 3


# ---------------------------------------------------------------------------
# Pass 3 structured-first parser
# ---------------------------------------------------------------------------


def test_parse_structured_brief_happy_path():
    from countyiq.lib.pass3_brief_generation import parse_brief_output

    out = parse_brief_output(
        {
            "brief": "text [Signal: tax_distress]",
            "assessment": "emerging",
            "assessment_reasoning": "because [Signal: tax_distress]",
            "key_questions": ["q1"],
            "citations": ["tax_distress"],
            "recommendation": "investigate",
            "urgency": "none",
            "top_signal_key": "tax_distress",
            "top_risk": "owner pays it off",
            "evidence_strength": "moderate",
            "confidence": 0.75,
        }
    )
    assert "error" not in out
    assert out["recommendation"] == "investigate"
    assert out["urgency"] == "none"
    assert out["confidence"] == 0.75
    assert out["evidence_strength"] == "moderate"


def test_parse_clamps_invalid_enums():
    from countyiq.lib.pass3_brief_generation import parse_brief_output

    out = parse_brief_output(
        {
            "brief": "text",
            "assessment": "nonsense",  # not a valid assessment
            "recommendation": "maybe",  # not valid
            "urgency": "whenever",  # not valid
            "evidence_strength": "spicy",  # not valid
            "confidence": 2.5,  # out of range
        }
    )
    assert out["assessment"] == "speculative"  # clamped default
    assert out["recommendation"] is None
    assert out["urgency"] is None
    assert out["evidence_strength"] is None
    assert out["confidence"] == 1.0  # clamped to [0, 1]


def test_parse_legacy_brief_still_works():
    from countyiq.lib.pass3_brief_generation import parse_brief_output

    out = parse_brief_output(
        {
            "brief": "legacy narrative",
            "assessment": "constrained",
        }
    )
    assert "error" not in out
    assert out["recommendation"] is None
    assert out["confidence"] is None
    assert out["assessment"] == "constrained"


def test_parse_rejects_missing_brief():
    from countyiq.lib.pass3_brief_generation import parse_brief_output

    out = parse_brief_output({"assessment": "emerging"})
    assert "error" in out


# ---------------------------------------------------------------------------
# Owner-brief parser
# ---------------------------------------------------------------------------


def test_owner_brief_parser_clamps_and_defaults():
    from countyiq.lib.pass3_owner_briefs import parse_owner_brief_output

    out = parse_owner_brief_output(
        {
            "narrative": "portfolio story",
            "portfolio_strategy": "accumulator",
            "recommendation": "investigate",
            "urgency": "none",
            "evidence_strength": "strong",
            "confidence": 0.81,
            "citations": ["tax_distress"],
            "parcel_citations": ["0100101000100"],
        }
    )
    assert out["portfolio_strategy"] == "accumulator"
    assert out["recommendation"] == "investigate"
    assert out["confidence"] == 0.81


def test_owner_brief_rejects_missing_narrative():
    from countyiq.lib.pass3_owner_briefs import parse_owner_brief_output

    out = parse_owner_brief_output({"portfolio_strategy": "accumulator"})
    assert "error" in out


# ---------------------------------------------------------------------------
# Pass 2 selection gate wiring — verifies the SQL references expected
# columns and signal names.
# ---------------------------------------------------------------------------


def test_gate_query_requires_interacting_interpretive_signals():
    from countyiq.assets.enrichment.signal_validation_batched import (
        PARCELS_NEEDING_VALIDATION_QUERY,
    )

    q = PARCELS_NEEDING_VALIDATION_QUERY
    for sig in (
        "active_subdivision",
        "municipal_action",
        "ownership_change",
        "assemblage",
        "entity_assemblage",
        "zoning_mismatch",
    ):
        assert sig in q, f"interpretive signal {sig} missing from gate"
    for deterministic in (
        "tax_distress",
        "flood_zone",
        "economic_development_park",
        "environmental_diligence",
        "nearby_subdivision",
        "vacancy",
    ):
        assert deterministic not in q
    assert "WHERE 2 <=" in q


def test_fast_path_query_omits_full_scan_branch():
    from countyiq.assets.enrichment.signal_validation_batched import (
        _FULL_SCAN_BRANCH,
        PARCELS_NEEDING_VALIDATION_FAST_QUERY,
        PARCELS_NEEDING_VALIDATION_QUERY,
        pass2_config_fingerprint,
    )

    assert _FULL_SCAN_BRANCH.strip() in PARCELS_NEEDING_VALIDATION_QUERY
    assert _FULL_SCAN_BRANCH.strip() not in PARCELS_NEEDING_VALIDATION_FAST_QUERY
    assert PARCELS_NEEDING_VALIDATION_FAST_QUERY.count(
        "FROM public.development_signals ds"
    ) == (
        PARCELS_NEEDING_VALIDATION_QUERY.count("FROM public.development_signals ds") - 1
    )
    # Errored attempts stay reachable on the fast path.
    assert "ip.status = 'error'" in PARCELS_NEEDING_VALIDATION_FAST_QUERY
    assert pass2_config_fingerprint("m", 1) != pass2_config_fingerprint("m", 3)
    assert len(pass2_config_fingerprint("m", 1)) == 16


def test_prompt_version_is_stable_hash():
    """If PROMPT_VERSION changes, it should be because the template
    changed — not because of non-determinism in the hash."""
    from countyiq.lib.pass2_batched_validation import PROMPT_VERSION as P2
    from countyiq.lib.pass3_brief_generation import PROMPT_VERSION as P3
    from countyiq.lib.pass3_owner_briefs import PROMPT_VERSION as POB

    assert len(P2) == 12
    assert len(P3) == 12
    assert len(POB) == 12
    assert P2 != P3 != POB


# ---------------------------------------------------------------------------
# Model default
# ---------------------------------------------------------------------------


def test_pass2_defaults_to_luna(monkeypatch):
    """Pass 2 default is gpt-5.6-luna (expN: 15-1 vs mercury-2, blind
    judged; FINAL LINEUP 2026-08-06 in docs/decisions.md) with
    reasoning_effort=low retained as the cost control from exp H.
    deepseek-v4-flash-0731 stays the documented cost fallback via env.
    """
    from countyiq.lib.pass_llm_config import (
        resolve_pass_model,
        resolve_pass_reasoning_effort,
    )

    monkeypatch.delenv("COUNTYIQ_PASS2_MODEL", raising=False)
    monkeypatch.delenv("COUNTYIQ_OPENROUTER_MODEL", raising=False)
    monkeypatch.delenv("COUNTYIQ_PASS2_REASONING_EFFORT", raising=False)
    assert resolve_pass_model(2) == "openai/gpt-5.6-luna"
    assert resolve_pass_reasoning_effort(2) == "low"


def test_pass2_reasoning_effort_env_override(monkeypatch):
    from countyiq.lib.pass_llm_config import resolve_pass_reasoning_effort

    monkeypatch.setenv("COUNTYIQ_PASS2_REASONING_EFFORT", "medium")
    assert resolve_pass_reasoning_effort(2) == "medium"


def test_pass2_env_override_wins(monkeypatch):
    from countyiq.lib.pass_llm_config import resolve_pass_model

    monkeypatch.setenv("COUNTYIQ_PASS2_MODEL", "override/model")
    assert resolve_pass_model(2) == "override/model"
