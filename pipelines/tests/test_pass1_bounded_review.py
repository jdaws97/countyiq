"""Bounded reviews publish only after complete votes and a fresh parent snapshot."""

from contextlib import nullcontext
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from countyiq.assets.enrichment import entity_verification as pass1
from countyiq.lib.entity_context_plan import (
    EntitySourceChanged,
    build_context_plan,
    make_review_unit,
)
from countyiq.lib.pass_llm_config import PassCallLimitReached, PassSubscriptionPaused


def _plan():
    names = ["A", "B", "C"]
    dossiers = {
        name: {"candidate_names": [name], "source_inventory_hash": name}
        for name in names
    }
    plan = build_context_plan(names, [("A", "B"), ("B", "C")], dossiers, [])
    units = tuple(
        make_review_unit(plan.parent_key, dossiers, pair)
        for pair in [("A", "B"), ("B", "C")]
    )
    manifest = dict(
        plan.manifest, units=[{"key": unit.key, "names": unit.names} for unit in units]
    )
    return replace(plan, units=units, manifest=manifest)


class _Author:
    def __init__(self, plan, cache, call_limit=100, pause=None):
        self.plan = plan
        self.cache = cache
        self.calls = 0
        self.call_limit = call_limit
        self.pause = pause

    def __call__(self, config, prompt, **kwargs):
        key = kwargs["archive_key"]
        if key in self.cache:
            return self.cache[key]
        if self.pause is not None:
            raise self.pause
        if self.calls == self.call_limit:
            raise PassCallLimitReached("per-run call limit")
        self.calls += 1
        unit = next(unit for unit in self.plan.units if key.startswith(unit.key))
        parsed = {
            "entities": [
                {
                    "canonical_name": name,
                    "member_names": [name],
                    "entity_type": "individual",
                    "confidence": 0.8,
                    "reasoning": f"Recorded person [Evidence: candidate:{name}]",
                    "linked_records": {},
                    "relationships": [],
                }
                for name in unit.names
            ],
            "rejected_matches": [],
            "abstentions": [],
        }
        result = SimpleNamespace(success=True, parsed=parsed, metadata={"receipt": key})
        self.cache[key] = result
        return result


@pytest.fixture
def publication(monkeypatch):
    plan = _plan()
    writes = []
    snapshots = []
    current = [plan]

    def gather(cursor, names, **kwargs):
        snapshots.append(tuple(names))
        return current[0]

    def record(database, **kwargs):
        writes.append(("ledger", kwargs))
        return SimpleNamespace(accepted=True, inference_id=42)

    def project(database, entities, names, **kwargs):
        writes.append(("projection", kwargs))
        return len(entities)

    monkeypatch.setattr(pass1, "gather_context_plan", gather)
    monkeypatch.setattr(pass1, "record_inference_decision", record)
    monkeypatch.setattr(pass1, "_replace_cluster_entities", project)
    monkeypatch.setattr(
        pass1, "_update_pass_status", lambda *args: writes.append(("status", args))
    )
    database = SimpleNamespace(read_snapshot=lambda: nullcontext(object()))
    budget = SimpleNamespace(claim=lambda *args, **kwargs: True)

    def run(author, prior=None):
        return pass1._verify_bounded_cluster(
            database,
            plan.source["candidate_names"],
            SimpleNamespace(model_path="codex/subscription:gpt-6-astra"),
            author,
            prior or {},
            budget,
            Mock(),
            n_trials=3,
            adaptive=True,
            progress=None,
        )

    return SimpleNamespace(
        plan=plan, run=run, current=current, writes=writes, snapshots=snapshots
    )


def test_resume_reuses_completed_votes_and_publishes_the_original_parent_once(
    publication,
):
    cache = {}
    first = _Author(publication.plan, cache, call_limit=3)
    with pytest.raises(PassCallLimitReached):
        publication.run(first)
    assert publication.writes == []
    assert first.calls == 3

    resumed = _Author(publication.plan, cache, call_limit=3)
    outcome = publication.run(resumed)
    assert outcome == {"status": "accepted", "entities": 3, "abstentions": 0}
    assert resumed.calls == 1
    assert [kind for kind, _ in publication.writes] == [
        "ledger",
        "projection",
        "status",
    ]
    ledger = publication.writes[0][1]
    assert ledger["subject_key"] == publication.plan.parent_key
    assert ledger["payload"]["bounded_review"]["units"][0]["trial_receipts"]
    assert (
        len(publication.snapshots) == 3
    )  # Failed run, resumed input, final freshness.

    # A complete current parent skips before dispatch, even with no available login.
    publication.writes.clear()
    paused = _Author(
        publication.plan, cache, pause=PassSubscriptionPaused("login expired")
    )
    assert publication.run(
        paused, {publication.plan.parent_key: ledger["input_hash"]}
    ) == {"status": "skipped"}
    assert publication.writes == []


def test_changed_evidence_after_long_reviews_prevents_all_publication(publication):
    author = _Author(publication.plan, {})
    changed = deepcopy(publication.plan.source)
    changed["source_inventory_hashes"]["C"] = "changed beyond visible detail"

    def invoke(config, prompt, **kwargs):
        result = author(config, prompt, **kwargs)
        publication.current[0] = replace(publication.plan, source=changed)
        return result

    with pytest.raises(EntitySourceChanged, match="changed during"):
        publication.run(invoke)
    assert publication.writes == []
    assert len(publication.snapshots) == 2


def test_auth_or_quota_pause_propagates_without_publishing_or_substituting_a_call_cap(
    publication,
):
    author = _Author(
        publication.plan, {}, pause=PassSubscriptionPaused("quota unavailable")
    )
    with pytest.raises(PassSubscriptionPaused) as stopped:
        publication.run(author)
    assert type(stopped.value) is PassSubscriptionPaused
    assert publication.writes == []
