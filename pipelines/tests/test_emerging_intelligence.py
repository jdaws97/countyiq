from copy import deepcopy

import pytest
from countyiq.lib.emerging_intelligence import analysis_prompt, validate_analysis
from countyiq.lib.emerging_packets import build_packet
from jsonschema import ValidationError


def text_source(source_id, text, document_identity):
    return {
        "id": source_id,
        "text": text,
        "document_identity": document_identity,
    }


def packet_with_sources(*sources):
    return {"sources": list(sources)}


def claim(source_id, quote):
    return {
        "source_id": source_id,
        "quote": quote,
        "fact_keys": [],
        "statement": "The source contains the quoted observation.",
    }


def analysis_for(*supporting_facts, status="supported", strength="moderate"):
    source_ids = [fact["source_id"] for fact in supporting_facts]
    citations = " ".join(f"[Evidence:source:{source_id}]" for source_id in source_ids)
    return {
        "hypotheses": [
            {
                "family": "business_expansion",
                "title": "Potential expansion",
                "hypothesis": f"The observations may indicate expansion. {citations}",
                "status": status,
                "evidence_strength": strength,
                "stage": f"Early planning. {citations}",
                "supporting_facts": list(supporting_facts),
                "contrary_evidence": [],
                "alternatives": [
                    {
                        "explanation": "Routine maintenance could explain the records.",
                        "why_plausible": f"The records are preliminary. {citations}",
                        "distinguishing_check": "Review the submitted plans.",
                    }
                ],
                "unknowns": ["The project scope is unknown."],
                "next_checks": [
                    {
                        "question": "Was a plan approved?",
                        "source_to_check": "Municipal decision record",
                        "why_it_changes_the_case": "Approval would clarify the stage.",
                    }
                ],
                "opportunities": [],
                "project_types": [],
            }
        ],
        "abstention_reason": None,
        "source_presentations": [
            {
                "source_id": source_id,
                "language": "en",
                "english_text": None,
            }
            for source_id in source_ids
        ],
    }


def canonical_source():
    return {
        "seed_bundle": "seed",
        "municipal_bundles": [
            {
                "subject_key": "seed",
                "municipality": "Example Township",
                "sources": [
                    {
                        "id": "old",
                        "record_key": "municipal:old",
                        "meeting_date": "2026-01-10T00:00:00+00:00",
                        "url": "https://example.test/old",
                        "text": "Old municipal observation.",
                    },
                    {
                        "id": "new-date",
                        "record_key": "municipal:new-date",
                        "meeting_date": "2026-03-10T00:00:00+00:00",
                        "url": "https://example.test/new-date",
                        "text": "Newer municipal observation.",
                    },
                    {
                        "id": "new-observed",
                        "record_key": "municipal:new-observed",
                        "meeting_date": "2026-01-11T00:00:00+00:00",
                        "url": "https://example.test/new-observed",
                        "text": "Later observed municipal observation.",
                    },
                ],
            }
        ],
        "record_availability": {
            "municipal:old": "2026-01-12T00:00:00+00:00",
            "municipal:new-date": "2026-01-12T00:00:00+00:00",
            "municipal:new-observed": "2026-03-11T00:00:00+00:00",
        },
        "property_bundles": [
            {
                "pidn": "parcel-1",
                "relationship": "adjoins the seed parcel",
                "source": {
                    "sources": [
                        {
                            "id": "parcel",
                            "facts": {
                                "address": "100 Current Context Road",
                                "owner": "Current Owner",
                                "acres": 5,
                            },
                        }
                    ]
                },
            }
        ],
        "relationships": [{"from": "parcel-1", "to": "seed", "kind": "touches"}],
        "settings": {"neighbor_limit": 6},
        "scope_limits": {"municipal_records": 3},
    }


def test_empty_abstention_succeeds_with_nonempty_source_packet():
    packet = packet_with_sources(text_source("S1", "A meeting was held.", "doc-1"))
    analysis = {
        "hypotheses": [],
        "abstention_reason": "The packet has no project-specific evidence.",
        "source_presentations": [],
    }

    assert validate_analysis(analysis, packet) == analysis


