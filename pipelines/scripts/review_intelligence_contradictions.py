"""Operate the intelligence review queue and the sampled audit.

This command uses the pipeline database writer. It never calls a pass model;
the optional judge model is invoked only by ``auto``. Resolution changes the
serving projection, so ``resolve`` requires the exact source hash and an
explicit confirmation flag.

Commands
  list      Contradictions still waiting for a person, with the reason.
  show      Complete prior/challenger evidence for one contradiction.
  resolve   Record and apply a human resolution.
  auto      Apply the rule/judge policy to the whole backlog.
  sample    Draw the weekly audit sample of accepted outputs.
  approve   Record that a sampled output is correct (emits a gold candidate).
  reject    Record that a sampled output is wrong (emits a gold candidate).
"""

from __future__ import annotations

import argparse
import json
import os
import random
from datetime import UTC, datetime
from pathlib import Path

from countyiq.lib.intelligence_autoresolve import (
    _gather_evidence_text,
    auto_resolve_queue,
)
from countyiq.lib.intelligence_resolution import (
    ContradictionResolutionError,
    get_contradiction,
    resolve_contradiction,
)
from countyiq.resources.database import make_database_resource

REPO_ROOT = Path(__file__).resolve().parents[1]


def _print_json(value) -> None:
    print(json.dumps(value, indent=2, default=str))


def _rows(database, sql: str, params=None, keys: tuple[str, ...] = ()) -> list[dict]:
    rows = database.execute(sql, params) or []
    return [
        dict(row) if isinstance(row, dict) else dict(zip(keys, row, strict=True))
        for row in rows
    ]


def cmd_list(database, args) -> int:
    queue = _rows(
        database,
        """
        SELECT contradiction_id, pass_number, output_kind, subject_key, detected_at,
               COALESCE(queue_reason, 'not_yet_assessed') AS queue_reason,
               assessment, judge_verdict, judge_reason
        FROM meta.intelligence_review_queue
        LIMIT %s
        """,
        (min(max(int(args.limit), 1), 500),),
        keys=(
            "contradiction_id", "pass_number", "output_kind", "subject_key",
            "detected_at", "queue_reason", "assessment", "judge_verdict", "judge_reason",
        ),
    )
    for item in queue:
        assessment = item.get("assessment") or {}
        if isinstance(assessment, str):
            assessment = json.loads(assessment)
        item["reasons"] = assessment.get("reasons", [])
        item.pop("assessment", None)
    _print_json(queue)
    return 0


def cmd_show(database, args) -> int:
    detail = get_contradiction(database, args.contradiction_id)
    if detail is None:
        print(f"contradiction {args.contradiction_id} not found")
        return 2
    detail["auto_resolution"] = _rows(
        database,
        """
        SELECT outcome, rule_default, judge_model, judge_verdict, judge_confidence,
               judge_reason, assessment, created_at
        FROM meta.intelligence_auto_resolutions
        WHERE contradiction_id = %s
        ORDER BY auto_resolution_id DESC
        """,
        (args.contradiction_id,),
        keys=(
            "outcome", "rule_default", "judge_model", "judge_verdict",
            "judge_confidence", "judge_reason", "assessment", "created_at",
        ),
    )
    _print_json(detail)
    return 0


def cmd_resolve(database, args) -> int:
    try:
        result = resolve_contradiction(
            database,
            contradiction_id=args.contradiction_id,
            resolution=args.decision,
            resolved_by=args.resolved_by,
            rationale=args.rationale,
            expected_source_hash=args.expected_source_hash,
        )
    except (ContradictionResolutionError, ValueError) as exc:
        print(f"resolution refused: {exc}")
        return 2
    _print_json(result.__dict__)
    return 0


def cmd_auto(database, args) -> int:
    import logging

    counts = auto_resolve_queue(database, limit=args.limit, log=logging.getLogger("countyiq.autoresolve"))
    _print_json({"processed": sum(counts.values()), "outcomes": counts})
    return 0


