"""Static system prefixes must stay long enough for provider prompt caching.

OpenAI caches only prompts whose identical prefix is at least 1,024 tokens.
The 2026-09-02 audit found every pass below that floor (487–838 tokens) with
``cached_tokens: 0`` on every call. 4,600 characters is a conservative floor
(~1,150 tokens at four characters per token; JSON-heavy text tokenizes
denser, which only helps). The live Pass 0 canary after the change reported
cached tokens on 24 of 25 Luna calls.
"""

import pytest

from countyiq.lib.pass0_templates import PASS0_SYSTEM_PROMPT
from countyiq.lib.pass1_entity_verification import ENTITY_VERIFICATION_SYSTEM_PROMPT
from countyiq.lib.pass2_batched_validation import BATCHED_VALIDATION_SYSTEM_PROMPT
from countyiq.lib.pass3_brief_generation import BRIEF_GENERATION_SYSTEM_PROMPT
from countyiq.lib.pass3_owner_briefs import OWNER_ROLLUP_SYSTEM_PROMPT
from countyiq.lib.prompt_prefix import CITATION_FORMAT_BLOCK

MIN_PREFIX_CHARS = 4_600

PROMPTS = [
    ("pass0", PASS0_SYSTEM_PROMPT),
    ("pass1", ENTITY_VERIFICATION_SYSTEM_PROMPT),
    ("pass2", BATCHED_VALIDATION_SYSTEM_PROMPT),
    ("pass3", BRIEF_GENERATION_SYSTEM_PROMPT),
    ("pass3b", OWNER_ROLLUP_SYSTEM_PROMPT),
]


@pytest.mark.parametrize("label, prompt", PROMPTS)
def test_static_system_prefix_exceeds_cache_minimum(label: str, prompt: str) -> None:
    assert len(prompt) >= MIN_PREFIX_CHARS, f"{label} prefix is {len(prompt)} chars"
    # Static means static: no format placeholders may survive into the prefix.
    assert "{county_context}" not in prompt


@pytest.mark.parametrize(
    "prompt",
    [
        BATCHED_VALIDATION_SYSTEM_PROMPT,
        BRIEF_GENERATION_SYSTEM_PROMPT,
        OWNER_ROLLUP_SYSTEM_PROMPT,
    ],
)
def test_citation_format_block_is_verbatim_in_cited_passes(prompt: str) -> None:
    assert CITATION_FORMAT_BLOCK in prompt


def test_prefix_blocks_carry_no_signal_semantics() -> None:
    # The gate-relevant blocks may describe format and field contracts only.
    # A glossary of what each signal "does NOT establish" shifted Luna's Pass 2
    # statuses on the reviewed gold set (2026-09-02) and must not return.
    assert "does NOT establish" not in BATCHED_VALIDATION_SYSTEM_PROMPT
    assert "SIGNAL DEFINITIONS" not in BATCHED_VALIDATION_SYSTEM_PROMPT