@pytest.mark.parametrize(
    ("claim_value", "error"),
    [
        (claim("S1", "Forged quote."), "absent from its source"),
        (claim("S9", "Permit application."), "unknown source"),
    ],
)
def test_rejects_forged_quotes_and_unknown_sources(claim_value, error):
    packet = packet_with_sources(
        text_source("S1", "Permit application.", "doc-1"),
        text_source("S2", "Utility work.", "doc-2"),
    )
    analysis = analysis_for(claim_value, claim("S2", "Utility work."))

    with pytest.raises(ValueError, match=error):
        validate_analysis(analysis, packet)


def test_rejects_strong_case_corroborated_only_by_same_document_url():
    packet = packet_with_sources(
        text_source("S1", "Permit application.", "https://example.test/agenda"),
        text_source("S2", "Utility work.", "https://example.test/agenda"),
    )
    analysis = analysis_for(
        claim("S1", "Permit application."),
        claim("S2", "Utility work."),
        strength="strong",
    )

    with pytest.raises(ValueError, match="distinct source records"):
        validate_analysis(analysis, packet)


def test_rejects_act_readiness_for_an_early_signal():
    packet = packet_with_sources(text_source("S1", "Permit application.", "doc-1"))
    analysis = analysis_for(claim("S1", "Permit application."), status="early_signal")
    analysis["hypotheses"][0]["opportunities"] = [
        {
            "audience": "service_business",
            "services": ["engineering"],
            "title": "Offer engineering services",
            "rationale": "A permit was filed. [Evidence:source:S1]",
            "next_action": "Contact the applicant.",
            "target_role": "Applicant representative",
            "readiness": "act",
            "commercial_basis": {
                key: claim("S1", "Permit application.")
                for key in ("need", "timing", "qualification_route")
            },
            "blockers": ["The scope is unknown."],
            "disqualifiers": ["The filing may be withdrawn."],
        }
    ]

    with pytest.raises(ValueError, match="cannot be ready to act"):
        validate_analysis(analysis, packet)


def test_schema_requires_plausible_alternative():
    packet = packet_with_sources(text_source("S1", "Permit application.", "doc-1"))
    analysis = analysis_for(claim("S1", "Permit application."), status="early_signal")
    analysis["hypotheses"][0]["alternatives"] = []

    with pytest.raises(ValidationError):
        validate_analysis(analysis, packet)


def qualified_analysis():
    text = "The authority seeks civil design proposals for the water extension. Submit qualifications to the authority before the design review."
    packet = packet_with_sources(text_source("S1", text, "doc-1"))
    analysis = analysis_for(claim("S1", text), status="early_signal")
    opportunity = {
        "audience": "service_business",
        "services": ["engineering"],
        "title": "Qualify civil design scope",
        "rationale": "The authority is seeking design proposals. [Evidence:source:S1]",
        "next_action": "Review the authority's qualifications process and scope.",
        "target_role": "Civil engineering firm",
        "readiness": "qualify",
        "commercial_basis": {
            "need": claim("S1", "civil design proposals for the water extension"),
            "timing": claim("S1", "before the design review"),
            "qualification_route": claim(
                "S1", "Submit qualifications to the authority"
            ),
        },
        "blockers": ["Firm eligibility needs review."],
        "disqualifiers": ["The firm cannot meet the qualifications."],
    }
    analysis["hypotheses"][0]["opportunities"] = [opportunity]
    return packet, analysis


def test_qualified_opportunity_requires_all_three_source_backed_premises():
    packet, analysis = qualified_analysis()
    assert validate_analysis(analysis, packet) == analysis
    analysis["hypotheses"][0]["opportunities"][0]["commercial_basis"] = None
    with pytest.raises(ValueError, match="needs evidence of need, timing"):
        validate_analysis(analysis, packet)


