#!/usr/bin/env python3
"""Re-score saved frozen Pass 2 outputs without making model calls."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from eval.challenger import summarize_pass2_gold
from eval.fixture_io import load_frozen_cases
from eval.scoring import PASS2_SCORING_VERSION, score_pass2


FIXTURES = Path(__file__).resolve().parent / "fixtures"


def rescore_result(
    source: Path,
    destination: Path | None = None,
    fixture_path: Path | None = None,
) -> Path:
    payload = json.loads(source.read_text())
    pass2 = payload.get("pass2")
    if not isinstance(pass2, dict) or not str(pass2.get("dataset_mode")).startswith(
        "frozen_"
    ):
        raise ValueError("Result does not contain a frozen Pass 2 run")

    resolved_fixture = fixture_path or FIXTURES / "p2_frozen.json"
    fixtures = {case["id"]: case for case in load_frozen_cases(resolved_fixture)}
    rows = pass2.get("case_rows") or []
    for row in rows:
        case_id = row.get("case_id")
        case = fixtures.get(case_id)
        if not case:
            raise ValueError(f"Unknown frozen case: {case_id}")
        if row.get("context_sha256") != case["context_sha256"]:
            raise ValueError(
                f"Context hash mismatch for {case_id}; refusing invalid rescore"
            )
        for side in ("challenger", "incumbent"):
            row[side]["score"] = score_pass2(row[side].get("parsed"), case)

    pass2["scoring_version"] = PASS2_SCORING_VERSION
    pass2["gold"] = summarize_pass2_gold(rows)
    payload["rescored_at"] = datetime.now(timezone.utc).isoformat()
    payload["rescored_from"] = str(source)
    if isinstance(payload.get("summary"), dict):
        payload["summary"]["p2"] = (
            pass2["gold"] | pass2.get("tally", {}) | {"judged": pass2.get("judged", 0)}
        )

    target = destination or source.with_name(f"{source.stem}_rescored.json")
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=1, default=str))
    temporary.replace(target)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fixture", type=Path)
    args = parser.parse_args()
    target = rescore_result(args.result, args.output, args.fixture)
    print(f"Wrote {target}")


if __name__ == "__main__":
    main()
