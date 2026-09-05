from api.lib.development_radar import (
    SIGNAL_CAVEATS,
    SIGNAL_INTERPRETATIONS,
    SIGNAL_TITLES,
    build_signal_presentation,
    format_signal_label,
    sanitize_signals_for_public,
)

EXPECTED_SIGNAL_KEYS = {
    "active_subdivision",
    "nearby_subdivision",
    "economic_development_park",
    "municipal_action",
    "zoning_mismatch",
    "ownership_change",
    "vacancy",
    "tax_distress",
    "assemblage",
    "entity_assemblage",
    "penndot_project",
    "development_overlay",
    "local_traffic_activity",
    "growth_area",
    "soil_constraint",
    "zoning_constraint",
    "environmental_diligence",
    "flood_zone",
    "conservation_easement",
    "ag_security",
}


def test_every_signal_has_a_title_interpretation_and_caveat():
    assert set(SIGNAL_TITLES) == EXPECTED_SIGNAL_KEYS
    assert set(SIGNAL_INTERPRETATIONS) == EXPECTED_SIGNAL_KEYS
    assert set(SIGNAL_CAVEATS) == EXPECTED_SIGNAL_KEYS


def test_soil_label_names_the_actual_slope_trigger_not_drainage():
    signal = {
        "weight": -0.08,
        "site_screening_points": -15,
        "evidence": {
            "soil_units": [
                {
                    "map_unit_symbol": "PcF",
                    "map_unit_name": "PENN CHANNERY LOAM, 25 TO 50 PERCENT SLOPES, VERY STONY",
                    "coverage_pct": 67.9,
                    "drainage": "Well drained",
                    "septic_rating": "Very limited",
                    "slope_low": 25,
                    "slope_high": 50,
                    "representative_slope": 37,
                    "hydrologic_group": "B",
                }
            ]
        },
    }

    label = format_signal_label("soil_constraint", signal)
    presentation = build_signal_presentation("soil_constraint", signal)

    assert "37% representative slope" in label
    assert "Well drained" not in label
    assert presentation["score_impacts"]["site_screening"] == -15
    assert any(fact["label"] == "Mapped drainage" for fact in presentation["facts"])


def test_ag_security_is_context_and_explicitly_not_a_prohibition():
    signal = {
        "affects_eligibility": False,
        "momentum_points": 0,
        "opportunity_points": 0,
        "site_screening_points": 0,
        "evidence": {"resolution": "2020-04", "development_prohibition": False},
    }

    presentation = build_signal_presentation("ag_security", signal)

    assert presentation["affects_eligibility"] is False
    assert "not a development prohibition" in presentation["summary"]
    assert set(presentation["score_impacts"].values()) == {0}


def test_tax_claim_amounts_are_suppressed_even_when_people_display_is_allowed():
    signals = {
        "tax_distress": {
            "weight": 0.1,
            "evidence": {
                "has_current_delinquency": True,
                "total_owed": 1234.56,
                "years_delinquent": 3,
                "oldest_year": 2023,
                "source_url": "https://example.test/tax.pdf",
            },
        }
    }

    public = sanitize_signals_for_public(signals)
    evidence = public["tax_distress"]["evidence"]

    assert evidence["has_current_delinquency"] is True
    assert "total_owed" not in evidence
    assert "years_delinquent" not in evidence
    assert "oldest_year" not in evidence


def test_labels_do_not_overclaim_investor_or_assemblage_intent():
    ownership = {
        "evidence": {
            "buyer_name_looks_organizational": True,
            "saledt": "01-JAN-2026",
            "price": 250000,
        }
    }
    contiguous = {"evidence": {"contiguous_same_owner_parcels": 3}}

    assert "organization-name buyer" in format_signal_label("ownership_change", ownership)
    assert "Investor" not in format_signal_label("ownership_change", ownership)
    assert "Same recorded owner holds" in format_signal_label("entity_assemblage", contiguous)
    assert "assembling" not in format_signal_label("entity_assemblage", contiguous)
