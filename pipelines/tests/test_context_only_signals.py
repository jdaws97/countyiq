"""Context-only signal demotion (rules-first Pass 2).

Deterministic spatial facts and constraints should reach the prompt as
background context and never as validation targets.
"""

from countyiq.lib.pass2_batched_validation import (
    CONTEXT_ONLY_SIGNALS,
    _format_context_signals,
    build_batched_signal_prompt,
)


def _ctx(signals, context_signals):
    return {
        "pidn": "6700012345678",
        "parcel": {"owner": "SMITH JOHN"},
        "entity": {"found": False},
        "portfolio": [],
        "tax_claims": [],
        "neighbors": [],
        "corporate": [],
        "proceedings": [],
        "signals": signals,
        "context_signals": context_signals,
    }


VACANCY_SIGNAL = {
    "signal_key": "vacancy", "signal_weight": 0.12,
    "source_table": "staging.structures", "source_id": "x",
    "distance_m": None, "evidence": {"structure_count": 0},
}
GROWTH_SIGNAL = {
    "signal_key": "growth_area", "signal_weight": 0.05,
    "source_table": "staging.growth_areas", "source_id": "g1",
    "distance_m": 10.0, "evidence": {"tier": "primary"},
}


def test_context_only_set_matches_eval_findings():
    assert CONTEXT_ONLY_SIGNALS == {
        "growth_area",
        "development_overlay",
        "local_traffic_activity",
        "soil_constraint",
        "zoning_constraint",
        "economic_development_park",
        "tax_distress",
        "penndot_project",
        "flood_zone",
        "environmental_diligence",
        "conservation_easement",
        "ag_security",
    }


def test_context_signals_render_as_background():
    section = _format_context_signals([GROWTH_SIGNAL])
    assert "growth_area" in section
    assert "do NOT validate" in section


def test_prompt_excludes_context_signals_from_validation_list():
    prompt = build_batched_signal_prompt(_ctx([VACANCY_SIGNAL], [GROWTH_SIGNAL]))
    assert "AREA CONTEXT" in prompt
    assert "vacancy" in prompt
    # growth_area appears only in the context block, not as a numbered
    # validation target — the count says exactly 1 signal to validate.
    assert "1 signal" in prompt


def test_no_context_signals_no_section():
    prompt = build_batched_signal_prompt(_ctx([VACANCY_SIGNAL], []))
    assert "AREA CONTEXT" not in prompt
