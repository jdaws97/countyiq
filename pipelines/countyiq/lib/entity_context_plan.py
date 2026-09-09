"""Plan bounded source reviews while preserving the whole candidate component.

Units are temporary comparison contexts, never independently published entities.
The parent source manifest binds every candidate edge, each per-name dossier,
and the registration evidence used to exclude already resolved comparisons.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass

from countyiq.lib.intelligence_common import compute_input_hash
from countyiq.lib.pass1_entity_verification import (
    CANDIDATE_CLUSTERS_QUERY,
    DETERMINISTIC_VARIANT_VERSION,
    ENTITY_REGISTRATION_ROWS_QUERY,
    _legal_name_key,
    _registered_entity_type,
    build_deterministic_entity_resolution,
    build_entity_cluster_prompt,
    gather_cluster_records,
    stable_cluster_key,
)

PLAN_VERSION = "bounded-entity-dossiers-v3"
REVIEW_UNIT_VERSION = "bounded-entity-dossiers-v2"
SOURCE_KINDS = (
    "parcels",
    "tax_claims",
    "plcb_licenses",
    "corporate_entities",
    "proceedings",
)


class EntityContextLimit(ValueError):
    """A complete comparison cannot fit the reviewed context bounds."""


class EntitySourceChanged(ValueError):
    """The original parent no longer matches a complete candidate component."""


@dataclass(frozen=True)
class EntityReviewUnit:
    key: str
    names: tuple[str, ...]
    source: dict
    prompt: str


@dataclass(frozen=True)
class EntityContextPlan:
    parent_key: str
    source: dict
    manifest: dict
    units: tuple[EntityReviewUnit, ...]
    anchors: dict[str, tuple[str, str]]
    deterministic_partition: dict | None


def _canonical_rows(rows) -> list[dict]:
    unique = {json.dumps(row, sort_keys=True, default=str): row for row in rows}
    return [unique[key] for key in sorted(unique)]


def combine_name_dossiers(dossiers: dict[str, dict], names) -> dict:
    """Combine complete prepared dossiers without letting one owner crowd another."""
    names = sorted(names)
    records = {"candidate_names": names}
    for kind in SOURCE_KINDS:
        records[kind] = _canonical_rows(
            row for name in names for row in dossiers[name].get(kind, [])
        )
    records["portfolio_summaries"] = [
        {"candidate_name": name, "summary": dossiers[name]["portfolio_summary"]}
        for name in names
        if "portfolio_summary" in dossiers[name]
    ]
    records["source_inventory_hashes"] = {
        name: dossiers[name]["source_inventory_hash"] for name in names
    }
    records["identity_inventories"] = [
        {"candidate_name": name, "inventory": dossiers[name]["identity_inventory"]}
        for name in names
        if "identity_inventory" in dossiers[name]
    ]
    return records


def make_review_unit(
    parent_key: str,
    dossiers: dict[str, dict],
    names,
    *,
    max_names: int = 40,
    max_characters: int = 64_000,
) -> EntityReviewUnit:
    names = tuple(sorted(set(names)))
    if not names or len(names) > max_names:
        raise EntityContextLimit(f"Review context has {len(names)} candidate names")
    source = combine_name_dossiers(dossiers, names)
    prompt = build_entity_cluster_prompt(source)
    if len(prompt) > max_characters:
        raise EntityContextLimit(
            f"Review context has {len(prompt)} dynamic prompt characters"
        )
    unit_key = stable_cluster_key(list(names)).removeprefix("entity_cluster:")
    return EntityReviewUnit(
        # A changed planner must not invent new votes for an unchanged complete
        # review input. The parent execution hash separately binds the full plan.
        key=f"{parent_key}:{REVIEW_UNIT_VERSION}:{unit_key}:{compute_input_hash(source)}",
        names=names,
        source=source,
        prompt=prompt,
    )


def _registration_anchors(names, dossiers, registration_rows):
    numbers_by_key = defaultdict(set)
    keys_by_number = defaultdict(set)
    for row in registration_rows:
        key = _legal_name_key(str(row.get("entity_name") or ""))
        number = str(row.get("entity_number") or "").strip()
        if key and number:
            numbers_by_key[key].add(number)
            keys_by_number[number].add(key)

    anchors = {}
    selected_names = set(names)
    corporate_by_key = defaultdict(list)
    for dossier in dossiers.values():
        for row in dossier.get("corporate_entities", []):
            if row.get("entity_name") in selected_names:
                corporate_by_key[_legal_name_key(row["entity_name"])].append(row)
    for name in names:
        key = _legal_name_key(name)
        numbers = numbers_by_key[key]
        if not _registered_entity_type(key) or len(numbers) != 1:
            continue
        number = next(iter(numbers))
        # A number associated with distinct legal keys requires name-history
        # evidence. It cannot supply this exact-spelling registration shortcut.
        if len(keys_by_number[number]) != 1:
            continue
        dossier_numbers = {
            str(row["entity_number"]).strip()
            for row in corporate_by_key[key]
            if str(row.get("entity_number") or "").strip()
        }
        if dossier_numbers == {number}:
            anchors[name] = (key, number)

    selected_keys = {_legal_name_key(name) for name in names}
    selected_numbers = set().union(*(numbers_by_key[key] for key in selected_keys))
    relevant_rows = _canonical_rows(
        row
        for row in registration_rows
        if _legal_name_key(str(row.get("entity_name") or "")) in selected_keys
        or str(row.get("entity_number") or "").strip() in selected_numbers
    )
    return anchors, relevant_rows


def _cover_edges(parent_key, dossiers, edges, *, max_names, max_characters):
    remaining = set(edges)
    units = []
    review_names = {name for edge in edges for name in edge}
    costs = {
        name: len(build_entity_cluster_prompt(dossiers[name])) + 100
        for name in review_names
    }
    # Leave room for labels in the combined per-owner portfolio summaries.
    character_budget = max_characters - 1000
    while remaining:
        adjacent = defaultdict(set)
        for left, right in remaining:
            adjacent[left].add(right)
            adjacent[right].add(left)
        seed = min(adjacent, key=lambda name: (-len(adjacent[name]), name))
        selected = {seed}
        cost = costs[seed]
        while len(selected) < max_names:
            candidates = set().union(*(adjacent[name] for name in selected)) - selected
            fitting = [
                name for name in candidates if cost + costs[name] <= character_budget
            ]
            if not fitting:
                break
            chosen = min(
                fitting,
                key=lambda name: (
                    -len(adjacent[name] & selected),
                    -len(adjacent[name]),
                    name,
                ),
            )
            selected.add(chosen)
            cost += costs[chosen]
        covered = {edge for edge in remaining if set(edge) <= selected}
        if not covered:
            raise EntityContextLimit(
                f"A complete source comparison involving {seed} exceeds the bounds"
            )
        unit = make_review_unit(
            parent_key,
            dossiers,
            selected,
            max_names=max_names,
            max_characters=max_characters,
        )
        units.append(unit)
        remaining -= covered
    return tuple(units)


def build_context_plan(
    names,
    candidate_edges,
    dossiers: dict[str, dict],
    registration_rows: list[dict],
    *,
    max_names: int = 40,
    max_characters: int = 64_000,
) -> EntityContextPlan:
    """Cover every original edge or its exact-registration disposition.

    Callers gather each name separately in one read snapshot using
    ``gather_cluster_records(..., stable_source_snapshot=True)``. The complete
    dossier manifest is retained under the original, unsplit parent key.
    """
    names = sorted(set(names))
    selected = set(names)
    if len(names) < 2 or set(dossiers) != selected:
        raise ValueError("A component needs the exact complete set of name dossiers")
    if max_names < 2 or max_characters <= 1000:
        raise ValueError("Context bounds must permit a complete pair comparison")
    for name, dossier in dossiers.items():
        if dossier.get("candidate_names") != [name]:
            raise ValueError("A dossier must belong to exactly its named candidate")
        if not dossier.get("source_inventory_hash"):
            raise ValueError(
                "Every dossier must fingerprint its complete source inventory"
            )

    edges = sorted({tuple(sorted(edge)) for edge in candidate_edges})
    if any(len(edge) != 2 or len(set(edge)) != 2 for edge in edges):
        raise ValueError("Candidate edges must contain two distinct names")
    if {name for edge in edges for name in edge} != selected:
        raise ValueError("Candidate edges must account for every component name")
    adjacent = defaultdict(set)
    for left, right in edges:
        adjacent[left].add(right)
        adjacent[right].add(left)
    reached = {names[0]}
    pending = [names[0]]
    while pending:
        for neighbor in adjacent[pending.pop()] - reached:
            reached.add(neighbor)
            pending.append(neighbor)
    if reached != selected:
        raise EntitySourceChanged("The candidate parent has split into components")
    anchors, registration_evidence = _registration_anchors(
        names, dossiers, registration_rows
    )
    anchored_groups = defaultdict(list)
    for name, anchor in anchors.items():
        anchored_groups[anchor].append(name)
    deterministic_entities = []
    safe_names = set()
    for members in anchored_groups.values():
        proposal = build_deterministic_entity_resolution(
            combine_name_dossiers(dossiers, members), members
        )
        if proposal is not None:
            deterministic_entities.extend(proposal["entities"])
            safe_names.update(members)
    resolved_edges = []
    unresolved = []
    for left, right in edges:
        if left in safe_names and right in safe_names:
            if anchors[left][1] != anchors[right][1]:
                resolved_edges.append(
                    {"names": [left, right], "reason": "distinct_registration_numbers"}
                )
                continue
            if anchors[left] == anchors[right]:
                resolved_edges.append(
                    {
                        "names": [left, right],
                        "reason": "exact_registered_legal_spelling",
                    }
                )
                continue
        unresolved.append((left, right))

    parent_key = stable_cluster_key(names)
    units = _cover_edges(
        parent_key,
        dossiers,
        unresolved,
        max_names=max_names,
        max_characters=max_characters,
    )
    accounted = set(safe_names)
    for unit in units:
        accounted.update(unit.names)
    if accounted != selected:
        raise ValueError("The review plan leaves candidate names unaccounted for")
    if any(
        not any(set(edge) <= set(unit.names) for unit in units) for edge in unresolved
    ):
        raise ValueError("The review plan leaves candidate comparisons unaccounted for")

    source = combine_name_dossiers(dossiers, names)
    source["name_dossiers"] = {name: dossiers[name] for name in names}
    source["candidate_edges"] = edges
    source["registration_evidence"] = registration_evidence
    manifest = {
        "version": PLAN_VERSION,
        "parent_key": parent_key,
        "max_candidate_names": max_names,
        "max_dynamic_prompt_characters": max_characters,
        "resolved_edges": resolved_edges,
        "deterministic_names": sorted(safe_names),
        "units": [{"key": unit.key, "names": unit.names} for unit in units],
    }
    deterministic = (
        {
            "entities": deterministic_entities,
            "rejected_matches": [],
            "abstentions": [],
            "resolution_tier": DETERMINISTIC_VARIANT_VERSION,
        }
        if deterministic_entities
        else None
    )
    return EntityContextPlan(
        parent_key, source, manifest, units, anchors, deterministic
    )


def gather_context_plan(cursor, names, *, max_names=40, max_characters=64_000):
    """Gather inside a caller-owned snapshot; reject changed parent boundaries."""
    selected = set(names)
    cursor.execute(CANDIDATE_CLUSTERS_QUERY)
    edges = []
    for row in cursor.fetchall():
        left, right = row["name_a"], row["name_b"]
        if left not in selected and right not in selected:
            continue
        if left not in selected or right not in selected:
            raise EntitySourceChanged(
                "The candidate parent has joined another component"
            )
        edges.append((left, right))
    cursor.execute(ENTITY_REGISTRATION_ROWS_QUERY)
    registrations = [dict(row) for row in cursor.fetchall()]
    dossiers = {
        name: gather_cluster_records(cursor, [name], stable_source_snapshot=True)
        for name in sorted(selected)
    }
    return build_context_plan(
        names,
        edges,
        dossiers,
        registrations,
        max_names=max_names,
        max_characters=max_characters,
    )
