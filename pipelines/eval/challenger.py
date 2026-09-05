#!/usr/bin/env python3
"""Push-button challenger eval: one new model vs the current per-pass defaults.

Run this when a re-eval TRIGGER fires (see docs/decisions.md → model churn
policy) — never on a calendar. ~$0.30-0.60 and ~30 minutes per challenger.

    .venv/bin/python -m eval.challenger --model <slug> [--passes 0]
        [--live] [--judge-model <slug>] [--quantizations fp8,bf16]

What it does per pass:
  Pass 0: 6 immutable PDFs with human-reviewed expected matters → native-PDF
          extraction with the production template and deterministic gold
          scoring. This is the current promotion-grade frozen lane.
  Pass 1: 8 immutable, de-identified entity-partition cases with human labels.
  Pass 2: 10 immutable, de-identified cases covering every exact two-signal
          combination, scored against human calibration/grounding labels. A
          custom --pass2-fixture can run wider rubric diagnostics separately.
  Pass 3: 4 immutable, production-shaped decision/citation cases derived from
          reviewed Pass 2 evidence.

Use --live for the separate current-database Pass 1/2 drift lane. Live results
save the exact context hash and prompt but are not a promotion oracle.

The current defaults come from pass_llm_config; the optional diagnostic judge
is x-ai/grok-4.6. Human labels remain the acceptance gate.
Results land in eval/results/challenger_<model>_<ts>.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras

from countyiq.lib.doc_text import extract_text_from_pdf_bytes
from countyiq.lib.intelligence_integrity import (
    validate_entity_membership,
    validate_parcel_brief_citations,
    validate_pass0_extractions,
    validate_pass2_evidence_refs,
)
from countyiq.lib.llm_harness import (
    HarnessConfig,
    extract_json_object,
    get_preset_for_model,
    strip_thinking,
)
from countyiq.lib.pass0_templates import document_prompt
from countyiq.lib.proceeding_claims import hydrate_claims
from countyiq.lib.pass1_entity_verification import (
    build_entity_cluster_prompt,
    gather_cluster_records,
    parse_entity_verification_output,
)
from countyiq.lib.pass2_batched_validation import (
    BATCHED_VALIDATION_SYSTEM_PROMPT,
    build_batched_signal_prompt,
    gather_parcel_batch_context,
    parse_batched_signal_output,
)
from countyiq.lib.pass3_brief_generation import (
    build_brief_generation_prompt,
    parse_brief_output,
)
from countyiq.lib.pass_llm_config import resolve_pass_model
from eval.fixture_io import canonical_context_hash, load_frozen_cases
from eval.protocol import (
    EvalCostLedger,
    EvalCostLimitExceeded,
    EvalCostUnavailable,
    build_production_eval_config,
    invoke_tracked,
)
from eval.scoring import (
    PASS2_SCORING_VERSION,
    enforce_production_gate,
    score_pass0,
    score_pass1,
    score_pass2,
    score_pass3,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
RESULTS = Path(__file__).resolve().parent / "results"
RECOMMENDED_JUDGE = "x-ai/grok-4.6"


def _is_default_pass2_fixture(path: Path) -> bool:
    return path.resolve() == (FIXTURES / "p2_frozen.json").resolve()


JUDGE_SYSTEM_PROMPT = """You are a strict evidence auditor comparing two parcel signal validations.
Use only facts in SOURCE CASE. Prefer calibrated uncertainty when provenance,
authority, corridor pattern, owner distress, causality, or intent is absent.

