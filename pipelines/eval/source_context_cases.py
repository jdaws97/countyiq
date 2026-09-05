"""Explicit, reproducible diagnostic contexts for the rules-first signal policy.

Historical fixtures and labels remain immutable. This derivation moves retired
Pass 2 targets to factual context and reconstructs Pass 3 facts from the original
Pass 2 source snapshot instead of its hand-written validation narration. Exact
derived inputs must be frozen in each evaluation protocol before any model call.
These are repeated diagnostic cases, not new independent holdouts or a release
approval. Pass 3 statuses are synthetic fixture inputs, not recorded model runs.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from countyiq.lib.pass3_brief_generation import source_evidence_facts
from countyiq.lib.signal_policy import INTERPRETIVE_SIGNAL_KEYS
from eval.fixture_io import canonical_context_hash, load_frozen_cases

DERIVATION_VERSION = "source-context-v1"
FIXTURES = Path(__file__).with_name("fixtures")


def _check_source(case: dict) -> None:
    if canonical_context_hash(case["context"]) != case["context_sha256"]:
        raise ValueError(f"Damaged source context: {case['id']}")


def derive_pass2_case(source: dict) -> dict:
    _check_source(source)
    case = deepcopy(source)
    context = case["context"]
    retired = [s for s in context["signals"] if s["signal_key"] not in INTERPRETIVE_SIGNAL_KEYS]
    context["signals"] = [s for s in context["signals"] if s["signal_key"] in INTERPRETIVE_SIGNAL_KEYS]
    context["context_signals"] = [*(context.get("context_signals") or []), *retired]
    keys = {s["signal_key"] for s in context["signals"]}
    case["labels"]["signals"] = [label for label in case["labels"]["signals"] if label["signal_key"] in keys]
    case["signal_combination"] = sorted(keys)
    case["call_eligible"] = len(keys) >= 2
    case["context_sha256"] = canonical_context_hash(context)
    case["source_lineage"] = {
        "derivation": DERIVATION_VERSION,
        "source_context_sha256": source["context_sha256"],
        "source_labels_sha256": canonical_context_hash(source["labels"]),
        "retired_validation_targets": [s["signal_key"] for s in retired],
    }
    case["review"] = {
        "status": "derived_diagnostic_requires_review",
        "prior_review": deepcopy(source.get("review")),
        "note": "Remaining label values are unchanged; cases below two interpretive signals require no production call.",
    }
    return case


def derive_pass3_case(source: dict, pass2_source: dict) -> dict:
    _check_source(source)
    _check_source(pass2_source)
    if source["source_pass2_case"] != pass2_source["id"]:
        raise ValueError("Pass 3 source case does not match its retained Pass 2 snapshot")
    case = deepcopy(source)
    raw_context = pass2_source["context"]
    raw_signals = {s["signal_key"]: s for s in raw_context["signals"]}
    signals = []
    for prior in source["context"]["validated_signals"]:
        key = prior["signal_key"]
        if key not in INTERPRETIVE_SIGNAL_KEYS:
            continue
        if key not in raw_signals:
            raise ValueError(f"Missing source evidence for {source['id']}/{key}")
        signals.append({
            "signal_key": key,
            "validation_status": prior["validation_status"],
            "adjusted_significance": prior["adjusted_significance"],
            "key_facts": source_evidence_facts(raw_signals[key].get("evidence")),
            "source_url": "",
            "internal_url": f"/property/{raw_context['pidn']}",
        })
    context = case["context"] = {
        "pidn": raw_context["pidn"],
        "parcel": deepcopy(raw_context["parcel"]),
        "entity": deepcopy(raw_context.get("entity") or {"found": False}),
        "portfolio": deepcopy(source["context"].get("portfolio") or {}),
        "validated_signals": signals,
    }
    keys = {s["signal_key"] for s in signals}
    for field in ("required_citations", "allowed_citations"):
        case["labels"][field] = [key for key in case["labels"][field] if key in keys]
    # This old case alone required footprint facts through its retired vacancy
    # validation. They remain available in Pass 2 context and the product's GIS
    # record, but the current Pass 3 query does not consume that source signal.
    if source["id"] == "p3-001":
        case["labels"]["required_fact_groups"] = [
            group for group in case["labels"]["required_fact_groups"]
            if group != ["0 structures", "no mapped structure"]
        ]
    case["context_sha256"] = canonical_context_hash(context)
    case["upstream_pass2_eligible"] = derive_pass2_case(pass2_source)["call_eligible"]
    case["source_lineage"] = {
        "derivation": DERIVATION_VERSION,
        "source_context_sha256": source["context_sha256"],
        "source_pass2_context_sha256": pass2_source["context_sha256"],
        "source_labels_sha256": canonical_context_hash(source["labels"]),
        "upstream_assessments": "synthetic fixture statuses; no recorded Pass 2 inference",
        "limitations": "Original de-identification aliases plan titles by surname; name equality is not verified parcel inclusion. Missing fields are unknown, not proof of absent activity.",
    }
    case["review"] = {
        "status": "derived_diagnostic_requires_review",
        "prior_review": deepcopy(source.get("review")),
        "note": "Source fields restored; generated reasoning and reference prose removed. Recommendation labels are retained for diagnostic comparison, not newly approved gold.",
    }
    return case


def pass2_cases(path: Path | None = None) -> list[dict]:
    return [derive_pass2_case(case) for case in load_frozen_cases(path or FIXTURES / "p2_expanded_stability20.json")]


def pass3_cases() -> list[dict]:
    source_by_id = {c["id"]: c for c in load_frozen_cases(FIXTURES / "p2_frozen.json")}
    return [derive_pass3_case(c, source_by_id[c["source_pass2_case"]])
            for c in load_frozen_cases(FIXTURES / "p3_investigation_frozen.json")]
