#!/usr/bin/env python3
"""Live smoke/performance runner for CountyIQ intelligence passes.

Runs Pass 2 or Pass 3 against current database context and stores transport,
schema, latency, and cost results for eval_report.py. This is not a model-quality
or promotion gate; use challenger.py's frozen human-labeled lane for that.

Usage:
    .venv/bin/python -m eval.eval_runner --model inception/mercury-2 --pass 2 --limit 10
    .venv/bin/python -m eval.eval_runner --model google/gemini-2.5-flash --pass 3 --limit 10
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras

from countyiq.lib.llm_harness import (
    HarnessConfig,
    get_preset_for_model,
    detect_model_family,
)
from countyiq.lib.pass2_batched_validation import (
    build_batched_signal_prompt,
    gather_parcel_batch_context,
    parse_batched_signal_output,
)
from countyiq.lib.pass3_brief_generation import (
    build_brief_generation_prompt,
    gather_brief_context,
    parse_brief_output,
)
from eval.protocol import (
    EVAL_MODEL_PRICE_CEILINGS,
    EvalCostLedger,
    EvalCostLimitExceeded,
    EvalCostUnavailable,
    build_production_eval_config,
    invoke_tracked,
)


# ---------------------------------------------------------------------------
# Dataset SQL for ad hoc stratified sampling. Frozen fixture keys remain the
# preferred cross-model comparison path.
# ---------------------------------------------------------------------------

DATASET_SQL = """
WITH high_signal AS (
    SELECT
        ds.pidn,
        COUNT(*)                                    AS signal_count,
        (
            SELECT ds2.signal_key
            FROM public.development_signals ds2
            WHERE ds2.pidn = ds.pidn
            ORDER BY ds2.signal_weight DESC
            LIMIT 1
        )                                           AS top_signal,
        'high_signal'                               AS category
    FROM public.development_signals ds
    GROUP BY ds.pidn
    HAVING COUNT(*) >= 3
    ORDER BY RANDOM()
    LIMIT 50
),
tax_distress AS (
    SELECT
        ds.pidn,
        COUNT(*)                                    AS signal_count,
        ds.signal_key                               AS top_signal,
        'tax_distress'                              AS category
    FROM public.development_signals ds
    WHERE ds.signal_key = 'tax_distress'
      AND ds.pidn NOT IN (SELECT pidn FROM high_signal)
    GROUP BY ds.pidn, ds.signal_key
    ORDER BY RANDOM()
    LIMIT 20
),
exclusion AS (
    SELECT
        ds.pidn,
        COUNT(*)                                    AS signal_count,
        ds.signal_key                               AS top_signal,
        'exclusion'                                 AS category
    FROM public.development_signals ds
    WHERE ds.signal_key = 'conservation_easement'
      AND ds.pidn NOT IN (SELECT pidn FROM high_signal)
      AND ds.pidn NOT IN (SELECT pidn FROM tax_distress)
    GROUP BY ds.pidn, ds.signal_key
    ORDER BY RANDOM()
    LIMIT 10
),
assemblage AS (
    SELECT
        ds.pidn,
        COUNT(*)                                    AS signal_count,
        ds.signal_key                               AS top_signal,
        'assemblage'                                AS category
    FROM public.development_signals ds
    WHERE ds.signal_key = 'assemblage'
      AND ds.pidn NOT IN (SELECT pidn FROM high_signal)
      AND ds.pidn NOT IN (SELECT pidn FROM tax_distress)
      AND ds.pidn NOT IN (SELECT pidn FROM exclusion)
    GROUP BY ds.pidn, ds.signal_key
    ORDER BY RANDOM()
    LIMIT 20
)
SELECT * FROM (
    SELECT * FROM high_signal
    UNION ALL
    SELECT * FROM tax_distress
    UNION ALL
    SELECT * FROM exclusion
    UNION ALL
    SELECT * FROM assemblage
) combined
ORDER BY RANDOM()
"""

# Query to fetch all signals for a parcel (needed for Pass 2 iteration)
SIGNALS_FOR_PIDN_SQL = """
    SELECT
        pidn,
        signal_key,
        signal_weight,
        source_table,
        source_id,
        distance_m,
        evidence
    FROM public.development_signals
    WHERE pidn = %(pidn)s
    ORDER BY signal_weight DESC
