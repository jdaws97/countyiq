"""Immutable fixture loading and canonical context fingerprints."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def canonical_context_hash(context: Any) -> str:
    payload = json.dumps(
        context,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_frozen_cases(path: Path) -> list[dict]:
    """Load cases and reject a stale or manually damaged context snapshot."""
    payload = json.loads(path.read_text())
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"Frozen fixture has no cases: {path}")
    for case in cases:
        expected = case.get("context_sha256")
        actual = canonical_context_hash(case.get("context"))
        if expected != actual:
            raise ValueError(
                f"Frozen context hash mismatch for {case.get('id')}: "
                f"expected {expected}, got {actual}"
            )
    return cases
