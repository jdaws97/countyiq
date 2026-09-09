"""Preserve parent coverage, source freshness and exact-registration ambiguity."""

from copy import deepcopy

import pytest
from countyiq.lib.entity_context_plan import (
    EntityContextLimit,
    build_context_plan,
    combine_name_dossiers,
)
from countyiq.lib.intelligence_integrity import content_hash
from countyiq.lib.pass1_entity_verification import (
    build_entity_cluster_prompt,
    gather_cluster_records,
    stable_cluster_key,
)


def dossier(name, number=None):
    records = {
        "candidate_names": [name],
        "parcels": [{"pidn": name, "owner_full": name, "mail_addr_full": "10 MAIN ST"}],
        "tax_claims": [],
        "plcb_licenses": [],
        "corporate_entities": [],
        "proceedings": [],
    }
    if number is not None:
        records["corporate_entities"] = [
            {"entity_name": name, "entity_number": number, "status": "Active"}
        ]
    records["source_inventory_hash"] = content_hash(records)
    return records


def test_large_connected_component_keeps_one_parent_and_covers_every_edge():
    names = [f"OWNER {number:03d}" for number in range(121)]
    edges = [(names[0], name) for name in names[1:]]
    dossiers = {name: dossier(name) for name in names}
    plan = build_context_plan(names, edges, dossiers, [])
    assert plan.parent_key == stable_cluster_key(names)
    assert len(plan.units) == 4
    assert all(
        len(unit.names) <= 40 and len(unit.prompt) <= 64_000 for unit in plan.units
    )
    assert all(
        any(set(edge) <= set(unit.names) for unit in plan.units) for edge in edges
    )
    assert plan.source["candidate_names"] == names
    assert set(plan.source["name_dossiers"]) == set(names)
    assert all(unit.key.startswith(plan.parent_key + ":") for unit in plan.units)
    reversed_plan = build_context_plan(
        list(reversed(names)), list(reversed(edges)), dossiers, []
    )
    assert content_hash(plan.source) == content_hash(reversed_plan.source)


def test_exact_registered_spellings_and_distinct_numbers_leave_unknown_edges_for_review():
    names = ["ALPHA LLC", "ALPHA, LLC", "BETA LLC", "UNKNOWN OWNER"]
    dossiers = {name: dossier(name) for name in names}
    dossiers["ALPHA LLC"] = dossier("ALPHA LLC", "100")
    dossiers["BETA LLC"] = dossier("BETA LLC", "200")
    registrations = [
        {"entity_name": "ALPHA LLC", "entity_number": "100"},
        {"entity_name": "BETA LLC", "entity_number": "200"},
    ]
    edges = [(names[0], name) for name in names[1:]]
    plan = build_context_plan(names, edges, dossiers, registrations)
    assert set(plan.anchors) == {"ALPHA LLC", "ALPHA, LLC", "BETA LLC"}
    assert {row["reason"] for row in plan.source["review_plan"]["resolved_edges"]} == {
        "distinct_registration_numbers",
        "exact_registered_legal_spelling",
    }
    assert len(plan.units) == 1
    assert set(plan.units[0].names) == {"ALPHA LLC", "UNKNOWN OWNER"}
    assert {
        tuple(entity["member_names"])
        for entity in plan.deterministic_partition["entities"]
    } == {("ALPHA LLC", "ALPHA, LLC"), ("BETA LLC",)}


def test_registration_name_history_outside_the_component_disables_the_shortcut():
    names = ["ALPHA LLC", "BETA LLC"]
    dossiers = {
        name: dossier(name, number) for name, number in zip(names, ("100", "200"))
    }
    registrations = [
        {"entity_name": "ALPHA LLC", "entity_number": "100"},
        {"entity_name": "HISTORICAL COMPANY LLC", "entity_number": "100"},
        {"entity_name": "BETA LLC", "entity_number": "200"},
    ]
    plan = build_context_plan(names, [names], dossiers, registrations)
    assert "ALPHA LLC" not in plan.anchors
    assert plan.source["review_plan"]["resolved_edges"] == []
    assert len(plan.units) == 1
    assert registrations[1] in plan.source["review_plan"]["registration_evidence"]


