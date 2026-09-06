"""Rule-first, judge-assisted resolution of quarantined contradictions.

A contradiction means the model changed its semantic decision on evidence whose
hash did not change. Until now every one of those waited for a person at the
CLI. That does not scale: a prompt improvement that changes ten percent of
Pass 2 decisions is hundreds of manual adjudications.

Policy (see ``docs/operations/intelligence-rollout.md``):

* **Consequential flips always wait for a person.** Any entity membership merge or split, a proceeding decision flipping
  between approved and denied, a signal crossing the medium-or-high brief
  eligibility boundary, or a brief moving between investigate and insufficient
  evidence (including historical pursue/pass/none labels).
* **Version upgrades default to the challenger.** When the challenger came
  from a different model or prompt version than the incumbent, the newer
  reviewed code is presumed better.
* **Same-version flips default to the incumbent.** Identical model, prompt,
  and evidence means sampling noise; the serving projection stays put.
* **A judge model, when configured, must not disagree.** The judge either
  confirms the rule default (or is unclear) and the contradiction resolves,
  or disagrees and a person reviews it with the judge's reasoning attached.

Every assessment is written to ``meta.intelligence_auto_resolutions``; every
resolution goes through the same atomic path the CLI uses.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any

from countyiq.lib.intelligence_integrity import (
    canonical_json,
    signal_validation_consequence,
)
from countyiq.lib.intelligence_resolution import (
    ContradictionResolutionError,
    get_contradiction,
    list_unresolved_contradictions,
    resolve_contradiction,
)

_ORGANIZATION_TYPES = {"business", "trust", "government"}


@dataclass(frozen=True)
class FlipAssessment:
    output_kind: str
    consequential: bool
    version_upgrade: bool
    reasons: list[str] = field(default_factory=list)

    @property
    def rule_default(self) -> str:
        return "accept_challenger" if self.version_upgrade else "accept_prior"


@dataclass(frozen=True)
class AutoResolutionOutcome:
    contradiction_id: int
    outcome: str  # auto_resolved | queued_consequential | queued_disagreement | queued_judge_unavailable | queued_resolution_refused
    resolution: str | None = None
    rationale: str = ""
    assessment: FlipAssessment | None = None

    @property
    def resolved(self) -> bool:
        return self.outcome == "auto_resolved"


def auto_resolution_enabled() -> bool:
    value = (
        os.environ.get("COUNTYIQ_AUTO_RESOLVE_CONTRADICTIONS", "true").strip().lower()
    )
    return value in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def _entity_kind(name: str) -> str:
    from countyiq.assets.enrichment.owners import classify_entity

    kind = classify_entity(name)
    return (
        "person"
        if kind == "person"
        else ("organization" if kind in _ORGANIZATION_TYPES else "unknown")
    )


def _entity_groups(payload: dict) -> list[frozenset[str]]:
    groups = []
    for entity in payload.get("entities", []) or []:
        members = entity.get("member_names") if isinstance(entity, dict) else None
        if isinstance(members, list):
            names = frozenset(
                str(name).strip() for name in members if str(name).strip()
            )
            if names:
                groups.append(names)
    return groups


def _grouped_pairs(groups: list[frozenset[str]]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for group in groups:
        ordered = sorted(group)
        for i, a in enumerate(ordered):
            for b in ordered[i + 1 :]:
                pairs.add((a, b))
    return pairs


def _assess_entities(prior: dict, challenger: dict) -> list[str]:
    changed = _grouped_pairs(_entity_groups(prior)) ^ _grouped_pairs(
        _entity_groups(challenger)
    )
    reasons = []
    for a, b in sorted(changed):
        reasons.append(f"identity membership changed: {a!r} <> {b!r}")
    return reasons


def _matter_key(extraction: dict) -> tuple[str, ...]:
    return tuple(
        str(extraction.get(key) or "").strip().casefold()
        for key in (
            "extraction_type",
            "applicant_name",
            "parcel_reference",
            "project_name",
        )
    )


def _assess_proceeding(prior: dict, challenger: dict) -> list[str]:
    def decisions(payload: dict) -> dict[tuple[str, ...], str]:
        return {
            _matter_key(item): str(item.get("decision") or "").strip().lower()
            for item in payload.get("extractions", []) or []
            if isinstance(item, dict)
        }

    before, after = decisions(prior), decisions(challenger)
    reasons = []
    for key in before.keys() & after.keys():
        if {before[key], after[key]} == {"approved", "denied"}:
            reasons.append(
                f"decision flipped {before[key]} -> {after[key]} for {key[1] or key[0]}"
            )
    return reasons


def _assess_signals(prior: dict, challenger: dict) -> list[str]:
    before = {
        item["signal_key"]: item["serving_band"]
        for item in signal_validation_consequence(prior)
    }
    after = {
        item["signal_key"]: item["serving_band"]
        for item in signal_validation_consequence(challenger)
    }
    reasons = []
    for key in before.keys() & after.keys():
        before_eligible = before[key] in {"high", "medium"}
        after_eligible = after[key] in {"high", "medium"}
        if before_eligible != after_eligible:
            reasons.append(
                f"{key} crossed the brief-eligibility boundary "
                f"({before[key]} -> {after[key]})"
            )
    return reasons


def _assess_field_flip(
    prior: dict,
    challenger: dict,
    field_name: str,
    actionable: set[str],
    insufficient: set[str],
) -> list[str]:
    before = str(prior.get(field_name) or "").strip()
    after = str(challenger.get(field_name) or "").strip()
    if (before in actionable and after in insufficient) or (
        after in actionable and before in insufficient
    ):
        return [f"{field_name} flipped {before} -> {after}"]
    return []


def classify_flip(
    *,
    output_kind: str,
    prior_payload: Any,
    challenger_payload: Any,
    prior_input_hash: str | None,
    challenger_input_hash: str | None,
) -> FlipAssessment:
    """Decide whether a same-evidence flip needs a person, and the rule default."""

    prior = prior_payload if isinstance(prior_payload, dict) else {}
    challenger = challenger_payload if isinstance(challenger_payload, dict) else {}
    if output_kind == "entity_verification":
        reasons = _assess_entities(prior, challenger)
    elif output_kind == "proceeding_extraction":
        reasons = _assess_proceeding(prior, challenger)
    elif output_kind == "signal_validation":
        reasons = _assess_signals(prior, challenger)
    elif output_kind == "parcel_brief":
        reasons = _assess_field_flip(
            prior,
            challenger,
            "recommendation",
            {"pursue_now", "investigate"},
            {"pass", "insufficient_evidence"},
        )
    elif output_kind == "owner_brief":
        reasons = _assess_field_flip(
            prior,
            challenger,
            "recommendation",
            {"pursue_acquisition", "investigate"},
            {"none", "insufficient_evidence"},
        )
    else:
        reasons = [f"unknown output kind {output_kind}"]
    version_upgrade = bool(
        prior_input_hash
        and challenger_input_hash
        and prior_input_hash != challenger_input_hash
    )
    return FlipAssessment(
        output_kind=output_kind,
        consequential=bool(reasons),
        version_upgrade=version_upgrade,
        reasons=reasons,
    )


def decide(
    assessment: FlipAssessment, judge_winner: str | None, judge_available: bool
) -> str:
    """Map an assessment plus judge verdict to an outcome name."""

    if assessment.consequential:
        return "queued_consequential"
    if not judge_available:
        return "auto_resolved"
    if judge_winner is None:
        return "queued_judge_unavailable"
    expected = (
        "challenger" if assessment.rule_default == "accept_challenger" else "prior"
    )
    if judge_winner in {expected, "unclear"}:
        return "auto_resolved"
    return "queued_disagreement"


# ---------------------------------------------------------------------------
# Evidence gathering for the judge
# ---------------------------------------------------------------------------


def _gather_evidence_text(
    database, contradiction: dict, prior: dict, challenger: dict
) -> str:
    """Rebuild the exact user-facing evidence block each pass showed the model."""

    kind = contradiction["output_kind"]
    subject_key = contradiction["subject_key"]
    with database.dict_cursor() as cur:
        if kind == "proceeding_extraction":
            cur.execute(
                "SELECT raw_text FROM staging.public_proceedings WHERE id = %s AND valid_to IS NULL",
                (int(subject_key.split(":", 1)[1]),),
            )
            row = cur.fetchone()
            return (row["raw_text"] if row else "") or ""
        if kind == "entity_verification":
            from countyiq.lib.intelligence_resolution import _candidate_names
            from countyiq.lib.pass1_entity_verification import (
                build_entity_cluster_prompt,
                gather_cluster_records,
            )

            names = _candidate_names(prior, challenger)
            return (
                build_entity_cluster_prompt(gather_cluster_records(cur, names))
                if names
                else ""
            )
        if kind == "signal_validation":
            from countyiq.lib.pass2_batched_validation import (
                build_batched_signal_prompt,
                gather_parcel_batch_context,
            )

            return build_batched_signal_prompt(
                gather_parcel_batch_context(cur, subject_key)
            )
        if kind == "parcel_brief":
            from countyiq.lib.pass3_brief_generation import (
                build_brief_generation_prompt,
                gather_brief_context,
            )

            return build_brief_generation_prompt(gather_brief_context(cur, subject_key))
        if kind == "owner_brief":
            from countyiq.lib.pass3_owner_briefs import (
                OWNER_PORTFOLIO_QUERY,
                PORTFOLIO_EVIDENCE_QUERY,
                build_owner_rollup_prompt,
            )

            cur.execute(
                "SELECT owner_id FROM public.owner_briefs WHERE active_inference_id = %s",
                (contradiction["prior_inference_id"],),
            )
            projection = cur.fetchone()
            if projection is None:
                return ""
            cur.execute(OWNER_PORTFOLIO_QUERY, {"owner_id": projection["owner_id"]})
            owner = cur.fetchone()
            if owner is None:
                return ""
            owner = dict(owner)
            cur.execute(PORTFOLIO_EVIDENCE_QUERY, {"pidns": owner["pidns"] or []})
            return build_owner_rollup_prompt(
                owner, [dict(row) for row in cur.fetchall()]
            )
    return ""


def _decision_summary(kind: str, payload: Any) -> Any:
    """The parts of a payload a judge should weigh: decisions plus reasoning."""

    if not isinstance(payload, dict):
        return payload
    if kind == "signal_validation":
        return {
            "validations": [
                {
                    k: item.get(k)
                    for k in (
                        "signal_key",
                        "validation_status",
                        "adjusted_significance",
                        "reasoning",
                    )
                }
                for item in payload.get("validations", [])
                if isinstance(item, dict)
            ],
            "cross_signal_insight": payload.get("cross_signal_insight"),
        }
    if kind == "entity_verification":
        return {
            "entities": [
                {
                    k: item.get(k)
                    for k in (
                        "canonical_name",
                        "member_names",
                        "entity_type",
                        "reasoning",
                    )
                }
                for item in payload.get("entities", [])
                if isinstance(item, dict)
            ],
            "rejected_matches": payload.get("rejected_matches"),
            "abstentions": payload.get("abstentions"),
        }
    if kind == "proceeding_extraction":
        return {
            "extractions": [
                {
                    k: item.get(k)
                    for k in (
                        "extraction_type",
                        "applicant_name",
                        "parcel_reference",
                        "project_name",
                        "decision",
                        "supporting_text",
                    )
                }
                for item in payload.get("extractions", [])
                if isinstance(item, dict)
            ]
        }
    if kind == "parcel_brief":
        return {
            k: payload.get(k)
            for k in (
                "recommendation",
                "urgency",
                "assessment",
                "assessment_reasoning",
                "top_signal_key",
                "top_risk",
                "evidence_strength",
            )
        }
    if kind == "owner_brief":
        return {
            k: payload.get(k)
            for k in (
                "portfolio_strategy",
                "recommendation",
                "urgency",
                "key_pattern",
                "top_risk",
                "evidence_strength",
            )
        }
    return payload


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def _record_assessment(
    database,
    *,
    contradiction_id: int,
    assessment: FlipAssessment,
    judge,
    outcome: str,
    resolution_id: int | None,
) -> None:
    with database.transaction() as cur:
        cur.execute(
            """
            INSERT INTO meta.intelligence_auto_resolutions (
                contradiction_id, assessment, consequential, version_upgrade,
                rule_default, judge_model, judge_verdict, judge_confidence,
                judge_reason, outcome, resolution_id
            )
            VALUES (%s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                contradiction_id,
                canonical_json(asdict(assessment)),
                assessment.consequential,
                assessment.version_upgrade,
                assessment.rule_default,
                judge.model if judge else None,
                judge.winner if judge else None,
                judge.confidence if judge else None,
                judge.reason if judge else None,
                outcome,
                resolution_id,
            ),
        )


