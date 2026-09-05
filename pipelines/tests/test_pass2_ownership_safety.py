"""Ownership-change prompts must not invite unsupported distress or intent claims."""

from countyiq.lib.pass2_batched_validation import (
    BATCHED_VALIDATION_SYSTEM_PROMPT,
    _format_signals_list,
)


def test_ownership_change_prompt_states_safety_boundary():
    prompt = BATCHED_VALIDATION_SYSTEM_PROMPT.lower()
    questions = _format_signals_list(
        [
            {
                "signal_key": "ownership_change",
                "signal_weight": 0.06,
                "evidence": {
                    "price": 2500,
                    "price_to_assessed_pct": 10,
                    "buyer_name_looks_organizational": True,
                },
            }
        ]
    ).lower()

    assert "does not establish" in prompt
    assert "developer identity, or development intent" in prompt
    assert "do not infer distress, foreclosure, or a flip" in questions
    assert "does not establish developer identity or intent" in questions
