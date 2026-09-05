#!/usr/bin/env python3
"""Audit a deterministic, population-weighted sample of skipped Pass 1 clusters."""

from __future__ import annotations

import argparse
import itertools
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras

from countyiq.assets.enrichment.owners import normalize_name
from countyiq.lib.backfill_estimator import build_name_clusters
from countyiq.lib.intelligence_integrity import validate_entity_membership
from countyiq.lib.llm_harness import extract_json_object, strip_thinking
from countyiq.lib.pass1_entity_verification import (
    CANDIDATE_CLUSTERS_QUERY,
    build_entity_cluster_prompt,
    cluster_involves_organization,
    gather_cluster_records,
    parse_entity_verification_output,
    stable_cluster_key,
)
from eval.fixture_io import canonical_context_hash
from eval.protocol import EvalCostLedger, build_production_eval_config, invoke_tracked

RESULTS = Path(__file__).resolve().parent / "results"
QUOTAS = {
    "joint_pair": 12,
    "multi": 4,
    "low_pair": 2,
    "high_pair": 1,
    "mid_pair": 1,
}

# Human review of the deterministic sample selected on 2026-09-04. Names not
# grouped together here are distinct owner-of-record entities. The selection
# assertion below fails if source data or classifier changes move the sample.
REVIEWED_MERGES = {
    "entity_cluster:0015afb2c55a29411edb": [
        [
            "OSTASEWSKI STANLEY J SR & CHERYL L",
            "OSTASEWSKI STANLEY J SR-TR & CHERYL L-TR   ET AL",
        ]
    ],
    "entity_cluster:002ac0bd5363764616ab": [
        ["TOURAS JOHN G & LETITIA D", "TOURAS LETITIA D & JOHN G"]
    ],
    "entity_cluster:003c4787fd4c22f9aa2d": [
        ["MOLISON JEREMY & MELISSA", "MOLISON JEREMY L & MELISSA L"]
    ],
    "entity_cluster:005cd45f6623ec9f1ae3": [
        [
            "SHEPPARD PETER H & DANIEL D EHRHART III",
            "SHEPPARD PETER HARPER & DANIEL D III ET AL",
        ]
    ],
    "entity_cluster:0097121910e18902171b": [
        [
            "KEARNEY ALAN & MELISSA ELIZABETH",
            "KEARNEY ALAN M & MELISSA E AKA MELISSA E SHIREY",
            "KEARNEY ALAN MICHAEL & MELISSA E",
        ]
    ],
    "entity_cluster:00adf60b292f3136fee0": [
        ["WEAVER KEVIN", "WEAVER KEVIN L"]
    ],
    "entity_cluster:012282c0420bad97b9ab": [
        ["RENTZEL ERIC J", "RENTZEL ERIC J W"]
    ],
    "entity_cluster:00f3319383ff265c393e": [
        ["BENYOU TIMOTHY M", "BENYOU TIMOTHY W"]
    ],
}

REVIEWED_SAMPLE_KEYS = {
    "entity_cluster:000cc226767d5ea7de81",
    "entity_cluster:0015afb2c55a29411edb",
    "entity_cluster:00233f70c8e2c93b34b0",
    "entity_cluster:002ac0bd5363764616ab",
    "entity_cluster:003c4787fd4c22f9aa2d",
    "entity_cluster:0048c7f536ea5a17850b",
    "entity_cluster:005111a9a4f2c821829d",
    "entity_cluster:00534780f23aaef77c97",
    "entity_cluster:005cd45f6623ec9f1ae3",
    "entity_cluster:005dca857499bf0b96bb",
    "entity_cluster:007b422515a771705363",
    "entity_cluster:0085433c3aa003cce48b",
    "entity_cluster:005867368bc12365ad96",
    "entity_cluster:0097121910e18902171b",
    "entity_cluster:00997813346dabc9e71f",
    "entity_cluster:00adf60b292f3136fee0",
    "entity_cluster:005d952a17cce985c6a6",
    "entity_cluster:0112e63dea60591aab66",
    "entity_cluster:012282c0420bad97b9ab",
    "entity_cluster:00f3319383ff265c393e",
}


