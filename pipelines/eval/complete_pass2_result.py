#!/usr/bin/env python3
"""Recover checkpointed Pass 2 outputs from archives and fill only missing calls."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from countyiq.lib.pass2_batched_validation import (
    build_batched_signal_prompt,
    parse_batched_signal_output,
)
from countyiq.lib.pass_llm_config import resolve_pass_model
from eval.challenger import _mk_config, _parse, _pass2_prompt_one, summarize_pass2_gold
from eval.fixture_io import load_frozen_cases
from eval.protocol import EvalCostLedger
from eval.scoring import PASS2_SCORING_VERSION, score_pass2


def _archived_outputs(
    archive_root: Path, *, ran_at: str, case_ids: set[str]
) -> dict[tuple[str, str], dict]:
    outputs = {}
    for path in archive_root.glob("archives/challenger/*/*.json"):
        try:
            record = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if record.get("archived_at", "") < ran_at:
            continue
        key = str(record.get("key") or "")
        parts = key.split(":", 2)
        if len(parts) != 3 or parts[0] != "chal_p2" or parts[1] not in case_ids:
            continue
        identity = (parts[1], parts[2])
        if (
            identity not in outputs
            or record["archived_at"] > outputs[identity]["archived_at"]
        ):
            outputs[identity] = record
    return outputs


def _from_archive(record: dict, signals: list[dict]) -> dict:
    raw = record.get("raw_output") or ""
    parsed = parse_batched_signal_output(_parse(raw) or {}, signals)
    error = (record.get("metadata") or {}).get("error")
    return {
        "success": not error and isinstance(parsed, dict),
        "error": error,
        "usage": record.get("metadata") or {},
        "parsed": parsed,
        "output": json.dumps(parsed) if parsed else "",
    }


def complete_result(
    source: Path,
    fixture_path: Path,
    destination: Path,
    *,
    max_fill_cost_usd: float,
) -> dict:
    payload = json.loads(source.read_text())
    cases = load_frozen_cases(fixture_path)
    case_ids = {case["id"] for case in cases}
    archive_root = Path.cwd()
    archived = _archived_outputs(
        archive_root, ran_at=payload["ran_at"], case_ids=case_ids
    )
    challenger_model = payload["challenger"]
    incumbent_model = resolve_pass_model(2)
    configs = {
        "challenger": _mk_config(
            challenger_model,
            2,
            max_tokens=4096,
            effort="low",
            quant=("fp8",) if challenger_model == "z-ai/glm-5.3-flash" else None,
        ),
        "incumbent": _mk_config(incumbent_model, 2, max_tokens=4096, effort="low"),
    }
    models = {"challenger": challenger_model, "incumbent": incumbent_model}
    ledger = EvalCostLedger(max_cost_usd=max_fill_cost_usd)
    filled = []
    rows = []
    for case in cases:
        context = case["context"]
        prompt = build_batched_signal_prompt(context)
        values = {}
        for side in ("challenger", "incumbent"):
            record = archived.get((case["id"], models[side]))
            if record:
                values[side] = _from_archive(record, context["signals"])
            else:
                values[side] = _pass2_prompt_one(
                    configs[side],
                    prompt,
                    context["signals"],
                    case["id"],
                    ledger,
                )
                filled.append({"case_id": case["id"], "side": side})
            values[side]["score"] = score_pass2(values[side]["parsed"], case)
        rows.append(
            {
                "case_id": case["id"],
                "case_type": case["case_type"],
                "context_sha256": case["context_sha256"],
                **values,
            }
        )

    archived_spend = sum(
        float((record.get("metadata") or {}).get("cost") or 0)
        for record in archived.values()
    )
    total_spend = archived_spend + ledger.spent_usd
    payload["pass2"] = {
        "dataset_mode": "frozen_rubric",
        "fixture_file": str(fixture_path),
        "scoring_version": PASS2_SCORING_VERSION,
        "n_parcels": len(cases),
        "judged": 0,
        "judge_mode": "not_run",
        "tally": {},
        "case_rows": rows,
        "judgments": [],
        "gold": summarize_pass2_gold(rows),
    }
    payload["spend_usd"] = round(total_spend, 9)
    payload["budget"] = {
        "calls": len(archived) + ledger.calls,
        "spend_usd": round(total_spend, 9),
        "reserved_usd": 0.0,
        "max_fill_cost_usd": max_fill_cost_usd,
    }
    payload["summary"] = {"p2": payload["pass2"]["gold"] | {"judged": 0}}
    payload["recovered_at"] = datetime.now(timezone.utc).isoformat()
    payload["recovered_from"] = str(source)
    payload["archive_outputs_recovered"] = len(archived)
    payload["missing_calls_filled"] = filled
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=1, default=str))
    temporary.replace(destination)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-fill-cost-usd", type=float, default=0.05)
    args = parser.parse_args()
    if not os.environ.get("OPENROUTER_API_KEY"):
        key_file = Path("~/.config/openrouter/key").expanduser()
        if key_file.exists():
            os.environ["OPENROUTER_API_KEY"] = key_file.read_text().strip()
        else:
            raise SystemExit("OPENROUTER_API_KEY not set")
    destination = args.output or args.result.with_name(
        f"{args.result.stem}_completed.json"
    )
    payload = complete_result(
        args.result,
        args.fixture,
        destination,
        max_fill_cost_usd=args.max_fill_cost_usd,
    )
    print(f"Wrote {destination}")
    print(json.dumps(payload["summary"]["p2"], indent=2))
    print(f"Filled {len(payload['missing_calls_filled'])} missing calls")
    print(f"Spend: ${payload['spend_usd']:.9f}")


if __name__ == "__main__":
    main()
