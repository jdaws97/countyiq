"""Unit coverage for fail-closed LLM integrity contracts."""

from unittest.mock import Mock

from countyiq.lib.intelligence_integrity import (
    content_hash,
    inference_input_hash,
    pass0_semantic_decision,
    record_validation_rejection,
    signal_validation_consequence,
    validate_entity_membership,
    validate_owner_brief_citations,
    validate_parcel_brief_citations,
    validate_pass0_extractions,
    validate_pass2_evidence_refs,
)


def test_validation_rejection_is_persisted_as_normalized_json() -> None:
    database = Mock()
    database.execute.return_value = [(17,)]

    rejection_id = record_validation_rejection(
        database,
        subject_key="parcel:123",
        pass_number=3,
        output_kind="parcel_brief",
        source_hash="source",
        input_hash="input",
        requested_model="test/model",
        prompt_version="p3-test",
        errors=[" missing citation ", "", "unknown signal"],
    )

    assert rejection_id == 17
    params = database.execute.call_args.args[1]
    assert params[-1] == '["missing citation","unknown signal"]'


def test_pass0_requires_source_text_and_exact_quote() -> None:
    extraction = {
        "extraction_type": "rezoning_application",
        "applicant_name": "Acme LLC",
        "parcel_reference": "123",
        "project_name": "Acme Site",
        "decision": "approved",
        "supporting_text": "The board approved the Acme application.",
    }

    assert validate_pass0_extractions(
        [extraction], "Minutes: The board approved the Acme application. Next item."
    ) == []
    assert "source text is unavailable" in validate_pass0_extractions(
        [extraction], ""
    )[0]
    assert "not present in source" in validate_pass0_extractions(
        [{**extraction, "supporting_text": "The board denied it."}],
        "The board approved the Acme application.",
    )[0]


def test_pass0_rejects_duplicate_and_conflicting_matters() -> None:
    base = {
        "extraction_type": "rezoning_application",
        "applicant_name": "Acme LLC",
        "parcel_reference": "123",
        "project_name": "Acme Site",
        "decision": "approved",
        "supporting_text": "Acme was approved.",
    }
    errors = validate_pass0_extractions(
        [base, {**base, "decision": "denied"}], "Acme was approved."
    )
    assert any("conflicts" in error for error in errors)


def test_pass0_semantic_fingerprint_ignores_extraction_order() -> None:
    first = {"extraction_type": "variance_request", "applicant_name": "A"}
    second = {"extraction_type": "rezoning_application", "applicant_name": "B"}
    assert pass0_semantic_decision([first, second]) == pass0_semantic_decision(
        [second, first]
    )


def _entity_records() -> dict:
    return {
        "parcels": [{"pidn": "P1", "owner_full": "ACME LLC"}],
        "tax_claims": [],
        "plcb_licenses": [],
        "corporate_entities": [{"entity_name": "ACME HOLDINGS"}],
        "proceedings": [],
    }


def _valid_entity_partition() -> dict:
    return {
        "entities": [{
            "canonical_name": "ACME LLC",
            "member_names": ["ACME LLC", "ACME HOLDINGS"],
            "reasoning": "The candidate names are grouped [Evidence: candidate:ACME LLC].",
            "linked_records": {
                "parcels": ["P1"],
                "tax_claims": [],
                "plcb_licenses": [],
                "corporate_entities": ["ACME HOLDINGS"],
                "proceedings": [],
            },
            "relationships": [],
        }],
        "rejected_matches": [],
        "abstentions": [],
    }


def test_identity_membership_accepts_exact_partition() -> None:
    assert validate_entity_membership(
        _valid_entity_partition(), _entity_records(), ["ACME LLC", "ACME HOLDINGS"]
    ) == []


def test_identity_membership_rejects_fabricated_id_and_overlap() -> None:
    parsed = _valid_entity_partition()
    parsed["entities"][0]["linked_records"]["parcels"] = ["MADE-UP"]
    parsed["entities"].append({
        "canonical_name": "ACME HOLDINGS",
        "member_names": ["ACME HOLDINGS"],
        "reasoning": "The candidate is separate [Evidence: candidate:ACME HOLDINGS].",
        "linked_records": {
            "parcels": [], "tax_claims": [], "plcb_licenses": [],
            "corporate_entities": [], "proceedings": [],
        },
        "relationships": [],
    })

    errors = validate_entity_membership(
        parsed, _entity_records(), ["ACME LLC", "ACME HOLDINGS"]
    )
    assert any("absent from input" in error for error in errors)
    assert any("appears in entities" in error for error in errors)


