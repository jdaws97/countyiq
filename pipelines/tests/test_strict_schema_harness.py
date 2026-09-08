"""Strict structured-output harness upgrades (2026-08-02).

Pins the chain: pass schemas -> HarnessConfig -> OpenRouter payload,
plus the provider-preference knobs (require_parameters, max_price, zdr),
the json_object fallback on 404 (no provider supports strict schema),
and the Pass 1 abstention channel.
"""

import json
import os
from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest
import requests
from countyiq.lib import llm_harness
from countyiq.lib.llm_harness import HarnessConfig, build_openrouter_payload
from countyiq.lib.pass1_entity_verification import parse_entity_verification_output
from countyiq.lib.pass_llm_config import build_pass_harness_config
from countyiq.lib.pass_schemas import (
    PASS0_EXTRACTION_SCHEMA,
    PASS1_ENTITY_VERIFICATION_SCHEMA,
    PASS2_BATCHED_VALIDATION_SCHEMA,
    PASS3_BRIEF_SCHEMA,
    PASS3B_OWNER_BRIEF_SCHEMA,
)

ALL_SCHEMAS = [
    PASS0_EXTRACTION_SCHEMA,
    PASS1_ENTITY_VERIFICATION_SCHEMA,
    PASS2_BATCHED_VALIDATION_SCHEMA,
    PASS3_BRIEF_SCHEMA,
    PASS3B_OWNER_BRIEF_SCHEMA,
]


def test_llm_archive_retention_prunes_only_expired_harness_files(tmp_path):
    archive_day = tmp_path / "pass2" / "2026-01-01"
    archive_day.mkdir(parents=True)
    expired = archive_day / "0123456789abcdef_010203_123456.json"
    recent = archive_day / "fedcba9876543210_010203_123456.json"
    unrelated = archive_day / "notes.json"
    expired.write_text("{}")
    recent.write_text("{}")
    unrelated.write_text("keep")
    now = datetime(2026, 8, 30, tzinfo=timezone.utc)
    old_timestamp = (now - timedelta(days=91)).timestamp()
    recent_timestamp = (now - timedelta(days=10)).timestamp()
    os.utime(expired, (old_timestamp, old_timestamp))
    os.utime(recent, (recent_timestamp, recent_timestamp))

    removed = llm_harness.prune_llm_archives(tmp_path, retention_days=90, now=now)

    assert removed == 1
    assert not expired.exists()
    assert recent.exists()
    assert unrelated.exists()


def test_llm_archive_probe_requires_explicit_directory(monkeypatch):
    monkeypatch.delenv("COUNTYIQ_ARCHIVE_DIR", raising=False)

    result = llm_harness.probe_llm_archive_destination()

    assert result["ok"] is False
    assert "not explicitly configured" in result["reason"]


def test_llm_archive_probe_writes_and_cleans_up(tmp_path, monkeypatch):
    monkeypatch.setenv("COUNTYIQ_ARCHIVE_DIR", str(tmp_path))

    result = llm_harness.probe_llm_archive_destination()

    assert result["ok"] is True
    assert list(tmp_path.iterdir()) == []


def test_strict_llm_archive_failure_is_not_silenced(tmp_path, monkeypatch):
    invalid_root = tmp_path / "archive-root-is-a-file"
    invalid_root.write_text("not a directory", encoding="utf-8")
    monkeypatch.setenv("COUNTYIQ_ARCHIVE_DIR", str(invalid_root))
    monkeypatch.setenv("COUNTYIQ_ARCHIVE_STRICT", "true")

    with pytest.raises(RuntimeError, match="LLM transcript archive failed"):
        llm_harness.archive_raw_output("pass2", "pidn", "prompt", "{}")


def test_non_strict_llm_archive_failure_remains_a_warning(tmp_path, monkeypatch):
    invalid_root = tmp_path / "archive-root-is-a-file"
    invalid_root.write_text("not a directory", encoding="utf-8")
    monkeypatch.setenv("COUNTYIQ_ARCHIVE_DIR", str(invalid_root))
    monkeypatch.setenv("COUNTYIQ_ARCHIVE_STRICT", "false")

    assert llm_harness.archive_raw_output("pass2", "pidn", "prompt", "{}") is None


