"""Score version 7: transparent signal effects and corrected legal semantics."""

from countyiq.assets.enrichment import development_momentum as dm
from countyiq.assets.enrichment.development_signals import (
    _SIGNALS,
    BUSINESS_OWNER_REGEX,
)


def test_score_version_is_seven_and_sql_has_no_llm_multipliers():
    sql = dm.build_rebuild_sql()
    assert dm.SCORE_VERSION == 7
    assert f"{dm.SCORE_VERSION}                               AS score_version" in sql
    # The v5 multipliers keyed on Pass 2 output must be gone from the score path.
    assert "significance_multiplier" not in sql
    assert "status_multiplier" not in sql
    assert "base_weight AS effective_weight" in sql
    # Pass 2 output still travels as an annotation for the property page.
    assert "'validation_reasoning', validation_reasoning" in sql
    assert "'momentum_points', momentum_points" in sql
    assert "'opportunity_points', opportunity_points" in sql
    assert "'site_screening_points', site_screening_points" in sql


def test_opportunity_weights_cover_every_non_label_signal():
    signal_keys = {key for key, _ in _SIGNALS}
    scored = set(dm.OPPORTUNITY_WEIGHTS)
    # Own-plan / own-matter signals zero the opportunity score instead of
    # contributing to it, and exclusions never score.
    expected = signal_keys - set(dm.ACTIVE_PLAN_SIGNAL_KEYS) - {"conservation_easement"}
    assert scored == expected
    risk = {"flood_zone", "soil_constraint", "zoning_constraint", "environmental_diligence"}
    assert all(dm.OPPORTUNITY_WEIGHTS[key] <= 0 for key in risk)
    assert all(dm.OPPORTUNITY_WEIGHTS[key] >= 0 for key in scored - risk)
    assert dm.OPPORTUNITY_WEIGHTS["ag_security"] == 0


def test_only_conservation_easement_excludes_radar_eligibility():
    sql = dm.build_rebuild_sql()
    assert "BOOL_OR(signal_key = 'conservation_easement')" in sql
    assert "signal_key IN ('conservation_easement', 'ag_security')" not in sql
    assert "Agricultural Security Area enrollment (not a development prohibition)" in sql


def test_momentum_excludes_optionality_and_opportunity_gate_is_parcel_level():
    assert "vacancy" not in dm.MOMENTUM_SIGNAL_KEYS
    assert "assemblage" not in dm.MOMENTUM_SIGNAL_KEYS
    assert "municipal_action" in dm.MOMENTUM_SIGNAL_KEYS
    assert "growth_area" not in dm.OPPORTUNITY_GATE_KEYS
    sql = dm.build_rebuild_sql()
    assert "WHEN a.has_active_plan THEN 0" in sql
    assert "WHEN NOT a.passes_opportunity_gate THEN 0" in sql


def test_history_sql_compares_to_a_snapshot_at_least_one_day_old():
    assert "h.computed_at < NOW() - INTERVAL '1 day'" in dm.HISTORY_SQL
    assert "is_new = (l.pidn IS NULL)" in dm.HISTORY_SQL
    assert "ON CONFLICT (pidn, computed_at) DO NOTHING" in dm.APPEND_HISTORY_SQL


def test_signal_definitions_include_new_deterministic_signals():
    keys = [key for key, _ in _SIGNALS]
    for key in ("active_subdivision", "nearby_subdivision", "municipal_action", "entity_assemblage"):
        assert key in keys
    sql = dict(_SIGNALS)
    # Proximity joins narrow with an index-friendly envelope before the exact test.
    for key in ("nearby_subdivision", "penndot_project", "local_traffic_activity", "environmental_diligence"):
        assert "ST_Expand(" in sql[key], key
    # Extraction linking uses the normalized address function from migration 048.
    assert "public.proceeding_parcel_matches" in sql["municipal_action"]
    # Ownership change decays with age and no longer substring-matches "LP".
    assert "months_since_sale <= 3" in sql["ownership_change"]
    assert "ILIKE '%%LP%%'" not in sql["ownership_change"]
    assert r"\m(" in BUSINESS_OWNER_REGEX
    assert "point_on_parcel" in sql["active_subdivision"]
    assert "COALESCE(pp.status, '') NOT ILIKE '%%complete%%'" in sql["penndot_project"]
    assert "screen_basis', 'parcel_overlap'" in sql["soil_constraint"]
    assert "minimum_trigger_coverage_pct', 5" in sql["soil_constraint"]
    assert "development_prohibition', FALSE" in sql["ag_security"]


def test_business_owner_regex_uses_word_boundaries():
    import re

    # PostgreSQL \m / \M are word boundaries; emulate with \b for the check.
    pattern = re.compile(BUSINESS_OWNER_REGEX.replace(r"\m", r"\b").replace(r"\M", r"\b"), re.IGNORECASE)
    assert pattern.search("RIDGE HOLDINGS LP")
    assert pattern.search("ACME PROPERTIES LLC")
    assert not pattern.search("PHILPOT JOHN")
    assert not pattern.search("ALPINE MARY")
