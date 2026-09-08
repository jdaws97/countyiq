import json
from copy import deepcopy
from pathlib import Path

import pytest
from countyiq.lib.backfill_authorization import (
    BackfillAuthorizationError,
    create_backfill_authorization,
)
from countyiq.lib.pass0_packet_facts import full_source_interpretation_prompt
from countyiq.lib.pass0_source import index_source
from eval.pass0_experiment import (
    authorization,
    model_config,
    prepare,
    run,
    run_job,
)

from tests.test_pass0_facts import consent_fixture
from tests.test_pass0_packet_facts import full_source_fixture


def budget_at(path: Path):
    create_backfill_authorization(
        path,
        pass_number=0,
        model="pass0-experiments",
        max_cost_usd=5,
        max_price_prompt=5.5,
        max_price_completion=22,
    )
    return authorization(path)


def job_fixture():
    text, payload = consent_fixture()
    source = {"id": 1, "raw_text": text}
    job = {
        "job_id": "example",
        "source_id": 1,
        "source_sha256": index_source(text).sha256,
        "model": "openai/gpt-5.6-luna",
        "review_kind": "facts",
        "maximum_cost_usd": 0.1,
        "payload": {},
    }
    return source, payload, job


def test_explicit_cap_requires_matching_ledger_and_preserves_prior_spending(tmp_path):
    path = tmp_path / "budget.json"
    create_backfill_authorization(
        path,
        pass_number=0,
        model="pass0-experiments",
        max_cost_usd=6,
        max_price_prompt=5.5,
        max_price_completion=22,
    )
    budget = authorization(path, max_cost_usd=6)
    settled = budget.reserve(0.5)
    budget.settle(settled, 0.25)
    unresolved = budget.reserve(1.0)
    original = path.read_bytes()

    for wrong_cap in (5, 7):
        with pytest.raises(BackfillAuthorizationError, match="max_cost_usd"):
            authorization(path, max_cost_usd=wrong_cap).snapshot()
        assert path.read_bytes() == original

    resumed = authorization(path, max_cost_usd=6).snapshot()
    assert resumed["spent_usd"] == 0.25
    assert resumed["reserved_usd"] == 1.0
    assert unresolved in resumed["reservations"]
    assert resumed["remaining_usd"] == 4.75
    assert path.read_bytes() == original


@pytest.mark.parametrize("model", ["openai/gpt-5.6-sol", "openai/gpt-5.6-terra"])
def test_expensive_models_cannot_be_prepared_or_resumed(tmp_path, model):
    with pytest.raises(ValueError, match="current Pass 0 selection"):
        model_config(model, "low", 4096)

    (tmp_path / "protocol.json").write_text(json.dumps({"jobs": [{"model": model}]}))
    with pytest.raises(ValueError, match="current Pass 0 selection"):
        run(tmp_path, tmp_path / "unused-budget.json")
    assert not (tmp_path / "unused-budget.json").exists()


@pytest.mark.parametrize("mode", ["scope", "claim_verification", "field_projection"])
def test_retired_modes_fail_before_creating_a_request_or_charging(tmp_path, mode):
    source, _, job = job_fixture()
    job["review_kind"] = mode
    budget = budget_at(tmp_path / "budget.json")
    original = (tmp_path / "budget.json").read_bytes()

    with pytest.raises(ValueError, match="Unsupported Pass 0 mode"):
        run_job(job, source, tmp_path, budget, "test-secret")

    assert not (tmp_path / "example").exists()
    assert (tmp_path / "budget.json").read_bytes() == original


def test_default_discovery_preparation_excludes_reference_answers(tmp_path):
    source, _, _ = job_fixture()
    sources = tmp_path / "sources.json"
    sources.write_text(json.dumps([source]))
    reference = tmp_path / "reference.json"
    reference.write_text('{"answer": "REFERENCE ONLY SENTINEL"}')

    protocol = prepare(
        sources, reference, tmp_path / "run", ["openai/gpt-5.6-luna"], [1]
    )

    job = protocol["jobs"][0]
    assert job["review_kind"] == "discovery"
    schema = job["config"]["json_schema"]
    assert "conditions" not in schema["$defs"]["matter"]["properties"]
    assert "milestones" not in schema["$defs"]["matter"]["properties"]
    assert "REFERENCE ONLY SENTINEL" not in json.dumps(job["payload"])
    assert "eval/pass0_discovery.py" in protocol["code_sha256"]
    assert "eval/pass0_schema_guidance.py" in protocol["code_sha256"]


