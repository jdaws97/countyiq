#!/usr/bin/env python3
"""Test spatial cluster validation — run Grok 4.1 Fast on real clusters.

Finds the top N densest spatial clusters in the database and validates
all parcels in each cluster in a single LLM call.

Usage:
    OPENROUTER_API_KEY=$(cat ~/.config/openrouter/key) \
      python3 eval/test_spatial_clusters.py [--limit 5] [--model x-ai/grok-4.1-fast]
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

from countyiq.lib.llm_harness import HarnessConfig, get_preset_for_model, invoke_with_retry
from countyiq.lib.pass2_spatial_validation import (
    CLUSTER_PARCELS_QUERY,
    gather_cluster_context,
    build_spatial_validation_prompt,
    parse_spatial_validation_output,
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=5, help="Number of clusters to test")
    ap.add_argument("--model", default="x-ai/grok-4.1-fast")
    ap.add_argument("--thinking", action="store_true", default=True)
    ap.add_argument("--max-tokens", type=int, default=16384)
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

    preset = get_preset_for_model(args.model, thinking=args.thinking)
    config = HarnessConfig(
        model_path=args.model,
        backend="openrouter",
        thinking=args.thinking,
        max_tokens=args.max_tokens,
        archive_label="test_spatial",
        **preset,
    )

    print(f"Model: {args.model}  Thinking: {args.thinking}  Max tokens: {args.max_tokens}")
    print()

    with conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Find clusters
            print("Finding spatial clusters...")
            cur.execute(CLUSTER_PARCELS_QUERY)
            clusters = [dict(r) for r in cur.fetchall()]
            print(f"Found {len(clusters)} clusters total")

            # Pick top N by size
            test_clusters = clusters[:args.limit]
            print(f"Testing top {len(test_clusters)} clusters")
            print()

            results = []
            for i, cluster in enumerate(test_clusters, 1):
                cid = cluster["cluster_id"]
                pidns = cluster["pidns"]
                size = cluster["cluster_size"]

                print(f"[{i}/{len(test_clusters)}] Cluster {cid}: {size} parcels... ", end="", flush=True)

                t0 = time.perf_counter()
                try:
                    ctx = gather_cluster_context(cur, pidns)
                    prompt = build_spatial_validation_prompt(ctx)
                    prompt_tokens = len(prompt) // 4

                    result = invoke_with_retry(config, prompt, archive_key=f"cluster:{cid}", retries=1)
                    elapsed = time.perf_counter() - t0

                    if not result.success:
                        print(f"FAIL ({result.error[:80]})  [{elapsed:.1f}s]")
                        results.append({
                            "cluster_id": cid, "size": size, "success": False,
                            "error": result.error, "elapsed": round(elapsed, 2),
                        })
                        continue

                    parsed = parse_spatial_validation_output(result.parsed or {}, pidns)

                    n_validated = sum(len(v) for v in parsed["parcel_validations"].values())
                    n_insights = len(parsed.get("cluster_insights", []))
                    n_patterns = len(parsed.get("entity_patterns", []))
                    n_missing = len(parsed.get("missing_pidns", []))

                    missing_str = f"  MISSING:{n_missing}" if n_missing else ""
                    print(
                        f"OK  {elapsed:.1f}s  "
                        f"prompt~{prompt_tokens}tok  "
                        f"{len(parsed['parcel_validations'])}/{size} parcels  "
                        f"{n_validated} signals  "
                        f"{n_insights} insights  "
                        f"{n_patterns} entity patterns"
                        f"{missing_str}"
                    )

                    results.append({
                        "cluster_id": cid,
                        "size": size,
                        "municipality": ctx.get("municipality", "?"),
                        "success": True,
                        "elapsed": round(elapsed, 2),
                        "prompt_tokens_est": prompt_tokens,
                        "parcels_returned": len(parsed["parcel_validations"]),
                        "signals_validated": n_validated,
                        "cluster_insights": parsed.get("cluster_insights", []),
                        "entity_patterns": parsed.get("entity_patterns", []),
                        "missing_pidns": parsed.get("missing_pidns", []),
                        "parcel_validations": parsed["parcel_validations"],
                    })

                except Exception as exc:
                    elapsed = time.perf_counter() - t0
                    print(f"ERROR ({exc})  [{elapsed:.1f}s]")
                    results.append({
                        "cluster_id": cid, "size": size, "success": False,
                        "error": str(exc), "elapsed": round(elapsed, 2),
                    })

    # Summary
    print()
    print("=" * 70)
    succ = [r for r in results if r.get("success")]
    total_parcels = sum(r["size"] for r in results)
    total_validated = sum(r.get("parcels_returned", 0) for r in succ)
    total_signals = sum(r.get("signals_validated", 0) for r in succ)
    total_insights = sum(len(r.get("cluster_insights", [])) for r in succ)
    total_patterns = sum(len(r.get("entity_patterns", [])) for r in succ)
    avg_elapsed = sum(r["elapsed"] for r in succ) / max(len(succ), 1)

    print(f"Clusters tested           : {len(results)}")
    print(f"Succeeded                 : {len(succ)}")
    print(f"Total parcels in clusters : {total_parcels}")
    print(f"Parcels validated         : {total_validated}")
    print(f"Signals validated         : {total_signals}")
    print(f"Cluster insights          : {total_insights}")
    print(f"Entity patterns found     : {total_patterns}")
    print(f"Avg elapsed per cluster   : {avg_elapsed:.1f}s")

    if succ:
        # Estimated cost
        total_in = sum(r.get("prompt_tokens_est", 0) for r in succ)
        total_out = total_signals * 30 + total_insights * 50  # rough estimate
        in_cost = total_in / 1e6 * 0.20  # Grok pricing
        out_cost = total_out / 1e6 * 0.50
        print(f"\nCost estimate (this run)   : ${in_cost + out_cost:.4f}")

        # Project to full county
        full_clusters = len(clusters)
        avg_size = sum(c["cluster_size"] for c in clusters) / max(len(clusters), 1)
        scale = full_clusters / max(len(succ), 1)
        print(f"\nProjected full county ({full_clusters} clusters, avg {avg_size:.0f} parcels each):")
        print(f"  Total cost    : ~${(in_cost + out_cost) * scale:.2f}")
        print(f"  Wall time     : ~{full_clusters * avg_elapsed / 3600:.1f}h serial | ~{full_clusters * avg_elapsed / 3600 / 10:.1f}h @ 10x parallel")

    # Print cluster insights
    print()
    print("=" * 70)
    print("CLUSTER INSIGHTS & ENTITY PATTERNS")
    print("=" * 70)
    for r in succ:
        print(f"\nCluster {r['cluster_id']} ({r['size']} parcels, {r.get('municipality', '?')})")
        for insight in r.get("cluster_insights", []):
            print(f"  INSIGHT: {insight[:300]}")
        for pat in r.get("entity_patterns", []):
            print(f"  ENTITY: {pat.get('entity', '?')} @ {pat.get('pidns', [])} — {pat.get('pattern', '')[:200]}")

    # Save results
    out = Path(__file__).resolve().parent / "results" / "test_spatial_clusters.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump({"meta": {"model": args.model, "thinking": args.thinking}, "results": results}, f, indent=2, default=str)
    print(f"\nResults written: {out}")


if __name__ == "__main__":
    main()
