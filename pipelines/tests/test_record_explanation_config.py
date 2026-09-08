"""Production and calibration must send the same model-specific request."""

import pytest
from countyiq.lib.llm_harness import build_openrouter_payload
from countyiq.lib.pass_llm_config import build_pass_harness_config
from countyiq.lib.quality_release import release_identity
from countyiq.lib.record_explanations import (
    EXPLANATION_SCHEMA,
    SYSTEM_PROMPT,
    configure_explanation_harness,
)
from eval.record_explanations_canary import canary_config, run


@pytest.mark.parametrize("kind", ["municipal", "property"])
@pytest.mark.parametrize(
    "model, effort, expected_tokens, prices",
    [
        ("z-ai/glm-5.3-flash", "low", 4096, (0.16, 0.55)),
        ("z-ai/glm-5.3-flash", "high", 8192, (0.16, 0.55)),
        ("z-ai/glm-5.3-flash", "max", 8192, (0.16, 0.55)),
        ("openai/gpt-5.6-luna", "low", 2048, (0.28, 1.32)),
        ("deepseek/deepseek-v4-flash-0731", "low", 2048, (0.16, 0.32)),
        ("deepseek/deepseek-v4-flash-0731", "none", 2048, (0.16, 0.32)),
    ],
)
def test_production_and_canary_payloads_match(
    monkeypatch, kind, model, effort, expected_tokens, prices
):
    provider = "test-provider"
    for key, value in {
        "COUNTYIQ_PASS3_MODEL": model,
        "COUNTYIQ_PASS3_REASONING_EFFORT": effort,
        "COUNTYIQ_PASS3_THINKING": "false",
        "COUNTYIQ_PASS3_MAX_TOKENS": "",
        "COUNTYIQ_PASS3_PROVIDER_ONLY": provider,
        "COUNTYIQ_PASS3_PROVIDER_ORDER": provider,
        "COUNTYIQ_PASS3_PROVIDER_ALLOW_FALLBACKS": "false",
        "COUNTYIQ_MAX_PRICE_PROMPT": str(prices[0]),
        "COUNTYIQ_MAX_PRICE_COMPLETION": str(prices[1]),
        "COUNTYIQ_ZDR": "false",
    }.items():
        monkeypatch.setenv(key, value)
    config = build_pass_harness_config(
        pass_number=3,
        archive_label="record_explanations",
        reasoning_task=True,
        default_max_tokens=2048,
        json_schema=EXPLANATION_SCHEMA,
        schema_name="record_explanation",
        system_prompt=SYSTEM_PROMPT,
        require_enabled=False,
    )
    production = configure_explanation_harness(config, kind)
    calibration = canary_config(
        model, provider=provider, reasoning_effort=effort, kind=kind
    )
    payload = build_openrouter_payload(production, "same source")
    assert payload == build_openrouter_payload(calibration, "same source")
    assert payload["max_tokens"] == expected_tokens
    assert payload["provider"]["only"] == [provider]
    assert payload["provider"]["allow_fallbacks"] is False
    if model.startswith("z-ai/"):
        assert payload["temperature"] == 1
        assert payload["top_p"] == 0.95
        assert "top_k" not in payload
    elif model.startswith("openai/") or effort == "low":
        assert "temperature" not in payload and "top_p" not in payload


def test_explicit_budget_survives_glm_defaults():
    config = canary_config(
        "z-ai/glm-5.3-flash", reasoning_effort="high", max_tokens=6000
    )
    assert config.max_tokens == 6000


def test_calibration_requires_provider_before_reading_cases_or_budget(tmp_path):
    with pytest.raises(ValueError, match="explicit provider"):
        run(tmp_path / "missing-cases", tmp_path / "out", tmp_path / "missing-budget")
    assert not (tmp_path / "out").exists()


def test_records_never_downgrade_schema(monkeypatch):
    monkeypatch.setenv("COUNTYIQ_ALLOW_SCHEMA_FALLBACK", "true")
    monkeypatch.setenv("COUNTYIQ_STRICT_SCHEMA", "false")
    monkeypatch.setenv("COUNTYIQ_PASS3_MODEL", "z-ai/glm-5.3-flash")
    monkeypatch.setenv("COUNTYIQ_PASS3_REASONING_EFFORT", "low")
    config = build_pass_harness_config(
        pass_number=3,
        archive_label="test",
        reasoning_task=True,
        default_max_tokens=2048,
        json_schema=EXPLANATION_SCHEMA,
        require_enabled=False,
    )
    assert config.allow_schema_fallback and config.json_schema is None
    config = configure_explanation_harness(config, "property")
    assert not config.allow_schema_fallback
    assert config.json_schema is not None and config.require_parameters


@pytest.mark.parametrize(
    "setting, value",
    [
        ("COUNTYIQ_PASS3_PROVIDER_ONLY", "other-provider"),
        ("COUNTYIQ_PROVIDER_ORDER", "other-provider"),
        ("COUNTYIQ_PASS3_PROVIDER_ALLOW_FALLBACKS", "false"),
        ("COUNTYIQ_ALLOW_SCHEMA_FALLBACK", "true"),
        ("COUNTYIQ_MAX_PRICE_PROMPT", "999"),
    ],
)
def test_routing_and_schema_policy_changes_invalidate_release_identity(
    monkeypatch, setting, value
):
    monkeypatch.delenv(setting, raising=False)
    previous = release_identity(3)
    monkeypatch.setenv(setting, value)
    assert release_identity(3) != previous