def _db():
    return psycopg2.connect(
        host=os.environ.get("DATABASE_HOST", "localhost"),
        port=int(os.environ.get("DATABASE_PORT", "5433")),
        dbname=os.environ.get("DATABASE_NAME", "countyiq"),
        user=os.environ.get("DATABASE_USER", "dagster_admin"),
        password=os.environ.get("DATABASE_PASSWORD", "localtest"),
    )


def _stratum(names: list[str], maximum_similarity: float) -> str:
    if len(names) >= 3:
        return "multi"
    if any("&" in name for name in names):
        return "joint_pair"
    if maximum_similarity >= 0.8:
        return "high_pair"
    if maximum_similarity >= 0.65:
        return "mid_pair"
    return "low_pair"


def _sample(conn) -> tuple[list[dict], Counter]:
    with conn.cursor() as cur:
        cur.execute(CANDIDATE_CLUSTERS_QUERY)
        pairs = cur.fetchall()
    clusters = build_name_clusters(pairs)
    name_to_cluster = {name: index for index, names in enumerate(clusters) for name in names}
    similarities = defaultdict(list)
    for name_a, name_b, _municipality, similarity in pairs:
        index = name_to_cluster.get(name_a)
        if index is not None and name_to_cluster.get(name_b) == index:
            similarities[index].append(float(similarity or 0))

    by_stratum = defaultdict(list)
    deterministic_count = 0
    person_count = 0
    for index, names in enumerate(clusters):
        if cluster_involves_organization(names):
            continue
        person_count += 1
        if len({normalize_name(name) for name in names}) == 1:
            deterministic_count += 1
            continue
        maximum = max(similarities[index] or [0])
        item = {
            "cluster_key": stable_cluster_key(names),
            "names": names,
            "stratum": _stratum(names, maximum),
            "similarity_min": min(similarities[index] or [0]),
            "similarity_max": maximum,
        }
        by_stratum[item["stratum"]].append(item)

    selected = []
    counts = Counter({key: len(items) for key, items in by_stratum.items()})
    for stratum, quota in QUOTAS.items():
        selected.extend(
            sorted(by_stratum[stratum], key=lambda item: item["cluster_key"])[:quota]
        )
    selected_keys = {item["cluster_key"] for item in selected}
    if selected_keys != REVIEWED_SAMPLE_KEYS:
        raise RuntimeError(
            "Representative sample changed; re-review labels before spending. "
            f"added={sorted(selected_keys - REVIEWED_SAMPLE_KEYS)} "
            f"removed={sorted(REVIEWED_SAMPLE_KEYS - selected_keys)}"
        )
    counts["person_only_total"] = person_count
    counts["deterministic_exact"] = deterministic_count
    counts["unresolved_person"] = person_count - deterministic_count
    return selected, counts


def _gold_partition(names: list[str], cluster_key: str) -> tuple[tuple[str, ...], ...]:
    remaining = set(names)
    groups = []
    for merged in REVIEWED_MERGES.get(cluster_key, []):
        group = tuple(sorted(merged))
        groups.append(group)
        remaining.difference_update(group)
    groups.extend((name,) for name in sorted(remaining))
    return tuple(sorted(groups))


def _output_partition(parsed: dict, names: list[str]) -> tuple[tuple[str, ...], ...]:
    candidate_set = set(names)
    assigned = set()
    groups = []
    for entity in parsed.get("entities", []) if isinstance(parsed, dict) else []:
        members = sorted(
            {
                name
                for name in (entity.get("member_names") or [])
                if name in candidate_set
            }
        )
        if members:
            groups.append(tuple(members))
            assigned.update(members)
    groups.extend((name,) for name in sorted(candidate_set - assigned))
    return tuple(sorted(groups))


def _pairs(partition):
    return {
        tuple(sorted(pair))
        for group in partition
        for pair in itertools.combinations(group, 2)
    }