def auto_resolve_contradiction(
    database, contradiction_id: int, log=None
) -> AutoResolutionOutcome:
    """Apply the policy to one freshly quarantined contradiction."""

    from countyiq.lib import intelligence_judge

    if not auto_resolution_enabled():
        return AutoResolutionOutcome(
            contradiction_id,
            "queued_consequential",
            rationale="auto-resolution disabled",
        )

    detail = get_contradiction(database, contradiction_id)
    if detail is None or detail.get("resolution") is not None:
        return AutoResolutionOutcome(
            contradiction_id, "auto_resolved", rationale="already resolved"
        )
    contradiction, prior, challenger = (
        detail["contradiction"],
        detail["prior"],
        detail["challenger"],
    )

    assessment = classify_flip(
        output_kind=contradiction["output_kind"],
        prior_payload=prior.get("payload"),
        challenger_payload=challenger.get("payload"),
        prior_input_hash=prior.get("input_hash"),
        challenger_input_hash=challenger.get("input_hash"),
    )

    judge = None
    judge_available = intelligence_judge.judge_enabled()
    if judge_available:
        try:
            judge = intelligence_judge.ask_judge(
                contradiction_id=contradiction_id,
                output_kind=contradiction["output_kind"],
                evidence_text=_gather_evidence_text(
                    database, contradiction, prior, challenger
                ),
                prior_decision=_decision_summary(
                    contradiction["output_kind"], prior.get("payload")
                ),
                challenger_decision=_decision_summary(
                    contradiction["output_kind"], challenger.get("payload")
                ),
            )
        except Exception as exc:  # judge problems must never block the pass
            if log is not None:
                log.warning(
                    "Judge unavailable for contradiction %s: %s", contradiction_id, exc
                )
            judge = None

    outcome = decide(assessment, judge.winner if judge else None, judge_available)
    resolution_id = None
    resolution = None
    rationale = ""
    if outcome == "auto_resolved":
        resolution = assessment.rule_default
        basis = (
            "newer reviewed model/prompt version"
            if assessment.version_upgrade
            else "same-version sampling flip; incumbent retained"
        )
        rationale = f"auto-resolution: {basis}; non-consequential flip"
        if judge is not None:
            rationale += f"; judge {judge.model} said {judge.winner} ({judge.confidence:.2f}): {judge.reason}"
        try:
            result = resolve_contradiction(
                database,
                contradiction_id=contradiction_id,
                resolution=resolution,
                resolved_by=f"auto:rule{'+judge' if judge else ''}",
                rationale=rationale,
                expected_source_hash=contradiction["source_hash"],
                decision_origin="auto_resolution",
            )
            resolution_id = result.resolution_id
        except (ContradictionResolutionError, ValueError) as exc:
            # The resolver re-checks the live source hash and supersession;
            # if either moved, a person (or a fresh pass run) must look.
            outcome = "queued_resolution_refused"
            resolution = None
            rationale = f"auto-resolution refused: {exc}"
            if log is not None:
                log.warning(
                    "Contradiction %s left for review: %s", contradiction_id, exc
                )
    elif outcome == "queued_consequential":
        rationale = "; ".join(assessment.reasons) or "consequential flip"
    elif outcome == "queued_disagreement":
        rationale = f"judge {judge.model} preferred {judge.winner} against rule default {assessment.rule_default}: {judge.reason}"
    else:
        rationale = "judge configured but unavailable; left for review"

    _record_assessment(
        database,
        contradiction_id=contradiction_id,
        assessment=assessment,
        judge=judge,
        outcome=outcome,
        resolution_id=resolution_id,
    )
    return AutoResolutionOutcome(
        contradiction_id=contradiction_id,
        outcome=outcome,
        resolution=resolution,
        rationale=rationale,
        assessment=assessment,
    )


def auto_resolve_queue(database, *, limit: int = 500, log=None) -> dict[str, int]:
    """Apply the policy to the existing backlog; returns counts by outcome."""

    counts: dict[str, int] = {}
    for item in list_unresolved_contradictions(database, limit=limit):
        outcome = auto_resolve_contradiction(
            database, int(item["contradiction_id"]), log
        )
        counts[outcome.outcome] = counts.get(outcome.outcome, 0) + 1
    return counts
