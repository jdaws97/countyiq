"""Freeze and execute Pass 0 experiments under one durable spending cap.

Every dispatched request has an immutable request/response artifact. A crashed
or uncertain call retains its full reservation; a run cannot dispatch it again.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

import requests
from countyiq.lib import pass0_locator, pass0_packet_facts
from countyiq.lib.backfill_authorization import BackfillAuthorization
from countyiq.lib.llm_harness import (
    OPENROUTER_URL,
    HarnessConfig,
    build_openrouter_payload,
    get_preset_for_model,
)
from countyiq.lib.pass0_facts import (
    FACTS_SCHEMA,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    document_prompt,
    facts_schema,
    structural_review,
)

from eval.pass0_discovery import (
    discovery_schema,
    discovery_system_prompt,
    review_discovery,
)
from eval.protocol import estimate_max_call_cost

PIPELINES = Path(__file__).resolve().parents[1]
PRICE_CEILINGS = {"openai/gpt-5.6-luna": (0.28, 1.32)}
REVIEW_MODES = ("discovery", "locations", "packet_facts", "facts")
SOURCE_FILES = (
    "eval/pass0_experiment.py",
    "eval/pass0_discovery.py",
    "eval/pass0_schema_guidance.py",
    "countyiq/lib/pass0_facts.py",
    "countyiq/lib/pass0_locator.py",
    "countyiq/lib/pass0_packet_facts.py",
    "countyiq/lib/pass0_source.py",
    "countyiq/lib/llm_harness.py",
    "countyiq/lib/proceeding_contract.py",
)


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_new(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def model_config(model: str, effort: str, max_tokens: int) -> HarnessConfig:
    if model not in PRICE_CEILINGS:
        raise ValueError(f"Model is outside the current Pass 0 selection: {model}")
    if effort not in {"low", "medium", "high"}:
        raise ValueError("Luna experiments require low, medium or high reasoning")
    prompt_price, completion_price = PRICE_CEILINGS[model]
    preset = get_preset_for_model(model, thinking=True, reasoning_task=False)
    return HarnessConfig(
        model_path=model,
        max_tokens=max_tokens,
        thinking=True,
        reasoning_effort=effort,
        system_prompt=SYSTEM_PROMPT,
        json_schema=FACTS_SCHEMA,
        schema_name="municipal_facts",
        require_parameters=True,
        max_price_prompt=prompt_price,
        max_price_completion=completion_price,
        **preset,
    )


def prepare(
    sources_path: Path,
    reference_path: Path,
    output: Path,
    models: list[str],
    source_ids: list[int],
    *,
    mode: str = "discovery",
    effort: str = "low",
    max_tokens: int = 16_384,
    inventory_path: Path | None = None,
    per_matter: bool = False,
    group_overlaps: bool = False,
) -> dict:
    if mode not in REVIEW_MODES:
        raise ValueError(f"Unsupported Pass 0 mode: {mode}")
    if (mode == "packet_facts") != (inventory_path is not None):
        raise ValueError("Only packet_facts requires a frozen inventory")
    if per_matter and mode != "packet_facts":
        raise ValueError("Per-matter interpretation requires packet_facts")
    if group_overlaps and not per_matter:
        raise ValueError("Overlap grouping requires per-matter interpretation")
    sources = json.loads(sources_path.read_text())
    selected = [row for row in sources if row["id"] in source_ids]
    if len(selected) != len(set(source_ids)) or len(source_ids) != len(set(source_ids)):
        raise ValueError("Every selected source must exist exactly once")
    if len(models) != len(set(models)) or not models:
        raise ValueError("Select distinct models")
    if not selected or any(not source.get("raw_text") for source in selected):
        raise ValueError("Select nonempty text sources")
    source_data = {str(row["id"]): row for row in selected}
    inventories = {}
    if inventory_path is not None:
        for result in json.loads(inventory_path.read_text())["results"]:
            if result["source_id"] not in source_ids:
                continue
            if result["source_id"] in inventories:
                raise ValueError("Every selected source needs exactly one inventory")
            inventories[result["source_id"]] = result
        if set(inventories) != set(source_ids):
            raise ValueError("Inventory must cover every selected source")
    jobs = []
    for source in selected:
        prompt, document = document_prompt(source)
        locations = None
        evidence_ranges = None
        context_ranges = None
        if inventory_path is not None:
            inventory = inventories[source["id"]]
            if inventory["source_sha256"] != document.sha256 or inventory["errors"]:
                raise ValueError("Inventory failed or belongs to another source")
            locations = inventory["parsed"]
            prompt, document, evidence_ranges, context_ranges = (
                pass0_packet_facts.full_source_interpretation_prompt(source, locations)
            )
        for model in models:
            config = model_config(model, effort, max_tokens)
            if mode == "discovery":
                config = replace(
                    config,
                    system_prompt=discovery_system_prompt(),
                    json_schema=discovery_schema(document),
                    schema_name="municipal_discovery",
                )
            elif mode == "locations":
                config = replace(
                    config,
                    system_prompt=pass0_locator.SYSTEM_PROMPT,
                    json_schema=pass0_locator.SCHEMA,
                    schema_name="municipal_locations",
                )
            elif mode == "packet_facts":
                config = replace(
                    config,
                    system_prompt=pass0_packet_facts.interpretation_system_prompt(),
                    json_schema=pass0_packet_facts.packet_schema(
                        locations,
                        document,
                        evidence_ranges=evidence_ranges,
                        context_ranges=context_ranges,
                    ),
                    schema_name="municipal_packets",
                )
            else:
                config = replace(config, json_schema=facts_schema(document))
            jobs.append(
                {
                    "job_id": f"{source['id']}-{model.replace('/', '--')}",
                    "source_id": source["id"],
                    "source_sha256": document.sha256,
                    "model": model,
                    "review_kind": mode,
                    "draft": locations,
                    "evidence_ranges": evidence_ranges,
                    "context_ranges": context_ranges,
                    "config": asdict(config),
                    "payload": build_openrouter_payload(config, prompt),
                    "maximum_cost_usd": estimate_max_call_cost(
                        config, prompt, retries=0
                    ),
                }
            )
    if per_matter:
        jobs = expand_matter_jobs(jobs, source_data, group_overlaps=group_overlaps)
    protocol = {
        "created_at": datetime.now(UTC).isoformat(),
        "purpose": "Pass 0 discovery and interpretation comparison; no production writes",
        "prompt_version": PROMPT_VERSION,
        "code_sha256": {
            name: sha256((PIPELINES / name).read_bytes()) for name in SOURCE_FILES
        },
        "reference_sha256": sha256(reference_path.read_bytes()),
        "sources_sha256": sha256(sources_path.read_bytes()),
        "jobs": jobs,
        "calls": len(jobs),
        "generation_retries": 0,
        "transport_retries": 0,
        "maximum_cost_usd": sum(job["maximum_cost_usd"] for job in jobs),
        "acceptance": "Measure distinct topic coverage, identity/action attribution, consistency and cost; secondary details can be enriched later.",
    }
    output.mkdir(parents=True, exist_ok=False)
    if inventory_path is not None:
        protocol["inventory_sha256"] = sha256(inventory_path.read_bytes())
        (output / "inventory.json").write_bytes(inventory_path.read_bytes())
    write_new(output / "sources.json", source_data)
    protocol["selected_sources_sha256"] = sha256((output / "sources.json").read_bytes())
    for name in SOURCE_FILES:
        archived = output / "code" / name
        archived.parent.mkdir(parents=True, exist_ok=True)
        archived.write_bytes((PIPELINES / name).read_bytes())
    (output / "reference.json").write_bytes(reference_path.read_bytes())
    write_new(output / "protocol.json", protocol)
    return protocol


def expand_matter_jobs(
    jobs: list[dict], sources: dict[str, dict], *, group_overlaps: bool = False
) -> list[dict]:
    """Interpret each inventory group with full context and bounded fact citations."""
    expanded = []
    for job in jobs:
        source = sources[str(job["source_id"])]
        _, document = document_prompt(source)
        groups = (
            pass0_packet_facts.overlap_groups(job["draft"], document)
            if group_overlaps
            else [[index] for index in range(len(job["draft"]["matters"]))]
        )
        for group_index, indices in enumerate(groups):
            locations = {
                "matters": [job["draft"]["matters"][index] for index in indices]
            }
            prompt, document, evidence_ranges, context_ranges = (
                pass0_packet_facts.full_source_interpretation_prompt(source, locations)
            )
            config = replace(
                HarnessConfig(**job["config"]),
                json_schema=pass0_packet_facts.packet_schema(
                    locations,
                    document,
                    evidence_ranges=evidence_ranges,
                    context_ranges=context_ranges,
                ),
            )
            expanded.append(
                {
                    **job,
                    "job_id": f"{job['job_id']}-group-{group_index}",
                    "inventory_index": indices[0] if len(indices) == 1 else None,
                    "inventory_indices": indices,
                    "evidence_ranges": evidence_ranges,
                    "context_ranges": context_ranges,
                    "source_boundary": "complete_document_with_bounded_facts",
                    "draft": locations,
                    "config": asdict(config),
                    "payload": build_openrouter_payload(config, prompt),
                    "maximum_cost_usd": estimate_max_call_cost(
                        config, prompt, retries=0
                    ),
                }
            )
    return expanded


def authorization(path: Path, *, max_cost_usd: float = 5.0) -> BackfillAuthorization:
    return BackfillAuthorization(
        path,
        pass_number=0,
        model="pass0-experiments",
        max_cost_usd=max_cost_usd,
        max_price_prompt=5.5,
        max_price_completion=22.0,
    )


def run_job(
    job: dict,
    source: dict,
    output: Path,
    budget: BackfillAuthorization,
    api_key: str,
) -> dict:
    if job.get("review_kind") not in REVIEW_MODES:
        raise ValueError(f"Unsupported Pass 0 mode: {job.get('review_kind')}")
    if job["model"] not in PRICE_CEILINGS:
        raise ValueError(
            f"Model is outside the current Pass 0 selection: {job['model']}"
        )
    started = time.monotonic()
    job_dir = output / job["job_id"]
    job_dir.mkdir(exist_ok=False)
    request_path = job_dir / "request.json"
    write_new(request_path, job)
    reservation = budget.reserve(job["maximum_cost_usd"])
    write_new(job_dir / "reservation.json", {"id": reservation})
    parsed = None
    errors = []
    response_data = None
    cost = None
    request_failed = True
    try:
        response = requests.post(
            OPENROUTER_URL,
            json=job["payload"],
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "X-Title": "CountyIQ Pass 0 qualification",
            },
            timeout=(15, 240),
        )
        (job_dir / "response.txt").write_text(response.text)
        response_data = response.json()
        cost = (response_data.get("usage") or {}).get("cost")
        response.raise_for_status()
        choice = response_data["choices"][0]
        finish_reason = choice.get("finish_reason")
        # Truncation and filtering are failures of this document's output, not
        # evidence that the provider cannot serve other prepared documents.
        request_failed = finish_reason not in {"stop", "length", "content_filter"}
        if finish_reason != "stop":
            errors.append(f"Incomplete response: {finish_reason}")
        else:
            # Reasoning is retained in the raw response, never treated as output.
            parsed = json.loads(choice["message"]["content"])
    except (
        requests.RequestException,
        ValueError,
        KeyError,
        IndexError,
        TypeError,
    ) as error:
        errors.append(f"{type(error).__name__}: {error}")
    finally:
        cost_known = (
            isinstance(cost, (int, float))
            and not isinstance(cost, bool)
            and math.isfinite(cost)
            and cost >= 0
        )
        if cost_known:
            budget.settle(reservation, cost)
            if cost > job["maximum_cost_usd"]:
                request_failed = True
                errors.append("Provider cost exceeded the reserved ceiling")
        else:
            request_failed = True
            budget.forfeit(reservation)
            errors.append("Cost unavailable; full reservation charged conservatively")
    _, document = document_prompt(source)
    if document.sha256 != job["source_sha256"]:
        raise ValueError("Source changed after request preparation")
    if job["review_kind"] == "locations":
        review = pass0_locator.review_locations(parsed, document)
    elif job.get("review_kind") == "packet_facts":
        review = pass0_packet_facts.review_packet_facts(
            parsed,
            document,
            job["draft"],
            evidence_ranges=job.get("evidence_ranges"),
            context_ranges=job.get("context_ranges"),
        )
    elif job.get("review_kind") == "discovery":
        review = review_discovery(parsed, document)
    else:
        review = structural_review(parsed, document)
    if not errors:
        errors.extend(review["envelope_errors"])
        if review["rejected"]:
            errors.append(
                f"{len(review['rejected'])} extracted matters failed structural validation"
            )
    result = {
        "job_id": job["job_id"],
        "source_id": source["id"],
        "inventory_index": job.get("inventory_index"),
        "inventory_indices": job.get("inventory_indices"),
        "model": job["model"],
        "source_sha256": document.sha256,
        "draft_sha256": sha256(json.dumps(job["draft"], sort_keys=True).encode())
        if job.get("draft") is not None
        else None,
        "elapsed_seconds": time.monotonic() - started,
        "cost_usd": cost,
        "charged_usd": cost if cost_known else job["maximum_cost_usd"],
        "errors": errors,
        "request_failed": request_failed,
        "usage": response_data.get("usage")
        if isinstance(response_data, dict)
        else None,
        "provider": response_data.get("provider")
        if isinstance(response_data, dict)
        else None,
        "parsed": parsed,
        "review": review,
    }
    write_new(job_dir / "result.json", result)
    return result


def run(
    output: Path,
    budget_path: Path,
    *,
    workers: int = 3,
    max_cost_usd: float = 5.0,
) -> dict:
    protocol_path = output / "protocol.json"
    protocol = json.loads(protocol_path.read_text())
    for job in protocol["jobs"]:
        if job["model"] not in PRICE_CEILINGS:
            raise ValueError(
                f"Model is outside the current Pass 0 selection: {job['model']}"
            )
        if job.get("review_kind") not in REVIEW_MODES:
            raise ValueError(f"Unsupported Pass 0 mode: {job.get('review_kind')}")
    for name, expected in protocol["code_sha256"].items():
        if sha256((PIPELINES / name).read_bytes()) != expected:
            raise ValueError(f"Code changed after preparation: {name}")
    if sha256((output / "reference.json").read_bytes()) != protocol["reference_sha256"]:
        raise ValueError("Reference changed after preparation")
    if (
        sha256((output / "sources.json").read_bytes())
        != protocol["selected_sources_sha256"]
    ):
        raise ValueError("Source text or metadata changed after preparation")
    sources = json.loads((output / "sources.json").read_text())
    for job in protocol["jobs"]:
        _, document = document_prompt(sources[str(job["source_id"])])
        if document.sha256 != job["source_sha256"]:
            raise ValueError("Source changed after preparation")
    budget = authorization(budget_path, max_cost_usd=max_cost_usd)
    budget.snapshot()
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        key = Path("~/.config/openrouter/key").expanduser().read_text().strip()
    if not key:
        raise ValueError("OpenRouter API key is unavailable")
    jobs_dir = output / "jobs"
    jobs_dir.mkdir(exist_ok=False)
    write_new(
        output / "dispatch.json",
        {
            "started_at": datetime.now(UTC).isoformat(),
            "pid": os.getpid(),
            "protocol_sha256": sha256(protocol_path.read_bytes()),
            "authorization_path": str(budget_path.resolve()),
        },
    )
    results, errors, skipped = [], [], []
    queued = deque(protocol["jobs"])
    blocked_models = set()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {}
        while queued or pending:
            while queued and len(pending) < workers:
                job = queued.popleft()
                if job["model"] in blocked_models:
                    skipped.append(
                        {
                            "job": job["job_id"],
                            "reason": "Earlier candidate call failed",
                        }
                    )
                    continue
                future = pool.submit(
                    run_job,
                    job,
                    sources[str(job["source_id"])],
                    jobs_dir,
                    budget,
                    key,
                )
                pending[future] = job
            if not pending:
                break
            future = next(as_completed(pending))
            job = pending.pop(future)
            try:
                result = future.result()
                results.append(result)
                if result["request_failed"]:
                    blocked_models.add(job["model"])
                print(
                    json.dumps(
                        {
                            "job": result["job_id"],
                            "cost": result["cost_usd"],
                            "matters": len(result["review"]["matters"]),
                            "errors": result["errors"],
                        }
                    ),
                    flush=True,
                )
            except Exception as error:  # noqa: BLE001 -- isolate failed paid workers; never retry them
                errors.append({"job": job["job_id"], "error": str(error)})
                blocked_models.add(job["model"])
    report = {
        "status": "completed_with_errors"
        if errors or skipped or any(result["errors"] for result in results)
        else "completed",
        "completed_at": datetime.now(UTC).isoformat(),
        "protocol_sha256": sha256(protocol_path.read_bytes()),
        "results": results,
        "errors": errors,
        "skipped_jobs": skipped,
        "budget": budget.snapshot(),
    }
    write_new(output / "results.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    preparation = commands.add_parser("prepare")
    preparation.add_argument("--sources", type=Path, required=True)
    preparation.add_argument("--reference", type=Path, required=True)
    preparation.add_argument("--output", type=Path, required=True)
    preparation.add_argument(
        "--models", nargs="+", default=list(PRICE_CEILINGS), choices=PRICE_CEILINGS
    )
    preparation.add_argument("--source-ids", nargs="+", type=int, required=True)
    preparation.add_argument("--mode", choices=REVIEW_MODES, default="discovery")
    preparation.add_argument(
        "--effort", choices=("low", "medium", "high"), default="low"
    )
    preparation.add_argument("--max-tokens", type=int, default=16_384)
    preparation.add_argument("--inventory", type=Path)
    preparation.add_argument("--per-matter", action="store_true")
    preparation.add_argument("--group-overlaps", action="store_true")
    execution = commands.add_parser("run")
    execution.add_argument("--output", type=Path, required=True)
    execution.add_argument("--budget", type=Path, required=True)
    execution.add_argument(
        "--max-cost-usd",
        type=float,
        required=True,
        help="Approved total cap; must match the existing ledger.",
    )
    execution.add_argument("--workers", type=int, default=3, choices=range(1, 5))
    args = parser.parse_args()
    if args.command == "prepare":
        protocol = prepare(
            args.sources,
            args.reference,
            args.output,
            args.models,
            args.source_ids,
            mode=args.mode,
            effort=args.effort,
            max_tokens=args.max_tokens,
            inventory_path=args.inventory,
            per_matter=args.per_matter,
            group_overlaps=args.group_overlaps,
        )
        print(
            json.dumps(
                {"calls": protocol["calls"], "max_cost": protocol["maximum_cost_usd"]}
            )
        )
    else:
        report = run(
            args.output,
            args.budget,
            workers=args.workers,
            max_cost_usd=args.max_cost_usd,
        )
        print(json.dumps({"status": report["status"], "budget": report["budget"]}))


if __name__ == "__main__":
    main()
