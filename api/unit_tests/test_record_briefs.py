"""Record summaries stay grounded without depending on paid interpretation."""

from copy import deepcopy

from api.lib.record_briefs import build_record_brief


def build(signals):
    return build_record_brief(signals, source_updated_at="2026-09-05")


def test_recorded_activity_keeps_concurrent_constraints_and_source_citations():
    result = build(
        {
            "active_subdivision": {
                "evidence": {"plan_title": "Creekside", "distance_m": 0},
                "distance_m": 0,
            },
            "ownership_change": {
                "evidence": {"price": 1100000, "saledt": "2026-04-08"}
            },
            "flood_zone": {"evidence": {"overlap_pct": 12}},
            "soil_constraint": {
                "evidence": {"representative_slope": 18, "coverage_pct": 35}
            },
            "growth_area": {"evidence": {"ga_type": "PGA"}},
        }
    )
    keys = {finding["signal_key"] for finding in result["findings"]}
    assert keys == {
        "active_subdivision",
        "ownership_change",
        "flood_zone",
        "soil_constraint",
    }
    assert result["signal_count"] == 5
    text = " ".join(finding["text"] for finding in result["findings"])
    assert "Creekside" in text
    assert "$1,100,000" in text
    assert "12" in text
    assert all(
        f"[Signal: {finding['signal_key']}]" in finding["text"]
        for finding in result["findings"]
    )
    assert any(
        "boundary include this parcel" in question for question in result["questions"]
    )
    assert "not a surveyed plan boundary" in result["findings"][0]["caveat"]


def test_model_judgments_cannot_change_the_record_summary():
    original = {
        "ownership_change": {"evidence": {"price": 250000, "saledt": "2026-02-01"}}
    }
    decorated = deepcopy(original)
    decorated["ownership_change"].update(
        validation_status="validated",
        adjusted_significance="high",
        validation_reasoning="The buyer will build warehouses; acquire immediately.",
        confidence=1,
    )
    assert build(original) == build(decorated)
    assert "confidence" not in build(original)
    assert "recommendation" not in build(original)


def test_exact_tax_balances_never_enter_summary():
    signals = {
        "tax_distress": {"evidence": {"total_owed": 1234567.89, "years_delinquent": 8}},
    }
    result = build(signals)
    assert "1234567" not in str(result)
    assert "8 years" not in str(result)
    assert "Tax Claim Bureau" in result["questions"][0]
    assert signals["tax_distress"]["evidence"]["total_owed"] == 1234567.89


def test_easement_is_not_lost_behind_activity_or_asa_context():
    result = build(
        {
            "ownership_change": {"evidence": {"price": 200000}},
            "active_subdivision": {"evidence": {"plan_title": "A"}},
            "municipal_action": {"evidence": {"extraction_type": "hearing"}},
            "conservation_easement": {"evidence": {"ease_id": "E-123"}},
            "ag_security": {"evidence": {"resolution": "2026-1"}},
        }
    )
    constraint = next(
        f for f in result["findings"] if f["signal_key"] == "conservation_easement"
    )
    assert constraint["category"] == "constraint"
    asa = build({"ag_security": {"evidence": {"resolution": "2026-1"}}})
    assert asa["findings"][0]["category"] == "context"
    assert "does not itself prevent" in asa["findings"][0]["caveat"]


def test_summary_is_stable_for_reordered_inputs_and_ignores_unknown_signals():
    signals = {
        "flood_zone": {"evidence": {"overlap_pct": 5}},
        "ownership_change": {"evidence": {"price": 50000}},
    }
    assert build(signals) == build(dict(reversed(list(signals.items()))))
    assert build(None) is None
    assert build({}) is None
    assert build({"seller_wants_to_sell": {"confidence": 1}}) is None