Ignore wrapper metadata, field ordering, length, and prose style. Evaluate the
substantive validations only. Penalize claims that turn a capture timestamp
into plan authority or intent, treat missing evidence as proof of absence, turn
background-only context into causal evidence, or assert policy/market effects
without source support. Return the strict JSON object only."""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "winner": {"type": "string", "enum": ["A", "B", "tie"]},
        "a_grounding": {"type": "integer", "minimum": 1, "maximum": 5},
        "b_grounding": {"type": "integer", "minimum": 1, "maximum": 5},
        "a_unsupported_claims": {"type": "array", "items": {"type": "string"}},
        "b_unsupported_claims": {"type": "array", "items": {"type": "string"}},
        "decisive_reason": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": [
        "winner",
        "a_grounding",
        "b_grounding",
        "a_unsupported_claims",
        "b_unsupported_claims",
        "decisive_reason",
        "confidence",
    ],
    "additionalProperties": False,
}


def _mk_config(model, pass_number, max_tokens=None, effort=None, quant=None):
    return build_production_eval_config(
        model,
        pass_number,
        archive_label="challenger",
        max_tokens=max_tokens,
        reasoning_effort=effort,
        provider_quantizations=quant,
    )


def _mk_judge_config(model):
    price_ceiling = {
        RECOMMENDED_JUDGE: (2.50, 8.00),
    }.get(model, (None, None))
    return HarnessConfig(
        model_path=model,
        max_tokens=2048,
        thinking=False,
        reasoning_effort="low",
        archive_label="challenger",
        json_schema=JUDGE_SCHEMA,
        schema_name="pass2_pairwise_judgment",
        system_prompt=JUDGE_SYSTEM_PROMPT,
        max_price_prompt=price_ceiling[0],
        max_price_completion=price_ceiling[1],
        zdr=True,
        **get_preset_for_model(model, thinking=False, reasoning_task=True),
    )


def _parse(raw):
    try:
        obj = json.loads(extract_json_object(strip_thinking(raw or "")))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _db():
    return psycopg2.connect(
        host=os.environ.get("DATABASE_HOST", "localhost"),
        port=int(os.environ.get("DATABASE_PORT", 5433)),
        dbname=os.environ.get("DATABASE_NAME", "countyiq"),
        user=os.environ.get("DATABASE_USER", "dagster_admin"),
        password=os.environ.get("DATABASE_PASSWORD", "localtest"),
    )


# ---------------------------------------------------------------- Pass 0
def run_pass0(cfg, ledger, on_progress=None) -> list[dict]:
    corpus = json.loads((FIXTURES / "p0_expected.json").read_text())
    rows = []
    for fixture in corpus["documents"]:
        fname = fixture["file"]
        pdf = (FIXTURES / "p0_pdfs" / fname).read_bytes()
        source_text = extract_text_from_pdf_bytes(pdf)
        prompt = document_prompt(source_text,
            body_name=fixture["body_name"],
            county_name="York County",
            state="PA",
            proceeding_type=fixture["proceeding_type"],
            meeting_date=fixture.get("meeting_date"),
        )
        t0 = time.time()
        res = invoke_tracked(
            ledger,
            cfg,
            prompt,
            archive_key=f"chal_p0:{fname}",
            pdf_bytes=None,
        )
        parsed = res.parsed or _parse(res.raw_output)
        try:
            hydrated = hydrate_claims(parsed, source_text, meeting_date=fixture.get("meeting_date"))
            errors = validate_pass0_extractions(hydrated, source_text, require_contract=True)
        except ValueError as exc:
            hydrated, errors = [], [str(exc)]
        score = enforce_production_gate(score_pass0({"extractions": hydrated}, fixture), errors)
        rows.append(
            {
                "doc": fname,
                "success": res.success,
                "dataset_mode": "frozen_gold",
                **score,
                "elapsed_s": round(time.time() - t0, 1),
                "error": res.error,
                "usage": res.metadata,
            }
        )
        if on_progress:
            on_progress(rows)
        print(
            f"  p0 {fname:22s} expected={score['expected_count']} "
            f"actual={score['actual_count']} "
            f"gold={'PASS' if score['gold_pass'] else 'FAIL'}"
        )
    return rows


# ---------------------------------------------------------------- Pass 1
def _norm_pidn(s: str) -> str:
    """Normalize a PIDN-ish string for grounding comparison.

    The 2026-08-06 audit found the old regex-only check FALSELY flagged
    models that echo legitimate PIDNs with formatting ("PIDN 37000BF0015P0",
    dashes) — every 'hallucination' it reported for mercury/luna/grok was an
    artifact. Compare normalized alphanumerics with the PIDN prefix stripped.
    """
    t = re.sub(r"[^A-Z0-9]", "", str(s).upper())
    return t[4:] if t.startswith("PIDN") else t


def _prompt_pidns(prompt):
    """Every parcel identifier actually present in the prompt (normalized)."""
    ids = set()
    for m in re.finditer(r"PIDN\s+([A-Za-z0-9]+)", prompt):
        ids.add(_norm_pidn(m.group(1)))
    for m in re.finditer(r"\b(\d{2}000[A-Z0-9]{6,10})\b", prompt):
        ids.add(_norm_pidn(m.group(1)))
    return ids


def _fixture_cluster_names(case: dict) -> list[str]:
    """Recover the candidate-name universe carried by a frozen Pass 1 case."""

    # Partition labels are record IDs, not names; production cluster names
    # are the owner-name strings the trigram pairs were built from.
    records = case.get("context") or {}
    explicit = records.get("candidate_names")
    if isinstance(explicit, list) and explicit:
        return sorted(str(name).strip() for name in explicit if str(name).strip())
    names: set[str] = set()
    fields = {
        "parcels": ("owner_full",),
        "tax_claims": ("owner_name",),
        "plcb_licenses": ("licensee", "premises_owner"),
        "corporate_entities": ("entity_name",),
        "proceedings": ("applicant_name",),
    }
    for source, source_fields in fields.items():
        for row in records.get(source, []) or []:
            for field in source_fields:
                value = row.get(field) if isinstance(row, dict) else None
                if isinstance(value, str) and value.strip():
                    names.add(value.strip())
    return sorted(names)


def run_pass1_live(cfg, ledger, on_progress=None) -> list[dict]:
    clusters = json.loads((FIXTURES / "p1_clusters.json").read_text())
    conn = _db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    rows = []
    for i, c in enumerate(clusters):
        records = gather_cluster_records(cur, c["names"])
        prompt = build_entity_cluster_prompt(records)
        context_hash = canonical_context_hash(records)
        t0 = time.time()
        res = invoke_tracked(ledger, cfg, prompt, archive_key=f"chal_p1:c{i}")
        parsed = parse_entity_verification_output(
            res.parsed or _parse(res.raw_output) or {}
        )
        row = {
            "cluster": i,
            "success": res.success,
            "error": res.error,
            "json_valid": isinstance(parsed, dict) and "entities" in parsed,
            "dataset_mode": "live_context_from_frozen_selectors",
            "context_sha256": context_hash,
            "context": records,
            "prompt": prompt,
            "elapsed_s": round(time.time() - t0, 1),
            "usage": res.metadata,
            "production_gate_errors": validate_entity_membership(
                parsed,
                records,
                c["names"],
            ),
        }
        row["production_gate_pass"] = not row["production_gate_errors"]
        if row["json_valid"]:
            in_p = _prompt_pidns(prompt)
            out_p = set()
            for e in parsed.get("entities", []):
                lr = e.get("linked_records") or {}
                for field in ("parcels", "tax_claims"):
                    for p in lr.get(field) or []:
                        if isinstance(p, str) and p.strip():
                            out_p.add(_norm_pidn(p))
            fabricated = sorted(out_p - in_p) if in_p else []
            row["hallucinated_pidns"] = len(fabricated)
            row["fabricated_samples"] = fabricated[:5]
            row["n_abstained"] = len(parsed.get("abstentions") or [])
            row["n_rejected"] = len(parsed.get("rejected_matches") or [])
        rows.append(row)
        if on_progress:
            on_progress(rows)
        print(
            f"  p1 c{i:02d} json={row['json_valid']} "
            f"halluc={row.get('hallucinated_pidns')} {row['elapsed_s']}s"
        )
    conn.close()
    return rows


def run_pass1_frozen(cfg, ledger, on_progress=None) -> list[dict]:
    cases = load_frozen_cases(FIXTURES / "p1_frozen.json")
    rows = []
    for case in cases:
        cluster_names = _fixture_cluster_names(case)
        prompt_records = {**case["context"], "candidate_names": cluster_names}
        prompt = build_entity_cluster_prompt(prompt_records)
        t0 = time.time()
        res = invoke_tracked(ledger, cfg, prompt, archive_key=f"chal_p1:{case['id']}")
        parsed = parse_entity_verification_output(
            res.parsed or _parse(res.raw_output) or {}
        )
        score = enforce_production_gate(
            score_pass1(parsed, {"records": case["context"], **case}),
            validate_entity_membership(
                parsed,
                prompt_records,
                cluster_names,
            ),
        )
        row = {
            "case_id": case["id"],
            "case_type": case["case_type"],
            "dataset_mode": "frozen_gold",
            "context_sha256": case["context_sha256"],
            "success": res.success,
            "error": res.error,
            "elapsed_s": round(time.time() - t0, 1),
            "usage": res.metadata,
            **score,
        }
        rows.append(row)
        if on_progress:
            on_progress(rows)
        print(
            f"  p1 {case['id']} partition="
            f"{'PASS' if score['gold_pass'] else 'FAIL'} {row['elapsed_s']}s"
        )
    return rows


# ---------------------------------------------------------------- Pass 2
JUDGE_PROMPT = """Blind-judge two AI signal-validation outputs for the same parcel.
The source case below is the only allowed evidence.