def test_strict_invoke_requires_archive_key(monkeypatch):
    monkeypatch.setenv("COUNTYIQ_ARCHIVE_STRICT", "true")
    monkeypatch.setattr(
        llm_harness,
        "_invoke_openrouter",
        lambda config, prompt, pdf_bytes=None: ("{}", None, {"cost": 0.01}),
    )

    with pytest.raises(RuntimeError, match="archive key is missing"):
        llm_harness.invoke(
            HarnessConfig(model_path="x/y", archive_label="pass2"),
            "prompt",
        )


def _walk_objects(schema: dict):
    if schema.get("type") == "object" or "properties" in schema:
        yield schema
    for sub in (schema.get("properties") or {}).values():
        yield from _walk_objects(sub)
    if isinstance(schema.get("items"), dict):
        yield from _walk_objects(schema["items"])


@pytest.mark.parametrize("schema", ALL_SCHEMAS)
def test_schemas_satisfy_strict_mode_rules(schema):
    """Strict mode requires required == all properties and no extras."""
    for obj in _walk_objects(schema):
        props = obj.get("properties")
        if props is None:
            continue
        assert obj.get("additionalProperties") is False
        assert sorted(obj.get("required", [])) == sorted(props.keys())


def test_json_schema_payload_and_require_parameters():
    config = HarnessConfig(
        model_path="inception/mercury-2",
        json_schema=PASS2_BATCHED_VALIDATION_SCHEMA,
        schema_name="pass2_validations",
    )
    payload = build_openrouter_payload(config, "prompt")
    rf = payload["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["strict"] is True
    assert rf["json_schema"]["name"] == "pass2_validations"
    assert rf["json_schema"]["schema"] == PASS2_BATCHED_VALIDATION_SCHEMA
    assert payload["provider"]["require_parameters"] is True


def test_no_schema_keeps_json_object_and_no_provider_block():
    payload = build_openrouter_payload(HarnessConfig(model_path="x/y"), "prompt")
    assert payload["response_format"] == {"type": "json_object"}
    assert "provider" not in payload


def test_max_price_and_zdr_flow_into_provider_prefs():
    config = HarnessConfig(
        model_path="x/y", max_price_prompt=0.5, max_price_completion=2.0, zdr=True
    )
    payload = build_openrouter_payload(config, "prompt")
    assert payload["provider"]["max_price"] == {"prompt": 0.5, "completion": 2.0}
    assert payload["provider"]["zdr"] is True


def test_system_prompt_becomes_leading_system_message():
    config = HarnessConfig(model_path="x/y", system_prompt="You are a rubric.")
    payload = build_openrouter_payload(config, "user question")
    assert payload["messages"][0] == {"role": "system", "content": "You are a rubric."}
    assert payload["messages"][1]["role"] == "user"


def test_pass_config_carries_system_prompt_and_pdf_engine(monkeypatch):
    monkeypatch.setenv("COUNTYIQ_PASS0_ENABLED", "true")
    config = build_pass_harness_config(
        pass_number=0,
        archive_label="t",
        reasoning_task=False,
        default_max_tokens=1024,
        system_prompt="Static rules.",
        pdf_engine="native",
    )
    assert config.system_prompt == "Static rules."
    assert config.pdf_engine == "native"


def test_pdf_engine_pins_file_parser_plugin_only_with_pdf():
    config = HarnessConfig(model_path="x/y", pdf_engine="native")
    with_pdf = build_openrouter_payload(config, "prompt", pdf_bytes=b"%PDF-1.4")
    assert with_pdf["plugins"] == [{"id": "file-parser", "pdf": {"engine": "native"}}]
    without_pdf = build_openrouter_payload(config, "prompt")
    assert "plugins" not in without_pdf


def test_no_pdf_engine_means_no_plugins_block():
    config = HarnessConfig(model_path="x/y")
    payload = build_openrouter_payload(config, "prompt", pdf_bytes=b"%PDF-1.4")
    assert "plugins" not in payload


def test_openai_family_omits_all_sampling_params():
    """gpt-5.x endpoints accept NO sampling params (OpenRouter listing
    2026-08-06); with require_parameters=true, sending temperature/top_p
    would exclude every provider and 404 each strict-schema call."""
    from countyiq.lib.llm_harness import detect_model_family, get_preset_for_model

    assert detect_model_family("openai/gpt-5.6-luna") == "openai"
    # gpt-oss keeps its own family despite the openai/ prefix.
    assert detect_model_family("openai/gpt-oss-120b") == "gpt_oss"

    preset = get_preset_for_model("openai/gpt-5.6-luna")
    config = HarnessConfig(
        model_path="openai/gpt-5.6-luna",
        json_schema=PASS2_BATCHED_VALIDATION_SCHEMA,
        schema_name="pass2_validations",
        **preset,
    )
    payload = build_openrouter_payload(config, "prompt")
    for banned in (
        "temperature",
        "top_p",
        "top_k",
        "min_p",
        "presence_penalty",
        "frequency_penalty",
    ):
        assert banned not in payload, f"{banned} must not be sent to gpt-5.x"
    assert payload["provider"]["require_parameters"] is True
    assert payload["response_format"]["type"] == "json_schema"


def test_default_lineup_is_luna_for_all_passes(monkeypatch):
    from countyiq.lib.pass_llm_config import resolve_pass_model

    for key in list(os.environ):
        if key.startswith("COUNTYIQ_PASS") or key == "COUNTYIQ_OPENROUTER_MODEL":
            monkeypatch.delenv(key, raising=False)
    for pass_number in range(5):
        assert resolve_pass_model(pass_number) == "openai/gpt-5.6-luna"


def test_pass_config_resolves_schema_and_env_knobs(monkeypatch):
    monkeypatch.setenv("COUNTYIQ_PASS2_ENABLED", "true")
    monkeypatch.setenv("COUNTYIQ_MAX_PRICE_PROMPT", "1.5")
    monkeypatch.setenv("COUNTYIQ_MAX_PRICE_COMPLETION", "6.0")
    monkeypatch.setenv("COUNTYIQ_ZDR", "true")
    config = build_pass_harness_config(
        pass_number=2,
        archive_label="t",
        reasoning_task=True,
        default_max_tokens=1024,
        json_schema=PASS2_BATCHED_VALIDATION_SCHEMA,
    )
    assert config.json_schema == PASS2_BATCHED_VALIDATION_SCHEMA
    assert config.max_price_prompt == 1.5
    assert config.max_price_completion == 6.0
    assert config.zdr is True


def test_strict_schema_global_kill_switch(monkeypatch):
    monkeypatch.setenv("COUNTYIQ_PASS2_ENABLED", "true")
    monkeypatch.setenv("COUNTYIQ_STRICT_SCHEMA", "false")
    config = build_pass_harness_config(
        pass_number=2,
        archive_label="t",
        reasoning_task=True,
        default_max_tokens=1024,
        json_schema=PASS2_BATCHED_VALIDATION_SCHEMA,
    )
    assert config.json_schema is None


def _http_error(status: int):
    resp = mock.Mock()
    resp.status_code = status
    resp.text = "No eligible provider"
    return requests.exceptions.HTTPError(response=resp)


def test_404_falls_back_to_json_object_once_only_when_explicitly_enabled():
    """No provider supports the strict schema -> retry downgraded, tagged."""
    calls = []

    def fake_post(url, json_payload, headers, timeout):
        calls.append(json_payload)
        if json_payload["response_format"]["type"] == "json_schema":
            raise _http_error(404)
        resp = mock.Mock()
        resp.json.return_value = {
            "choices": [
                {"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "provider": "TestProvider",
        }
        resp.text = ""
        return resp

    config = HarnessConfig(
        model_path="x/y",
        json_schema=PASS2_BATCHED_VALIDATION_SCHEMA,
        allow_schema_fallback=True,
        provider_only=("test-provider",),
        provider_allow_fallbacks=False,
        provider_quantizations=("fp8",),
        max_price_prompt=0.16,
        max_price_completion=0.55,
    )
    with (
        mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "test"}),
        mock.patch.object(llm_harness, "_post_with_backoff", side_effect=fake_post),
    ):
        raw, error, meta = llm_harness._invoke_openrouter(config, "prompt")

    assert error is None
    assert raw == '{"ok": true}'
    assert meta["schema_fallback"] is True
    assert len(calls) == 2
    assert calls[1]["response_format"] == {"type": "json_object"}
    assert calls[1]["provider"] == {
        "only": ["test-provider"],
        "allow_fallbacks": False,
        "quantizations": ["fp8"],
        "max_price": {"prompt": 0.16, "completion": 0.55},
    }
    assert (
        json.dumps(PASS2_BATCHED_VALIDATION_SCHEMA, sort_keys=True)
        in calls[1]["messages"][0]["content"]
    )
    assert meta["effective_request"]["response_format"] == {"type": "json_object"}
    assert meta["strict_request_sha256"] != meta["request_sha256"]


def test_strict_schema_404_fails_closed_by_default():
    config = HarnessConfig(
        model_path="x/y", json_schema=PASS2_BATCHED_VALIDATION_SCHEMA
    )
    with (
        mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "test"}),
        mock.patch.object(
            llm_harness, "_post_with_backoff", side_effect=_http_error(404)
        ) as post,
    ):
        raw, error, metadata = llm_harness._invoke_openrouter(config, "prompt")
    assert raw == "" and "No eligible provider" in error
    assert post.call_count == 1
    assert not metadata.get("schema_fallback")
    assert metadata["effective_request"]["response_format"]["type"] == "json_schema"


