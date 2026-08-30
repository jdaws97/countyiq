#!/usr/bin/env python3
"""Build a 100-case, rubric-labeled Pass 2 diagnostic corpus without model calls."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from hashlib import md5
from typing import Any

import psycopg2.extras

from countyiq.lib.pass2_batched_validation import gather_parcel_batch_context
from eval.build_fixtures import (
    FIXTURES,
    INTERPRETIVE_SIGNALS,
    _db,
    _deidentify_context,
)
from eval.fixture_io import canonical_context_hash


OUTPUT = FIXTURES / "p2_expanded_frozen.json"
SELECTION_QUERY = """
WITH per_pidn AS (
    SELECT pidn,
           array_agg(DISTINCT signal_key ORDER BY signal_key) FILTER (
               WHERE signal_key = ANY(%(signals)s)
           ) AS keys
    FROM public.development_signals
    GROUP BY pidn
)
SELECT pidn, keys
FROM per_pidn
WHERE cardinality(keys) BETWEEN 2 AND 4
ORDER BY keys, md5(pidn)
"""

_NUMBER_WORDS = {
    0: "zero",
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    11: "eleven",
    12: "twelve",
    13: "thirteen",
    14: "fourteen",
    15: "fifteen",
    16: "sixteen",
    17: "seventeen",
    18: "eighteen",
    19: "nineteen",
    20: "twenty",
}


def _number_group(value: Any, noun: str | None = None) -> list[str]:
    number = float(value or 0)
    compact = f"{number:.3f}".rstrip("0").rstrip(".")
    alternatives = [compact, f"{number:,.3f}".rstrip("0").rstrip(".")]
    if number.is_integer():
        integer = int(number)
        alternatives.extend([str(integer), f"{integer:,}"])
        if integer in _NUMBER_WORDS:
            alternatives.append(_NUMBER_WORDS[integer])
    if noun:
        alternatives = [f"{item} {noun}" for item in alternatives]
    return list(dict.fromkeys(alternatives))


def _signal_map(context: dict) -> dict[str, dict]:
    return {item["signal_key"]: item for item in context.get("signals") or []}


def _owner_is_institutional(owner: str) -> bool:
    upper = owner.upper()
    return any(
        token in upper
        for token in ("COMPANY", "AUTHORITY", "DISTRICT", "TOWNSHIP", "BOROUGH")
    )


def _active_subdivision_label(signal: dict) -> dict:
    evidence = signal.get("evidence") or {}
    lots = int(evidence.get("prop_lots") or 0)
    units = int(evidence.get("prop_du") or 0)
    scale = max(lots, units)
    if scale >= 3:
        statuses, significance = ["confirmed", "upgraded"], ["high", "medium"]
    elif scale == 2:
        statuses, significance = ["confirmed", "downgraded"], ["medium", "low"]
    else:
        statuses, significance = ["downgraded", "irrelevant"], ["low", "none"]
    facts = [
        _number_group(lots, "lot") + [f"prop lots {lots}"],
        _number_group(units, "unit") + [f"prop du {units}"],
    ]
    distance = signal.get("distance_m")
    if distance is not None:
        facts.append(
            _number_group(float(distance), "meter")
            + _number_group(round(float(distance)), "meter")
        )
    return {
        "signal_key": "active_subdivision",
        "accepted_statuses": statuses,
        "accepted_significance": significance,
        "required_fact_groups": facts,
        "forbidden_claims": [
            "approved",
            "entitled",
            "owner filed",
            "development intent",
        ],
    }


def _assemblage_label(context: dict, signal: dict) -> dict:
    evidence = signal.get("evidence") or {}
    neighbors = context.get("neighbors") or []
    count = int(evidence.get("neighbor_parcels") or len(neighbors))
    distinct = int(evidence.get("different_owner_neighbors") or 0)
    total_acres = sum(float(item.get("acres") or 0) for item in neighbors)
    institutional = _owner_is_institutional(context.get("parcel", {}).get("owner", ""))
    meaningful_scale = not institutional and (count >= 8 or total_acres >= 10)
    statuses = (
        ["confirmed", "downgraded"]
        if meaningful_scale
        else ["downgraded", "irrelevant"]
    )
    significance = ["medium", "low"] if meaningful_scale else ["low", "none"]
    delinquent = any(
        float(item.get("total_owed") or 0) > 0
        or int(item.get("years_delinquent") or 0) > 0
        for item in neighbors
    )
    delinquency = (
        ["delinquent neighbor", "tax delinquency", "distress evidence"]
        if delinquent
        else ["no delinquency", "no tax delinquency", "no distress", "none delinquent"]
    )
    return {
        "signal_key": "assemblage",
        "accepted_statuses": statuses,
        "accepted_significance": significance,
        "required_fact_groups": [
            _number_group(count, "neighbor"),
            _number_group(distinct, "different owner")
            + _number_group(distinct, "distinct owner"),
            delinquency,
        ],
        "forbidden_claims": [
            "coordinated acquisition",
            "motivated seller",
            "development intent",
        ],
    }


def _ownership_change_label(context: dict, signal: dict) -> dict:
    evidence = signal.get("evidence") or {}
    price = float(evidence.get("price") or 0)
    buyer_is_llc = bool(evidence.get("buyer_is_llc"))
    if price >= 500_000:
        significance = ["high", "medium"]
    elif price >= 75_000:
        significance = ["medium", "low"]
    else:
        significance = ["low", "none"]
    buyer_group = (
        ["buyer is llc", "buyer is llc true", "llc buyer", "limited liability"]
        if buyer_is_llc
        else ["buyer is llc false", "not an llc", "non llc", "individual buyer"]
    )
    return {
        "signal_key": "ownership_change",
        "accepted_statuses": ["confirmed", "downgraded"],
        "accepted_significance": significance,
        "required_fact_groups": [_number_group(price), buyer_group],
        "forbidden_claims": [
            "distressed",
            "developer buyer",
            "development intent",
            "arm's length",
        ],
    }


def _vacancy_label(context: dict, signal: dict) -> dict:
    evidence = signal.get("evidence") or {}
    structures = int(evidence.get("structure_count") or 0)
    assessed = float(evidence.get("aprtotal") or 0)
    property_class = str(evidence.get("class") or "unknown")
    owner = context.get("parcel", {}).get("owner", "")
    class_alternatives = {
        "R": ["class r", "r class", "residential class"],
        "C": ["class c", "c class", "commercial class"],
        "F": ["class f", "f class", "vacant land"],
        "E": ["class e", "e class", "exempt class"],
    }.get(
        property_class.upper(), [f"class {property_class}", f"{property_class} class"]
    )
    clean_vacancy = structures == 0 and property_class.upper() == "F"
    if clean_vacancy and not _owner_is_institutional(owner):
        statuses, significance = ["confirmed", "upgraded"], ["medium", "low"]
    else:
        statuses, significance = ["downgraded", "irrelevant"], ["low", "none"]
    return {
        "signal_key": "vacancy",
        "accepted_statuses": statuses,
        "accepted_significance": significance,
        "required_fact_groups": [
            ["structure count 0", "0 structure", "zero structure", "no structure"]
            if structures == 0
            else _number_group(structures, "structure"),
            _number_group(assessed),
            class_alternatives
            if property_class.upper() == "F"
            else class_alternatives + ["data gap"],
        ],
        "forbidden_claims": ["demolished", "abandoned", "development ready"],
    }


def _zoning_mismatch_label(signal: dict) -> dict:
    evidence = signal.get("evidence") or {}
    current = str(evidence.get("current_zname") or "unknown")
    future = str(evidence.get("future_lu") or evidence.get("general_lu") or "unknown")
    c, f = current.lower(), future.lower()
    general = str(evidence.get("general_lu") or "")
    future_group = [future, future.split(",", 1)[0]]
    if general:
        future_group.extend([general, general.split("-", 1)[0]])
    compatible = (
        ("rural" in c and ("rural" in f or "conservation" in f))
        or ("commercial" in c and ("commercial" in f or "mixed" in f))
        or ("industrial" in c and ("industrial" in f or "mixed" in f))
        or ("residential" in c and "residential" in f)
    )
    return {
        "signal_key": "zoning_mismatch",
        "accepted_statuses": ["downgraded", "irrelevant"]
        if compatible
        else ["confirmed", "downgraded"],
        "accepted_significance": ["low", "none"] if compatible else ["medium", "low"],
        "required_fact_groups": [[current], list(dict.fromkeys(future_group))],
        "forbidden_claims": ["rezoning", "upzoning", "approved", "policy change"],
    }


def _rubric_labels(context: dict) -> dict:
    labels = []
    for key, signal in _signal_map(context).items():
        if key == "active_subdivision":
            labels.append(_active_subdivision_label(signal))
        elif key == "assemblage":
            labels.append(_assemblage_label(context, signal))
        elif key == "ownership_change":
            labels.append(_ownership_change_label(context, signal))
        elif key == "vacancy":
            labels.append(_vacancy_label(context, signal))
        elif key == "zoning_mismatch":
            labels.append(_zoning_mismatch_label(signal))
    return {"signals": labels}


def _select(rows: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, ...], list[dict]] = defaultdict(list)
    for row in rows:
        grouped[tuple(row["keys"])].append(row)
    selected = []
    limits = {2: 5, 3: 3, 4: 10_000}
    for keys in sorted(grouped):
        selected.extend(grouped[keys][: limits[len(keys)]])
    selected_ids = {row["pidn"] for row in selected}
    remaining = [row for row in rows if row["pidn"] not in selected_ids]
    remaining.sort(
        key=lambda row: md5(
            (row["pidn"] + "|" + "+".join(row["keys"])).encode()
        ).hexdigest()
    )
    selected.extend(remaining[: 100 - len(selected)])
    return sorted(
        selected, key=lambda row: (len(row["keys"]), row["keys"], row["pidn"])
    )


def build_payload() -> dict:
    conn = _db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(SELECTION_QUERY, {"signals": list(INTERPRETIVE_SIGNALS)})
    selected = _select([dict(row) for row in cur.fetchall()])
    if len(selected) != 100:
        raise RuntimeError(f"Expected 100 expanded cases, found {len(selected)}")
    cases = []
    for index, row in enumerate(selected, 1):
        case_id = f"p2x-{index:03d}"
        context = _deidentify_context(
            gather_parcel_batch_context(cur, row["pidn"]), case_id
        )
        cases.append(
            {
                "id": case_id,
                "case_type": "+".join(row["keys"]),
                "signal_combination": list(row["keys"]),
                "context": context,
                "context_sha256": canonical_context_hash(context),
                "labels": _rubric_labels(context),
                "review": {
                    "status": "rubric_generated_requires_human_confirmation",
                    "rubric": "pass2_expanded_v1",
                },
            }
        )
    cur.close()
    conn.close()
    cardinalities = Counter(len(case["signal_combination"]) for case in cases)
    return {
        "version": 1,
        "built_at": "2026-08-30",
        "promotion_status": "diagnostic_until_human_review",
        "selection": (
            "md5-stable stratified sample: five per two-signal combination, "
            "three per three-signal combination, every four-signal case, then "
            "deterministic fill to 100"
        ),
        "cardinality_counts": {str(key): value for key, value in cardinalities.items()},
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = json.dumps(build_payload(), indent=2) + "\n"
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text() != content:
            raise SystemExit(f"Stale generated fixture: {OUTPUT}")
        print(f"Verified {OUTPUT}")
    else:
        OUTPUT.write_text(content)
        print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
