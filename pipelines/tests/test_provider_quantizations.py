"""Provider quantization pinning must reach the OpenRouter payload.

Added 2026-08-06: OpenRouter's cheapest GLM-5.2 providers serve FP4/NVFP4
weights with documented output degradation — evals and production calls that
care about quality must be able to exclude them.
"""

from countyiq.lib.llm_harness import HarnessConfig, build_openrouter_payload


def test_quantizations_pin_reaches_provider_prefs():
    config = HarnessConfig(
        model_path="z-ai/glm-5.2",
        provider_quantizations=("fp8", "bf16", "fp16"),
    )
    payload = build_openrouter_payload(config, "hello")
    assert payload["provider"]["quantizations"] == ["fp8", "bf16", "fp16"]


def test_no_pin_leaves_provider_prefs_untouched():
    payload = build_openrouter_payload(HarnessConfig(model_path="z-ai/glm-5.2"), "hello")
    assert "quantizations" not in payload.get("provider", {})
