"""Review bounded contexts and reconcile them into one parent partition.

Overlap components are requests for another complete review, never inferred
identity unions. Nothing in this module writes a projection or a pass status.
"""

from __future__ import annotations

import json
from copy import deepcopy

from countyiq.lib.entity_context_plan import EntityContextPlan, make_review_unit
from countyiq.lib.intelligence_common import compute_input_hash
from countyiq.lib.intelligence_integrity import validate_entity_membership
from countyiq.lib.pass1_entity_verification import (
    entity_trial_majority_decided,
    merge_entity_trial_partitions,
    parse_entity_verification_output,
)

RECONCILIATION_VERSION = "bounded-parent-reconciliation-v1"


class EntityReviewInvalid(ValueError):
    """A proposed partition cannot safely supply the parent projection."""


def _members(entity):
    return frozenset(entity["member_names"])


def _question_names(question, kind):
    if kind == "rejected_matches":
        return frozenset((question["name_a"], question["name_b"]))
    return frozenset(question["names"])


def _unique(rows):
    keyed = {json.dumps(row, sort_keys=True, default=str): row for row in rows}
    return [keyed[key] for key in sorted(keyed)]


def validate_review_partition(partition, source, names, anchors):
    errors = validate_entity_membership(partition, source, list(names))
    groups = [_members(entity) for entity in partition.get("entities", [])]
    for members in groups:
        numbers = {anchors[name][1] for name in members if name in anchors}
        if len(numbers) > 1:
            errors.append("Entity combines distinct proven registration numbers")
    for kind in ("rejected_matches", "abstentions"):
        for question in partition.get(kind, []):
            question_names = _question_names(question, kind)
            if question_names and any(question_names <= group for group in groups):
                errors.append(f"Entity contains an unresolved {kind} decision")
    return errors


def review_unit(unit, config, invoke, anchors, *, target_trials=3, adaptive=True):
    """Validate every vote, retaining actual trial receipts for resumable review."""
    validated = []
    receipts = []
    failures = []
    for index in range(target_trials):
        result = invoke(
            config,
            unit.prompt,
            retries=1,
            archive_key=f"{unit.key}:trial-{index}",
        )
        if not result.success:
            failures.append(
                {"trial": index, "error": result.error, "metadata": result.metadata}
            )
            continue
        parsed = parse_entity_verification_output(result.parsed or {})
        errors = (
            [parsed["error"]]
            if "error" in parsed
            else validate_review_partition(parsed, unit.source, unit.names, anchors)
        )
        if errors:
            failures.append(
                {
                    "trial": index,
                    "errors": errors,
                    "parsed": result.parsed,
                    "metadata": result.metadata,
                }
            )
            continue
        validated.append(parsed)
        receipts.append({"trial": index, "metadata": result.metadata})
        if adaptive and entity_trial_majority_decided(
            validated, list(unit.names), target_trials=target_trials
        ):
            break
    partition = merge_entity_trial_partitions(
        validated, list(unit.names), target_trials=target_trials
    )
    errors = validate_review_partition(partition, unit.source, unit.names, anchors)
    if errors:
        raise EntityReviewInvalid("; ".join(errors))
    return {
        "key": unit.key,
        "names": list(unit.names),
        "source_hash": compute_input_hash(unit.source),
        "partition": partition,
        "validated_trials": validated,
        "trial_receipts": receipts,
        "failed_trials": failures,
    }


def _proposal_components(partitions):
    components = []
    for partition in partitions:
        for entity in partition.get("entities", []):
            names = set(_members(entity))
            touching = [group for group in components if group & names]
            for group in touching:
                names.update(group)
                components.remove(group)
            components.append(names)
    return sorted(components, key=lambda names: sorted(names))


def reconciliation_components(partitions):
    """Find positive proposals whose membership, type or uncertainty conflicts."""
    conflicts = []
    for component in _proposal_components(partitions):
        proposals = [
            entity
            for partition in partitions
            for entity in partition.get("entities", [])
            if _members(entity) & component
        ]
        shapes = {(_members(entity), entity["entity_type"]) for entity in proposals}
        uncertain = any(
            bool(names := _question_names(question, kind)) and names <= component
            for partition in partitions
            for kind in ("rejected_matches", "abstentions")
            for question in partition.get(kind, [])
        )
        if len(shapes) > 1 or uncertain:
            conflicts.append(component)
    return conflicts


def _combine_matching_proposals(proposals):
    """Combine citations only after exact membership and type agreement."""
    representative = deepcopy(proposals[0])
    representative["confidence"] = min(item["confidence"] for item in proposals)
    representative["reasoning"] = "\n".join(
        dict.fromkeys(item["reasoning"] for item in proposals)
    )
    representative["linked_records"] = {
        kind: sorted(
            {
                identifier
                for item in proposals
                for identifier in item.get("linked_records", {}).get(kind, [])
            }
        )
        for kind in sorted(
            {kind for item in proposals for kind in item.get("linked_records", {})}
        )
    }
    representative["relationships"] = []
    return representative


