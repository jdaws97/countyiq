"""Regression coverage for the 2026-09-03 Pass 2 prompt and hashing review."""

from countyiq.lib.intelligence_common import (
    NEIGHBORS_QUERY,
    VOLATILE_EVIDENCE_KEYS,
    strip_volatile_evidence,
)
from countyiq.lib.pass2_batched_validation import (
    BATCHED_VALIDATION_SYSTEM_PROMPT,
    _format_context_signals,
    _format_precomputed_metrics,
    _format_signals_list,
    pass2_source_fingerprint,
)
from eval.build_expanded_pass2 import _active_subdivision_label

PLAN_SIGNAL = {
    "signal_key": "active_subdivision",
    "signal_weight": 0.3,
    "distance_m": 36.4,
    # Postgres orders jsonb keys by length; a fixed prefix used to drop the
    # long, decision-relevant keys.
    "evidence": {
        "prop_du": 0,
        "date_rcvd": "2025-07-10",
        "pt_subdiv": "NO",
        "prop_lots": 0,
        "plan_title": "North Valley Plan",
        "source_url": "https://example.test/layer/0",
        "pt_land_dev": "YES",
        "total_acres": 5.0,
        "plan_location": "point_on_parcel",
        "months_since_received": 13,
    },
}


def test_signal_rendering_shows_every_decision_relevant_key_but_no_urls():
    text = _format_signals_list([PLAN_SIGNAL])
    assert "pt_land_dev=YES" in text
    assert "plan_location=point_on_parcel" in text
    assert "total_acres=5.0" in text
    assert "source_url" not in text


def test_context_rendering_skips_reference_noise():
    text = _format_context_signals(
        [
            {
                "signal_key": "growth_area",
                "evidence": {"source_url": "x", "ga_type": "PGA"},
            }
        ]
    )
    assert "ga_type=PGA" in text
    assert "source_url" not in text


def test_pass2_fingerprint_ignores_age_counters_and_decayed_weights():
    base = {
        "pidn": "P1",
        "parcel": {"acres": 5},
        "signals": [PLAN_SIGNAL],
        "context_signals": [],
    }
    aged = {
        **base,
        "signals": [
            {
                **PLAN_SIGNAL,
                "signal_weight": 0.2,
                "evidence": {**PLAN_SIGNAL["evidence"], "months_since_received": 14},
            }
        ],
    }
    changed = {
        **base,
        "signals": [
            {**PLAN_SIGNAL, "evidence": {**PLAN_SIGNAL["evidence"], "prop_lots": 4}}
        ],
    }
    assert pass2_source_fingerprint(base) == pass2_source_fingerprint(aged)
    assert pass2_source_fingerprint(base) != pass2_source_fingerprint(changed)


def test_strip_volatile_evidence_removes_only_age_counters():
    evidence = {"price": 1, "months_since_sale": 3, "months_since_meeting": 2}
    assert strip_volatile_evidence(evidence) == {"price": 1}
    assert strip_volatile_evidence(None) is None
    assert "months_since_sale" in VOLATILE_EVIDENCE_KEYS


def test_precomputed_metrics_include_neighbor_acreage():
    text = _format_precomputed_metrics(
        {
            "neighbors": [{"acres": 1.25}, {"acres": 2.5}],
            "signals": [{"signal_key": "assemblage"}],
        }
    )
    assert "adjacent_parcel_count: 2" in text
    assert "adjacent_acres_total: 3.75 [Evidence: signal:assemblage]" in text


def test_neighbor_totals_keep_same_owner_parcels_and_label_the_population():
    # Two other-owner parcels share owner B; a third belongs to the subject.
    # Signal counts describe 2 parcels / 1 other owner, not all 3 neighbors.
    context = {
        "parcel": {"owner": "A"},
        "neighbors": [{"owner": "B", "acres": 1}, {"owner": "B", "acres": 2},
                      {"owner": "A", "acres": 3}],
        "signals": [{"signal_key": "assemblage", "signal_weight": .1,
                     "evidence": {"neighbor_parcels": 2, "different_owner_neighbors": 1}}],
    }
    metrics = _format_precomputed_metrics(context)
    signal = _format_signals_list(context["signals"])
    assert "adjacent_parcel_count: 3" in metrics
    assert "adjacent_acres_total: 6.0" in metrics
    assert "includes all intersecting neighbors, including same-owner parcels" in metrics
    assert "neighbor_parcels=2" in signal
    assert "different_owner_neighbors=1" in signal
    assert "Do not attribute all-neighbor acreage to the other-owner subset" in BATCHED_VALIDATION_SYSTEM_PROMPT


