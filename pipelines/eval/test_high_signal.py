#!/usr/bin/env python3
"""Targeted test: run batched Pass 2 validation on high-signal parcels.

Picks the N parcels with the most development signals in the database
and runs them through the batched validator with Grok 4.1 Fast + thinking.
Reports per-parcel outcomes including whether the retry path kicked in
for any dropped signals.

Usage:
    OPENROUTER_API_KEY=$(cat ~/.config/openrouter/key) \
      python3 eval/test_high_signal.py [--limit 10]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2
import psycopg2.extras

from countyiq.lib.llm_harness import HarnessConfig, get_preset_for_model
from countyiq.lib.pass2_batched_validation import (
    gather_parcel_batch_context,
    build_batched_signal_prompt,
    parse_batched_signal_output,
)


HIGH_SIGNAL_QUERY = """
    SELECT pidn, COUNT(*) AS n_signals
    FROM public.development_signals
    GROUP BY pidn
    HAVING COUNT(*) >= %(min_signals)s
    ORDER BY COUNT(*) DESC, RANDOM()
    LIMIT %(limit)s
"""


def run_parcel(cursor, config: HarnessConfig, pidn: str) -> dict:
    """Run batched validation for one parcel with retry path."""
    from countyiq.lib.llm_harness import invoke_with_retry

    t0 = time.perf_counter()
    ctx = gather_parcel_batch_context(cursor, pidn)
    n_signals = len(ctx["signals"])

    # First attempt — all signals
    prompt = build_batched_signal_prompt(ctx)
    prompt_len = len(prompt)
    result = invoke_with_retry(config, prompt, archive_key=f"test:{pidn}")
    elapsed_first = time.perf_counter() - t0

    if not result.success:
        return {
            "pidn": pidn,
            "n_signals": n_signals,
            "prompt_chars": prompt_len,
            "elapsed_first": round(elapsed_first, 2),
            "success": False,
            "error": result.error,
        }

    parsed = parse_batched_signal_output(result.parsed or {}, ctx["signals"])
    all_validations = list(parsed.get("validations", []))

    # Retry path
    retry_keys = set(parsed.get("missing", [])) | set(parsed.get("errors", []))
    retry_recovered = 0
    retry_elapsed = 0.0
    if retry_keys:
        retry_signals = [s for s in ctx["signals"] if s["signal_key"] in retry_keys]
        t_retry = time.perf_counter()
        retry_prompt = build_batched_signal_prompt(ctx, signals_override=retry_signals)
        retry_result = invoke_with_retry(config, retry_prompt, archive_key=f"test:{pidn}:retry")
        retry_elapsed = time.perf_counter() - t_retry

        if retry_result.success:
            retry_parsed = parse_batched_signal_output(
                retry_result.parsed or {}, retry_signals
            )
            retry_vals = retry_parsed.get("validations", [])
            all_validations.extend(retry_vals)
            retry_recovered = len(retry_vals)

    total_elapsed = time.perf_counter() - t0

    return {
        "pidn": pidn,
        "n_signals": n_signals,
        "prompt_chars": prompt_len,
        "prompt_tokens_est": prompt_len // 4,  # rough: ~4 chars/token
        "elapsed_total": round(total_elapsed, 2),
        "elapsed_first": round(elapsed_first, 2),
        "elapsed_retry": round(retry_elapsed, 2),
        "success": True,
        "n_validations": len(all_validations),
        "n_missing_initial": len(parsed.get("missing", [])),
        "retry_triggered": bool(retry_keys),
        "retry_recovered": retry_recovered,
        "final_unrecovered": n_signals - len(all_validations),
        "cross_signal_insight": parsed.get("cross_signal_insight", "")[:200],
        "validations": [
            {
                "signal_key": v["signal_key"],
                "status": v["validation_status"],
                "sig": v["adjusted_significance"],
            }
            for v in all_validations
        ],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--min-signals", type=int, default=6)
    ap.add_argument("--model", default="x-ai/grok-4.1-fast")
    ap.add_argument("--thinking", action="store_true", default=True)
    args = ap.parse_args()

    if not os.environ.get("OPENROUTER_API_KEY"):
        print("ERROR: OPENROUTER_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    conn = psycopg2.connect(
        host=os.environ.get("DATABASE_HOST", "localhost"),
        port=int(os.environ.get("DATABASE_PORT", 5433)),
        dbname=os.environ.get("DATABASE_NAME", "countyiq"),
        user=os.environ.get("DATABASE_USER", "dagster_admin"),
        password=os.environ.get("DATABASE_PASSWORD", "localtest"),
    )

    preset = get_preset_for_model(args.model, thinking=args.thinking, reasoning_task=True)
    config = HarnessConfig(
        model_path=args.model,
        backend="openrouter",
        thinking=args.thinking,
        max_tokens=4096,
        archive_label="test_high_signal",
        **preset,
    )

    print(f"Model: {args.model}  Thinking: {args.thinking}")
    print(f"Targeting parcels with >={args.min_signals} signals, limit={args.limit}")
    print()

    with conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                HIGH_SIGNAL_QUERY,
                {"min_signals": args.min_signals, "limit": args.limit},
            )
            targets = [dict(r) for r in cur.fetchall()]

            if not targets:
                print(f"No parcels with >={args.min_signals} signals found.")
                return

            results = []
            for i, target in enumerate(targets, 1):
                pidn = target["pidn"]
                expected = target["n_signals"]
                print(
                    f"[{i}/{len(targets)}] {pidn} ({expected} signals)... ",
                    end="",
                    flush=True,
                )
                r = run_parcel(cur, config, pidn)
                results.append(r)
                if r["success"]:
                    marker = ""
                    if r.get("retry_triggered"):
                        marker += f" RETRY({r['retry_recovered']}/{r['n_missing_initial']} recovered)"
                    if r.get("final_unrecovered", 0) > 0:
                        marker += f" UNRECOVERED({r['final_unrecovered']})"
                    print(
                        f"OK  {r['elapsed_total']:.1f}s  "
                        f"prompt~{r['prompt_tokens_est']}tok  "
                        f"{r['n_validations']}/{r['n_signals']} validated{marker}"
                    )
                else:
                    print(f"FAIL  {r.get('error', '')[:80]}")

    # Save results
    out = Path(__file__).resolve().parent / "results" / "test_high_signal.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(
            {
                "meta": {
                    "model": args.model,
                    "thinking": args.thinking,
                    "min_signals": args.min_signals,
                    "limit": args.limit,
                },
                "results": results,
            },
            f,
            indent=2,
            default=str,
        )

    # Summary
    print()
    print("=" * 70)
    succ = [r for r in results if r["success"]]
    retry_triggered = [r for r in succ if r.get("retry_triggered")]
    any_unrecovered = [r for r in succ if r.get("final_unrecovered", 0) > 0]
    avg_prompt_tokens = sum(r["prompt_tokens_est"] for r in succ) / max(len(succ), 1)
    avg_elapsed = sum(r["elapsed_total"] for r in succ) / max(len(succ), 1)

    print(f"Parcels tested            : {len(results)}")
    print(f"Succeeded                 : {len(succ)}")
    print(f"Avg prompt tokens         : ~{int(avg_prompt_tokens):,}")
    print(f"Avg elapsed               : {avg_elapsed:.1f}s")
    print(f"Retry path triggered      : {len(retry_triggered)}")
    print(f"Parcels unrecovered after retry : {len(any_unrecovered)}")
    print(f"Results written           : {out}")


if __name__ == "__main__":
    main()
