#!/usr/bin/env python3
"""Build a 100-case, rubric-labeled Pass 2 diagnostic corpus without model calls.

``--relabel`` re-applies the current rubric to the stored, de-identified
contexts of the existing fixtures without touching the database or the
contexts themselves, so a rubric correction is a reviewable label diff rather
than a regenerated corpus.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import md5
from pathlib import Path
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
STABILITY_OUTPUT = FIXTURES / "p2_expanded_stability20.json"

# Rubric v2 (2026-09-03 review of the 20-case stability subset):
# - a land-development plan (pt_land_dev = YES) is believable with zero lots
#   and zero dwelling units, exactly as the v7 signal filter treats it;
# - the plan must plausibly sit on the parcel (within one parcel width and
#   not far smaller than the parcel) before "confirmed" is accepted;
# - a residential-class parcel under the $50k vacancy screen may be confirmed
#   vacant; class alone does not force a downgrade;
# - agricultural, conservation, open-space, and parks designations belong to
#   one land-use family, so they are not a plan/zoning divergence.
RUBRIC_VERSION = "pass2_expanded_v5"
GENERATED_STATUS = "rubric_generated_requires_human_confirmation"
REVIEWED_STATUS = "rubric_reviewed"
EXPANDED_INTERPRETIVE_SIGNALS = (*INTERPRETIVE_SIGNALS, "entity_assemblage")
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


def _plan_is_believable(evidence: dict) -> bool:
    """Mirror the score-version-7 believability filter."""
    land_development = str(evidence.get("pt_land_dev") or "").upper() == "YES"
    return land_development or int(evidence.get("prop_du") or 0) > 0


def _plan_plausibly_on_parcel(signal: dict, context: dict) -> bool:
    """A plan point within 30 m or one parcel width is plausibly parcel-specific."""
    distance = float(signal.get("distance_m") or 0)
    parcel_acres = float((context.get("parcel") or {}).get("acres") or 0)
    parcel_width_m = math.sqrt(max(parcel_acres, 0.0) * 4046.86)
    return distance <= max(30.0, parcel_width_m)


def _active_subdivision_label(signal: dict, context: dict) -> dict:
    evidence = signal.get("evidence") or {}
    lots = int(evidence.get("prop_lots") or 0)
    units = int(evidence.get("prop_du") or 0)
    land_development = str(evidence.get("pt_land_dev") or "").upper() == "YES"
    scale = max(lots, units)
    if not _plan_is_believable(evidence) or not _plan_plausibly_on_parcel(
        signal, context
    ):
        statuses, significance = ["downgraded", "irrelevant"], ["low", "none"]
    elif scale >= 3 or float(evidence.get("total_acres") or 0) >= 10:
        statuses, significance = ["confirmed", "upgraded"], ["high", "medium"]
    else:
        statuses, significance = ["confirmed", "downgraded"], ["medium", "low"]
    facts = []
    if lots > 0:
        facts.append(_number_group(lots, "lot") + [f"prop lots {lots}"])
    if units > 0:
        facts.append(
            _number_group(units, "unit")
            + _number_group(units, "dwelling unit")
            + [f"prop du {units}"]
        )
    if land_development:
        facts.append(
            [
                "land development",
                "land-development",
                "pt land dev yes",
                "pt_land_dev=yes",
            ]
        )
    if not facts:
        facts.extend(
            [
                _number_group(lots, "lot") + [f"prop lots {lots}"],
                _number_group(units, "unit") + [f"prop du {units}"],
            ]
        )
    plan_acres = float(evidence.get("total_acres") or 0)
    if plan_acres > 0:
        facts.append(
            _number_group(plan_acres, "acre")
            + [f"total acres {plan_acres:g}", "acreage matches parcel"]
        )
    distance = signal.get("distance_m")
    if distance is not None:
        distance_value = float(distance)
        location = str(evidence.get("plan_location") or "")
        location_facts = [f"{distance_value:g}m", location, location.replace("_", " ")]
        if location == "within_30m_of_parcel":
            location_facts.extend(["within 30 meter", "within 30 meters"])
        elif location == "point_on_parcel":
            location_facts.extend(["point on parcel", "on the parcel"])
        facts.append(
            _number_group(distance_value, "meter")
            + _number_group(round(distance_value), "meter")
            + location_facts
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
        else [
            "no delinquency",
            "no tax delinquency",
            "no distress",
            "none delinquent",
            "0 delinquent adjacent",
            "zero delinquent adjacent",
            "adjacent delinquent count 0",
        ]
    )
    return {
        "signal_key": "assemblage",
        "accepted_statuses": statuses,
        "accepted_significance": significance,
        "required_fact_groups": [
            _number_group(count, "neighbor"),
            _number_group(distinct, "different owner")
            + _number_group(distinct, "distinct owner"),
            _number_group(total_acres, "acre") + [f"combined acreage {total_acres:g}"],
            delinquency,
        ],
        "forbidden_claims": [
            "coordinated acquisition",
            "motivated seller",
            "development intent",
        ],
    }


def _entity_assemblage_label(signal: dict) -> dict:
    """Label a same-owner contiguous acquisition without inferring intent."""
    evidence = signal.get("evidence") or {}
    count = int(evidence.get("contiguous_same_owner_parcels") or 0)
    latest = str(evidence.get("latest_acquisition") or "unknown")
    months = int(evidence.get("months_since_latest_acquisition") or 0)
    meaningful_scale = count >= 3
    timing_group = [latest]
    timing_group.extend(_number_group(months, "month"))
    timing_group.extend(_number_group(months, "months"))
    timing_group.extend(
        [
            f"{months} months since acquisition",
            f"months since acquisition is {months}",
        ]
    )
    return {
        "signal_key": "entity_assemblage",
        "accepted_statuses": ["confirmed", "downgraded"],
        "accepted_significance": (
            ["medium", "low"] if meaningful_scale else ["low", "medium"]
        ),
        "required_fact_groups": [
            _number_group(count, "contiguous parcel")
            + _number_group(count, "same-owner parcel"),
            list(dict.fromkeys(timing_group)),
        ],
        "forbidden_claims": [
            "developer",
            "development intent",
            "investor",
            "coordinated acquisition",
        ],
    }


def _ownership_change_label(context: dict, signal: dict) -> dict:
    evidence = signal.get("evidence") or {}
    price = float(evidence.get("price") or 0)
    if "buyer_is_llc" in evidence:
        buyer_is_llc = bool(evidence.get("buyer_is_llc"))
        buyer_group = (
            ["buyer is llc", "buyer is llc true", "llc buyer", "limited liability"]
            if buyer_is_llc
            else ["buyer is llc false", "not an llc", "non llc", "individual buyer"]
        )
    else:
        looks_organizational = bool(evidence.get("buyer_name_looks_organizational"))
        buyer_group = (
            ["buyer name looks organizational", "organizational-looking buyer"]
            if looks_organizational
            else [
                "buyer name looks individual",
                "individual-looking buyer",
                "buyer name does not look organizational",
                "buyer name is not organizational",
            ]
        )
    if price >= 500_000:
        significance = ["high", "medium", "low"]
    elif price >= 75_000:
        significance = ["medium", "low"]
    else:
        significance = ["low", "none"]
    required_facts = [_number_group(price), buyer_group]
    ratio = evidence.get("price_to_assessed_pct")
    if ratio is not None:
        ratio_value = float(ratio)
        ratio_text = f"{ratio_value:g}"
        ratio_group = [
            f"{ratio_text}%",
            f"{ratio_text} percent",
            f"price to assessed {ratio_text}",
        ]
        if ratio_value.is_integer():
            ratio_group.extend(
                [f"{int(ratio_value):,}%", f"{int(ratio_value):,} percent"]
            )
        required_facts.append(ratio_group)
    return {
        "signal_key": "ownership_change",
        "accepted_statuses": ["confirmed", "downgraded"],
        "accepted_significance": significance,
        "required_fact_groups": required_facts,
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
    class_code = property_class.upper()
    if structures > 0 or assessed <= 0 or _owner_is_institutional(owner):
        # A footprint, a zero assessment, or an institutional owner reads as
        # a data gap or a non-market parcel, not a vacant-land opportunity.
        statuses, significance = ["downgraded", "irrelevant"], ["low", "none"]
    elif class_code in {"F", "A"}:
        statuses, significance = ["confirmed", "upgraded"], ["medium", "low"]
    elif class_code == "R" and assessed < 50_000:
        # The deterministic screen already caps residential parcels at $50k;
        # land-only value with no footprint is a defensible vacant lot.
        statuses, significance = ["confirmed", "downgraded"], ["medium", "low"]
    elif class_code in {"C", "I"}:
        # Commercial/industrial land with no mapped footprint may be vacant
        # park land or a stale footprint layer; either reading is defensible.
        statuses, significance = ["confirmed", "downgraded"], ["low", "none"]
    else:
        statuses, significance = ["downgraded", "irrelevant"], ["low", "none"]
    required_facts = [
        ["structure count 0", "0 structure", "zero structure", "no structure"]
        if structures == 0
        else _number_group(structures, "structure"),
        _number_group(assessed),
        class_alternatives
        if property_class.upper() == "F"
        else class_alternatives + ["data gap"],
    ]
    if _owner_is_institutional(owner):
        required_facts.append([owner, "institutional owner", "public owner"])
    return {
        "signal_key": "vacancy",
        "accepted_statuses": statuses,
        "accepted_significance": significance,
        "required_fact_groups": required_facts,
        "forbidden_claims": ["demolished", "abandoned", "development ready"],
    }


def _land_use_families(text: str) -> set[str]:
    """Coarse land-use families; overlap means the labels are not divergent."""
    lowered = text.lower()
    families: set[str] = set()
    if any(
        token in lowered
        for token in (
            "conservation",
            "open space",
            "agricultur",
            "preserv",
            "park",
            "recreation",
            "forest",
        )
    ):
        families.add("rural_open")
    if any(token in lowered for token in ("residential", "living", "density")):
        families.add("residential")
    if any(
        token in lowered for token in ("commercial", "business", "shopping", "retail")
    ):
        families.add("commercial")
    if any(token in lowered for token in ("industrial", "manufactur", "employment")):
        families.add("industrial")
    if "mixed" in lowered:
        families.update({"commercial", "residential"})
    if any(
        token in lowered
        for token in ("institution", "school", "cemeter", "public building")
    ):
        families.add("institutional")
    return families


def _zoning_mismatch_label(signal: dict) -> dict:
    evidence = signal.get("evidence") or {}
    current = str(evidence.get("current_zname") or "unknown")
    future = str(evidence.get("future_lu") or evidence.get("general_lu") or "unknown")
    general = str(evidence.get("general_lu") or "")
    future_group = [future, future.split(",", 1)[0]]
    if general:
        future_group.extend([general, general.split("-", 1)[0]])
    current_families = _land_use_families(current)
    future_families = _land_use_families(f"{future} {general}")
    compatible = bool(current_families) and current_families == future_families
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
            labels.append(_active_subdivision_label(signal, context))
        elif key == "assemblage":
            labels.append(_assemblage_label(context, signal))
        elif key == "entity_assemblage":
            labels.append(_entity_assemblage_label(signal))
        elif key == "ownership_change":
            labels.append(_ownership_change_label(context, signal))
        elif key == "vacancy":
            labels.append(_vacancy_label(context, signal))
        elif key == "zoning_mismatch":
            labels.append(_zoning_mismatch_label(signal))
        else:
            raise ValueError(f"Expanded Pass 2 rubric has no label for {key!r}")
    return {"signals": labels}


def _select(rows: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, ...], list[dict]] = defaultdict(list)
    for row in rows:
        grouped[tuple(row["keys"])].append(row)
    selected = []
    limits = {2: 2, 3: 2, 4: 2}
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
    cur.execute(SELECTION_QUERY, {"signals": list(EXPANDED_INTERPRETIVE_SIGNALS)})
    selected = _select([dict(row) for row in cur.fetchall()])
    if len(selected) != 100:
        raise RuntimeError(f"Expected 100 expanded cases, found {len(selected)}")
    cases = []
    for index, row in enumerate(selected, 1):
        case_id = f"p2x-{index:03d}"
        context = _deidentify_context(
            gather_parcel_batch_context(cur, row["pidn"]), case_id
        )
        actual_keys = sorted(_signal_map(context))
        if actual_keys != list(row["keys"]):
            raise RuntimeError(
                f"{case_id} selected {list(row['keys'])!r} but gathered "
                f"{actual_keys!r}; update the expanded signal set and rubric"
            )
        cases.append(
            {
                "id": case_id,
                "case_type": "+".join(row["keys"]),
                "signal_combination": list(row["keys"]),
                "context": context,
                "context_sha256": canonical_context_hash(context),
                "labels": _rubric_labels(context),
                "review": {"status": GENERATED_STATUS, "rubric": RUBRIC_VERSION},
            }
        )
    cur.close()
    conn.close()
    cardinalities = Counter(len(case["signal_combination"]) for case in cases)
    return {
        "version": 1,
        "built_at": "2026-09-04",
        "promotion_status": "diagnostic_until_human_review",
        "selection": (
            "md5-stable stratified sample: up to two cases per observed "
            "two-, three-, and four-signal combination, then deterministic "
            "fill to 100"
        ),
        "cardinality_counts": {str(key): value for key, value in cardinalities.items()},
        "cases": cases,
    }


def build_stability_payload(full_payload: dict) -> dict:
    """Select a stable, cardinality-balanced subset for manual review."""
    quotas = {2: 7, 3: 7, 4: 6}
    selected = []
    for cardinality, quota in quotas.items():
        rows = [
            case
            for case in full_payload["cases"]
            if len(case["signal_combination"]) == cardinality
        ]
        rows.sort(
            key=lambda case: md5(
                (case["id"] + "|" + "+".join(case["signal_combination"])).encode()
            ).hexdigest()
        )
        selected.extend(rows[:quota])
    return {
        "version": 1,
        "built_at": full_payload["built_at"],
        "promotion_status": "diagnostic_until_human_review",
        "source_fixture": OUTPUT.name,
        "selection": (
            "md5-stable cardinality-balanced sample: seven two-signal, "
            "seven three-signal, and six four-signal cases"
        ),
        "cases": selected,
    }


def relabel(
    paths: list[Path],
    *,
    reviewed_ids: set[str],
    reviewer: str | None,
    reviewed_at: str | None,
    review_record: str | None,
) -> dict[str, int]:
    """Rewrite labels from stored contexts; contexts and hashes stay untouched."""
    changed: dict[str, int] = {}
    for path in paths:
        payload = json.loads(path.read_text())
        count = 0
        for case in payload["cases"]:
            new_labels = _rubric_labels(case["context"])
            if new_labels != case.get("labels"):
                count += 1
            case["labels"] = new_labels
            review = {"status": GENERATED_STATUS, "rubric": RUBRIC_VERSION}
            if case["id"] in reviewed_ids:
                review = {
                    "status": REVIEWED_STATUS,
                    "rubric": RUBRIC_VERSION,
                    "reviewed_by": reviewer,
                    "reviewed_at": reviewed_at,
                    "review_record": review_record,
                }
            case["review"] = review
        if reviewed_ids and all(
            case["id"] in reviewed_ids for case in payload["cases"]
        ):
            payload["promotion_status"] = "reviewed_stability_subset"
        path.write_text(json.dumps(payload, indent=2) + "\n")
        changed[str(path)] = count
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--build-stability", action="store_true")
    parser.add_argument(
        "--relabel",
        action="store_true",
        help="re-apply the rubric to the stored fixture contexts without a database",
    )
    parser.add_argument("--reviewer")
    parser.add_argument("--reviewed-at", default=datetime.now(timezone.utc).isoformat())
    parser.add_argument("--review-record")
    args = parser.parse_args()
    if args.build_stability:
        full_payload = json.loads(OUTPUT.read_text())
        content = json.dumps(build_stability_payload(full_payload), indent=2) + "\n"
        STABILITY_OUTPUT.write_text(content)
        print(f"Wrote {STABILITY_OUTPUT}")
        return
    if args.relabel:
        stability = json.loads(STABILITY_OUTPUT.read_text())
        reviewed_ids = (
            {case["id"] for case in stability["cases"]} if args.reviewer else set()
        )
        changed = relabel(
            [OUTPUT, STABILITY_OUTPUT],
            reviewed_ids=reviewed_ids,
            reviewer=args.reviewer,
            reviewed_at=args.reviewed_at,
            review_record=args.review_record,
        )
        for path, count in changed.items():
            print(f"Relabeled {path}: {count} case(s) changed")
        return
    payload = build_payload()
    content = json.dumps(payload, indent=2) + "\n"
    if args.check:
        if not OUTPUT.exists():
            raise SystemExit(f"Stale generated fixture: {OUTPUT}")
        stored = json.loads(OUTPUT.read_text())
        # Human-review metadata is layered onto the reproducible artifact.
        # Compare regenerated evidence and labels without deleting that receipt.
        for case in stored.get("cases", []):
            case["review"] = {"status": GENERATED_STATUS, "rubric": RUBRIC_VERSION}
        if stored != payload:
            raise SystemExit(f"Stale generated fixture: {OUTPUT}")
        print(f"Verified {OUTPUT}")
    else:
        OUTPUT.write_text(content)
        print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