def test_usage_meta_captured():
    def fake_post(url, json_payload, headers, timeout):
        resp = mock.Mock()
        resp.json.return_value = {
            "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 40,
                "cost": 0.0042,
                "cost_details": {"upstream_inference_cost": 0.0039},
                "completion_tokens_details": {"reasoning_tokens": 12},
                "prompt_tokens_details": {"cached_tokens": 80},
            },
            "provider": "DeepInfra",
            "model": "x/y",
        }
        return resp

    with (
        mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "test"}),
        mock.patch.object(llm_harness, "_post_with_backoff", side_effect=fake_post),
    ):
        _, error, meta = llm_harness._invoke_openrouter(
            HarnessConfig(model_path="x/y"), "p"
        )

    assert error is None
    assert meta["prompt_tokens"] == 100
    assert meta["cost"] == 0.0042
    assert meta["cost_details"]["upstream_inference_cost"] == 0.0039
    assert meta["completion_tokens"] == 40
    assert meta["reasoning_tokens"] == 12
    assert meta["cached_tokens"] == 80
    assert meta["provider"] == "DeepInfra"


def test_missing_api_key_preserves_three_value_invoke_contract(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    raw, error, meta = llm_harness._invoke_openrouter(
        HarnessConfig(model_path="x/y"), "prompt"
    )

    assert raw == ""
    assert error == "OPENROUTER_API_KEY not set"
    assert meta == {}


def test_invoke_exposes_usage_metadata_on_result():
    def fake_post(url, json_payload, headers, timeout):
        resp = mock.Mock()
        resp.json.return_value = {
            "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 40,
                "cost": 0.0042,
            },
            "provider": "TestProvider",
            "model": "x/y",
        }
        return resp

    with (
        mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "test"}),
        mock.patch.object(llm_harness, "_post_with_backoff", side_effect=fake_post),
    ):
        result = llm_harness.invoke(HarnessConfig(model_path="x/y"), "p")

    assert result.success
    assert result.metadata["cost"] == 0.0042
    assert result.metadata["prompt_tokens"] == 100
    assert (
        result.metadata["attempt_count"] if "attempt_count" in result.metadata else True
    )