def test_registration_index_cannot_override_conflicting_dossier_evidence():
    names = ["ALPHA LLC", "BETA LLC"]
    dossiers = {name: dossier(name, "999") for name in names}
    registrations = [
        {"entity_name": "ALPHA LLC", "entity_number": "100"},
        {"entity_name": "BETA LLC", "entity_number": "200"},
    ]
    plan = build_context_plan(names, [names], dossiers, registrations)
    assert plan.anchors == {}
    assert len(plan.units) == 1


def test_a_matching_index_number_does_not_hide_another_number_in_the_dossier():
    names = ["ALPHA LLC", "BETA LLC"]
    dossiers = {
        "ALPHA LLC": dossier("ALPHA LLC", "100"),
        "BETA LLC": dossier("BETA LLC", "200"),
    }
    dossiers["ALPHA LLC"]["corporate_entities"].append(
        {"entity_name": "ALPHA LLC", "entity_number": "999", "status": "Active"}
    )
    registrations = [
        {"entity_name": "ALPHA LLC", "entity_number": "100"},
        {"entity_name": "BETA LLC", "entity_number": "200"},
    ]
    plan = build_context_plan(names, [names], dossiers, registrations)
    assert "ALPHA LLC" not in plan.anchors
    assert plan.source["review_plan"]["resolved_edges"] == []
    assert len(plan.units) == 1
    assert set(plan.units[0].names) == set(names)


def test_uncovered_candidate_name_is_rejected_before_any_review():
    names = ["A", "B", "C"]
    with pytest.raises(ValueError, match="account for every component name"):
        build_context_plan(
            names, [("A", "B")], {name: dossier(name) for name in names}, []
        )


def test_an_overlarge_pair_is_deferred_without_truncating_its_records():
    names = ["A", "B"]
    dossiers = {name: dossier(name) for name in names}
    for records in dossiers.values():
        records["parcels"][0]["mail_addr_full"] = "X" * 3000
    with pytest.raises(EntityContextLimit):
        build_context_plan(names, [names], dossiers, [], max_characters=4000)
    assert all(
        len(records["parcels"][0]["mail_addr_full"]) == 3000
        for records in dossiers.values()
    )


class SourceCursor:
    description = True

    def __init__(self, parcels):
        self.results = iter([parcels, [], [], [], []])

    def execute(self, query, parameters):
        pass

    def fetchall(self):
        return next(self.results)


def test_dossier_detail_is_stable_and_omitted_rows_still_change_its_source_hash():
    parcels = [
        {"pidn": f"{number:03d}", "owner_full": "OWNER", "price": 0}
        for number in range(51)
    ]
    original = gather_cluster_records(
        SourceCursor(list(reversed(parcels))), ["OWNER"], stable_source_snapshot=True
    )
    reordered = gather_cluster_records(
        SourceCursor(parcels), ["OWNER"], stable_source_snapshot=True
    )
    assert original == reordered
    changed = deepcopy(parcels)
    changed[-1]["price"] = 100
    revised = gather_cluster_records(
        SourceCursor(changed), ["OWNER"], stable_source_snapshot=True
    )
    assert original["parcels"] == revised["parcels"]
    assert build_entity_cluster_prompt(original) == build_entity_cluster_prompt(revised)
    assert original["source_inventory_hash"] != revised["source_inventory_hash"]


def test_one_owners_portfolio_cannot_consume_another_owners_detail_allowance():
    dossiers = {}
    for name in ("LARGE OWNER", "OTHER OWNER"):
        rows = [
            {"pidn": f"{name}:{number}", "owner_full": name} for number in range(51)
        ]
        dossiers[name] = gather_cluster_records(
            SourceCursor(rows), [name], stable_source_snapshot=True
        )
    combined = combine_name_dossiers(dossiers, dossiers)
    assert len(combined["parcels"]) == 100
    assert len(combined["portfolio_summaries"]) == 2
    prompt = build_entity_cluster_prompt(combined)
    assert "PORTFOLIO SUMMARY FOR candidate:LARGE OWNER" in prompt
    assert "PORTFOLIO SUMMARY FOR candidate:OTHER OWNER" in prompt
    assert prompt.count("Total parcels: 51 (showing 50 above)") == 2