"""


# ---------------------------------------------------------------------------
# DB connection
# ---------------------------------------------------------------------------


def get_connection():
    """Return a psycopg2 connection using environment variables."""
    return psycopg2.connect(
        host=os.environ.get("DATABASE_HOST", "localhost"),
        port=int(os.environ.get("DATABASE_PORT", 5433)),
        dbname=os.environ.get("DATABASE_NAME", "countyiq"),
        user=os.environ.get("DATABASE_USER", "dagster_admin"),
        password=os.environ.get("DATABASE_PASSWORD", "localtest"),
    )


# ---------------------------------------------------------------------------
# Pass 2 BATCHED evaluation — one LLM call validates ALL signals on a parcel
# ---------------------------------------------------------------------------


def run_pass2_batched(
    cursor, config: HarnessConfig, pidn: str, ledger: EvalCostLedger
) -> dict:
    """Run batched Pass 2 validation for all signals on a parcel.

    Includes retry path for dropped signals: if the first LLM call returns
    fewer validations than signals sent, makes a second call with only the
    missing signals to recover them.
    """
    t0 = time.perf_counter()
    try:
        ctx = gather_parcel_batch_context(cursor, pidn)
        if not ctx.get("signals"):
            return {
                "success": False,
                "elapsed_seconds": 0.0,
                "raw_output": "",
                "parsed_output": None,
                "error": f"No signals found for pidn={pidn}",
            }

        prompt = build_batched_signal_prompt(ctx)
        archive_key = f"batch:{pidn}"
        result = invoke_tracked(ledger, config, prompt, archive_key=archive_key)

        if not result.success:
            elapsed = time.perf_counter() - t0
            return {
                "success": False,
                "elapsed_seconds": round(elapsed, 2),
                "raw_output": (result.raw_output or "")[:4000],
                "parsed_output": None,
                "error": result.error,
                "n_signals": len(ctx["signals"]),
                "usage": result.metadata,
            }

        parsed = parse_batched_signal_output(result.parsed or {}, ctx["signals"])
        all_validations = list(parsed.get("validations", []))
        retry_attempted = 0
        retry_recovered = 0
        retry_usage = None

        # Retry path: recover signals the LLM dropped or failed to parse
        retry_keys = set(parsed.get("missing", [])) | set(parsed.get("errors", []))
        if retry_keys:
            retry_signals = [s for s in ctx["signals"] if s["signal_key"] in retry_keys]
            retry_attempted = len(retry_signals)
            retry_prompt = build_batched_signal_prompt(
                ctx, signals_override=retry_signals
            )
            retry_result = invoke_tracked(
                ledger, config, retry_prompt, archive_key=f"batch:{pidn}:retry"
            )
            retry_usage = retry_result.metadata
            if retry_result.success:
                retry_parsed = parse_batched_signal_output(
                    retry_result.parsed or {}, retry_signals
                )
                retry_vals = retry_parsed.get("validations", [])
                all_validations.extend(retry_vals)
                retry_recovered = len(retry_vals)

        elapsed = time.perf_counter() - t0
        success = len(all_validations) > 0

        return {
            "success": success,
            "elapsed_seconds": round(elapsed, 2),
            "raw_output": (result.raw_output or "")[:4000],
            "parsed_output": {
                "validations": all_validations,
                "cross_signal_insight": parsed.get("cross_signal_insight", ""),
            },
            "error": parsed.get("parse_error") if not success else None,
            "n_signals": len(ctx["signals"]),
            "n_validations": len(all_validations),
            "n_missing_initial": len(parsed.get("missing", [])),
            "retry_attempted": retry_attempted,
            "retry_recovered": retry_recovered,
            "cross_signal_insight": parsed.get("cross_signal_insight", ""),
            "usage": result.metadata,
            "retry_usage": retry_usage,
        }
    except (EvalCostLimitExceeded, EvalCostUnavailable):
        raise
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        return {
            "success": False,
            "elapsed_seconds": round(elapsed, 2),
            "raw_output": "",
            "parsed_output": None,
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# Pass 3 evaluation
# ---------------------------------------------------------------------------


def run_pass3(cursor, config: HarnessConfig, pidn: str, ledger: EvalCostLedger) -> dict:
    """Run Pass 3 (brief generation) for a parcel.

    Returns a result dict with: success, elapsed_seconds, raw_output,
    parsed_output, error.
    """
    t0 = time.perf_counter()
    try:
        context = gather_brief_context(cursor, pidn)
        prompt = build_brief_generation_prompt(context)
        result = invoke_tracked(ledger, config, prompt, archive_key=pidn)
        elapsed = time.perf_counter() - t0

        if result.success:
            parsed = parse_brief_output(result.parsed)
            success = "error" not in parsed
            return {
                "success": success,
                "elapsed_seconds": round(elapsed, 2),
                "raw_output": (result.raw_output or "")[:2000],
                "parsed_output": parsed,
                "error": parsed.get("error") if not success else None,
                "usage": result.metadata,
            }
        else:
            return {
                "success": False,
                "elapsed_seconds": round(elapsed, 2),
                "raw_output": (result.raw_output or "")[:2000],
                "parsed_output": None,
                "error": result.error,
                "usage": result.metadata,
            }
    except (EvalCostLimitExceeded, EvalCostUnavailable):
        raise
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        return {
            "success": False,
            "elapsed_seconds": round(elapsed, 2),
            "raw_output": "",
            "parsed_output": None,
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="CountyIQ live Pass 2/3 smoke, latency, and cost runner.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  .venv/bin/python -m eval.eval_runner --model inception/mercury-2 --pass 2 --limit 10
  .venv/bin/python -m eval.eval_runner --model google/gemini-2.5-flash --pass 3 --limit 20
        """,
    )
    parser.add_argument(
        "--model",
        required=True,
        help="OpenRouter model slug to evaluate.",
    )
    parser.add_argument(
        "--pass",
        dest="pass_num",
        type=int,
        choices=[2, 3],
        required=True,
        help="Which pass to evaluate: 2 (signal validation) or 3 (brief generation).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of parcels to evaluate (default: 10).",
    )
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parent / "results"),
        help="Directory to write result JSON files (default: pipelines/eval/results).",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="Sampling temperature. If not set, uses model's recommended preset.",
    )
    parser.add_argument(
        "--top-p",
        type=float,
        default=None,
        help="Top-p sampling. If not set, uses model's recommended preset.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=None,
        help="Top-k sampling. If not set, uses model's recommended preset.",
    )
    parser.add_argument(
        "--min-p",
        type=float,
        default=None,
        help="Min-p sampling. If not set, uses model's recommended preset.",
    )
    parser.add_argument(
        "--presence-penalty",
        type=float,
        default=None,
        help="Presence penalty. If not set, uses model's recommended preset.",
    )
    parser.add_argument(
        "--repeat-penalty",
        type=float,
        default=None,
        help="Repeat penalty. If not set, uses model's recommended preset.",
    )
    parser.add_argument(
        "--thinking",
        action="store_true",
        help="Enable thinking mode (Gemma <|think|>, Qwen3.5 /think). Default: off. For Mistral, use the Reasoning model variant.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="Max output tokens. Default: 4096 for Pass 2 or 2048 for Pass 3. Reasoning models may need 8192+.",
    )
    parser.add_argument(
        "--pidns-file",
        default=None,
        help="File with one PIDN per line — evaluate exactly these parcels instead "
        "of a fresh random sample. Use one shared file across models so every "
        "model sees identical parcels (cross-model comparability).",
    )
    parser.add_argument(
        "--quantizations",
        default=None,
        help="Comma-separated provider quantization allowlist (e.g. 'fp8,bf16,fp16'). "
        "Needed for models whose cheapest OpenRouter hosts serve degraded FP4 "
        "(documented for GLM-5.2).",
    )
    parser.add_argument(
        "--reasoning-effort",
        default=None,
        choices=["low", "medium", "high"],
        help="Explicit reasoning effort override (production Pass 2 runs 'low').",
    )
    parser.add_argument(
        "--max-cost-usd",
        type=float,
        default=1.0,
        help="Reserve maximum call charges before dispatch (default: 1.00).",
    )
    parser.add_argument(
        "--max-price-prompt",
        type=float,
        default=None,
        help="Required $/M input-token ceiling for an unlisted model.",
    )
    parser.add_argument(
        "--max-price-completion",
        type=float,
        default=None,
        help="Required $/M output-token ceiling for an unlisted model.",
    )
    args = parser.parse_args()
    if args.max_cost_usd <= 0:
        parser.error("--max-cost-usd must be positive")

    if not os.environ.get("OPENROUTER_API_KEY"):
        print("ERROR: OPENROUTER_API_KEY not set in environment", file=sys.stderr)
        sys.exit(1)
    model_path_str = args.model
    model_name = args.model.replace("/", "_").replace(":", "_")

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load the model's recommended preset and apply any CLI overrides
    family = detect_model_family(model_path_str)
    preset = get_preset_for_model(
        model_path_str, thinking=args.thinking, reasoning_task=True
    )

    resolved_params = {
        "temperature": args.temperature
        if args.temperature is not None
        else preset["temperature"],
        "top_p": args.top_p if args.top_p is not None else preset["top_p"],
        "top_k": args.top_k if args.top_k is not None else preset["top_k"],
        "min_p": args.min_p if args.min_p is not None else preset["min_p"],
        "presence_penalty": args.presence_penalty
        if args.presence_penalty is not None
        else preset["presence_penalty"],
        "repeat_penalty": args.repeat_penalty
        if args.repeat_penalty is not None
        else preset["repeat_penalty"],
    }

    print(f"Model:      {model_name}")
    print(f"Family:     {family}")
    print(f"Pass:       {args.pass_num}")
    print(f"Limit:      {args.limit}")
    print(f"Thinking:   {'ON' if args.thinking else 'OFF'}")
    print(
        f"Sampling:   temp={resolved_params['temperature']}  top_p={resolved_params['top_p']}  top_k={resolved_params['top_k']}  min_p={resolved_params['min_p']}  pres_pen={resolved_params['presence_penalty']}  rep_pen={resolved_params['repeat_penalty']}"
    )
    print(f"Output dir: {output_dir}")
    print()

    # ------------------------------------------------------------------
    # Build harness config
    # ------------------------------------------------------------------
    # Archive every LLM call so results survive process death.
    # Label includes model + mode so archives don't collide across runs.
    mode_tag_for_archive = "thinking" if args.thinking else "nothink"
    archive_label = f"eval_{model_name}_{mode_tag_for_archive}_pass{args.pass_num}"

    # Default output budget: 4096 for Pass 2, 2048 for Pass 3.
    # Reasoning models (Mercury, GPT-OSS) may need 8192+ because reasoning
    # tokens count against the output budget before the JSON answer.
    if args.max_tokens is not None:
        max_tokens = args.max_tokens
    elif args.pass_num == 2:
        max_tokens = 4096
    else:
        max_tokens = 2048

    quantizations = (
        tuple(q.strip() for q in args.quantizations.split(",") if q.strip())
        if args.quantizations
        else None
    )
    known_prices = EVAL_MODEL_PRICE_CEILINGS.get(model_path_str, (None, None))
    price_prompt = args.max_price_prompt or known_prices[0]
    price_completion = args.max_price_completion or known_prices[1]
    if price_prompt is None or price_completion is None:
        parser.error(
            "Unknown model pricing: provide --max-price-prompt and "
            "--max-price-completion so the run can reserve a hard ceiling"
        )
    config = build_production_eval_config(
        model_path_str,
        args.pass_num,
        archive_label=archive_label,
        max_tokens=max_tokens,
        thinking=args.thinking,
        reasoning_effort=args.reasoning_effort,
        provider_quantizations=quantizations,
    )
    config = dataclasses.replace(
        config,
        model_family=family,
        max_price_prompt=price_prompt,
        max_price_completion=price_completion,
        **resolved_params,
    )
    ledger = EvalCostLedger(max_cost_usd=args.max_cost_usd)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_model_name = model_name.replace(" ", "_")
    mode_parts = []
    if args.pass_num == 2:
        mode_parts.append("batched")
    mode_parts.append("thinking" if args.thinking else "nothink")
    mode_tag = "_".join(mode_parts)
    output_file = output_dir / (
        f"eval_{safe_model_name}_{mode_tag}_pass{args.pass_num}_{timestamp}.json"
    )
    results = []
    budget_stop = None

    def checkpoint_results() -> None:
        payload = {
            "meta": {
                "model_name": model_name,
                "model_path": model_path_str,
                "model_family": family,
                "pass_num": args.pass_num,
                "limit": args.limit,
                "thinking": args.thinking,
                "mode_tag": mode_tag,
                "sampling": resolved_params,
                "evaluated_at": timestamp,
                "parcels_evaluated": len(results),
                "budget": ledger.summary(),
                "budget_stop": budget_stop,
            },
            "results": results,
        }
        temporary = output_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2, default=str))
        temporary.replace(output_file)

    checkpoint_results()

    # ------------------------------------------------------------------
    # Connect to DB and load test parcels
    # ------------------------------------------------------------------
    print("Connecting to database...")
    try:
        conn = get_connection()
    except Exception as exc:
        print(f"ERROR: Could not connect to database: {exc}", file=sys.stderr)
        sys.exit(1)

    with conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            if args.pidns_file:
                pidns = [
                    line.strip()
                    for line in Path(args.pidns_file).read_text().splitlines()
                    if line.strip() and not line.startswith("#")
                ]
                print(f"Loading {len(pidns)} fixed parcels from {args.pidns_file}...")
                all_parcels = []
                for pidn in pidns:
                    cursor.execute(SIGNALS_FOR_PIDN_SQL, {"pidn": pidn})
                    rows = cursor.fetchall()
                    if rows:
                        top = dict(rows[0])
                        all_parcels.append(
                            {
                                "pidn": pidn,
                                "top_signal": top.get("signal_key", ""),
                                "category": "fixed",
                                "signal_count": len(rows),
                            }
                        )
            else:
                print("Loading test parcels from dataset...")
                try:
                    cursor.execute(DATASET_SQL)
                    all_parcels = [dict(row) for row in cursor.fetchall()]
                except Exception as exc:
                    print(
                        f"ERROR: Dataset query failed: {exc}\n"
                        "Hint: public.development_signals may not exist yet. "
                        "Run the signal detection pipeline first.",
                        file=sys.stderr,
                    )
                    sys.exit(1)

            if not all_parcels:
                print(
                    "WARNING: No parcels found in public.development_signals. "
                    "The pipeline may not have run yet.",
                    file=sys.stderr,
                )
                sys.exit(0)

            test_parcels = all_parcels[: args.limit]
            print(
                f"Found {len(all_parcels)} parcels in dataset; evaluating {len(test_parcels)}."
            )
            print()

            # ------------------------------------------------------------------
            # Run evaluation
            # ------------------------------------------------------------------
            for i, row in enumerate(test_parcels, 1):
                pidn = row["pidn"]
                top_signal = row.get("top_signal", "")
                category = row.get("category", "")
                signal_count = row.get("signal_count", 0)

                print(
                    f"[{i:3d}/{len(test_parcels)}] pidn={pidn}  "
                    f"category={category}  signals={signal_count}  "
                    f"top={top_signal}",
                    end="  ",
                    flush=True,
                )

                try:
                    if args.pass_num == 2:
                        outcome = run_pass2_batched(cursor, config, pidn, ledger)
                    else:
                        outcome = run_pass3(cursor, config, pidn, ledger)
                except (EvalCostLimitExceeded, EvalCostUnavailable) as exc:
                    budget_stop = str(exc)
                    print(f"-> STOPPED ({budget_stop})")
                    checkpoint_results()
                    break

                status_str = (
                    "OK"
                    if outcome["success"]
                    else f"FAIL ({outcome.get('error', '')[:60]})"
                )
                print(f"-> {status_str}  [{outcome['elapsed_seconds']:.1f}s]")

                results.append(
                    {
                        "pidn": pidn,
                        "category": category,
                        "signal_count": signal_count,
                        "top_signal": top_signal,
                        "model_name": model_name,
                        "pass_num": args.pass_num,
                        "success": outcome["success"],
                        "elapsed_seconds": outcome["elapsed_seconds"],
                        "raw_output": outcome["raw_output"],
                        "parsed_output": outcome["parsed_output"],
                        "error": outcome["error"],
                        "usage": outcome.get("usage"),
                        "retry_usage": outcome.get("retry_usage"),
                    }
                )
                checkpoint_results()

    conn.close()

    checkpoint_results()

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    total = len(results)
    succeeded = sum(1 for r in results if r["success"])
    failed = total - succeeded
    avg_time = sum(r["elapsed_seconds"] for r in results) / total if total else 0.0

    json_valid = sum(
        1 for r in results if r["success"] and isinstance(r.get("parsed_output"), dict)
    )

    print()
    print("=" * 60)
    print(f"SUMMARY — {model_name}  Pass {args.pass_num}")
    print("=" * 60)
    print(f"  Total evaluated : {total}")
    print(
        f"  Succeeded       : {succeeded}  ({succeeded / total * 100:.1f}% success rate)"
        if total
        else "  Succeeded       : 0"
    )
    print(f"  Failed          : {failed}")
    print(
        f"  JSON valid      : {json_valid}  ({json_valid / total * 100:.1f}%)"
        if total
        else "  JSON valid      : 0"
    )
    print(f"  Avg time/parcel : {avg_time:.1f}s")
    print(f"  Results written : {output_file}")
    print()

    if failed > 0:
        print("Failures:")
        for r in results:
            if not r["success"]:
                print(f"  pidn={r['pidn']}  error={r.get('error', '')[:80]}")
        print()


if __name__ == "__main__":
    main()