def test_retry_result_reports_total_attempt_cost():
    from countyiq.lib.llm_harness import HarnessResult, invoke_with_retry

    attempts = [
        HarnessResult(
            raw_output='{"partial',
            parsed=None,
            success=False,
            error="Response truncated at max_tokens=100 (finish_reason=length)",
            metadata={"cost": 0.01, "completion_tokens": 100},
        ),
        HarnessResult(
            raw_output="{}",
            parsed={},
            success=True,
            metadata={"cost": 0.02, "completion_tokens": 150},
        ),
    ]

    with mock.patch.object(llm_harness, "invoke", side_effect=attempts):
        result = invoke_with_retry(
            HarnessConfig(model_path="x/y", max_tokens=100), "p", retries=1
        )

    assert result.success
    assert result.metadata["attempt_count"] == 2
    assert result.metadata["cost"] == 0.03
    assert result.metadata["completion_tokens"] == 250


def test_pass1_abstentions_parsed_and_shape_guarded():
    parsed = parse_entity_verification_output(
        {
            "entities": [],
            "rejected_matches": [],
            "abstentions": [
                {"names": ["SMITH J", "J SMITH LLC"], "reason": "no shared address"},
                {"reason": "malformed, no names key"},
                "not a dict",
            ],
        }
    )
    assert parsed["abstentions"] == [
        {"names": ["SMITH J", "J SMITH LLC"], "reason": "no shared address"}
    ]


