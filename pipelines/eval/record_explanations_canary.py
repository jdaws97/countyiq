"""Evaluate frozen record bundles under the existing shared authorization ledger.

Never dispatch a case twice. A missing or uncertain provider cost stops the run
and retains the reservation. Outputs are proposals, not automatic UI imports.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import asdict
from pathlib import Path

import requests
from countyiq.lib.backfill_authorization import BackfillAuthorization
from countyiq.lib.llm_harness import (
    OPENROUTER_URL,
    HarnessConfig,
    build_harness_config,
    build_openrouter_payload,
    extract_json_object,
    strip_thinking,
)
from countyiq.lib.pass_llm_config import estimate_reserved_call_cost
from countyiq.lib.record_explanations import (
    EXPLANATION_SCHEMA,
    SYSTEM_PROMPT,
    configure_explanation_harness,
    correction_prompt,
    explanation_prompt,
    prepare_explanation,
    validate_explanation,
)
from jsonschema import ValidationError


def canary_config(
    model: str = "openai/gpt-5.6-luna",
    *,
    provider: str | None = None,
    reasoning_effort: str | None = None,
    max_tokens: int | None = None,
    kind: str = "municipal",
) -> HarnessConfig:
    prices = {
        "openai/gpt-5.6-luna": (0.28, 1.32),
        "z-ai/glm-5.3-flash": (0.16, 0.55),
        "deepseek/deepseek-v4-flash-0731": (0.16, 0.32),
    }
    prompt_price, completion_price = prices[model]
    if reasoning_effort is None:
        reasoning_effort = "low"
    config = build_harness_config(
        model_path=model,
        max_tokens=max_tokens,
        thinking=False,
        reasoning_effort=reasoning_effort,
        json_schema=EXPLANATION_SCHEMA,
        schema_name="record_explanation",
        system_prompt=SYSTEM_PROMPT,
        max_price_prompt=prompt_price,
        max_price_completion=completion_price,
        require_parameters=True,
        provider_only=(provider,) if provider else None,
        provider_order=(provider,) if provider else None,
        provider_allow_fallbacks=False if provider else None,
    )
    return configure_explanation_harness(config, kind)


def _write_new(path: Path, value: object) -> None:
    with path.open("x") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, default=str)
        handle.write("\n")


def run(
    cases_path: Path,
    output: Path,
    budget_path: Path,
    model: str = "openai/gpt-5.6-luna",
    *,
    provider: str | None = None,
    reasoning_effort: str | None = None,
    max_tokens: int | None = None,
) -> None:
    if not provider or not provider.strip():
        raise ValueError("Calibration requires one explicit provider; use --provider")
    provider = provider.strip()
    if max_tokens is not None and not 256 <= max_tokens <= 8192:
        raise ValueError("max_tokens must be between 256 and 8192")
    config = canary_config(
        model,
        provider=provider,
        reasoning_effort=reasoning_effort,
        max_tokens=max_tokens,
    )
    budget = BackfillAuthorization(
        budget_path,
        pass_number=0,
        model="pass03-optimization",
        max_cost_usd=5.0,
        max_price_prompt=3.0,
        max_price_completion=15.0,
    )
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        key = Path("~/.config/openrouter/key").expanduser().read_text().strip()
    for case in json.loads(cases_path.read_text()):
        directory = output / case["id"]
        source = case["source"]
        config = configure_explanation_harness(config, source["kind"])
        prompt = explanation_prompt(source)
        if case.get("correction_error"):
            prompt = correction_prompt(source, case["correction_error"])
        payload = build_openrouter_payload(config, prompt)
        if directory.exists():
            if json.loads((directory / "request.json").read_text()) != payload:
                raise ValueError(
                    "Existing cohort uses a different request; use a new output directory"
                )
            result_path = directory / "result.json"
            if not result_path.exists() or json.loads(result_path.read_text()).get(
                "stop"
            ):
                raise RuntimeError("Earlier dispatch is unsettled; do not retry")
            continue
        ceiling = estimate_reserved_call_cost(
            prompt_tokens=len(json.dumps(payload, ensure_ascii=False).encode()),
            max_tokens=config.max_tokens,
            max_price_prompt=config.max_price_prompt,
            max_price_completion=config.max_price_completion,
            retries=0,
        )
        reservation = budget.reserve(ceiling)
        directory.mkdir(parents=True)
        _write_new(directory / "request.json", payload)
        _write_new(directory / "config.json", asdict(config))
        _write_new(directory / "source.json", source)
        _write_new(
            directory / "reservation.json", {"id": reservation, "ceiling": ceiling}
        )
        result = {"id": case["id"], "errors": [], "structural_pass": False}
        cost = None
        try:
            response = requests.post(
                OPENROUTER_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {key}",
                    "X-Title": "CountyIQ record explanation canary",
                },
                timeout=(15, 120),
            )
            (directory / "response.json").write_text(response.text)
            body = response.json()
            result["usage"] = body.get("usage") or {}
            result["provider"] = body.get("provider")
            result["served_model"] = body.get("model")
            cost = result["usage"].get("cost")
            response.raise_for_status()
            choice = body["choices"][0]
            if choice.get("finish_reason") != "stop":
                raise ValueError(f"Incomplete response: {choice.get('finish_reason')}")
            clean_output = strip_thinking(choice["message"]["content"] or "")
            parsed = json.loads(extract_json_object(clean_output))
            result["raw_parsed"] = parsed
            prepared, preparation_notes = prepare_explanation(parsed, source)
            result["parsed"] = prepared
            result["preparation_notes"] = preparation_notes
            validate_explanation(prepared, source)
            result["structural_pass"] = True
        except (
            requests.RequestException,
            ValueError,
            ValidationError,
            KeyError,
            IndexError,
            TypeError,
        ) as error:
            result["errors"].append(f"{type(error).__name__}: {error}")
        finally:
            known = (
                isinstance(cost, (int, float))
                and not isinstance(cost, bool)
                and math.isfinite(cost)
                and cost >= 0
            )
            if known:
                budget.settle(reservation, cost)
            else:
                budget.forfeit(reservation)
            result.update(
                cost_usd=cost if known else None, stop=not known or cost > ceiling
            )
            _write_new(directory / "result.json", result)
        print(
            json.dumps(
                {
                    key: result[key]
                    for key in ("id", "structural_pass", "cost_usd", "errors")
                }
            ),
            flush=True,
        )
        if result["stop"]:
            raise RuntimeError("Uncertain provider accounting; run stopped")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--budget", type=Path, required=True)
    parser.add_argument(
        "--provider",
        required=True,
        help="One exact OpenRouter provider slug; fallback is disabled",
    )
    parser.add_argument(
        "--reasoning-effort", choices=["none", "low", "medium", "high", "max"]
    )
    parser.add_argument("--max-tokens", type=int)
    parser.add_argument(
        "--model",
        choices=[
            "openai/gpt-5.6-luna",
            "z-ai/glm-5.3-flash",
            "deepseek/deepseek-v4-flash-0731",
        ],
        default="openai/gpt-5.6-luna",
    )
    args = parser.parse_args()
    run(
        args.cases,
        args.output,
        args.budget,
        args.model,
        provider=args.provider,
        reasoning_effort=args.reasoning_effort,
        max_tokens=args.max_tokens,
    )


if __name__ == "__main__":
    main()
