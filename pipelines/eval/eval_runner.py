#!/usr/bin/env python3
"""Model evaluation runner for CountyIQ intelligence passes.

Runs Pass 2 (signal validation) or Pass 3 (brief generation) against a
sample of test parcels using a specified GGUF model and stores the results
as JSON for later comparison with eval_report.py.

Usage:
    python eval_runner.py --model /path/to/model.gguf --pass 2 --limit 10
    python eval_runner.py --model /path/to/model.gguf --pass 3 --limit 10
    python eval_runner.py --model /path/to/model.gguf --pass 2 --limit 50 --output /tmp/eval_results
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup: add pipelines/ to sys.path so countyiq.* imports resolve when
# the script is run directly (e.g., python eval/eval_runner.py).
# ---------------------------------------------------------------------------
_PIPELINES_DIR = Path(__file__).resolve().parent.parent
if str(_PIPELINES_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINES_DIR))

import psycopg2
import psycopg2.extras

from countyiq.lib.llm_harness import HarnessConfig, invoke_with_retry
from countyiq.lib.pass2_signal_validation import (
    build_signal_validation_prompt,
    gather_signal_context,
    parse_signal_validation_output,
)
from countyiq.lib.pass3_brief_generation import (
    build_brief_generation_prompt,
    gather_brief_context,
    parse_brief_output,
)


# ---------------------------------------------------------------------------
# Dataset SQL — mirrors eval_dataset.sql combined query
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
    WHERE ds.signal_key IN ('conservation_easement', 'ag_security')
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
SELECT * FROM high_signal
UNION ALL
SELECT * FROM tax_distress
UNION ALL
SELECT * FROM exclusion
UNION ALL
SELECT * FROM assemblage
ORDER BY category, pidn
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
# Pass 2 evaluation
# ---------------------------------------------------------------------------

def run_pass2(cursor, config: HarnessConfig, pidn: str, top_signal: str) -> dict:
    """Run Pass 2 (signal validation) for the top signal on a parcel.

    Returns a result dict with: success, elapsed_seconds, raw_output,
    parsed_output, error.
    """
    # Fetch the top signal row
    cursor.execute(SIGNALS_FOR_PIDN_SQL, {"pidn": pidn})
    signal_rows = cursor.fetchall()

    if not signal_rows:
        return {
            "success": False,
            "elapsed_seconds": 0.0,
            "raw_output": "",
            "parsed_output": None,
            "error": f"No signals found in database for pidn={pidn}",
        }

    # Use the highest-weight signal that matches top_signal, or fallback to first
    target_row = None
    for row in signal_rows:
        r = dict(row)
        if r.get("signal_key") == top_signal:
            target_row = r
            break
    if target_row is None:
        target_row = dict(signal_rows[0])

    # Build evidence dict — stored as JSONB, psycopg2 returns it as dict already
    evidence = target_row.get("evidence") or {}
    if isinstance(evidence, str):
        try:
            evidence = json.loads(evidence)
        except (json.JSONDecodeError, TypeError):
            evidence = {}

    signal = {
        "signal_key": target_row["signal_key"],
        "signal_weight": target_row.get("signal_weight", 0),
        "source_table": target_row.get("source_table", ""),
        "source_id": target_row.get("source_id"),
        "distance_m": target_row.get("distance_m"),
        "evidence": evidence,
    }

    t0 = time.perf_counter()
    try:
        context = gather_signal_context(cursor, pidn, signal)
        prompt = build_signal_validation_prompt(context)
        result = invoke_with_retry(config, prompt)
        elapsed = time.perf_counter() - t0

        if result.success:
            parsed = parse_signal_validation_output(result.parsed)
            success = "error" not in parsed
            return {
                "success": success,
                "elapsed_seconds": round(elapsed, 2),
                "raw_output": result.raw_output[:2000],  # truncate for storage
                "parsed_output": parsed,
                "error": parsed.get("error") if not success else None,
            }
        else:
            return {
                "success": False,
                "elapsed_seconds": round(elapsed, 2),
                "raw_output": result.raw_output[:2000],
                "parsed_output": None,
                "error": result.error,
            }
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

def run_pass3(cursor, config: HarnessConfig, pidn: str) -> dict:
    """Run Pass 3 (brief generation) for a parcel.

    Returns a result dict with: success, elapsed_seconds, raw_output,
    parsed_output, error.
    """
    t0 = time.perf_counter()
    try:
        context = gather_brief_context(cursor, pidn)
        prompt = build_brief_generation_prompt(context)
        result = invoke_with_retry(config, prompt)
        elapsed = time.perf_counter() - t0

        if result.success:
            parsed = parse_brief_output(result.parsed)
            success = "error" not in parsed
            return {
                "success": success,
                "elapsed_seconds": round(elapsed, 2),
                "raw_output": result.raw_output[:2000],
                "parsed_output": parsed,
                "error": parsed.get("error") if not success else None,
            }
        else:
            return {
                "success": False,
                "elapsed_seconds": round(elapsed, 2),
                "raw_output": result.raw_output[:2000],
                "parsed_output": None,
                "error": result.error,
            }
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
        description="CountyIQ model evaluation runner — tests Pass 2 or Pass 3 LLM quality.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python eval_runner.py --model /models/mistral-7b.gguf --pass 2 --limit 10
  python eval_runner.py --model /models/mistral-7b.gguf --pass 3 --limit 20
  python eval_runner.py --model /models/qwen-7b.gguf --pass 2 --limit 50 --output /tmp/eval
        """,
    )
    parser.add_argument(
        "--model",
        required=True,
        help="Path to the GGUF model file to evaluate.",
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
        "--n-ctx",
        type=int,
        default=4096,
        help="Context window size for the model (default: 4096).",
    )
    parser.add_argument(
        "--n-gpu-layers",
        type=int,
        default=-1,
        help="GPU layers to offload: -1=all, 0=CPU-only (default: -1).",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.1,
        help="Sampling temperature (default: 0.1).",
    )
    args = parser.parse_args()

    model_path = Path(args.model)
    if not model_path.exists():
        print(f"ERROR: Model file not found: {model_path}", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    model_name = model_path.stem  # e.g., "mistral-7b-instruct-v0.2.Q4_K_M"

    print(f"Model:      {model_name}")
    print(f"Pass:       {args.pass_num}")
    print(f"Limit:      {args.limit}")
    print(f"Output dir: {output_dir}")
    print()

    # ------------------------------------------------------------------
    # Load model
    # ------------------------------------------------------------------
    config = HarnessConfig(
        model_path=str(model_path),
        n_ctx=args.n_ctx,
        n_gpu_layers=args.n_gpu_layers,
        temperature=args.temperature,
        max_tokens=2048,
    )

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
            print(f"Found {len(all_parcels)} parcels in dataset; evaluating {len(test_parcels)}.")
            print()

            # ------------------------------------------------------------------
            # Run evaluation
            # ------------------------------------------------------------------
            results = []
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

                if args.pass_num == 2:
                    outcome = run_pass2(cursor, config, pidn, top_signal)
                else:
                    outcome = run_pass3(cursor, config, pidn)

                status_str = "OK" if outcome["success"] else f"FAIL ({outcome.get('error', '')[:60]})"
                print(f"-> {status_str}  [{outcome['elapsed_seconds']:.1f}s]")

                results.append({
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
                })

    conn.close()

    # ------------------------------------------------------------------
    # Write results
    # ------------------------------------------------------------------
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_model_name = model_name.replace(" ", "_")
    output_file = output_dir / f"eval_{safe_model_name}_pass{args.pass_num}_{timestamp}.json"

    with open(output_file, "w") as f:
        json.dump(
            {
                "meta": {
                    "model_name": model_name,
                    "model_path": str(model_path),
                    "pass_num": args.pass_num,
                    "limit": args.limit,
                    "n_ctx": args.n_ctx,
                    "n_gpu_layers": args.n_gpu_layers,
                    "temperature": args.temperature,
                    "evaluated_at": timestamp,
                    "parcels_evaluated": len(results),
                },
                "results": results,
            },
            f,
            indent=2,
            default=str,
        )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    total = len(results)
    succeeded = sum(1 for r in results if r["success"])
    failed = total - succeeded
    avg_time = (
        sum(r["elapsed_seconds"] for r in results) / total if total else 0.0
    )

    json_valid = sum(
        1 for r in results
        if r["success"] and isinstance(r.get("parsed_output"), dict)
    )

    print()
    print("=" * 60)
    print(f"SUMMARY — {model_name}  Pass {args.pass_num}")
    print("=" * 60)
    print(f"  Total evaluated : {total}")
    print(f"  Succeeded       : {succeeded}  ({succeeded / total * 100:.1f}% success rate)" if total else "  Succeeded       : 0")
    print(f"  Failed          : {failed}")
    print(f"  JSON valid      : {json_valid}  ({json_valid / total * 100:.1f}%)" if total else "  JSON valid      : 0")
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