def compose_parent_partition(plan, reviews, reconciliations):
    """Assemble disjoint reviewed proposals, retaining withheld relation evidence."""
    expected = {unit.key: unit for unit in plan.units}
    if len(reviews) != len(expected) or {row["key"] for row in reviews} != set(
        expected
    ):
        raise EntityReviewInvalid("Every planned unit must have exactly one review")
    for review in reviews:
        unit = expected[review["key"]]
        if review["names"] != list(unit.names) or review[
            "source_hash"
        ] != compute_input_hash(unit.source):
            raise EntityReviewInvalid(
                "Unit review is bound to different source evidence"
            )
        errors = validate_review_partition(
            review["partition"], unit.source, unit.names, plan.anchors
        )
        if errors:
            raise EntityReviewInvalid("; ".join(errors))

    originals = [row["partition"] for row in reviews]
    if plan.deterministic_partition:
        originals.insert(0, plan.deterministic_partition)
    conflicts = reconciliation_components(originals)
    if len(reconciliations) != len(conflicts) or {
        frozenset(row["names"]) for row in reconciliations
    } != {frozenset(names) for names in conflicts}:
        raise EntityReviewInvalid("Every conflicting overlap needs its complete review")
    for review in reconciliations:
        unit = reconciliation_unit(plan, review["names"])
        if review["key"] != unit.key or review["source_hash"] != compute_input_hash(
            unit.source
        ):
            raise EntityReviewInvalid("Reconciliation is bound to different evidence")
        errors = validate_review_partition(
            review["partition"], unit.source, unit.names, plan.anchors
        )
        if errors:
            raise EntityReviewInvalid("; ".join(errors))

    proposals = [
        entity
        for partition in originals
        for entity in partition.get("entities", [])
        if not any(_members(entity) & names for names in conflicts)
    ]
    for review in reconciliations:
        proposals.extend(review["partition"]["entities"])
    by_members = {}
    for entity in proposals:
        by_members.setdefault(_members(entity), []).append(entity)
    entities = [
        _combine_matching_proposals(by_members[members])
        for members in sorted(by_members, key=lambda names: sorted(names))
    ]
    result = {"entities": entities}
    for kind in ("rejected_matches", "abstentions"):
        result[kind] = _unique(
            [
                question
                for partition in originals
                for question in partition.get(kind, [])
                if not any(
                    _question_names(question, kind) <= names for names in conflicts
                )
            ]
            + [
                question
                for review in reconciliations
                for question in review["partition"].get(kind, [])
            ]
        )

    # Retain a relation only when its entire original identity survives in one
    # final group. A split origin must not lend evidence to a chosen fragment.
    withheld = []
    final_by_name = {name: entity for entity in entities for name in _members(entity)}
    relation_sources = [(partition, False) for partition in originals]
    relation_sources.extend((row["partition"], True) for row in reconciliations)
    for partition, is_reconciliation in relation_sources:
        for entity in partition.get("entities", []):
            members = _members(entity)
            origin = final_by_name.get(entity["canonical_name"])
            for relation in entity.get("relationships", []):
                target_name = relation["related_entity"]
                target = final_by_name.get(target_name)
                internal_review = any(
                    members | {target_name} <= names for names in conflicts
                )
                reason = None
                if internal_review and not is_reconciliation:
                    reason = "replaced_by_complete_overlap_review"
                elif origin is None or not members <= _members(origin):
                    reason = "original_identity_split_or_withheld"
                elif target is None:
                    reason = "target_identity_withheld"
                elif origin is target:
                    reason = "relationship_is_internal_to_final_identity"
                if reason:
                    withheld.append(
                        {
                            "origin_names": sorted(members),
                            "relationship": relation,
                            "reason": reason,
                        }
                    )
                    continue
                mapped = dict(relation, related_entity=target["canonical_name"])
                origin["relationships"].append(mapped)
    for entity in entities:
        relationships = {}
        for relation in entity["relationships"]:
            key = (relation["relationship_type"], relation["related_entity"])
            if key not in relationships:
                relationships[key] = deepcopy(relation)
            else:
                relationships[key]["evidence"] = "\n".join(
                    dict.fromkeys(
                        [relationships[key]["evidence"], relation["evidence"]]
                    )
                )
        entity["relationships"] = [relationships[key] for key in sorted(relationships)]

    errors = validate_review_partition(
        result, plan.source, plan.source["candidate_names"], plan.anchors
    )
    if errors:
        raise EntityReviewInvalid("; ".join(errors))
    result["bounded_review"] = {
        "version": RECONCILIATION_VERSION,
        "plan": plan.manifest,
        "source_hash": compute_input_hash(plan.source),
        "deterministic_partition": plan.deterministic_partition,
        "units": reviews,
        "reconciliations": reconciliations,
        "withheld_relationships": _unique(withheld),
    }
    return result


def reconciliation_unit(plan, names):
    return make_review_unit(
        f"{plan.parent_key}:{RECONCILIATION_VERSION}",
        plan.source["name_dossiers"],
        names,
        max_names=plan.manifest["max_candidate_names"],
        max_characters=plan.manifest["max_dynamic_prompt_characters"],
    )


def review_context_plan(
    plan: EntityContextPlan,
    config,
    invoke,
    *,
    target_trials=3,
    adaptive=True,
    progress=None,
):
    """Resume through immutable native receipts; publish only a complete result."""
    reviews = []
    reconciliations = []

    def evaluate(unit, phase):
        review = review_unit(
            unit,
            config,
            invoke,
            plan.anchors,
            target_trials=target_trials,
            adaptive=adaptive,
        )
        if progress is not None:
            progress(phase, unit.key)
        return review

    for unit in plan.units:
        reviews.append(evaluate(unit, "unit"))
    partitions = [row["partition"] for row in reviews]
    if plan.deterministic_partition:
        partitions.insert(0, plan.deterministic_partition)
    for names in reconciliation_components(partitions):
        reconciliations.append(
            evaluate(reconciliation_unit(plan, names), "reconciliation")
        )
    return compose_parent_partition(plan, reviews, reconciliations)