def test_identity_membership_requires_complete_accounting() -> None:
    parsed = _valid_entity_partition()
    parsed["entities"][0]["member_names"] = ["ACME LLC"]
    errors = validate_entity_membership(
        parsed, _entity_records(), ["ACME LLC", "ACME HOLDINGS"]
    )
    assert any("not accounted for" in error for error in errors)


def _signal_validations() -> list[dict]:
    return [
        {
            "signal_key": "vacancy",
            "validation_status": "confirmed",
            "adjusted_significance": "high",
            "reasoning": "The vacancy flag is present [Evidence: signal:vacancy].",
            "cross_references": ["signal:vacancy"],
        },
        {
            "signal_key": "assemblage",
            "validation_status": "confirmed",
            "adjusted_significance": "medium",
            "reasoning": "Adjacent ownership supports the pattern [Evidence: signal:assemblage].",
            "cross_references": ["signal:assemblage"],
        },
    ]


def test_pass2_requires_known_inline_evidence_refs() -> None:
    signals = [{"signal_key": "vacancy"}, {"signal_key": "assemblage"}]
    assert validate_pass2_evidence_refs(
        _signal_validations(),
        signals,
        cross_signal_insight=(
            "The signals reinforce one another [Signal: vacancy] [Signal: assemblage]."
        ),
    ) == []

    invalid = _signal_validations()
    invalid[0]["cross_references"] = ["signal:not-real"]
    errors = validate_pass2_evidence_refs(invalid, signals)
    assert any("required signal:vacancy" in error for error in errors)
    assert any("unknown evidence references" in error for error in errors)


def _parcel_brief() -> dict:
    return {
        "recommendation": "watchlist",
        "urgency": "near_term_90d",
        "top_signal_key": "vacancy",
        "top_risk": "Timing remains uncertain [Signal: assemblage].",
        "evidence_strength": "moderate",
        "assessment": "emerging",
        "assessment_reasoning": "Vacancy raises interest [Signal: vacancy].",
        "brief": (
            "The site shows potential [Signal: vacancy]. "
            "Assembly remains incomplete [Signal: assemblage]."
        ),
        "citations": ["vacancy", "assemblage"],
    }


def test_parcel_brief_citations_are_bidirectional_and_consistent() -> None:
    assert validate_parcel_brief_citations(
        _parcel_brief(), {"vacancy", "assemblage"}
    ) == []

    invalid = _parcel_brief()
    invalid["brief"] = "The site shows potential."
    invalid["recommendation"] = "pursue_now"
    invalid["assessment"] = "not_actionable"
    errors = validate_parcel_brief_citations(
        invalid, {"vacancy", "assemblage"}
    )
    assert any("uncited brief" in error for error in errors)
    assert any("contradicts assessment" in error for error in errors)

    mixed = _parcel_brief()
    # One uncited lead sentence followed by a cited one is accepted: citation
    # is enforced per field, and the identifier checks stay strict.
    mixed["brief"] = (
        "The site shows potential. Vacancy supports it [Signal: vacancy]. "
        "Assembly remains incomplete [Signal: assemblage]."
    )
    assert validate_parcel_brief_citations(mixed, {"vacancy", "assemblage"}) == []

    decimal = _parcel_brief()
    decimal["brief"] = "The 2.5 acre site shows potential [Signal: vacancy]."
    decimal["citations"] = ["vacancy", "assemblage"]
    # assemblage remains used by top_risk, so decimal punctuation must not
    # create an artificial uncited sentence fragment.
    assert validate_parcel_brief_citations(
        decimal, {"vacancy", "assemblage"}
    ) == []


def test_parcel_brief_cannot_hide_unsupported_parcel_markers_beside_valid_signals() -> None:
    for field in ("brief", "assessment_reasoning", "top_risk"):
        parsed = _parcel_brief()
        parsed[field] += " An unrelated property is approved [Parcel: NOT-IN-CONTEXT]."
        errors = validate_parcel_brief_citations(parsed, {"vacancy", "assemblage"})
        assert any(f"{field} uses [Parcel: PIDN]" in error for error in errors)