def test_commercial_route_cannot_borrow_or_invent_a_source_quote():
    packet, analysis = qualified_analysis()
    basis = analysis["hypotheses"][0]["opportunities"][0]["commercial_basis"]
    basis["qualification_route"]["quote"] = (
        "Contact the general contractor to book equipment."
    )
    with pytest.raises(ValueError, match="absent from its source"):
        validate_analysis(analysis, packet)


def test_distinct_commercial_scopes_can_share_an_audience():
    packet, analysis = qualified_analysis()
    first = analysis["hypotheses"][0]["opportunities"][0]
    second = deepcopy(first)
    second["title"] = "Review design partnership eligibility"
    analysis["hypotheses"][0]["opportunities"].append(second)
    assert (
        len(validate_analysis(analysis, packet)["hypotheses"][0]["opportunities"]) == 2
    )
    second["title"] = first["title"]
    with pytest.raises(ValueError, match="must be distinct"):
        validate_analysis(analysis, packet)


def test_rejects_duplicate_observations():
    packet = packet_with_sources(text_source("S1", "Permit application.", "doc-1"))
    repeated = claim("S1", "Permit application.")
    analysis = analysis_for(repeated, deepcopy(repeated), status="early_signal")

    with pytest.raises(ValueError, match="Duplicate observations"):
        validate_analysis(analysis, packet)


def test_historical_packet_excludes_newer_records_and_current_context_from_model_prompt():
    packet = build_packet(
        canonical_source(),
        captured_at="2026-02-01T00:00:00+00:00",
        cutoff="2026-02-01T00:00:00+00:00",
    )

    assert packet["temporal_mode"] == "observed_cutoff"
    assert [source["original_id"] for source in packet["sources"]] == ["old"]
    assert packet["sources"][0]["document_identity"] == "https://example.test/old"
    assert packet["sources"][0]["available_at"] == "2026-01-12T00:00:00+00:00"
    assert packet["properties"] == []
    assert all(
        source["original_id"] != "retrieval_relationships"
        for source in packet["sources"]
    )

    # The raw source remains as a replay-verification dependency snapshot. The
    # analyst receives analysis_prompt(), which deliberately omits that snapshot.
    prompt = analysis_prompt(packet)
    assert "Current Owner" not in prompt
    assert "adjoins the seed parcel" not in prompt
    assert "Newer municipal observation." not in prompt
    assert "Later observed municipal observation." not in prompt


def test_historical_cutoff_cannot_follow_packet_capture():
    with pytest.raises(ValueError, match="cannot follow packet capture"):
        build_packet(
            canonical_source(),
            captured_at="2026-02-01T00:00:00+00:00",
            cutoff="2026-02-02T00:00:00+00:00",
        )


def test_replay_excludes_current_neighbor_discovery_even_for_old_records():
    source = canonical_source()
    neighbor = deepcopy(source["municipal_bundles"][0])
    neighbor["subject_key"] = "later-discovered-neighbor"
    neighbor["sources"][0]["text"] = "A neighboring company's old application."
    source["municipal_bundles"].append(neighbor)
    packet = build_packet(
        source, captured_at="2026-09-08T00:00:00Z", cutoff="2026-02-01T00:00:00Z"
    )
    prompt = analysis_prompt(packet)
    assert "neighboring company's" not in prompt
    assert "adjoining_parcels_found" not in prompt
    assert len(packet["sources"]) == 1


def test_empty_historical_packet_abstains_without_invoking_model():
    from countyiq.lib.emerging_intelligence import generate_analysis

    packet = {"sources": []}

    def unexpected_call(*args, **kwargs):
        raise AssertionError("No model call is needed without source observations")

    result, attempts = generate_analysis(packet, None, unexpected_call)
    assert attempts == 0
    assert result["hypotheses"] == []
    assert validate_analysis(result, packet) == result


def test_packet_cannot_substitute_an_unrelated_source_policy():
    from countyiq.lib.emerging_packets import DEFAULT_SETTINGS, fetch_scope

    with pytest.raises(ValueError, match="configured county parcel-source policy"):
        fetch_scope(
            None,
            "seed",
            {**DEFAULT_SETTINGS, "open_data_key": "another_permitted_source"},
        )
