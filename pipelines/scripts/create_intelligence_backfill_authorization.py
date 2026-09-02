"""Create a one-time cumulative dollar authorization for one paid pass."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path

from countyiq.lib.backfill_authorization import (
    BackfillAuthorizationError,
    create_backfill_authorization,
)
from countyiq.lib.pass_llm_config import resolve_pass_enabled, resolve_pass_model


def _positive_env(name: str) -> float:
    try:
        value = float(os.environ.get(name, ""))
    except ValueError as exc:
        raise BackfillAuthorizationError(f"{name} must be numeric") from exc
    if not math.isfinite(value) or value <= 0:
        raise BackfillAuthorizationError(f"{name} must be positive and finite")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pass-number", type=int, choices=range(4), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    pass_number = args.pass_number
    if resolve_pass_enabled(pass_number):
        parser.error(
            f"disable COUNTYIQ_PASS{pass_number}_ENABLED before creating authorization"
        )
    try:
        snapshot = create_backfill_authorization(
            args.output,
            pass_number=pass_number,
            model=resolve_pass_model(pass_number) or "",
            max_cost_usd=_positive_env(
                f"COUNTYIQ_PASS{pass_number}_MAX_COST_USD"
            ),
            max_price_prompt=_positive_env("COUNTYIQ_MAX_PRICE_PROMPT"),
            max_price_completion=_positive_env(
                "COUNTYIQ_MAX_PRICE_COMPLETION"
            ),
        )
    except BackfillAuthorizationError as exc:
        parser.error(str(exc))
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
