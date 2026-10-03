"""Unresolved candidate observations must not become owner graph edges."""

import json
from contextlib import contextmanager
from copy import deepcopy

import pytest
from countyiq.assets.enrichment.entity_verification import _replace_cluster_entities
from countyiq.lib.intelligence_resolution import _project_entities


class ProjectionDatabase:
    def __init__(self):
        self.inserted = []

    @contextmanager
    def transaction(self):
        yield self

    def execute(self, query, parameters):
        if "INSERT INTO public.entity_graph" in query:
            self.inserted.append(parameters)


@pytest.mark.parametrize("projection", ["ordinary", "contradiction_resolution"])
def test_only_accepted_target_identities_become_owner_edges(projection):
    def relationship(target):
        return {
            "related_entity": target,
            "relationship_type": "shares_address_with",
            "evidence": "The cited corporate rows share an office.",
        }

    entities = [
        {
            "canonical_name": "ROUNDTOP LLC",
            "member_names": ["ROUNDTOP LLC", "ROUNDTOP L L C"],
            "relationships": [
                relationship("RIVERS EDGE OASIS LLC"),
                relationship("ANOTHER L L C"),
                relationship("ROUNDTOP L L C"),
                relationship("OUTSIDE CANDIDATE"),
            ],
        },
        {
            "canonical_name": "ANOTHER LLC",
            "member_names": ["ANOTHER LLC", "ANOTHER L L C"],
            "relationships": [],
        },
    ]
    payload = {
        "entities": entities,
        "abstentions": [{"names": ["RIVERS EDGE OASIS LLC"]}],
    }
    original_payload = deepcopy(payload)
    names = [
        "ROUNDTOP LLC",
        "ROUNDTOP L L C",
        "ANOTHER LLC",
        "ANOTHER L L C",
        "RIVERS EDGE OASIS LLC",
    ]
    database = ProjectionDatabase()
    if projection == "ordinary":
        _replace_cluster_entities(database, entities, names, inference_id=42)
    else:
        history = {"evidence_refs": [f"candidate:{name}" for name in names]}
        _project_entities(database, history, history, payload, inference_id=42)

    assert len(database.inserted) == 2
    assert json.loads(database.inserted[0][4]) == [relationship("ANOTHER LLC")]
    assert json.loads(database.inserted[1][4]) == []
    assert payload == original_payload
