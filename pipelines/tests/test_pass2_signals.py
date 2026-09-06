"""Tests for Pass 2 signal validation.

Tests cover the shared output parser used by batched validation.
No actual LLM calls are made and no database is required.
"""

import pytest

from countyiq.lib.pass2_signal_validation import (
    VALID_STATUSES,
    VALID_SIGNIFICANCE,
    parse_signal_validation_output,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
        result = parse_signal_validation_output(
            {
                "signal_key": "test",
                "validation_status": status,
                "adjusted_significance": "high",
                "reasoning": "Reasoning here.",
                "key_facts": [],
                "cross_references": [],
            }
        )

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