def test_pass1_abstentions_default_empty():
    parsed = parse_entity_verification_output({"entities": []})
    assert parsed["abstentions"] == []


def test_truncation_retry_doubles_budget_and_steps_effort_down():
    """finish_reason=length must not be retried with an identical config."""
    from countyiq.lib.llm_harness import HarnessResult, invoke_with_retry

    configs_seen = []

    def fake_invoke(config, prompt, archive_key=None, pdf_bytes=None):
        configs_seen.append(config)
        if len(configs_seen) == 1:
            return HarnessResult(
                raw_output='{"partial',
                parsed=None,
                success=False,
                error=f"Response truncated at max_tokens={config.max_tokens} (finish_reason=length)",
            )
        return HarnessResult(raw_output="{}", parsed={}, success=True)

    config = HarnessConfig(model_path="x/y", max_tokens=3500, reasoning_effort="high")
    with mock.patch.object(llm_harness, "invoke", side_effect=fake_invoke):
        result = invoke_with_retry(config, "p", retries=1)

    assert result.success
    assert configs_seen[1].max_tokens == 7000
    assert configs_seen[1].reasoning_effort == "medium"


def test_truncation_retry_defaults_effort_low_when_unset():
    from countyiq.lib.llm_harness import HarnessResult, invoke_with_retry

    configs_seen = []

    def fake_invoke(config, prompt, archive_key=None, pdf_bytes=None):
        configs_seen.append(config)
        if len(configs_seen) == 1:
            return HarnessResult(
                raw_output="",
                parsed=None,
                success=False,
                error="Response truncated at max_tokens=2048 (finish_reason=length)",
            )
        return HarnessResult(raw_output="{}", parsed={}, success=True)

    with mock.patch.object(llm_harness, "invoke", side_effect=fake_invoke):
        invoke_with_retry(
            HarnessConfig(model_path="x/y", max_tokens=2048), "p", retries=1
        )

    assert configs_seen[1].reasoning_effort == "low"
    assert configs_seen[1].max_tokens == 4096


def test_missing_key_not_retried():
    from countyiq.lib.llm_harness import HarnessResult, invoke_with_retry

    calls = []

    def fake_invoke(config, prompt, archive_key=None, pdf_bytes=None):
        calls.append(1)
        return HarnessResult(
            raw_output="",
            parsed=None,
            success=False,
            error="OPENROUTER_API_KEY not set",
        )

    with mock.patch.object(llm_harness, "invoke", side_effect=fake_invoke):
        result = invoke_with_retry(HarnessConfig(model_path="x/y"), "p", retries=3)

    assert not result.success
    assert len(calls) == 1


