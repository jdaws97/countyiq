"""Tests for Pass 2 signal validation.

Tests cover only pure-Python parts (templates, prompt builder, output parser).
No actual LLM calls are made and no database is required.
"""

import json
from pathlib import Path

import pytest

from countyiq.lib.pass2_signal_validation import (
    SIGNAL_TEMPLATES,
    VALID_STATUSES,
    VALID_SIGNIFICANCE,
    build_signal_validation_prompt,
    parse_signal_validation_output,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_context():
    """Load the signal_context_sample.json fixture."""
    fixture_path = Path(__file__).parent / "fixtures" / "signal_context_sample.json"
    with open(fixture_path) as f:
        return json.load(f)


@pytest.fixture
def valid_llm_output():
    """Return a well-formed LLM signal validation output."""
    return {
        "signal_key": "active_subdivision",
        "validation_status": "confirmed",
        "adjusted_significance": "high",
        "reasoning": "Plan is recent (2025), within 85m, and already approved by planning commission.",
        "key_facts": [
            "Heritage Hills Phase III approved 2025-07-10",
            "42 proposed lots on 28.6 acres",
            "Owner is verified development LLC",
        ],
        "cross_references": [
            {
                "source": "proceedings",
                "detail": "Manchester Township Planning Commission approved 2025-07-10",
            }
        ],
    }


# ---------------------------------------------------------------------------
# TestSignalTemplates
# ---------------------------------------------------------------------------

class TestSignalTemplates:
    """Tests for the SIGNAL_TEMPLATES dict."""

    EXPECTED_SIGNAL_TYPES = [
        "active_subdivision",
        "tax_distress",
        "ownership_change",
        "zoning_mismatch",
        "vacancy",
        "assemblage",
        "economic_development_park",
        "penndot_project",
        "growth_area",
        "flood_zone",
        "conservation_easement",
        "ag_security",
    ]

    def test_all_12_signal_types_have_templates(self):
        for signal_type in self.EXPECTED_SIGNAL_TYPES:
            assert signal_type in SIGNAL_TEMPLATES, f"Missing template for {signal_type}"

    def test_exactly_14_templates(self):
        # 12 original signal types plus municipal_action and entity_assemblage.
        assert len(SIGNAL_TEMPLATES) == 14

    def test_each_has_base_questions(self):
        for signal_type, template in SIGNAL_TEMPLATES.items():
            assert "base_questions" in template, f"{signal_type} missing base_questions"
            assert len(template["base_questions"]) > 0, f"{signal_type} has empty base_questions"

    def test_each_has_conditional_questions_key(self):
        for signal_type, template in SIGNAL_TEMPLATES.items():
            assert "conditional_questions" in template, (
                f"{signal_type} missing conditional_questions"
            )

    def test_base_questions_are_strings(self):
        for signal_type, template in SIGNAL_TEMPLATES.items():
            for q in template["base_questions"]:
                assert isinstance(q, str), f"{signal_type} base question is not a string: {q}"

    def test_conditional_questions_structure(self):
        """Conditional questions should map condition keys to lists of strings."""
        for signal_type, template in SIGNAL_TEMPLATES.items():
            cond = template["conditional_questions"]
            assert isinstance(cond, dict), f"{signal_type} conditional_questions is not a dict"
            for key, questions in cond.items():
                assert isinstance(questions, list), (
                    f"{signal_type} conditional_questions[{key}] is not a list"
                )
                for q in questions:
                    assert isinstance(q, str), (
                        f"{signal_type} conditional_questions[{key}] contains non-string: {q}"
                    )

    def test_active_subdivision_has_conditionals(self):
        cond = SIGNAL_TEMPLATES["active_subdivision"]["conditional_questions"]
        assert "has_proceedings" in cond
        assert "has_corporate" in cond

    def test_economic_park_has_no_conditionals(self):
        cond = SIGNAL_TEMPLATES["economic_development_park"]["conditional_questions"]
        assert len(cond) == 0

    def test_penndot_has_no_conditionals(self):
        cond = SIGNAL_TEMPLATES["penndot_project"]["conditional_questions"]
        assert len(cond) == 0

    def test_growth_area_has_no_conditionals(self):
        cond = SIGNAL_TEMPLATES["growth_area"]["conditional_questions"]
        assert len(cond) == 0

    def test_flood_zone_has_no_conditionals(self):
        cond = SIGNAL_TEMPLATES["flood_zone"]["conditional_questions"]
        assert len(cond) == 0


# ---------------------------------------------------------------------------
# TestBuildSignalValidationPrompt
# ---------------------------------------------------------------------------

class TestBuildSignalValidationPrompt:
    """Tests for build_signal_validation_prompt(context) -> str."""

    def test_returns_string(self, sample_context):
        result = build_signal_validation_prompt(sample_context)
        assert isinstance(result, str)
        assert len(result) > 100

    def test_includes_signal_key(self, sample_context):
        result = build_signal_validation_prompt(sample_context)
        assert "active_subdivision" in result

    def test_includes_parcel_context(self, sample_context):
        result = build_signal_validation_prompt(sample_context)
        assert "6700112233445" in result
        assert "KEYSTONE DEVELOPMENT GROUP LLC" in result
        assert "Manchester Township" in result

    def test_includes_evidence(self, sample_context):
        result = build_signal_validation_prompt(sample_context)
        assert "HERITAGE HILLS PHASE III" in result

    def test_includes_conditional_questions_when_data_present(self, sample_context):
        """Proceedings are present in sample, so conditional questions should appear."""
        result = build_signal_validation_prompt(sample_context)
        # Proceedings are present; has_proceedings conditional should be included
        assert "PROCEEDINGS" in result

    def test_excludes_sections_without_data(self, sample_context):
        """Tax claims and neighbors are empty; their sections should be omitted."""
        result = build_signal_validation_prompt(sample_context)
        assert "TAX CLAIMS" not in result
        assert "ADJACENT PARCELS" not in result

    def test_includes_entity_context(self, sample_context):
        result = build_signal_validation_prompt(sample_context)
        assert "ENTITY" in result
        assert "verified" in result

    def test_includes_output_format(self, sample_context):
        result = build_signal_validation_prompt(sample_context)
        assert "validation_status" in result
        assert "adjusted_significance" in result

    def test_minimal_context(self):
        """Prompt builder should handle minimal context without error."""
        minimal = {
            "pidn": "6700000000001",
            "signal": {
                "signal_key": "growth_area",
                "signal_weight": 0.02,
                "source_table": "staging.growth_areas",
                "source_id": "GA-001",
                "distance_m": None,
                "evidence": {"ga_type": "PGA", "ga_status": "Designated"},
            },
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
            "tax_claims": [],
            "proceedings": [],
            "neighbors": [],
            "corporate": [],
            "portfolio": [],
        }
        result = build_signal_validation_prompt(minimal)
        assert isinstance(result, str)
        assert "growth_area" in result

    def test_all_optional_sections_included_when_populated(self):
        """When all optional sections have data, they should all appear."""
        context = {
            "pidn": "6700000000001",
            "signal": {
                "signal_key": "tax_distress",
                "signal_weight": 0.10,
                "source_table": "staging.tax_claims",
                "source_id": "6700000000001",
                "distance_m": None,
                "evidence": {"total_owed": 5000, "years_delinquent": 3, "oldest_year": 2022},
            },
            "parcel": {
                "pidn": "6700000000001",
                "owner": "DOE JOHN",
                "address": "200 ELM ST",
                "assessed_value": 150000,
                "acres": 1.0,
                "property_class": "R",
                "sale_date": "",
                "sale_price": 0,
                "previous_owner": "",
                "municipality": "York City",
                "school_district": "York City",
                "source_url": "",
            },
            "entity": {"found": True, "canonical_name": "DOE JOHN", "entity_type": "individual"},
            "tax_claims": [{"year": 2022, "authority": "COUNTY", "amount": 1500, "owner": "DOE JOHN"}],
            "proceedings": [{"type": "variance", "applicant": "DOE JOHN", "parcel": "6700000000001", "decision": "approved", "meeting_date": "2025-01-15", "body": "York City ZHB", "source_url": "", "supporting_text": ""}],
            "neighbors": [{"pidn": "6700000000002", "owner": "SMITH", "assessed_value": 100000, "acres": 0.5, "property_class": "R", "total_owed": 0, "years_delinquent": 0}],
            "corporate": [{"entity_name": "DOE HOLDINGS LLC", "entity_number": "123", "status": "ACTIVE", "formation_date": "2020-01-01", "office_address": "200 ELM ST", "source_url": ""}],
            "portfolio": [{"pidn": "6700000000001", "address": "200 ELM ST", "assessed_value": 150000, "sale_date": "", "sale_price": 0}],
        }
        result = build_signal_validation_prompt(context)
        assert "TAX CLAIMS" in result
        assert "PROCEEDINGS" in result
        assert "ADJACENT PARCELS" in result
        assert "CORPORATE RECORDS" in result


# ---------------------------------------------------------------------------
# TestParseSignalValidationOutput
# ---------------------------------------------------------------------------

class TestParseSignalValidationOutput:
    """Tests for parse_signal_validation_output(output) -> dict."""

    def test_valid_output_parsed(self, valid_llm_output):
        result = parse_signal_validation_output(valid_llm_output)
        assert result["signal_key"] == "active_subdivision"
        assert result["validation_status"] == "confirmed"
        assert result["adjusted_significance"] == "high"
        assert len(result["key_facts"]) == 3
        assert "error" not in result

    def test_invalid_status_defaults_to_confirmed(self):
        output = {
            "signal_key": "test",
            "validation_status": "banana",
            "adjusted_significance": "high",
            "reasoning": "Some reasoning.",
            "key_facts": [],
            "cross_references": [],
        }
        result = parse_signal_validation_output(output)
        assert result["validation_status"] == "confirmed"

    def test_invalid_significance_defaults_to_medium(self):
        output = {
            "signal_key": "test",
            "validation_status": "confirmed",
            "adjusted_significance": "super_high",
            "reasoning": "Some reasoning.",
            "key_facts": [],
            "cross_references": [],
        }
        result = parse_signal_validation_output(output)
        assert result["adjusted_significance"] == "medium"

    def test_missing_reasoning_returns_error(self):
        output = {
            "signal_key": "test",
            "validation_status": "confirmed",
            "adjusted_significance": "high",
            "reasoning": "",
            "key_facts": [],
            "cross_references": [],
        }
        result = parse_signal_validation_output(output)
        assert "error" in result

    def test_none_reasoning_returns_error(self):
        output = {
            "signal_key": "test",
            "validation_status": "confirmed",
            "adjusted_significance": "high",
            "key_facts": [],
            "cross_references": [],
        }
        result = parse_signal_validation_output(output)
        assert "error" in result

    def test_all_valid_statuses_accepted(self):
        for status in VALID_STATUSES:
            output = {
                "signal_key": "test",
                "validation_status": status,
                "adjusted_significance": (
                    "none" if status in {"stale", "irrelevant"} else "medium"
                ),
                "reasoning": "Reasoning here.",
                "key_facts": [],
                "cross_references": [],
            }
            result = parse_signal_validation_output(output)
            assert result["validation_status"] == status

    @pytest.mark.parametrize("status", ["stale", "irrelevant"])
    def test_non_serving_status_rejects_actionable_significance(self, status):
        result = parse_signal_validation_output({
            "signal_key": "test",
            "validation_status": status,
            "adjusted_significance": "high",
            "reasoning": "Reasoning here.",
            "key_facts": [],
            "cross_references": [],
        })

        assert "error" in result
        assert "requires adjusted_significance 'none'" in result["error"]

    def test_all_valid_significance_accepted(self):
        for sig in VALID_SIGNIFICANCE:
            output = {
                "signal_key": "test",
                "validation_status": "confirmed",
                "adjusted_significance": sig,
                "reasoning": "Reasoning here.",
                "key_facts": [],
                "cross_references": [],
            }
            result = parse_signal_validation_output(output)
            assert result["adjusted_significance"] == sig

    def test_cross_references_preserved(self, valid_llm_output):
        result = parse_signal_validation_output(valid_llm_output)
        assert len(result["cross_references"]) == 1
        assert result["cross_references"][0]["source"] == "proceedings"

    def test_key_facts_preserved(self, valid_llm_output):
        result = parse_signal_validation_output(valid_llm_output)
        assert "Heritage Hills Phase III" in result["key_facts"][0]

    def test_non_dict_returns_error(self):
        result = parse_signal_validation_output("not a dict")
        assert "error" in result

    def test_missing_signal_key_returns_error(self):
        output = {
            "validation_status": "confirmed",
            "adjusted_significance": "high",
            "reasoning": "Some reasoning.",
            "key_facts": [],
            "cross_references": [],
        }
        result = parse_signal_validation_output(output)
        assert "error" in result
