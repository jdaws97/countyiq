#!/usr/bin/env python3
"""Model evaluation report generator for CountyIQ.

Reads all eval_*.json files from a results directory (produced by
eval_runner.py) and prints a comparison table across models and passes.

Usage:
    python eval_report.py                          # uses pipelines/eval/results/
    python eval_report.py pipelines/eval/results/
    python eval_report.py /tmp/my_eval_results/
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_results(results_dir: Path) -> list[dict]:
    """Load all eval_*.json files from a directory."""
    files = sorted(results_dir.glob("eval_*.json"))
    if not files:
        return []

    all_files = []
    for fpath in files:
        try:
            with open(fpath) as f:
                data = json.load(f)
            data["_source_file"] = fpath.name
            all_files.append(data)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"WARNING: Could not load {fpath.name}: {exc}", file=sys.stderr)
    return all_files


def compute_stats(eval_data: dict) -> dict:
    """Compute summary statistics for a single eval file."""
    meta = eval_data.get("meta", {})
    results = eval_data.get("results", [])
    total = len(results)

    if total == 0:
        return {
            "model_name": meta.get("model_name", "unknown"),
            "pass_num": meta.get("pass_num", "?"),
            "evaluated_at": meta.get("evaluated_at", ""),
            "n_ctx": meta.get("n_ctx", "?"),
            "temperature": meta.get("temperature", "?"),
            "total": 0,
            "success_count": 0,
            "success_rate": 0.0,
            "json_valid_count": 0,
            "json_valid_rate": 0.0,
            "avg_time": 0.0,
            "p50_time": 0.0,
            "p90_time": 0.0,
            "source_file": eval_data.get("_source_file", ""),
        }

    succeeded = [r for r in results if r.get("success")]
    success_count = len(succeeded)
    success_rate = success_count / total * 100

    json_valid_count = sum(
        1 for r in results
        if r.get("success") and isinstance(r.get("parsed_output"), dict)
    )
    json_valid_rate = json_valid_count / total * 100

    times = sorted(r.get("elapsed_seconds", 0.0) for r in results)
    avg_time = sum(times) / total
    p50_time = times[int(total * 0.50)] if times else 0.0
    p90_time = times[int(total * 0.90)] if times else 0.0

    # Per-category breakdown
    categories: dict[str, dict] = {}
    for r in results:
        cat = r.get("category", "unknown")
        if cat not in categories:
            categories[cat] = {"total": 0, "success": 0}
        categories[cat]["total"] += 1
        if r.get("success"):
            categories[cat]["success"] += 1

    return {
        "model_name": meta.get("model_name", "unknown"),
        "pass_num": meta.get("pass_num", "?"),
        "evaluated_at": meta.get("evaluated_at", ""),
        "n_ctx": meta.get("n_ctx", "?"),
        "temperature": meta.get("temperature", "?"),
        "total": total,
        "success_count": success_count,
        "success_rate": success_rate,
        "json_valid_count": json_valid_count,
        "json_valid_rate": json_valid_rate,
        "avg_time": avg_time,
        "p50_time": p50_time,
        "p90_time": p90_time,
        "categories": categories,
        "source_file": eval_data.get("_source_file", ""),
    }


def _bar(rate: float, width: int = 10) -> str:
    """Render a simple ASCII progress bar for a rate 0-100."""
    filled = round(rate / 100 * width)
    return "[" + "#" * filled + "." * (width - filled) + "]"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="CountyIQ model evaluation report — compare results across models.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python eval_report.py
  python eval_report.py pipelines/eval/results/
  python eval_report.py /tmp/my_eval_results/ --pass 2
        """,
    )
    parser.add_argument(
        "results_dir",
        nargs="?",
        default=str(Path(__file__).resolve().parent / "results"),
        help="Directory containing eval_*.json files (default: pipelines/eval/results/).",
    )
    parser.add_argument(
        "--pass",
        dest="pass_filter",
        type=int,
        choices=[2, 3],
        default=None,
        help="Filter report to only Pass 2 or Pass 3 results.",
    )
    parser.add_argument(
        "--sort",
        choices=["success", "time", "model"],
        default="success",
        help="Sort order for the comparison table (default: success).",
    )
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    if not results_dir.is_dir():
        print(f"ERROR: Results directory not found: {results_dir}", file=sys.stderr)
        sys.exit(1)

    all_evals = load_results(results_dir)
    if not all_evals:
        print(
            f"No eval_*.json files found in {results_dir}.\n"
            "Run eval_runner.py first to generate results.",
            file=sys.stderr,
        )
        sys.exit(0)

    # Filter by pass if requested
    if args.pass_filter is not None:
        all_evals = [e for e in all_evals if e.get("meta", {}).get("pass_num") == args.pass_filter]
        if not all_evals:
            print(f"No results found for Pass {args.pass_filter}.", file=sys.stderr)
            sys.exit(0)

    # Compute stats for each eval file
    stats_list = [compute_stats(e) for e in all_evals]

    # Sort
    if args.sort == "success":
        stats_list.sort(key=lambda s: -s["success_rate"])
    elif args.sort == "time":
        stats_list.sort(key=lambda s: s["avg_time"])
    else:  # model
        stats_list.sort(key=lambda s: (s["model_name"], s["pass_num"]))

    # ------------------------------------------------------------------
    # Print report
    # ------------------------------------------------------------------
    print()
    print("=" * 80)
    print("CountyIQ Model Evaluation Report")
    print(f"Results directory: {results_dir}")
    print(f"Eval files loaded: {len(all_evals)}")
    if args.pass_filter:
        print(f"Filter: Pass {args.pass_filter} only")
    print("=" * 80)
    print()

    # Column widths
    COL_MODEL = 40
    COL_PASS = 5
    COL_N = 6
    COL_SUCCESS = 14
    COL_JSON = 14
    COL_AVG = 8
    COL_P50 = 8
    COL_P90 = 8

    header = (
        f"{'Model':<{COL_MODEL}} "
        f"{'Pass':>{COL_PASS}} "
        f"{'N':>{COL_N}} "
        f"{'Success %':<{COL_SUCCESS}} "
        f"{'JSON Valid %':<{COL_JSON}} "
        f"{'Avg(s)':>{COL_AVG}} "
        f"{'P50(s)':>{COL_P50}} "
        f"{'P90(s)':>{COL_P90}}"
    )
    print(header)
    print("-" * len(header))

    for s in stats_list:
        model_display = s["model_name"]
        if len(model_display) > COL_MODEL:
            model_display = model_display[: COL_MODEL - 3] + "..."

        success_bar = f"{s['success_rate']:5.1f}% {_bar(s['success_rate'])}"
        json_bar = f"{s['json_valid_rate']:5.1f}% {_bar(s['json_valid_rate'])}"

        print(
            f"{model_display:<{COL_MODEL}} "
            f"{s['pass_num']:>{COL_PASS}} "
            f"{s['total']:>{COL_N}} "
            f"{success_bar:<{COL_SUCCESS}} "
            f"{json_bar:<{COL_JSON}} "
            f"{s['avg_time']:>{COL_AVG}.1f} "
            f"{s['p50_time']:>{COL_P50}.1f} "
            f"{s['p90_time']:>{COL_P90}.1f}"
        )

    print()

    # ------------------------------------------------------------------
    # Per-category breakdown for each eval
    # ------------------------------------------------------------------
    if any(s.get("categories") for s in stats_list):
        print("Category Breakdown")
        print("-" * 60)
        for s in stats_list:
            cats = s.get("categories")
            if not cats:
                continue
            print(f"\n  {s['model_name']}  Pass {s['pass_num']}")
            for cat_name, cat_data in sorted(cats.items()):
                cat_total = cat_data["total"]
                cat_success = cat_data["success"]
                cat_rate = cat_success / cat_total * 100 if cat_total else 0.0
                print(
                    f"    {cat_name:<25} {cat_success:3d}/{cat_total:3d} "
                    f"({cat_rate:.0f}%)  {_bar(cat_rate, 8)}"
                )
        print()

    # ------------------------------------------------------------------
    # Source files
    # ------------------------------------------------------------------
    print("Source files:")
    for s in stats_list:
        print(f"  {s['source_file']}  (evaluated {s['evaluated_at']})")
    print()


if __name__ == "__main__":
    main()
