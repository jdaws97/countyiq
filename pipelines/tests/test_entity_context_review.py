"""Adversarial overlap decisions must not become transitive identity merges."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from countyiq.lib.entity_context_plan import (
    EntityContextLimit,
    build_context_plan,
    make_review_unit,
)
from countyiq.lib.entity_context_review import (
    EntityReviewInvalid,
    compose_parent_partition,
    reconciliation_components,
    reconciliation_unit,
    review_context_plan,
    review_unit,
)
from countyiq.lib.intelligence_common import compute_input_hash


def entity(*names, relationship=None):
    return {
        "canonical_name": names[0],
        "member_names": list(names),
        "entity_type": "individual",
        "confidence": 0.8,
        "reasoning": f"Source identity evidence [Evidence: candidate:{names[0]}]",
        "linked_records": {},
        "relationships": [relationship] if relationship else [],
    }


def partition(*entities, abstentions=(), rejected=()):
    return {
        "entities": list(entities),
        "abstentions": list(abstentions),
        "rejected_matches": list(rejected),
    }


def question(*names):
    return {
        "names": list(names),
        "reason": f"Identity uncertain [Evidence: candidate:{names[0]}]",
    }


def plan_for_pairs(pairs, max_names=3):
    names = sorted({name for pair in pairs for name in pair})
    dossiers = {
        name: {"candidate_names": [name], "source_inventory_hash": name}
        for name in names
    }
    plan = build_context_plan(names, pairs, dossiers, [], max_names=max_names)
    units = tuple(
        make_review_unit(plan.parent_key, dossiers, pair, max_names=max_names)
        for pair in pairs
    )
    manifest = dict(
        plan.manifest, units=[{"key": unit.key, "names": unit.names} for unit in units]
    )
    return replace(plan, units=units, manifest=manifest)


def review(unit, parsed):
    return {
        "key": unit.key,
        "names": list(unit.names),
        "source_hash": compute_input_hash(unit.source),
        "partition": parsed,
        "validated_trials": [parsed, parsed],
        "trial_receipts": [{"trial": 0}, {"trial": 1}],
    }


def test_transitive_unit_proposals_require_a_real_complete_overlap_review():
    plan = plan_for_pairs([("A", "B"), ("B", "C")])
    reviews = [
        review(plan.units[0], partition(entity("A", "B"))),
        review(plan.units[1], partition(entity("B", "C"))),
    ]
    with pytest.raises(EntityReviewInvalid, match="complete review"):
        compose_parent_partition(plan, reviews, [])
    full_unit = reconciliation_unit(plan, ["A", "B", "C"])
    reconciled = review(full_unit, partition(entity("A"), entity("B", "C")))
    result = compose_parent_partition(plan, reviews, [reconciled])
    assert [row["member_names"] for row in result["entities"]] == [["A"], ["B", "C"]]
    assert result["bounded_review"]["reconciliations"] == [reconciled]
    assert "trial_stats" not in result


def test_an_overlap_that_cannot_fit_is_pending_not_a_fabricated_abstention():
    plan = plan_for_pairs([("A", "B"), ("B", "C")], max_names=2)
    outputs = iter([partition(entity("A", "B")), partition(entity("B", "C"))])
    calls = []

    def invoke(config, prompt, **kwargs):
        calls.append(kwargs["archive_key"])
        return SimpleNamespace(success=True, parsed=next(outputs), metadata={})

    with pytest.raises(EntityContextLimit, match="3 candidate names"):
        review_context_plan(plan, None, invoke, target_trials=1)
    assert len(calls) == 2


@pytest.mark.parametrize(
    "second",
    [
        partition(entity("B"), abstentions=[question("A")]),
        partition(
            entity("A"),
            entity("B"),
            rejected=[
                {
                    "name_a": "A",
                    "name_b": "B",
                    "reason": "Different identities [Evidence: candidate:A]",
                }
            ],
        ),
        partition(dict(entity("A", "B"), entity_type="trust")),
    ],
)
def test_uncertainty_rejection_and_type_disagreement_all_require_review(second):
    assert reconciliation_components([partition(entity("A", "B")), second]) == [
        {"A", "B"}
    ]


def test_split_origin_does_not_transfer_a_relationship_to_one_fragment():
    plan = plan_for_pairs([("A", "B"), ("B", "C"), ("A", "D")])
    # A relation can cite only a target present in its actual review context.
    relation_unit = make_review_unit(
        plan.parent_key, plan.source["name_dossiers"], ["A", "B", "D"]
    )
    plan = replace(plan, units=(relation_unit, plan.units[1]))
    relation = {
        "related_entity": "D",
        "relationship_type": "shares_address",
        "evidence": "Same address [Evidence: candidate:A] [Evidence: candidate:D]",
    }
    reviews = [
        review(
            relation_unit,
            partition(entity("A", "B", relationship=relation), entity("D")),
        ),
        review(plan.units[1], partition(entity("B", "C"))),
    ]
    reconciled = review(
        reconciliation_unit(plan, ["A", "B", "C"]),
        partition(entity("A"), entity("B", "C")),
    )
    result = compose_parent_partition(plan, reviews, [reconciled])
    assert all(not item["relationships"] for item in result["entities"])
    assert result["bounded_review"]["withheld_relationships"] == [
        {
            "origin_names": ["A", "B"],
            "relationship": relation,
            "reason": "original_identity_split_or_withheld",
        }
    ]


def test_complete_origin_survives_target_canonicalization():
    plan = plan_for_pairs([("A", "B"), ("B", "C")])
    relation = {
        "related_entity": "B",
        "relationship_type": "shares_address",
        "evidence": "Same address [Evidence: candidate:A] [Evidence: candidate:B]",
    }
    reviews = [
        review(
            plan.units[0], partition(entity("A", relationship=relation), entity("B"))
        ),
        review(plan.units[1], partition(entity("C", "B"))),
    ]
    reconciled = review(
        reconciliation_unit(plan, ["B", "C"]), partition(entity("C", "B"))
    )
    result = compose_parent_partition(plan, reviews, [reconciled])
    assert result["entities"][0]["relationships"][0]["related_entity"] == "C"


def test_incomplete_or_stale_unit_evidence_cannot_supply_a_parent():
    plan = plan_for_pairs([("A", "B")])
    with pytest.raises(EntityReviewInvalid, match="Every planned unit"):
        compose_parent_partition(plan, [], [])
    stale = review(plan.units[0], partition(entity("A"), entity("B")))
    stale["source_hash"] = "stale"
    with pytest.raises(EntityReviewInvalid, match="different source"):
        compose_parent_partition(plan, [stale], [])


def test_invalid_registration_merge_cannot_vote_or_lower_the_majority_threshold():
    plan = plan_for_pairs([("A", "B")])
    outputs = iter(
        [
            partition(entity("A", "B")),
            partition(entity("A"), entity("B")),
            partition(entity("A", "B")),
        ]
    )

    def invoke(config, prompt, **kwargs):
        return SimpleNamespace(success=True, parsed=next(outputs), metadata={})

    with pytest.raises(ValueError, match="Insufficient validated trials"):
        review_unit(plan.units[0], None, invoke, {"A": ("A", "1"), "B": ("B", "2")})


def test_reconciliation_votes_cannot_reuse_initial_context_votes():
    plan = plan_for_pairs([("A", "B")])
    initial = plan.units[0]
    reconciled = reconciliation_unit(plan, initial.names)
    assert initial.source == reconciled.source
    assert initial.key != reconciled.key