def _sample(database, *, pass_number: int | None, size: int, days: int) -> list[dict]:
    """Disagreement-driven sample: judged disagreements, then low-agreement, then random."""

    pass_clause = "AND h.pass_number = %(pass_number)s" if pass_number is not None else ""
    params = {"pass_number": pass_number, "days": days, "size": size}
    keys = ("inference_id", "pass_number", "output_kind", "subject_key", "sampled_reason")

    flagged = _rows(
        database,
        f"""
        SELECT h.inference_id, h.pass_number, h.output_kind, h.subject_key,
               'auto_resolved_with_judge_reservation' AS sampled_reason
        FROM meta.intelligence_auto_resolutions a
        JOIN meta.intelligence_contradiction_resolutions r ON r.resolution_id = a.resolution_id
        JOIN meta.intelligence_inference_history h ON h.inference_id = r.resolved_inference_id
        WHERE a.outcome = 'auto_resolved'
          AND (a.judge_verdict = 'unclear' OR a.judge_confidence < 0.6)
          AND a.created_at >= NOW() - MAKE_INTERVAL(days => %(days)s)
          AND NOT EXISTS (SELECT 1 FROM meta.intelligence_audit_reviews v WHERE v.inference_id = h.inference_id)
          {pass_clause}
        ORDER BY a.created_at DESC
        LIMIT %(size)s
        """,
        params,
        keys=keys,
    )
    low_agreement = _rows(
        database,
        f"""
        SELECT DISTINCT ON (h.inference_id)
               h.inference_id, h.pass_number, h.output_kind, h.subject_key,
               'low_trial_agreement' AS sampled_reason
        FROM public.evidence e
        JOIN meta.intelligence_inference_history h ON h.inference_id = e.active_inference_id
        WHERE e.trial_agreement IS NOT NULL AND e.trial_agreement < 1
          AND h.created_at >= NOW() - MAKE_INTERVAL(days => %(days)s)
          AND NOT EXISTS (SELECT 1 FROM meta.intelligence_audit_reviews v WHERE v.inference_id = h.inference_id)
          {pass_clause}
        ORDER BY h.inference_id, e.trial_agreement
        LIMIT %(size)s
        """,
        params,
        keys=keys,
    )
    accepted = _rows(
        database,
        f"""
        SELECT h.inference_id, h.pass_number, h.output_kind, h.subject_key,
               'random' AS sampled_reason
        FROM meta.intelligence_inference_history h
        WHERE h.disposition = 'accepted' AND h.decision_origin = 'model'
          AND h.created_at >= NOW() - MAKE_INTERVAL(days => %(days)s)
          AND NOT EXISTS (SELECT 1 FROM meta.intelligence_audit_reviews v WHERE v.inference_id = h.inference_id)
          {pass_clause}
        ORDER BY h.inference_id DESC
        LIMIT 2000
        """,
        params,
        keys=keys,
    )
    chosen: list[dict] = []
    seen: set[int] = set()
    for bucket in (flagged, low_agreement):
        for item in bucket:
            if item["inference_id"] not in seen and len(chosen) < size:
                seen.add(item["inference_id"])
                chosen.append(item)
    remaining = [item for item in accepted if item["inference_id"] not in seen]
    random.Random(datetime.now(UTC).date().isoformat()).shuffle(remaining)
    chosen.extend(remaining[: max(size - len(chosen), 0)])
    return chosen


def cmd_sample(database, args) -> int:
    _print_json(_sample(database, pass_number=args.pass_number, size=args.size, days=args.days))
    return 0


def _inference(database, inference_id: int) -> dict | None:
    rows = _rows(
        database,
        """
        SELECT inference_id, pass_number, output_kind, subject_key, source_hash,
               input_hash, requested_model, prompt_version, payload, evidence_refs,
               disposition, decision_origin
        FROM meta.intelligence_inference_history
        WHERE inference_id = %s
        """,
        (inference_id,),
        keys=(
            "inference_id", "pass_number", "output_kind", "subject_key", "source_hash",
            "input_hash", "requested_model", "prompt_version", "payload", "evidence_refs",
            "disposition", "decision_origin",
        ),
    )
    return rows[0] if rows else None


def _gold_candidate_dir() -> Path:
    configured = os.environ.get("COUNTYIQ_GOLD_CANDIDATE_DIR", "").strip()
    return Path(configured) if configured else REPO_ROOT / "eval" / "fixtures" / "candidates"