@pytest.mark.parametrize("grouped", [False, True])
def test_prepared_inventory_jobs_keep_full_context_and_bounded_fact_evidence(
    tmp_path, grouped
):
    source, _, _ = job_fixture()
    locations = {
        "matters": [
            {"title": "Wawa", "lines": [[2, 3], [6, 6]]},
            {"title": "Mustang Pointe", "lines": [[2, 2], [5, 6]]},
        ]
    }
    sources = tmp_path / "sources.json"
    sources.write_text(json.dumps([source]))
    reference = tmp_path / "reference.json"
    reference.write_text("{}")
    inventory = tmp_path / "inventory.json"
    inventory.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "source_id": 1,
                        "source_sha256": index_source(source["raw_text"]).sha256,
                        "parsed": locations,
                        "errors": [],
                    }
                ]
            }
        )
    )

    protocol = prepare(
        sources,
        reference,
        tmp_path / "run",
        ["openai/gpt-5.6-luna"],
        [1],
        mode="packet_facts",
        inventory_path=inventory,
        per_matter=True,
        group_overlaps=grouped,
    )

    assert protocol["calls"] == (1 if grouped else 2)
    assigned = []
    for job in protocol["jobs"]:
        assigned.extend(job["inventory_indices"])
        content = job["payload"]["messages"][-1]["content"]
        assert index_source(source["raw_text"]).model_input() in content
        assert job["context_ranges"] == [[1, 6]]
        assert all(not first <= 4 <= last for first, last in job["evidence_ranges"])
        schema = job["config"]["json_schema"]
        assert len(schema["required"]) == len(job["inventory_indices"])
        assert "context_range" in schema["$defs"]
    assert assigned == [0, 1]


@pytest.mark.parametrize("invalid_matter", [False, True])
def test_one_dispatch_debits_actual_usage_and_cannot_be_repeated(
    tmp_path, monkeypatch, invalid_matter
):
    source, payload, job = job_fixture()
    if invalid_matter:
        broken = deepcopy(payload["matters"][0])
        broken["summary"]["excerpts"][0]["lines"] = [999, 999]
        payload["matters"].append(broken)
    budget = budget_at(tmp_path / "budget.json")
    calls = []

    class Response:
        text = "raw provider response"

        def json(self):
            return {
                "usage": {"cost": 0.01},
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": json.dumps(payload)},
                    }
                ],
            }

        def raise_for_status(self):
            pass

    def post(*args, **kwargs):
        calls.append(kwargs)
        return Response()

    monkeypatch.setattr("eval.pass0_experiment.requests.post", post)
    result = run_job(job, source, tmp_path, budget, "test-secret")

    assert bool(result["errors"]) is invalid_matter
    assert not result["request_failed"]
    assert len(result["review"]["matters"]) == 1
    assert budget.snapshot()["spent_usd"] == 0.01
    assert budget.snapshot()["reserved_usd"] == 0
    with pytest.raises(FileExistsError):
        run_job(job, source, tmp_path, budget, "test-secret")
    assert len(calls) == 1
    assert "test-secret" not in (tmp_path / "example/request.json").read_text()


def test_uncertain_transport_charges_full_reservation_without_retry(
    tmp_path, monkeypatch
):
    import requests

    source, _, job = job_fixture()
    budget = budget_at(tmp_path / "budget.json")
    calls = []

    def timeout(*args, **kwargs):
        calls.append(1)
        raise requests.Timeout("uncertain remote result")

    monkeypatch.setattr("eval.pass0_experiment.requests.post", timeout)
    result = run_job(job, source, tmp_path, budget, "test-secret")

    assert result["errors"]
    assert result["request_failed"]
    assert calls == [1]
    assert budget.snapshot()["spent_usd"] == 0.1
    assert budget.snapshot()["reserved_usd"] == 0