=== SOURCE CASE ===
{evidence}

=== OUTPUT A ===
{a}

=== OUTPUT B ===
{b}

Choose the better grounded and calibrated substantive validation. Use "tie"
only when the important factual and calibration errors are equivalent. Return
the strict JSON object."""


def _pass2_prompt_one(cfg, prompt, context, case_key, ledger):
    signals = context["signals"]
    res = invoke_tracked(
        ledger, cfg, prompt, archive_key=f"chal_p2:{case_key}:{cfg.model_path}"
    )
    raw_parsed = res.parsed or _parse(res.raw_output) or {}
    parsed = parse_batched_signal_output(raw_parsed, signals) if res.success else None
    production_gate_errors = (
        validate_pass2_evidence_refs(
            parsed.get("validations", []),
            signals,
            context.get("context_signals", []),
            parsed.get("cross_signal_insight"),
        )
        if parsed
        else ["Pass 2 output could not be parsed"]
    )
    return {
        "success": res.success,
        "error": res.error,
        "usage": res.metadata,
        "parsed": parsed,
        "output": json.dumps(parsed) if parsed else "",
        "production_gate_errors": production_gate_errors,
    }


def _judge_pass2_pair(key, prompt, challenger, incumbent, judge_cfg, ledger):
    cand_is_a = int(hashlib.md5(key.encode()).hexdigest(), 16) % 2 == 0
    a, b = (
        (challenger["output"], incumbent["output"])
        if cand_is_a
        else (incumbent["output"], challenger["output"])
    )
    evidence = BATCHED_VALIDATION_SYSTEM_PROMPT + "\n\n" + prompt
    res = invoke_tracked(
        ledger,
        judge_cfg,
        JUDGE_PROMPT.format(evidence=evidence, a=a, b=b),
        archive_key=f"chal_p2j:{key}",
    )
    value = res.parsed or _parse(res.raw_output)
    if not isinstance(value, dict) or "winner" not in value:
        return None
    winner = str(value["winner"]).upper().strip()
    verdict = (
        "tie"
        if winner == "TIE"
        else "challenger"
        if (winner == "A") == cand_is_a
        else "incumbent"
    )
    return {
        "case_id": key,
        "verdict": verdict,
        "usage": res.metadata,
        "reason": value.get("decisive_reason", value.get("reason", "")),
        "judgment": value,
    }


def run_pass2_live(
    cfg_challenger, cfg_incumbent, judge_cfg, ledger, on_progress=None
) -> dict:
    pidns = [
        line.strip()
        for line in (FIXTURES / "p2_pidns.txt").read_text().splitlines()
        if line.strip()
    ]
    conn = _db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    rows, verdicts = [], []
    result = {
        "dataset_mode": "live_context_from_frozen_selectors",
        "n_parcels": len(pidns),
        "judged": 0,
        "judge_mode": "llm_pairwise" if judge_cfg else "not_run",
        "tally": {},
        "case_rows": rows,
        "judgments": verdicts,
    }
    for pidn in pidns:
        context = gather_parcel_batch_context(cur, pidn)
        if not context.get("signals"):
            continue
        prompt = build_batched_signal_prompt(context)
        challenger = _pass2_prompt_one(
            cfg_challenger, prompt, context, pidn, ledger
        )
        incumbent = _pass2_prompt_one(
            cfg_incumbent, prompt, context, pidn, ledger
        )
        row = {
            "pidn": pidn,
            "context_sha256": canonical_context_hash(context),
            "context": context,
            "prompt": prompt,
            "challenger": challenger,
            "incumbent": incumbent,
        }
        rows.append(row)
        if judge_cfg and challenger["success"] and incumbent["success"]:
            judgment = _judge_pass2_pair(
                pidn, prompt, challenger, incumbent, judge_cfg, ledger
            )
            if judgment:
                verdicts.append(judgment)
        tally = defaultdict(int)
        for verdict in verdicts:
            tally[verdict["verdict"]] += 1
        result["judged"] = len(verdicts)
        result["tally"] = dict(tally)
        if on_progress:
            on_progress(result)
        print(f"  p2 {pidn} chal={challenger['success']} inc={incumbent['success']}")
    conn.close()
    return result


def run_pass2_frozen(
    cfg_challenger,
    cfg_incumbent,
    judge_cfg,
    ledger,
    on_progress=None,
    fixture_path: Path | None = None,
    workers: int = 1,
) -> dict:
    fixture_path = fixture_path or FIXTURES / "p2_frozen.json"
    cases = load_frozen_cases(fixture_path)
    rows, verdicts = [], []
    is_gold = _is_default_pass2_fixture(fixture_path)
    result = {
        "dataset_mode": "frozen_gold" if is_gold else "frozen_rubric",
        "fixture_file": str(fixture_path),
        "scoring_version": PASS2_SCORING_VERSION,
        "n_parcels": len(cases),
        "judged": 0,
        "judge_mode": "llm_pairwise_diagnostic" if judge_cfg else "not_run",
        "tally": {},
        "case_rows": rows,
        "judgments": verdicts,
    }

    def complete_case(case, challenger, incumbent):
        context = case["context"]
        prompt = build_batched_signal_prompt(context)
        challenger["score"] = enforce_production_gate(
            score_pass2(challenger["parsed"], case),
            challenger["production_gate_errors"],
        )
        incumbent["score"] = enforce_production_gate(
            score_pass2(incumbent["parsed"], case),
            incumbent["production_gate_errors"],
        )
        row = {
            "case_id": case["id"],
            "case_type": case["case_type"],
            "context_sha256": case["context_sha256"],
            "challenger": challenger,
            "incumbent": incumbent,
        }
        rows.append(row)
        if judge_cfg and challenger["success"] and incumbent["success"]:
            judgment = _judge_pass2_pair(
                case["id"], prompt, challenger, incumbent, judge_cfg, ledger
            )
            if judgment:
                verdicts.append(judgment)
        tally = defaultdict(int)
        for verdict in verdicts:
            tally[verdict["verdict"]] += 1
        result["judged"] = len(verdicts)
        result["tally"] = dict(tally)
        result["gold"] = summarize_pass2_gold(rows)
        if on_progress:
            on_progress(result)
        print(
            f"  p2 {case['id']} "
            f"chal={'PASS' if challenger['score']['gold_pass'] else 'FAIL'} "
            f"inc={'PASS' if incumbent['score']['gold_pass'] else 'FAIL'}"
        )

    if workers <= 1:
        for case in cases:
            context = case["context"]
            prompt = build_batched_signal_prompt(context)
            challenger = _pass2_prompt_one(
                cfg_challenger, prompt, context, case["id"], ledger
            )
            incumbent = _pass2_prompt_one(
                cfg_incumbent, prompt, context, case["id"], ledger
            )
            complete_case(case, challenger, incumbent)
    else:
        completed: dict[int, dict[str, dict]] = defaultdict(dict)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {}
            for index, case in enumerate(cases):
                context = case["context"]
                prompt = build_batched_signal_prompt(context)
                for side, config in (
                    ("challenger", cfg_challenger),
                    ("incumbent", cfg_incumbent),
                ):
                    future = executor.submit(
                        _pass2_prompt_one,
                        config,
                        prompt,
                        context,
                        case["id"],
                        ledger,
                    )
                    futures[future] = (index, side)
            for future in as_completed(futures):
                index, side = futures[future]
                completed[index][side] = future.result()
                pair = completed[index]
                if len(pair) == 2:
                    complete_case(cases[index], pair["challenger"], pair["incumbent"])
        rows.sort(key=lambda row: row["case_id"])
    return result


def summarize_pass2_gold(rows: list[dict]) -> dict:
    """Expose case, signal, decision, and evidence metrics separately."""
    summary = {"n": len(rows)}
    for side in ("challenger", "incumbent"):
        scores = [row[side]["score"] for row in rows]
        signal_scores = [
            score
            for case_score in scores
            for score in case_score.get("signal_scores", {}).values()
        ]
        matched = sum(
            score.get("matched_required_fact_groups", 0) for score in signal_scores
        )
        fact_count = sum(
            score.get("required_fact_group_count", 0) for score in signal_scores
        )
        summary.update(
            {
                f"{side}_cases_passed": sum(
                    bool(score.get("gold_pass")) for score in scores
                ),
                f"{side}_signals_passed": sum(
                    bool(score.get("pass")) for score in signal_scores
                ),
                f"{side}_status_passed": sum(
                    bool(score.get("status_pass")) for score in signal_scores
                ),
                f"{side}_significance_passed": sum(
                    bool(score.get("significance_pass")) for score in signal_scores
                ),
                f"{side}_calibration_passed": sum(
                    bool(score.get("status_pass"))
                    and bool(score.get("significance_pass"))
                    for score in signal_scores
                ),
                f"{side}_decisions_passed": sum(
                    bool(score.get("decision_pass")) for score in signal_scores
                ),
                f"{side}_forbidden_claim_signals": sum(
                    bool(score.get("forbidden_claims_found")) for score in signal_scores
                ),
                f"{side}_signals_n": len(signal_scores),
                f"{side}_fact_groups_matched": matched,
                f"{side}_fact_groups_n": fact_count,
                f"{side}_fact_recall": (
                    round(matched / fact_count, 3) if fact_count else 0.0
                ),
            }
        )
    return summary


def run_pass3_frozen(cfg, ledger, on_progress=None) -> list[dict]:
    cases = load_frozen_cases(FIXTURES / "p3_investigation_frozen.json")
    rows = []
    for case in cases:
        prompt = build_brief_generation_prompt(case["context"])
        t0 = time.time()
        res = invoke_tracked(ledger, cfg, prompt, archive_key=f"chal_p3:{case['id']}")
        parsed = parse_brief_output(res.parsed or _parse(res.raw_output) or {})
        allowed_signal_keys = {
            signal["signal_key"]
            for signal in case["context"].get("validated_signals", [])
            if signal.get("signal_key")
        }
        score = enforce_production_gate(
            score_pass3(parsed, case),
            validate_parcel_brief_citations(parsed, allowed_signal_keys),
        )
        row = {
            "case_id": case["id"],
            "case_type": case["case_type"],
            "dataset_mode": "frozen_gold",
            "context_sha256": case["context_sha256"],
            "success": res.success,
            "error": res.error,
            "elapsed_s": round(time.time() - t0, 1),
            "usage": res.metadata,
            **score,
        }
        rows.append(row)
        if on_progress:
            on_progress(rows)
        print(
            f"  p3 {case['id']} gold="
            f"{'PASS' if score['gold_pass'] else 'FAIL'} {row['elapsed_s']}s"
        )
    return rows


def _summarize(out: dict) -> dict:
    s: dict = {}
    if "pass0" in out:
        rows = out["pass0"]
        s["p0"] = {
            "ok": sum(r["success"] for r in rows),
            "n": len(rows),
            "gold_passed": sum(1 for r in rows if r["gold_pass"]),
            "gold_documents": len(rows),
            "matched_records": sum(len(r["matched_records"]) for r in rows),
            "expected_records": sum(r["expected_count"] for r in rows),
            "extra_extractions": sum(r["extra_extractions"] for r in rows),
        }
    if "pass1" in out:
        rows = out["pass1"]
        if rows and rows[0].get("dataset_mode") == "frozen_gold":
            s["p1"] = {
                "ok": sum(r["success"] for r in rows),
                "n": len(rows),
                "gold_passed": sum(r["gold_pass"] for r in rows),
            }
        else:
            s["p1"] = {
                "ok": sum(r["success"] for r in rows),
                "n": len(rows),
                "json": sum(r["json_valid"] for r in rows),
                "hallucinated_pidns": sum(
                    r.get("hallucinated_pidns") or 0 for r in rows
                ),
                "abstained": sum(r.get("n_abstained") or 0 for r in rows),
                "rejected": sum(r.get("n_rejected") or 0 for r in rows),
                "avg_s": round(
                    sum(r["elapsed_s"] for r in rows) / max(len(rows), 1), 1
                ),
            }
    if "pass2" in out:
        p2 = out["pass2"]
        s["p2"] = p2.get("gold", {}) | p2["tally"] | {"judged": p2["judged"]}
    if "pass3" in out:
        rows = out["pass3"]
        s["p3"] = {
            "ok": sum(r["success"] for r in rows),
            "n": len(rows),
            "gold_passed": sum(r["gold_pass"] for r in rows),
        }
    return s


def _write_checkpoint(path: Path, out: dict, spend_before: float, ledger) -> None:
    out["spend_usd"] = round(ledger.spent_usd - spend_before, 9)
    out["budget"] = ledger.summary()
    out["summary"] = _summarize(out)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(out, indent=1, default=str))
    temporary.replace(path)


def run_one(
    model: str,
    passes: set,
    quant,
    effort,
    judge_model,
    ledger,
    *,
    live=False,
    pass2_fixture: Path | None = None,
    workers: int = 1,
) -> dict:
    spend_before = ledger.spent_usd
    expanded = pass2_fixture is not None and not _is_default_pass2_fixture(
        pass2_fixture
    )
    mode = "live_shadow" if live else "frozen_rubric" if expanded else "frozen_gold"
    out: dict = {
        "challenger": model,
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "dataset_mode": mode,
    }
    RESULTS.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_file = RESULTS / f"challenger_{model.replace('/', '_')}_{mode}_{ts}.json"

    def checkpoint(key, value):
        out[key] = value
        _write_checkpoint(out_file, out, spend_before, ledger)

    _write_checkpoint(out_file, out, spend_before, ledger)
    if "0" in passes:
        print(f"Pass 0 — {model} on frozen PDF corpus")
        out["pass0"] = run_pass0(
            _mk_config(model, 0, max_tokens=8192, quant=quant),
            ledger,
            lambda rows: checkpoint("pass0", rows),
        )
    if "1" in passes:
        print(f"Pass 1 — {model} on {mode}")
        runner = run_pass1_live if live else run_pass1_frozen
        out["pass1"] = runner(
            _mk_config(model, 1, max_tokens=8192, effort=effort, quant=quant),
            ledger,
            lambda rows: checkpoint("pass1", rows),
        )
    if "2" in passes:
        incumbent = resolve_pass_model(2)
        judge_note = (
            f" judged by {judge_model}" if judge_model else " (no automated judge)"
        )
        print(f"Pass 2 — {model} vs incumbent {incumbent} on {mode}{judge_note}")
        configs = (
            _mk_config(model, 2, max_tokens=4096, effort=effort, quant=quant),
            _mk_config(incumbent, 2, max_tokens=4096, effort="low"),
            _mk_judge_config(judge_model) if judge_model else None,
            ledger,
        )
        if live:
            out["pass2"] = run_pass2_live(
                *configs, on_progress=lambda value: checkpoint("pass2", value)
            )
        else:
            out["pass2"] = run_pass2_frozen(
                *configs,
                on_progress=lambda value: checkpoint("pass2", value),
                fixture_path=pass2_fixture,
                workers=workers,
            )
        print(f"  verdict tally: {out['pass2']['tally']}")
    if "3" in passes:
        if live:
            raise ValueError("Pass 3 has no live shadow lane; use frozen fixtures")
        print(f"Pass 3 — {model} on frozen_gold")
        out["pass3"] = run_pass3_frozen(
            _mk_config(model, 3, max_tokens=2048, effort=effort, quant=quant),
            ledger,
            lambda rows: checkpoint("pass3", rows),
        )
    _write_checkpoint(out_file, out, spend_before, ledger)
    print(f"Wrote {out_file}\n")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--models",
        "--model",
        dest="models",
        required=True,
        help="Comma-separated OpenRouter slugs to evaluate.",
    )
    ap.add_argument("--passes", default="0")
    ap.add_argument(
        "--live",
        action="store_true",
        help="Use the mutable current-DB Pass 1/2 drift lane instead of frozen gold.",
    )
    ap.add_argument(
        "--judge-model",
        default=None,
        help=(
            "Optional pairwise Pass 2 judge slug. Omit to store both outputs "
            "without treating another LLM as ground truth. Current evaluated "
            f"choice: {RECOMMENDED_JUDGE}."
        ),
    )
    ap.add_argument(
        "--quantizations",
        default=None,
        help="Provider quantization allowlist, applied to every model.",
    )
    ap.add_argument("--reasoning-effort", default=None)
    ap.add_argument(
        "--pass2-fixture",
        type=Path,
        default=FIXTURES / "p2_frozen.json",
        help="Frozen Pass 2 fixture file; expanded rubric corpora remain diagnostic.",
    )
    ap.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Concurrent frozen Pass 2 calls; budget reservations remain thread-safe.",
    )
    ap.add_argument(
        "--max-cost-usd",
        type=float,
        default=1.0,
        help="Reserve maximum call charges before dispatch; default run ceiling: 1.00.",
    )
    args = ap.parse_args()

    if not os.environ.get("OPENROUTER_API_KEY"):
        key_file = Path("~/.config/openrouter/key").expanduser()
        if key_file.exists():
            os.environ["OPENROUTER_API_KEY"] = key_file.read_text().strip()
        else:
            sys.exit("OPENROUTER_API_KEY not set")

    quant = (
        tuple(q.strip() for q in args.quantizations.split(",") if q.strip())
        if args.quantizations
        else None
    )
    passes = {p.strip() for p in args.passes.split(",")}
    unsupported = passes - {"0", "1", "2", "3"}
    if unsupported:
        sys.exit(f"Unsupported pass value(s): {', '.join(sorted(unsupported))}")
    if args.live and "3" in passes:
        sys.exit("Pass 3 has no live shadow lane; omit --live or Pass 3")
    if args.live and not _is_default_pass2_fixture(args.pass2_fixture):
        sys.exit("--pass2-fixture cannot be combined with --live")
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    if args.max_cost_usd <= 0:
        sys.exit("--max-cost-usd must be positive")
    if args.workers <= 0:
        sys.exit("--workers must be positive")
    ledger = EvalCostLedger(max_cost_usd=args.max_cost_usd)

    summaries = {}
    try:
        for model in models:
            summaries[model] = run_one(
                model,
                passes,
                quant,
                args.reasoning_effort,
                args.judge_model,
                ledger,
                live=args.live,
                pass2_fixture=args.pass2_fixture,
                workers=args.workers,
            )["summary"]
    except (EvalCostLimitExceeded, EvalCostUnavailable) as exc:
        sys.exit(f"Stopped paid evaluation: {exc}")

    print("=" * 70)
    print("CROSS-MODEL SUMMARY")
    for model, s in summaries.items():
        print(f"\n{model}")
        for p, v in s.items():
            print(f"  {p}: {v}")
    print(f"\nBUDGET: {ledger.summary()}")


if __name__ == "__main__":
    main()