def _review(database, args, verdict: str) -> int:
    inference = _inference(database, args.inference_id)
    if inference is None:
        print(f"inference {args.inference_id} not found")
        return 2
    payload = inference["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    pseudo = {
        "output_kind": inference["output_kind"],
        "subject_key": inference["subject_key"],
        "prior_inference_id": inference["inference_id"],
    }
    try:
        context = _gather_evidence_text(database, pseudo, inference, inference)
    except Exception as exc:  # the review must still be recorded
        context = f"(context unavailable: {exc})"
    candidate = {
        "candidate_version": 1,
        "verdict": verdict,
        "reviewer": args.reviewer,
        "notes": args.notes,
        "reviewed_at": datetime.now(UTC).isoformat(),
        "inference": {
            key: inference[key]
            for key in (
                "inference_id", "pass_number", "output_kind", "subject_key",
                "source_hash", "input_hash", "requested_model", "prompt_version",
            )
        },
        "context": context,
        "payload": payload,
        "note": (
            "De-identify and label before promoting to a frozen fixture; see "
            "pipelines/eval/fixtures/README.md."
        ),
    }
    out_dir = _gold_candidate_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"pass{inference['pass_number']}-{inference['inference_id']}-{verdict}.json"
    path.write_text(json.dumps(candidate, indent=2, default=str) + "\n", encoding="utf-8")
    with database.transaction() as cur:
        cur.execute(
            """
            INSERT INTO meta.intelligence_audit_reviews
                (inference_id, verdict, reviewer, notes, sampled_reason, gold_candidate_path)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING review_id
            """,
            (
                inference["inference_id"], verdict, args.reviewer, args.notes,
                args.sampled_reason, str(path),
            ),
        )
        review_id = cur.fetchone()[0]
    _print_json({"review_id": review_id, "verdict": verdict, "gold_candidate": str(path)})
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    queue = sub.add_parser("list", help="Contradictions waiting for a person")
    queue.add_argument("--limit", type=int, default=50)

    show = sub.add_parser("show", help="Show complete review evidence")
    show.add_argument("contradiction_id", type=int)

    resolve = sub.add_parser("resolve", help="Record and apply a human resolution")
    resolve.add_argument("contradiction_id", type=int)
    resolve.add_argument("--decision", required=True, choices=("accept_prior", "accept_challenger", "discard_both"))
    resolve.add_argument("--resolved-by", required=True)
    resolve.add_argument("--rationale", required=True)
    resolve.add_argument("--expected-source-hash", required=True, help="Exact source_hash copied from the latest `show` output")
    resolve.add_argument("--confirm-projection-change", action="store_true", help="Required acknowledgement that the serving projection may change")

    auto = sub.add_parser("auto", help="Apply the rule/judge policy to the backlog")
    auto.add_argument("--limit", type=int, default=500)

    sample = sub.add_parser("sample", help="Draw the audit sample of accepted outputs")
    sample.add_argument("--pass-number", type=int, choices=range(4))
    sample.add_argument("--size", type=int, default=20)
    sample.add_argument("--days", type=int, default=30)

    for name, help_text in (("approve", "Record a correct sampled output"), ("reject", "Record an incorrect sampled output")):
        review = sub.add_parser(name, help=help_text)
        review.add_argument("inference_id", type=int)
        review.add_argument("--reviewer", required=True)
        review.add_argument("--notes", default="")
        review.add_argument("--sampled-reason", default=None)

    args = parser.parse_args()
    if args.command == "resolve" and not args.confirm_projection_change:
        parser.error("resolve requires --confirm-projection-change")

    database = make_database_resource()
    database.setup_for_execution(None)
    try:
        if args.command == "list":
            return cmd_list(database, args)
        if args.command == "show":
            return cmd_show(database, args)
        if args.command == "resolve":
            return cmd_resolve(database, args)
        if args.command == "auto":
            return cmd_auto(database, args)
        if args.command == "sample":
            return cmd_sample(database, args)
        if args.command == "approve":
            return _review(database, args, "approved")
        if args.command == "reject":
            return _review(database, args, "rejected")
        parser.error(f"unknown command {args.command}")
        return 2
    finally:
        database.teardown_after_execution(None)


if __name__ == "__main__":
    raise SystemExit(main())
