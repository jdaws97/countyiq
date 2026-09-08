"""Freeze and compare compact municipal readers under one durable $5 ledger.

Input is an archived evidence workspace. Only document metadata and complete
source pages enter prompts; previous cards and evaluation labels never do.
Every job is dispatched at most once. Uncertain costs stop the run and retain
the full reservation, including across process restarts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import signal
from dataclasses import asdict
from pathlib import Path

import requests
from countyiq.lib.backfill_authorization import BackfillAuthorization
from countyiq.lib.llm_harness import (
    OPENROUTER_URL,
    HarnessConfig,
    build_openrouter_payload,
)
from countyiq.lib.municipal_evidence import (
    REVIEW_SCHEMA,
    REVIEW_SYSTEM_PROMPT,
    REVIEW_VERSION,
    SELECTION_SCHEMA,
    SYSTEM_PROMPT,
    VERSION,
    EvidenceWindow,
    bind_evidence,
    bind_review,
    evidence_windows,
    review_prompt,
    source_document,
)
from countyiq.lib.municipal_value import source_value
from countyiq.lib.pass_llm_config import estimate_reserved_call_cost

# Verified against OpenRouter's model listing on 2026-09-07. Do not count
# Solar's temporary 90% promotion as a sustainable operating price.
PRICE_CEILINGS = {
    "openai/gpt-5.6-luna": (0.28, 1.32),
    "openai/gpt-5.6-luna-pro": (0.28, 1.32),
    "openai/gpt-5.6-sol": (2.80, 11.00),
    "google/gemini-2.5-flash-lite": (0.11, 0.44),
    "google/gemini-2.5-flash": (0.33, 2.75),
    "qwen/qwen3.5-flash-02-23": (0.08, 0.30),
    "deepseek/deepseek-v4-flash-0731": (0.16, 0.32),
    "z-ai/glm-5.3-flash": (0.16, 0.55),
    "minimax/minimax-m3": (0.33, 1.32),
}


def _write_new(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def prepare(workspace: Path, output: Path, model: str, source_ids: list[str]) -> dict:
    source = json.loads(workspace.read_text())
    selected = set(source_ids) or {str(row["source_id"]) for row in source["documents"]}
    pages_by_id: dict[str, list[dict]] = {}
    for page in source["source_pages"]:
        source_id = str(page["source_id"])
        if source_id in selected:
            pages_by_id.setdefault(source_id, []).append(page)
    if selected != pages_by_id.keys():
        raise ValueError("Every selected document must have archived source pages")
    prompt_price, completion_price = PRICE_CEILINGS[model]
    config = HarnessConfig(
        model_path=model,
        max_tokens=4096,
        temperature=0,
        top_k=0,
        top_p=1,
        thinking=False,
        reasoning_effort="low" if model.startswith("openai/") else None,
        json_schema=SELECTION_SCHEMA,
        schema_name="municipal_evidence",
        system_prompt=SYSTEM_PROMPT,
        max_price_prompt=prompt_price,
        max_price_completion=completion_price,
        require_parameters=True,
    )
    jobs = []
    for source_id, pages in sorted(pages_by_id.items()):
        pages.sort(key=lambda page: page["page"])
        document, page_spans = source_document(pages)
        windows = evidence_windows(document)
        for number, window in enumerate(windows, 1):
            payload = build_openrouter_payload(config, window.prompt)
            if model.startswith("qwen/"):
                payload["reasoning"] = {"enabled": False}
            payload["provider"]["allow_fallbacks"] = False
            # A byte is an upper bound on a text token, including non-ASCII
            # text. Include the schema and message framing in the reservation.
            max_input_tokens = (
                len(json.dumps(payload, ensure_ascii=False).encode()) + 256
            )
            reservation = estimate_reserved_call_cost(
                prompt_tokens=max_input_tokens,
                max_tokens=config.max_tokens,
                max_price_prompt=prompt_price,
                max_price_completion=completion_price,
                retries=0,
            )
            jobs.append(
                {
                    "id": f"{source_id}-w{number}",
                    "source_id": source_id,
                    "window": asdict(window),
                    "source_text_sha256": document.sha256,
                    "payload": payload,
                    "payload_sha256": _hash(payload),
                    "max_cost_usd": reservation,
                }
            )
        _write_new(
            output / "sources" / f"{source_id}.json",
            {"pages": pages, "page_spans": page_spans, "text_sha256": document.sha256},
        )
    protocol = {
        "version": VERSION,
        "model": model,
        "workspace_sha256": hashlib.sha256(workspace.read_bytes()).hexdigest(),
        "jobs": jobs,
        "max_cost_usd": sum(job["max_cost_usd"] for job in jobs),
    }
    _write_new(output / "protocol.json", protocol)
    return {"jobs": len(jobs), "maximum_reservation_usd": protocol["max_cost_usd"]}


def prepare_review(
    prior: Path,
    output: Path,
    model: str,
    *,
    direct: bool = False,
    reasoning_effort: str | None = None,
    max_tokens: int = 4096,
    provider: str | None = None,
    json_object: bool = False,
    provider_only: bool = False,
) -> dict:
    input_path = prior if direct else prior / "results.json"
    report = json.loads(input_path.read_text())
    by_source: dict[str, list[dict]] = {}
    sources = {}
    if direct:
        pages_by_source = {}
        for page in report["source_pages"]:
            pages_by_source.setdefault(str(page["source_id"]), []).append(page)
        for source_id, pages in pages_by_source.items():
            document, page_spans = source_document(pages)
            sources[source_id] = {
                "pages": pages,
                "page_spans": page_spans,
                "text_sha256": document.sha256,
            }
            by_source[source_id] = []
    else:
        for result in report["results"]:
            if result["errors"] or result.get("status") != "complete":
                raise ValueError("Review requires complete, source-bound discovery")
            by_source.setdefault(result["source_id"], []).extend(result["cards"])
    prompt_price, completion_price = PRICE_CEILINGS[model]
    config = HarnessConfig(
        model_path=model,
        max_tokens=max_tokens,
        temperature=0,
        top_k=0,
        top_p=1,
        thinking=False,
        reasoning_effort="low" if model.startswith("openai/") else None,
        json_schema=REVIEW_SCHEMA,
        schema_name="municipal_evidence_review",
        system_prompt=REVIEW_SYSTEM_PROMPT,
        max_price_prompt=prompt_price,
        max_price_completion=completion_price,
        require_parameters=True,
        provider_quantizations=("fp8",)
        if model == "z-ai/glm-5.3-flash" or model.startswith("deepseek/deepseek-v4")
        else None,
    )
    if reasoning_effort is not None:
        from dataclasses import replace

        config = replace(config, reasoning_effort=reasoning_effort)
    jobs = []
    for source_id, cards in sorted(by_source.items()):
        source = sources.get(source_id)
        if source is None:
            source = json.loads((prior / "sources" / f"{source_id}.json").read_text())
        _write_new(output / "sources" / f"{source_id}.json", source)
        document, _ = source_document(source["pages"])
        value = source_value(document)
        payload = build_openrouter_payload(config, review_prompt(cards, document))
        payload["provider"]["allow_fallbacks"] = True
        if provider:
            payload["provider"]["order"] = [provider]
            if provider_only:
                payload["provider"]["only"] = [provider]
                payload["provider"]["allow_fallbacks"] = False
        if json_object:
            payload["response_format"] = {"type": "json_object"}
            payload["messages"][-1]["content"] += (
                "\nRequired output JSON schema:\n"
                + json.dumps(REVIEW_SCHEMA, separators=(",", ":"))
            )
        max_input_tokens = len(json.dumps(payload, ensure_ascii=False).encode()) + 256
        reservation = estimate_reserved_call_cost(
            prompt_tokens=max_input_tokens,
            max_tokens=config.max_tokens,
            max_price_prompt=prompt_price,
            max_price_completion=completion_price,
            retries=0,
        )
        jobs.append(
            {
                "id": f"{source_id}-review",
                "kind": "skip" if value.skip_reason else "review",
                "skip_reason": value.skip_reason,
                "cards": cards,
                "cards_sha256": _hash(cards),
                "source_id": source_id,
                "source_text_sha256": document.sha256,
                "payload": payload,
                "payload_sha256": _hash(payload),
                "max_cost_usd": 0.0 if value.skip_reason else reservation,
            }
        )
    protocol = {
        "version": VERSION,
        "review_version": REVIEW_VERSION,
        "model": model,
        "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
        "method": "direct_source_read" if direct else "discovery_then_review",
        "jobs": jobs,
        "max_cost_usd": sum(job["max_cost_usd"] for job in jobs),
    }
    _write_new(output / "protocol.json", protocol)
    return {"jobs": len(jobs), "maximum_reservation_usd": protocol["max_cost_usd"]}


def run(output: Path, budget_path: Path, request_deadline_seconds: int = 300) -> dict:
    if not 1 <= request_deadline_seconds <= 900:
        raise ValueError("Request deadline must be between 1 and 900 seconds")
    protocol = json.loads((output / "protocol.json").read_text())
    if protocol["version"] != VERSION:
        raise ValueError("Reader changed after preparation")
    if protocol.get("review_version", REVIEW_VERSION) != REVIEW_VERSION:
        raise ValueError("Review changed after preparation")
    budget = BackfillAuthorization(
        budget_path,
        pass_number=0,
        model="pass03-optimization",
        max_cost_usd=5.0,
        max_price_prompt=3.00,
        max_price_completion=15.00,
    )
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        key = Path("~/.config/openrouter/key").expanduser().read_text().strip()
    results = []
    for job in protocol["jobs"]:
        directory = output / "jobs" / job["id"]
        if directory.exists():
            result_path = directory / "result.json"
            if not result_path.exists():
                raise RuntimeError(
                    "Earlier dispatch is unsettled; it cannot be repeated"
                )
            saved = json.loads(result_path.read_text())
            if saved.get("stop"):
                raise RuntimeError(
                    "Earlier job stopped on an accounting/transport failure"
                )
            results.append(saved)
            continue
        if _hash(job["payload"]) != job["payload_sha256"]:
            raise ValueError("Frozen request changed")
        if job.get("kind") == "review" and _hash(job["cards"]) != job["cards_sha256"]:
            raise ValueError("Candidate cards changed after preparation")
        archived = json.loads(
            (output / "sources" / f"{job['source_id']}.json").read_text()
        )
        document, _ = source_document(archived["pages"])
        if document.sha256 != job["source_text_sha256"]:
            raise ValueError("Archived source changed")
        if job.get("kind") == "skip":
            if source_value(document).skip_reason != job["skip_reason"]:
                raise ValueError("Value policy changed after preparation")
            skipped = {
                "id": job["id"],
                "source_id": job["source_id"],
                "status": "complete",
                "cards": [],
                "errors": [],
                "cost_usd": 0.0,
                "value_decision": job["skip_reason"],
            }
            _write_new(directory / "result.json", skipped)
            results.append(skipped)
            continue
        reservation = budget.reserve(job["max_cost_usd"])
        _write_new(directory / "reservation.json", {"id": reservation, "job": job})
        cost = None
        stop = False
        result = {
            "id": job["id"],
            "source_id": job["source_id"],
            "cards": [],
            "errors": [],
        }

        def deadline_expired(signum, frame):
            raise requests.Timeout(
                f"Total request deadline exceeded ({request_deadline_seconds}s)"
            )

        previous_handler = signal.signal(signal.SIGALRM, deadline_expired)
        signal.alarm(request_deadline_seconds)
        try:
            response = requests.post(
                OPENROUTER_URL,
                json=job["payload"],
                headers={
                    "Authorization": f"Bearer {key}",
                    "X-Title": "CountyIQ cost optimization",
                },
                timeout=(15, 180),
            )
            (directory / "response.txt").write_text(response.text)
            data = response.json()
            usage = data.get("usage") or {}
            cost = usage.get("cost")
            result["usage"] = usage
            result["provider"] = data.get("provider")
            response.raise_for_status()
            choice = data["choices"][0]
            if choice.get("finish_reason") != "stop":
                raise ValueError(f"Incomplete response: {choice.get('finish_reason')}")
            parsed = json.loads(choice["message"]["content"])
            result["parsed"] = parsed
            if job.get("kind") == "review":
                result.update(bind_review(parsed, job["cards"], document))
            else:
                result.update(
                    bind_evidence(parsed, document, EvidenceWindow(**job["window"]))
                )
        except (
            requests.RequestException,
            ValueError,
            KeyError,
            IndexError,
            TypeError,
            KeyboardInterrupt,
        ) as error:
            result["errors"].append(f"{type(error).__name__}: {error}")
            result["status"] = "failed"
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous_handler)
            known = (
                isinstance(cost, (int, float))
                and not isinstance(cost, bool)
                and math.isfinite(cost)
                and cost >= 0
            )
            if known:
                budget.settle(reservation, cost)
                stop = cost > job["max_cost_usd"]
            else:
                budget.forfeit(reservation)
                stop = True
            result.update(cost_usd=cost if known else None, stop=stop)
            _write_new(directory / "result.json", result)
        results.append(result)
        print(
            json.dumps(
                {
                    "job": job["id"],
                    "cards": len(result["cards"]),
                    "cost_usd": cost,
                    "errors": result["errors"],
                }
            ),
            flush=True,
        )
        if stop:
            raise RuntimeError("Provider accounting could not verify the cost ceiling")
    report = {
        "model": protocol["model"],
        "results": results,
        "budget": budget.snapshot(),
    }
    _write_new(output / "results.json", report)
    return {"jobs": len(results), "budget": report["budget"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode", choices=("prepare", "prepare-review", "prepare-direct", "run")
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--model", choices=PRICE_CEILINGS)
    parser.add_argument("--source-ids", nargs="*", default=[])
    parser.add_argument("--budget", type=Path)
    parser.add_argument("--prior", type=Path)
    parser.add_argument("--reasoning-effort", choices=("low", "medium", "high"))
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--provider")
    parser.add_argument("--provider-only", action="store_true")
    parser.add_argument("--json-object", action="store_true")
    parser.add_argument("--request-deadline-seconds", type=int, default=300)
    args = parser.parse_args()
    if args.mode == "prepare":
        if not args.workspace or not args.model:
            parser.error("prepare requires --workspace and --model")
        result = prepare(args.workspace, args.output, args.model, args.source_ids)
    elif args.mode == "prepare-review":
        if not args.prior or not args.model:
            parser.error("prepare-review requires --prior and --model")
        result = prepare_review(
            args.prior,
            args.output,
            args.model,
            reasoning_effort=args.reasoning_effort,
            max_tokens=args.max_tokens,
            provider=args.provider,
            json_object=args.json_object,
            provider_only=args.provider_only,
        )
    elif args.mode == "prepare-direct":
        if not args.workspace or not args.model:
            parser.error("prepare-direct requires --workspace and --model")
        result = prepare_review(
            args.workspace,
            args.output,
            args.model,
            direct=True,
            reasoning_effort=args.reasoning_effort,
            max_tokens=args.max_tokens,
            provider=args.provider,
            json_object=args.json_object,
            provider_only=args.provider_only,
        )
    else:
        if not args.budget:
            parser.error("run requires --budget")
        result = run(args.output, args.budget, args.request_deadline_seconds)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
