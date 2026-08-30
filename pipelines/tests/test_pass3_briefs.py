"""Tests for Pass 3 brief generation.

Tests cover only pure-Python parts (template, prompt builder, output parser,
eligibility check).  No actual LLM calls are made and no database is required.
"""

import json
from pathlib import Path

import pytest

from countyiq.lib.pass3_brief_generation import (
    BRIEF_GENERATION_SYSTEM_PROMPT,
    BRIEF_GENERATION_USER_TEMPLATE,
    VALID_ASSESSMENTS,
    should_generate_brief,
    build_brief_generation_prompt,
    parse_brief_output,
)

BRIEF_GENERATION_PROMPT_TEXT = (
    BRIEF_GENERATION_SYSTEM_PROMPT + "\n\n" + BRIEF_GENERATION_USER_TEMPLATE
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_context():
    """Load the validated_signals_sample.json fixture."""
    fixture_path = Path(__file__).parent / "fixtures" / "validated_signals_sample.json"
    with open(fixture_path) as f:
        return json.load(f)


@pytest.fixture
def valid_brief_output():
    """Return a well-formed LLM brief generation output."""
    return {
        "brief": (
            "This 3.2-acre vacant parcel at 550 Heritage Hills Dr is at the center of "
            "active residential development. Heritage Hills Phase III, a 42-lot final "
            "subdivision plan, was approved by Manchester Township Planning Commission "
            "in July 2025 [Signal: active_subdivision]. The developer, Keystone "
            "Development Group LLC, is a verified entity controlling Heritage Hills "
            "Realty LP with a 7-parcel portfolio valued at $1.45M.\n\n"
            "The parcel's Agricultural zoning conflicts with its Medium Density "
            "Residential future land use designation [Signal: zoning_mismatch]. This "
            "mismatch is part of a corridor-wide pattern affecting 4 adjacent parcels, "
            "suggesting planned rezoning is likely. Minimal FEMA Zone AE flood overlap "
            "(9% of parcel area) along the western edge does not affect the platted "
            "lots [Signal: flood_zone]."
        ),
        "assessment": "strong_opportunity",
        "assessment_reasoning": (
            "Active approved subdivision with a verified developer and corridor-wide "
            "zoning alignment signals strong near-term development momentum. The minor "
            "flood zone constraint does not materially affect buildability."
        ),
        "key_questions": [
            "Has Keystone Development Group LLC filed for rezoning from Agricultural to Residential?",
            "What is the timeline for infrastructure (sewer/water) extension to the subdivision?",
            "Are there any outstanding conditions from the planning commission approval?",
        ],
        "citations": [
            "active_subdivision",
            "zoning_mismatch",
            "flood_zone",
        ],
    }


# ---------------------------------------------------------------------------
# TestShouldGenerateBrief
# ---------------------------------------------------------------------------

class TestShouldGenerateBrief:
    """Tests for should_generate_brief(validated_signals) -> bool."""

    def test_yes_with_high_signal(self):
        signals = [
            {"signal_key": "active_subdivision", "adjusted_significance": "high"},
        ]
        assert should_generate_brief(signals) is True

    def test_yes_with_medium_signal(self):
        signals = [
            {"signal_key": "zoning_mismatch", "adjusted_significance": "medium"},
        ]
        assert should_generate_brief(signals) is True

    def test_yes_with_mixed_signals(self):
        signals = [
            {"signal_key": "active_subdivision", "adjusted_significance": "high"},
            {"signal_key": "flood_zone", "adjusted_significance": "low"},
        ]
        assert should_generate_brief(signals) is True

    def test_no_with_all_low(self):
        signals = [
            {"signal_key": "flood_zone", "adjusted_significance": "low"},
            {"signal_key": "growth_area", "adjusted_significance": "low"},
        ]
        assert should_generate_brief(signals) is False

    def test_no_with_empty(self):
        assert should_generate_brief([]) is False

    def test_no_with_none_significance(self):
        signals = [
            {"signal_key": "ag_security", "adjusted_significance": "none"},
        ]
        assert should_generate_brief(signals) is False


# ---------------------------------------------------------------------------
# TestBuildBriefGenerationPrompt
# ---------------------------------------------------------------------------

class TestBuildBriefGenerationPrompt:
    """Tests for build_brief_generation_prompt(context) -> str."""

    def test_returns_string(self, sample_context):
        result = build_brief_generation_prompt(sample_context)
        assert isinstance(result, str)
        assert len(result) > 100

    def test_includes_parcel_info(self, sample_context):
        result = build_brief_generation_prompt(sample_context)
        assert "6700112233445" in result
        assert "KEYSTONE DEVELOPMENT GROUP LLC" in result
        assert "Manchester Township" in result
        assert "550 HERITAGE HILLS DR" in result

    def test_includes_validated_signals(self, sample_context):
        result = build_brief_generation_prompt(sample_context)
        assert "active_subdivision" in result
        assert "zoning_mismatch" in result
        assert "flood_zone" in result

    def test_includes_entity_profile(self, sample_context):
        result = build_brief_generation_prompt(sample_context)
        assert "KEYSTONE DEVELOPMENT GROUP LLC" in result
        assert "llc" in result
        assert "KEYSTONE DEV GROUP" in result

    def test_includes_portfolio_stats(self, sample_context):
        result = build_brief_generation_prompt(sample_context)
        assert "7" in result  # portfolio_count
        assert "1,450,000" in result  # portfolio_value

    def test_includes_citation_constraint(self, sample_context):
        # Static constraints live in the system prompt now; the model sees
        # system + user together, so assert on the combined pair.
        full = BRIEF_GENERATION_SYSTEM_PROMPT + "\n" + build_brief_generation_prompt(sample_context)
        assert "[Signal:" in full or "[Signal: signal_key]" in full

    def test_includes_all_assessment_categories(self, sample_context):
        full = BRIEF_GENERATION_SYSTEM_PROMPT + "\n" + build_brief_generation_prompt(sample_context)
        for assessment in VALID_ASSESSMENTS:
            assert assessment in full, f"Missing assessment category: {assessment}"

    def test_includes_do_not_invent_constraint(self, sample_context):
        full = BRIEF_GENERATION_SYSTEM_PROMPT + "\n" + build_brief_generation_prompt(sample_context)
        assert "do not invent" in full.lower() or "no invented" in full.lower()

    def test_minimal_context(self):
        """Prompt builder should handle minimal context without error."""
        minimal = {
            "pidn": "6700000000001",
            "parcel": {
                "pidn": "6700000000001",
                "owner": "DOE JANE",
                "address": "100 OAK ST",
                "assessed_value": 100000,
                "acres": 0.5,
                "property_class": "R",
                "sale_date": "",
                "sale_price": 0,
                "previous_owner": "",
                "municipality": "York City",
                "school_district": "York City",
                "source_url": "",
            },
            "entity": {"found": False},
            "portfolio": {
                "portfolio_count": 1,
                "portfolio_value": 100000,
                "portfolio_delinquency": 0,
            },
            "validated_signals": [
                {
                    "signal_key": "vacancy",
                    "validation_status": "confirmed",
                    "adjusted_significance": "medium",
                    "reasoning": "Parcel is vacant.",
                    "key_facts": ["Vacant lot"],
                    "cross_references": [],
                    "source_url": "",
                    "internal_url": "/property/6700000000001",
                },
            ],
        }
        result = build_brief_generation_prompt(minimal)
        assert isinstance(result, str)
        assert "6700000000001" in result
        assert "vacancy" in result


# ---------------------------------------------------------------------------
# TestParseBriefOutput
# ---------------------------------------------------------------------------

class TestParseBriefOutput:
    """Tests for parse_brief_output(output) -> dict."""

    def test_valid_output_parsed(self, valid_brief_output):
        result = parse_brief_output(valid_brief_output)
        assert result["brief"] == valid_brief_output["brief"]
        assert result["assessment"] == "strong_opportunity"
        assert len(result["key_questions"]) == 3
        assert len(result["citations"]) == 3
        assert "error" not in result

    def test_invalid_assessment_defaults_to_speculative(self):
        output = {
            "brief": "Some brief text here.",
            "assessment": "super_amazing",
            "assessment_reasoning": "Because reasons.",
            "key_questions": ["Question 1?"],
            "citations": ["active_subdivision"],
        }
        result = parse_brief_output(output)
        assert result["assessment"] == "speculative"

    def test_missing_brief_returns_error(self):
        output = {
            "assessment": "emerging",
            "assessment_reasoning": "Because reasons.",
            "key_questions": ["Question 1?"],
            "citations": [],
        }
        result = parse_brief_output(output)
        assert "error" in result

    def test_empty_brief_returns_error(self):
        output = {
            "brief": "",
            "assessment": "emerging",
            "assessment_reasoning": "Because reasons.",
            "key_questions": ["Question 1?"],
            "citations": [],
        }
        result = parse_brief_output(output)
        assert "error" in result

    def test_non_dict_returns_error(self):
        result = parse_brief_output("not a dict")
        assert "error" in result

    def test_all_valid_assessments_accepted(self):
        for assessment in VALID_ASSESSMENTS:
            output = {
                "brief": "Brief text.",
                "assessment": assessment,
                "assessment_reasoning": "Reasoning.",
                "key_questions": ["Q?"],
                "citations": ["test"],
            }
            result = parse_brief_output(output)
            assert result["assessment"] == assessment

    def test_missing_assessment_defaults_to_speculative(self):
        output = {
            "brief": "Brief text.",
            "assessment_reasoning": "Reasoning.",
            "key_questions": ["Q?"],
            "citations": ["test"],
        }
        result = parse_brief_output(output)
        assert result["assessment"] == "speculative"

    def test_key_questions_default_to_empty_list(self):
        output = {
            "brief": "Brief text.",
            "assessment": "emerging",
            "assessment_reasoning": "Reasoning.",
            "citations": ["test"],
        }
        result = parse_brief_output(output)
        assert result["key_questions"] == []

    def test_citations_default_to_empty_list(self):
        output = {
            "brief": "Brief text.",
            "assessment": "emerging",
            "assessment_reasoning": "Reasoning.",
            "key_questions": ["Q?"],
        }
        result = parse_brief_output(output)
        assert result["citations"] == []


# ---------------------------------------------------------------------------
# TestBriefGenerationTemplate
# ---------------------------------------------------------------------------

class TestBriefGenerationTemplate:
    """Tests for the system and user prompt contract."""

    def test_has_constraints_section(self):
        assert "CONSTRAINTS" in BRIEF_GENERATION_PROMPT_TEXT

    def test_has_do_not_invent_phrase(self):
        lower = BRIEF_GENERATION_PROMPT_TEXT.lower()
        assert "do not invent" in lower

    def test_has_signal_citation_instruction(self):
        assert "[Signal:" in BRIEF_GENERATION_PROMPT_TEXT

    def test_has_output_format(self):
        assert "brief" in BRIEF_GENERATION_PROMPT_TEXT
        assert "assessment" in BRIEF_GENERATION_PROMPT_TEXT
        assert "key_questions" in BRIEF_GENERATION_PROMPT_TEXT

    def test_has_all_assessment_values(self):
        for assessment in VALID_ASSESSMENTS:
            assert assessment in BRIEF_GENERATION_PROMPT_TEXT
