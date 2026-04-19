"""Tests for Pass 0 multimodal document extraction.

Tests cover only pure-Python parts (templates, config, result types).
No actual LLM calls are made.
"""

from contextlib import contextmanager

import pytest

from countyiq.assets.enrichment.proceeding_extraction import _write_proceeding_extractions
from countyiq.lib.pass0_templates import EXTRACTION_PROMPT
from countyiq.lib.llm_harness import HarnessConfig, HarnessResult, _build_messages


# ---------------------------------------------------------------------------
# EXTRACTION_PROMPT template tests
# ---------------------------------------------------------------------------

class TestExtractionPrompt:

    def _filled(self, **overrides) -> str:
        """Return a fully-formatted prompt with sensible defaults."""
        defaults = dict(
            body_name="Springvale Township",
            proceeding_type="planning_commission",
            meeting_date="2025-11-14",
        )
        defaults.update(overrides)
        meeting_date = defaults.pop("meeting_date", None)
        date_clause = defaults.pop("date_clause", None)
        if date_clause is None:
            date_clause = f" dated {meeting_date}" if meeting_date else ""
        defaults["date_clause"] = date_clause
        return EXTRACTION_PROMPT.format(**defaults)

    def test_formats_without_error(self):
        prompt = self._filled()
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_body_name_interpolated(self):
        prompt = self._filled(body_name="York City Council")
        assert "York City Council" in prompt

    def test_meeting_date_omitted_when_missing(self):
        prompt = self._filled(meeting_date=None)
        assert "dated" not in prompt

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
            EXTRACTION_PROMPT.format(
                body_name="Test Body",
                proceeding_type="supervisors",
                date_clause=" dated 2025-06-01",
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

    def test_default_temperature(self):
        config = HarnessConfig(model_path="/models/llava.gguf")
        # Sampling should come from MODEL_PRESETS via get_preset_for_model();
        # this default is a last resort.
        assert config.temperature == 0.7

    def test_default_max_tokens(self):
        config = HarnessConfig(model_path="/models/llava.gguf")
        assert config.max_tokens == 2048

    def test_custom_values(self):
        config = HarnessConfig(
            model_path="/models/llava.gguf",
            n_ctx=8192,
            temperature=0.0,
            max_tokens=512,
        )
        assert config.n_ctx == 8192
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


class TestBuildMessages:

    def test_pdf_message_includes_file_block_and_prompt(self):
        config = HarnessConfig(model_path="x-ai/grok-4.1-fast")
        messages = _build_messages(
            config,
            "Extract records from this document.",
            pdf_bytes=b"%PDF-1.7 sample",
        )

        assert len(messages) == 1
        message = messages[0]
        assert message["role"] == "user"
        assert isinstance(message["content"], list)
        assert message["content"][0]["type"] == "file"
        assert message["content"][0]["file"]["filename"] == "document.pdf"
        assert message["content"][0]["file"]["file_data"].startswith(
            "data:application/pdf;base64,"
        )
        assert message["content"][1] == {
            "type": "text",
            "text": "Extract records from this document.",
        }

    def test_rejects_oversized_pdf_before_request_build(self, monkeypatch):
        monkeypatch.setenv("COUNTYIQ_PASS0_MAX_PDF_BYTES", "4")
        config = HarnessConfig(model_path="x-ai/grok-4.1-fast")

        with pytest.raises(ValueError, match="PDF too large for inline upload"):
            _build_messages(config, "Prompt", pdf_bytes=b"12345")


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


class _FakeTransactionCursor:
    def __init__(self, database):
        self.database = database
        self.pending: list[tuple[str, tuple | None]] = []
        self._fetchone_result = None

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split())

        if normalized.startswith(
            "SELECT COUNT(*) FROM staging.proceeding_extractions WHERE proceeding_id = %s"
        ):
            self._fetchone_result = (self.database.existing_count,)
            return

        if normalized.startswith(
            "DELETE FROM staging.proceeding_extractions WHERE proceeding_id = %s"
        ):
            self.pending.append((normalized, params))
            return

        if "INSERT INTO staging.proceeding_extractions" in normalized:
            extraction_type = params[1] if params and len(params) > 1 else None
            if extraction_type == self.database.fail_on_type:
                raise RuntimeError("simulated insert failure")
            self.pending.append((normalized, params))
            return

        raise AssertionError(f"Unexpected SQL in fake transaction: {normalized}")

    def fetchone(self):
        return self._fetchone_result


class _FakeDatabase:
    def __init__(self, *, existing_count=0, fail_on_type=None):
        self.existing_count = existing_count
        self.fail_on_type = fail_on_type
        self.committed: list[tuple[str, tuple | None]] = []

    @contextmanager
    def transaction(self):
        cursor = _FakeTransactionCursor(self)
        try:
            yield cursor
        except Exception:
            raise
        else:
            self.committed.extend(cursor.pending)


class TestProceedingPersistence:

    def test_rolls_back_when_any_insert_fails(self):
        database = _FakeDatabase(existing_count=2, fail_on_type="variance_request")
        extractions = [
            {
                "extraction_type": "variance_request",
                "applicant_name": "John Smith",
                "parcel_reference": "123 MAIN ST",
                "current_zoning": "R1",
                "proposed_zoning": None,
                "decision": "approved",
                "conditions": [],
                "supporting_text": "Approved by the board.",
                "confidence": "high",
            }
        ]

        with pytest.raises(RuntimeError, match="simulated insert failure"):
            _write_proceeding_extractions(
                database,
                proceeding_id=101,
                extractions=extractions,
                model_used="grok-4.1-fast",
            )

        assert database.committed == []

    def test_writes_empty_and_complete_sentinels_for_no_extractions(self):
        database = _FakeDatabase(existing_count=1)

        existing_count, inserted_count = _write_proceeding_extractions(
            database,
            proceeding_id=202,
            extractions=[],
            model_used="grok-4.1-fast",
        )

        assert existing_count == 1
        assert inserted_count == 0
        assert database.committed[0] == (
            "DELETE FROM staging.proceeding_extractions WHERE proceeding_id = %s",
            (202,),
        )
        assert "'_no_extractions'" in database.committed[1][0]
        assert database.committed[1][1] == (202, "grok-4.1-fast")
        assert "'_complete'" in database.committed[2][0]
        assert database.committed[2][1] == (202, "grok-4.1-fast")
