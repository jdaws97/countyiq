"""Tests for Pass 0 multimodal document extraction.

Tests cover only pure-Python parts (templates, config, result types).
No actual LLM calls are made — llama-cpp-python and pdf2image are NOT required.
"""

import pytest

from countyiq.lib.pass0_templates import EXTRACTION_PROMPT
from countyiq.lib.llm_harness import HarnessConfig, HarnessResult


# ---------------------------------------------------------------------------
# EXTRACTION_PROMPT template tests
# ---------------------------------------------------------------------------

class TestExtractionPrompt:

    def _filled(self, **overrides) -> str:
        """Return a fully-formatted prompt with sensible defaults."""
        defaults = dict(
            body_name="Springvale Township",
            page_num=1,
            total_pages=4,
            proceeding_type="planning_commission",
            meeting_date="2025-11-14",
        )
        defaults.update(overrides)
        return EXTRACTION_PROMPT.format(**defaults)

    def test_formats_without_error(self):
        prompt = self._filled()
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_body_name_interpolated(self):
        prompt = self._filled(body_name="York City Council")
        assert "York City Council" in prompt

    def test_page_num_interpolated(self):
        prompt = self._filled(page_num=3, total_pages=7)
        assert "3" in prompt
        assert "7" in prompt

    def test_meeting_date_interpolated(self):
        prompt = self._filled(meeting_date="2026-01-15")
        assert "2026-01-15" in prompt

    def test_proceeding_type_interpolated(self):
        prompt = self._filled(proceeding_type="zoning_hearing")
        assert "zoning_hearing" in prompt

    # Extraction types
    def test_contains_rezoning_application(self):
        prompt = self._filled()
        assert "rezoning_application" in prompt

    def test_contains_variance_request(self):
        prompt = self._filled()
        assert "variance_request" in prompt

    def test_contains_conditional_use(self):
        prompt = self._filled()
        assert "conditional_use" in prompt

    def test_contains_subdivision_review(self):
        prompt = self._filled()
        assert "subdivision_review" in prompt

    def test_contains_development_proposal(self):
        prompt = self._filled()
        assert "development_proposal" in prompt

    def test_contains_all_five_extraction_types(self):
        prompt = self._filled()
        for etype in [
            "rezoning_application",
            "variance_request",
            "conditional_use",
            "subdivision_review",
            "development_proposal",
        ]:
            assert etype in prompt, f"Missing extraction type '{etype}' in prompt"

    def test_contains_decision_values(self):
        prompt = self._filled()
        for decision in ("approved", "denied", "tabled", "continued"):
            assert decision in prompt

    def test_contains_confidence_levels(self):
        prompt = self._filled()
        for level in ("high", "medium", "low"):
            assert level in prompt

    def test_output_format_includes_extractions_key(self):
        prompt = self._filled()
        assert '"extractions"' in prompt

    def test_empty_page_guidance_present(self):
        prompt = self._filled()
        assert "extractions" in prompt.lower()
        # Should instruct the model to return empty list when nothing found
        assert "[]" in prompt

    def test_york_county_pa_present(self):
        prompt = self._filled()
        assert "York County, PA" in prompt

    def test_all_variables_accepted(self):
        """Verify the template accepts all documented variables without KeyError."""
        try:
            prompt = EXTRACTION_PROMPT.format(
                body_name="Test Body",
                page_num=2,
                total_pages=10,
                proceeding_type="supervisors",
                meeting_date="2025-06-01",
            )
        except KeyError as exc:
            pytest.fail(f"EXTRACTION_PROMPT missing template variable: {exc}")


# ---------------------------------------------------------------------------
# HarnessConfig tests
# ---------------------------------------------------------------------------

class TestHarnessConfig:

    def test_requires_model_path(self):
        config = HarnessConfig(model_path="/models/llava.gguf")
        assert config.model_path == "/models/llava.gguf"

    def test_default_n_ctx(self):
        config = HarnessConfig(model_path="/models/llava.gguf")
        assert config.n_ctx == 4096

    def test_default_n_gpu_layers(self):
        config = HarnessConfig(model_path="/models/llava.gguf")
        assert config.n_gpu_layers == -1

    def test_default_temperature(self):
        config = HarnessConfig(model_path="/models/llava.gguf")
        assert config.temperature == 0.1

    def test_default_max_tokens(self):
        config = HarnessConfig(model_path="/models/llava.gguf")
        assert config.max_tokens == 2048

    def test_custom_values(self):
        config = HarnessConfig(
            model_path="/models/llava.gguf",
            n_ctx=8192,
            n_gpu_layers=0,
            temperature=0.0,
            max_tokens=512,
        )
        assert config.n_ctx == 8192
        assert config.n_gpu_layers == 0
        assert config.temperature == 0.0
        assert config.max_tokens == 512

    def test_is_frozen(self):
        """HarnessConfig must be immutable (frozen dataclass)."""
        config = HarnessConfig(model_path="/models/llava.gguf")
        with pytest.raises((AttributeError, TypeError)):
            config.model_path = "/other/model.gguf"  # type: ignore[misc]

    def test_is_hashable(self):
        """Frozen dataclasses must be hashable (usable as dict keys)."""
        config = HarnessConfig(model_path="/models/llava.gguf")
        d = {config: "value"}
        assert d[config] == "value"


# ---------------------------------------------------------------------------
# HarnessResult tests
# ---------------------------------------------------------------------------

class TestHarnessResult:

    def test_success_construction(self):
        result = HarnessResult(
            raw_output='{"extractions": []}',
            parsed={"extractions": []},
            success=True,
        )
        assert result.success is True
        assert result.parsed == {"extractions": []}
        assert result.error is None

    def test_failure_construction(self):
        result = HarnessResult(
            raw_output="not json",
            parsed=None,
            success=False,
            error="JSON parse error: ...",
        )
        assert result.success is False
        assert result.parsed is None
        assert "JSON parse error" in result.error

    def test_raw_output_preserved_on_success(self):
        raw = '{"extractions": [{"extraction_type": "rezoning_application"}]}'
        result = HarnessResult(raw_output=raw, parsed={"extractions": []}, success=True)
        assert result.raw_output == raw

    def test_raw_output_preserved_on_failure(self):
        result = HarnessResult(raw_output="bad output", parsed=None, success=False, error="err")
        assert result.raw_output == "bad output"

    def test_error_defaults_to_none_on_success(self):
        result = HarnessResult(raw_output="{}", parsed={}, success=True)
        assert result.error is None

    def test_parsed_can_be_none_on_success(self):
        """Edge case: success=True but parsed=None is allowed (caller's responsibility)."""
        result = HarnessResult(raw_output="{}", parsed=None, success=True)
        assert result.success is True
        assert result.parsed is None

    def test_parsed_dict_with_extractions(self):
        parsed = {
            "extractions": [
                {
                    "extraction_type": "variance_request",
                    "applicant_name": "John Smith",
                    "parcel_reference": "67-000-00-0000-00-00000",
                    "current_zoning": "R1",
                    "proposed_zoning": None,
                    "decision": "approved",
                    "conditions": ["Setback reduced to 15ft"],
                    "supporting_text": "The Board approved the variance for John Smith...",
                    "confidence": "high",
                }
            ]
        }
        result = HarnessResult(raw_output="{}", parsed=parsed, success=True)
        assert len(result.parsed["extractions"]) == 1
        assert result.parsed["extractions"][0]["extraction_type"] == "variance_request"