def test_paid_packet_review_preserves_document_context_evidence(tmp_path, monkeypatch):
    source, locations, payload = full_source_fixture()
    source["id"] = 1
    _, document, ranges, context = full_source_interpretation_prompt(source, locations)
    _, _, job = job_fixture()
    job.update(
        source_sha256=document.sha256,
        review_kind="packet_facts",
        draft=locations,
        evidence_ranges=ranges,
        context_ranges=context,
    )

    class Response:
        text = "raw provider response"

        def json(self):
            return {
                "usage": {"cost": 0.01},
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": json.dumps(payload)},
                    }
                ],
            }

        def raise_for_status(self):
            pass

    monkeypatch.setattr(
        "eval.pass0_experiment.requests.post", lambda *args, **kwargs: Response()
    )
    result = run_job(
        job, source, tmp_path, budget_at(tmp_path / "budget.json"), "test-secret"
    )

    assert not result["errors"]
    assert result["review"]["matters"][0]["event_date_iso"] == "2026-09-01"
    assert result["review"]["matters"][0]["semantic_review_complete"] is False


@pytest.mark.parametrize("finish_reason", ["length", "content_filter"])
def test_incomplete_document_is_charged_and_does_not_stop_other_documents(
    tmp_path, monkeypatch, finish_reason
):
    source, payload, _ = job_fixture()
    sources = tmp_path / "sources.json"
    sources.write_text(json.dumps([source, {**source, "id": 2}]))
    reference = tmp_path / "reference.json"
    reference.write_text("{}")
    output = tmp_path / "run"
    prepare(sources, reference, output, ["openai/gpt-5.6-luna"], [1, 2], mode="facts")
    budget = budget_at(tmp_path / "budget.json")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-secret")
    calls = []

    class Response:
        text = "raw provider response"

        def __init__(self, reason):
            self.reason = reason

        def json(self):
            return {
                "usage": {"cost": 0.01},
                "choices": [
                    {
                        "finish_reason": self.reason,
                        "message": {"content": json.dumps(payload)},
                    }
                ],
            }

        def raise_for_status(self):
            pass

    def post(*args, **kwargs):
        calls.append(kwargs)
        return Response(finish_reason if len(calls) == 1 else "stop")

    monkeypatch.setattr("eval.pass0_experiment.requests.post", post)
    report = run(output, tmp_path / "budget.json", workers=1)

    assert len(calls) == 2
    assert not report["skipped_jobs"]
    assert report["status"] == "completed_with_errors"
    first, second = report["results"]
    assert first["errors"] == [f"Incomplete response: {finish_reason}"]
    assert not first["review"]["matters"]
    assert not first["request_failed"]
    assert not second["errors"]
    assert budget.snapshot()["spent_usd"] == 0.02


@pytest.mark.parametrize("request_failed", [True, False])
def test_only_request_failures_stop_undispatched_calls(
    tmp_path, monkeypatch, request_failed
):
    source, _, _ = job_fixture()
    sources = tmp_path / "sources.json"
    sources.write_text(json.dumps([source, {**source, "id": 2}]))
    reference = tmp_path / "reference.json"
    reference.write_text("{}")
    output = tmp_path / "run"
    prepare(
        sources,
        reference,
        output,
        ["openai/gpt-5.6-luna"],
        [1, 2],
    )
    budget_at(tmp_path / "budget.json")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-secret")
    calls = []

    def failed_job(job, *args):
        calls.append(job["job_id"])
        return {
            "job_id": job["job_id"],
            "errors": [
                "Provider rejected the request"
                if request_failed
                else "Classification cites outside its source inventory entry"
            ],
            "request_failed": request_failed,
            "cost_usd": None,
            "review": {"matters": []},
        }

    monkeypatch.setattr("eval.pass0_experiment.run_job", failed_job)
    report = run(output, tmp_path / "budget.json", workers=1)

    assert len(calls) == (1 if request_failed else 2)
    assert len(report["skipped_jobs"]) == (1 if request_failed else 0)
    assert report["status"] == "completed_with_errors"