def test_neighbor_context_uses_the_same_topology_as_the_assemblage_signal():
    assert "AND ST_Intersects(p.geom, n.geom)" in NEIGHBORS_QUERY
    assert "AND ST_Touches" not in NEIGHBORS_QUERY


def test_land_development_with_zero_lots_uses_the_decision_fact():
    context = {
        "parcel": {"acres": 5},
        "signals": [PLAN_SIGNAL],
        "context_signals": [],
    }
    label = _active_subdivision_label(PLAN_SIGNAL, context)

    prompt = BATCHED_VALIDATION_SYSTEM_PROMPT.lower()
    assert "pt_land_dev=yes" in prompt
    assert "may legitimately report zero lots" in prompt
    assert "downgrade active_subdivision only when" in prompt
    assert "confirmed" in label["accepted_statuses"]
    assert "one- or two-lot/unit proposal is normally medium or low" in prompt
    assert "missing-footprint screens are factual context, not validation targets" in prompt
    assert any(
        "pt_land_dev=yes" in fact_group for fact_group in label["required_fact_groups"]
    )
    assert not any(
        "0 unit" in fact_group for fact_group in label["required_fact_groups"]
    )


def test_replaced_proceeding_versions_change_validation_fingerprint():
    from countyiq.lib.intelligence_common import format_proceedings_context
    from countyiq.lib.pass2_batched_validation import proceeding_context_refs

    row = {
        "proceeding_id": 41,
        "extraction_id": 52,
        "active_inference_id": 63,
        "extraction_type": "variance_request",
        "supporting_text": "The board approved the variance.",
    }
    original = {"proceedings": format_proceedings_context([row])}
    assert proceeding_context_refs(original) == {
        "proceeding:41", "extraction:52", "inference:63",
    }
    for field in ("proceeding_id", "extraction_id", "active_inference_id"):
        replacement = {"proceedings": format_proceedings_context([
            {**row, field: row[field] + 100}
        ])}
        assert pass2_source_fingerprint(original) != pass2_source_fingerprint(replacement)
    # An unversioned fixture/legacy context must not invent an identity.
    assert proceeding_context_refs({
        "proceedings": format_proceedings_context([{"supporting_text": "legacy"}])
    }) == set()


def test_neighbor_claim_without_positive_amount_remains_visible_to_the_model():
    from countyiq.lib.pass2_batched_validation import _format_neighbors
    neighbors = [
        {'pidn': 'CLAIM', 'owner': 'Cedar Estate', 'acres': 3, 'years_delinquent': 2, 'total_owed': 0},
        {'pidn': 'BALANCE', 'owner': 'Birch LLC', 'acres': 4, 'years_delinquent': 1, 'total_owed': 254.94},
        {'pidn': 'CLEAR', 'owner': 'Ash LLC', 'acres': 1, 'years_delinquent': 0, 'total_owed': 0},
    ]
    rendered = _format_neighbors(neighbors)
    assert 'Tax claim years: 2 | No positive balance supplied' in rendered
    assert '$254.94' in rendered
    metrics = _format_precomputed_metrics({'neighbors': neighbors, 'signals': [{'signal_key': 'assemblage'}]})
    assert 'adjacent_delinquent_count: 2' in metrics
    assert 'adjacent_delinquency_rate_pct: 66.67' in metrics


def test_pass2_release_identity_binds_its_shared_question_module():
    from countyiq.lib.quality_release import release_identity
    identity = release_identity(2)
    assert 'pass2_signal_validation.py' in identity['source_hashes']


def test_reference_display_wrapper_preserves_identity_and_unknown_refs():
    from countyiq.lib.pass2_signal_validation import parse_signal_validation_output
    value = dict(signal_key='assemblage', validation_status='downgraded', adjusted_significance='low',
        reasoning='Fragmented ownership [Evidence: signal:assemblage]', key_facts=[],
        cross_references=['Evidence: signal:assemblage', 'Evidence: context:vacancy', 'Evidence: signal:invented', 'Evidence: signal:assemblage extra'])
    parsed = parse_signal_validation_output(value)
    assert parsed['cross_references'] == ['signal:assemblage', 'context:vacancy', 'signal:invented', 'Evidence: signal:assemblage extra']
    assert value['cross_references'][0] == 'Evidence: signal:assemblage'
