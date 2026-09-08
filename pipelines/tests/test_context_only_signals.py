"""Context-only signal demotion (rules-first Pass 2).

Deterministic spatial facts and constraints should reach the prompt as
background context and never as validation targets.
"""

from countyiq.lib.pass2_batched_validation import (
    CONTEXT_ONLY_SIGNALS,
    _PROMPT_FORMAT_VERSION,
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


SALE_SIGNAL = {
    "signal_key": "ownership_change",
    "signal_weight": 0.1,
    "source_table": "staging.parcels",
    "source_id": "x",
    "distance_m": None,
    "evidence": {"price": 100000},
}
GROWTH_SIGNAL = {
    "signal_key": "growth_area",
    "signal_weight": 0.05,
    "source_table": "staging.growth_areas",
    "source_id": "g1",
    "distance_m": 10.0,
    "evidence": {"tier": "primary"},
}


def test_context_only_set_matches_eval_findings():
    assert CONTEXT_ONLY_SIGNALS == {
        "municipal_record",
        "nearby_subdivision",
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
        "vacancy",
    }


def test_context_signals_render_as_background():
    section = _format_context_signals([GROWTH_SIGNAL])
    assert "growth_area" in section
    assert "do NOT validate" in section


def test_prompt_excludes_context_signals_from_validation_list():
    prompt = build_batched_signal_prompt(_ctx([SALE_SIGNAL], [GROWTH_SIGNAL]))
    assert "AREA CONTEXT" in prompt
    assert "ownership_change" in prompt
    # growth_area appears only in the context block, not as a numbered
    # validation target — the count says exactly 1 signal to validate.
    assert "1 signal" in prompt


def test_no_context_signals_no_section():
    prompt = build_batched_signal_prompt(_ctx([SALE_SIGNAL], []))
    assert "AREA CONTEXT" not in prompt


def test_prompt_supplies_deterministic_arithmetic_instead_of_asking_model():
    context = _ctx([SALE_SIGNAL], [])
    context.update(
        {
            "parcel": {"owner": "SMITH JOHN", "assessed_value": 100},
            "portfolio": [
                {"assessed_value": 100},
                {"assessed_value": 300},
            ],
            "tax_claims": [{"amount": 10}, {"amount": 20}],
            "neighbors": [{"total_owed": 50}, {"total_owed": 0}],
        }
    )
    prompt = build_batched_signal_prompt(context)
    assert "tax_claim_total: 30.0" in prompt
    assert "target_assessed_share_pct: 25.0" in prompt
    assert "adjacent_delinquency_rate_pct: 50.0" in prompt
    # Bumped when the deterministic rendering changes so stored input hashes
    # invalidate: v8 retires footprint absence as a validation target.
    assert _PROMPT_FORMAT_VERSION == "evidence-contract-v8"