def test_owner_brief_requires_known_signal_and_parcel_markers() -> None:
    parsed = {
        "brief_text": "Distress is concentrated [Signal: tax_distress] [Parcel: P1].",
        "concentration_notes": "Two assets share one area [Parcel: P1].",
        "key_pattern": "Tax distress is the main pattern [Signal: tax_distress].",
        "top_risk": "The evidence covers one parcel [Parcel: P1].",
        "citations": ["tax_distress"],
        "parcel_citations": ["P1"],
        "recommendation": "monitor",
        "evidence_strength": "weak",
        "urgency": "long_term_12mo",
    }
    assert validate_owner_brief_citations(
        parsed, {"tax_distress"}, {"P1"}
    ) == []

    parsed["brief_text"] = "An uncited portfolio assertion."
    assert any(
        "uncited owner brief_text" in error
        for error in validate_owner_brief_citations(
            parsed, {"tax_distress"}, {"P1"}
        )
    )

    parsed["brief_text"] = "Distress is concentrated [Signal: tax_distress] [Parcel: P1]."
    parsed["evidence_strength"] = "moderate"
    parsed["recommendation"] = "watch"
    parsed["urgency"] = "none"
    assert validate_owner_brief_citations(parsed, {"tax_distress"}, {"P1"}) == []
    parsed["urgency"] = "urgent_30d"
    assert "investigation briefs must not invent urgency" in validate_owner_brief_citations(parsed, {"tax_distress"}, {"P1"})


def test_input_hash_changes_with_model_or_prompt_but_source_hash_does_not() -> None:
    source_hash = content_hash({"evidence": [1, 2, 3]})
    assert source_hash == content_hash({"evidence": [1, 2, 3]})
    baseline = inference_input_hash(
        source_hash, requested_model="model-a", prompt_version="p1"
    )
    assert baseline != inference_input_hash(
        source_hash, requested_model="model-b", prompt_version="p1"
    )
    assert baseline != inference_input_hash(
        source_hash, requested_model="model-a", prompt_version="p2"
    )


def test_pass2_consequence_ignores_only_non_serving_flips() -> None:
    prior = {
        "validations": [
            {
                "signal_key": "vacancy",
                "validation_status": "downgraded",
                "adjusted_significance": "low",
            }
        ]
    }
    wording_flip = [
        {
            "signal_key": "vacancy",
            "validation_status": "irrelevant",
            "adjusted_significance": "none",
        }
    ]
    consequential_flip = [
        {
            "signal_key": "vacancy",
            "validation_status": "confirmed",
            "adjusted_significance": "medium",
        }
    ]
    assert signal_validation_consequence(prior) == signal_validation_consequence(
        wording_flip
    )
    assert signal_validation_consequence(prior) != signal_validation_consequence(
        consequential_flip
    )
    assert signal_validation_consequence({"status": "confirmed"}) == []


def test_brief_dependencies_bind_parcel_key_and_inference():
    import pytest
    from countyiq.lib.intelligence_integrity import signal_version_refs
    rows = [{"pidn": "123", "signal_key": "growth_area", "active_inference_id": 42}]
    assert signal_version_refs(rows + rows) == ["signal-version:123:growth_area:42"]
    assert signal_version_refs([dict(rows[0], pidn=None)], pidn="456") == [
        "signal-version:456:growth_area:42"
    ]
    for invalid in (None, 0, True, "42"):
        with pytest.raises(ValueError):
            signal_version_refs([dict(rows[0], active_inference_id=invalid)])


def test_owner_context_tracks_municipalities_without_signal_order_churn():
    from countyiq.lib.pass3_owner_briefs import owner_brief_context
    from countyiq.lib.intelligence_integrity import content_hash
    owner = {"owner_id": 1, "canonical_name": "Example", "entity_type": "llc",
             "pidns": ["1", "2"], "n_parcels": 2}
    evidence = [{"pidn": "1", "municipality": "York"}, {"pidn": "2", "municipality": None}]
    before = owner_brief_context(owner, evidence)
    assert before["signal_municipalities"] == {"1": "York", "2": None}
    assert content_hash(before) == content_hash(owner_brief_context(owner, list(reversed(evidence))))
    assert content_hash(before) != content_hash(owner_brief_context(
        owner, [dict(evidence[0], municipality="Hanover"), evidence[1]]
    ))
    assert "signal_municipalities" not in owner