def _parse_result(result):
    value = result.parsed
    if not isinstance(value, dict):
        try:
            value = json.loads(extract_json_object(strip_thinking(result.raw_output or "")))
        except Exception:
            value = {}
    return parse_entity_verification_output(value or {})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Dispatch the paid 20-case audit.")
    parser.add_argument("--model", default="openai/gpt-5.6-luna")
    parser.add_argument("--max-cost-usd", type=float, default=0.10)
    args = parser.parse_args()

    conn = _db()
    selected, counts = _sample(conn)
    print(
        json.dumps(
            {
                "sample_size": len(selected),
                "stratum_population": dict(counts),
                "sample_keys": [item["cluster_key"] for item in selected],
            },
            indent=2,
        )
    )
    if not args.run:
        conn.close()
        return

    if not os.environ.get("OPENROUTER_API_KEY"):
        key_file = Path("~/.config/openrouter/key").expanduser()
        if not key_file.exists():
            raise SystemExit("OPENROUTER_API_KEY not set")
        os.environ["OPENROUTER_API_KEY"] = key_file.read_text().strip()

    ledger = EvalCostLedger(max_cost_usd=args.max_cost_usd)
    config = build_production_eval_config(
        args.model,
        1,
        archive_label="person_cluster_audit",
        max_tokens=8192,
        reasoning_effort="high",
    )
    rows = []
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    for index, item in enumerate(selected, 1):
        records = gather_cluster_records(cursor, item["names"])
        prompt = build_entity_cluster_prompt(records)
        result = invoke_tracked(
            ledger,
            config,
            prompt,
            archive_key=f"person_sample:{item['cluster_key']}",
        )
        parsed = _parse_result(result)
        predicted = _output_partition(parsed, item["names"])
        gold = _gold_partition(item["names"], item["cluster_key"])
        gate_errors = validate_entity_membership(parsed, records, item["names"])
        row = {
            **item,
            "context_sha256": canonical_context_hash(records),
            "gold_partition": gold,
            "predicted_partition": predicted,
            "exact_partition": predicted == gold,
            "gold_pairs": sorted(_pairs(gold)),
            "predicted_pairs": sorted(_pairs(predicted)),
            "production_gate_errors": gate_errors,
            "success": result.success,
            "error": result.error,
            "usage": result.metadata,
            "parsed": parsed,
        }
        rows.append(row)
        print(
            f"{index:02d}/20 {item['stratum']:10s} "
            f"exact={row['exact_partition']} gate={not gate_errors}"
        )

    conn.close()
    gold_pairs = set()
    predicted_pairs = set()
    true_pairs = set()
    exact = 0
    weighted_exact = 0.0
    total_weight = 0.0
    merge_cases = 0
    merge_cases_exact = 0
    for row in rows:
        scoped_gold = {(row["cluster_key"], *pair) for pair in row["gold_pairs"]}
        scoped_predicted = {
            (row["cluster_key"], *pair) for pair in row["predicted_pairs"]
        }
        gold_pairs.update(scoped_gold)
        predicted_pairs.update(scoped_predicted)
        true_pairs.update(scoped_gold & scoped_predicted)
        exact += int(row["exact_partition"])
        weight = counts[row["stratum"]] / QUOTAS[row["stratum"]]
        total_weight += weight
        weighted_exact += weight * int(row["exact_partition"])
        if row["gold_pairs"]:
            merge_cases += 1
            merge_cases_exact += int(row["exact_partition"])

    summary = {
        "sample_size": len(rows),
        "stratum_population": dict(counts),
        "exact_partitions": exact,
        "exact_partition_rate": round(exact / len(rows), 3),
        "population_weighted_exact_rate": round(weighted_exact / total_weight, 3),
        "gold_merge_cases": merge_cases,
        "gold_merge_cases_exact": merge_cases_exact,
        "correct_merge_case_yield": round(merge_cases_exact / merge_cases, 3),
        "gold_pairs": len(gold_pairs),
        "predicted_pairs": len(predicted_pairs),
        "true_positive_pairs": len(true_pairs),
        "pair_precision": round(len(true_pairs) / len(predicted_pairs), 3)
        if predicted_pairs
        else 1.0,
        "pair_recall": round(len(true_pairs) / len(gold_pairs), 3)
        if gold_pairs
        else 1.0,
        "production_gate_passes": sum(not row["production_gate_errors"] for row in rows),
        "spend": ledger.summary(),
    }
    output = {
        "model": args.model,
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "reviewed_at": "2026-09-04",
        "sampling": "stable-hash stratified sample, quotas weighted to the live skipped population",
        "summary": summary,
        "cases": rows,
    }
    RESULTS.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = RESULTS / f"person_cluster_audit_{stamp}.json"
    path.write_text(json.dumps(output, indent=2, default=str))
    print(json.dumps(summary, indent=2))
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
