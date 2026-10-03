"""Native evaluation must retain the production quality gates without API calls."""

from types import SimpleNamespace

import pytest
from countyiq.lib.llm_harness import HarnessResult
from eval import subscription_challenger


@pytest.mark.parametrize("batch_failed", [False, True])
def test_empty_native_outputs_fail_every_frozen_entity_case_without_api_calls(
    tmp_path, monkeypatch, batch_failed
):
    prompts = []

    class EmptyAuthor:
        def __init__(self, directory, **kwargs):
            directory.mkdir(parents=True)
            self.receipts = []

        def prefetch(self, config, values):
            assert config.model_path == "codex/subscription:gpt-5.6-luna"
            prompts.extend(values)
            if batch_failed:
                raise ValueError("Incomplete batch")

        def __call__(self, config, prompt):
            return HarnessResult(success=True, parsed={}, raw_output="{}")

        def provenance(self):
            return {"api_calls": 0, "provider": "codex_subscription"}

    def forbidden_api(*args, **kwargs):
        raise AssertionError("Native evaluation dispatched an API call")

    monkeypatch.setattr(subscription_challenger, "SubscriptionAuthor", EmptyAuthor)
    monkeypatch.setattr("eval.protocol.invoke_with_retry", forbidden_api)
    args = SimpleNamespace(
        model="gpt-5.6-luna",
        pass_number=1,
        output=tmp_path,
        expanded=False,
        effort="medium",
        batch_size=8,
        trial=1,
    )
    report = subscription_challenger.run(args)
    assert len(report["cases"]) == 8
    assert all(not row["score"]["gold_pass"] for row in report["cases"])
    assert report["api_calls"] == 0
    assert bool(report["batch_failures"]) == batch_failed
    assert len(prompts) == 8
    assert all("acceptable_partitions" not in prompt for prompt in prompts)
    assert all("Independent review identifier:" in prompt for prompt in prompts)