@pytest.mark.parametrize(
    "effort, expected",
    [("max", "high"), ("high", "low"), ("low", "low"), (None, "low")],
)
def test_glm_truncation_retry_uses_only_supported_efforts(effort, expected):
    configs = []

    def fake_invoke(config, prompt, **kwargs):
        configs.append(config)
        return llm_harness.HarnessResult(
            raw_output="", parsed=None, success=False, error="finish_reason=length"
        )

    with mock.patch.object(llm_harness, "invoke", side_effect=fake_invoke):
        llm_harness.invoke_with_retry(
            HarnessConfig(
                model_path="z-ai/glm-5.3-flash",
                reasoning_effort=effort,
                max_tokens=4096,
            ),
            "prompt",
            retries=1,
        )
    assert len(configs) == 2
    assert configs[1].reasoning_effort == expected
    assert configs[1].max_tokens == 8192
    assert build_openrouter_payload(configs[1], "prompt")["reasoning"] == {
        "effort": expected
    }


def test_strict_archive_requires_key_before_paid_transport(monkeypatch):
    monkeypatch.setenv("COUNTYIQ_ARCHIVE_STRICT", "true")
    with (
        mock.patch.object(llm_harness, "_invoke_openrouter") as invoke_provider,
        pytest.raises(RuntimeError, match="archive key is missing"),
    ):
        llm_harness.invoke(
            HarnessConfig(model_path="x/y", archive_label="municipal_evidence"),
            "prompt",
        )
    invoke_provider.assert_not_called()


def test_unsupported_glm_effort_is_rejected_before_transport():
    with (
        mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "test"}),
        mock.patch.object(llm_harness, "_post_with_backoff") as post,
        pytest.raises(ValueError, match="low, high, or max"),
    ):
        llm_harness.invoke(
            HarnessConfig(model_path="z-ai/glm-5.3-flash", reasoning_effort="medium"),
            "prompt",
        )
    post.assert_not_called()


def test_http_error_preserves_provider_body_when_post_raises():
    response = requests.Response()
    response.status_code = 400
    response._content = (
        b'{"error":{"message":"Unsupported schema keyword: uniqueItems"}}'
    )
    error = requests.exceptions.HTTPError(response=response)
    with (
        mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "test"}),
        mock.patch.object(llm_harness, "_post_with_backoff", side_effect=error),
    ):
        _, detail, metadata = llm_harness._invoke_openrouter(
            HarnessConfig(model_path="x/y"), "p"
        )
    assert "Unsupported schema keyword: uniqueItems" in detail
    assert metadata["effective_request"]["model"] == "x/y"
    assert len(metadata["request_sha256"]) == 64


@pytest.mark.parametrize(
    "effort, expected", [(None, "low"), ("high", "high"), ("max", "max")]
)
def test_glm_flash_bounds_mandatory_reasoning_without_generic_sampling(
    effort, expected
):
    from countyiq.lib.llm_harness import get_preset_for_model

    model = "z-ai/glm-5.3-flash"
    payload = build_openrouter_payload(
        HarnessConfig(
            model_path=model,
            thinking=False,
            reasoning_effort=effort,
            json_schema=PASS2_BATCHED_VALIDATION_SCHEMA,
            provider_quantizations=("fp8",),
            **get_preset_for_model(model),
        ),
        "prompt",
    )
    assert payload["reasoning"] == {"effort": expected}
    assert payload["temperature"] == 1.0
    assert payload["top_p"] == 0.95
    assert "top_k" not in payload
    assert payload["provider"]["quantizations"] == ["fp8"]
    assert payload["provider"]["require_parameters"] is True


@pytest.mark.parametrize(
    "thinking, effort, expected",
    [
        (False, None, {"enabled": False}),
        (True, None, {"enabled": True}),
        (False, "low", {"effort": "low"}),
        (True, "high", {"effort": "high"}),
    ],
)
def test_deepseek_v4_uses_portable_reasoning_controls(thinking, effort, expected):
    payload = build_openrouter_payload(
        HarnessConfig(
            model_path="deepseek/deepseek-v4-flash-0731",
            thinking=thinking,
            reasoning_effort=effort,
            json_schema=PASS2_BATCHED_VALIDATION_SCHEMA,
        ),
        "prompt",
    )
    assert payload["reasoning"] == expected
    assert "chat_template_kwargs" not in payload
    if thinking or effort:
        assert "temperature" not in payload
        assert "top_p" not in payload
        assert "top_k" not in payload
    assert payload["response_format"]["type"] == "json_schema"
