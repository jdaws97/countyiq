"""Author bounded, resumable backfill batches using a ChatGPT Codex login."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from countyiq.assets.enrichment.proceeding_extraction import PENDING_PROCEEDINGS_QUERY
from countyiq.assets.enrichment.record_explanations import (
    _source_bundles,
    persist_explanation,
)
from countyiq.lib import municipal_matters
from countyiq.lib.county_config import get_county_config
from countyiq.lib.error_budget import check_error_budget
from countyiq.lib.intelligence_integrity import content_hash
from countyiq.lib.llm_harness import HarnessConfig
from countyiq.lib.municipal_evidence import (
    REVIEW_SCHEMA,
    REVIEW_SYSTEM_PROMPT,
    REVIEW_VERSION,
    review_prompt,
)
from countyiq.lib.municipal_evidence_pipeline import (
    persist_evidence,
    prepare_source,
    read_evidence,
    record_snapshot,
)
from countyiq.lib.record_explanations import (
    EXPLANATION_SCHEMA,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    explanation_prompt,
    generate_explanation,
)
from countyiq.lib.robots import RobotsPolicy
from countyiq.lib.source_rights import (
    authorize_municipality_sources,
    authorize_source,
    require_source_use,
)
from countyiq.lib.source_unit_refinement import refine_source_units
from countyiq.lib.subscription_backfill import (
    SubscriptionAuthor,
    SubscriptionUnavailable,
    prefetched_batches,
)
from countyiq.resources.database import make_database_resource
from jsonschema import ValidationError


def source_batches(sources, size):
    """Keep complete sources together and bound each combined model context."""
    batch = []
    characters = 0
    for source in sources:
        length = len(source["prompt"])
        if batch and (len(batch) >= size or characters + length > 120_000):
            yield batch
            batch = []
            characters = 0
        batch.append(source)
        characters += length
    if batch:
        yield batch


def previous_reads(database, kind):
    with database.dict_cursor() as cursor:
        cursor.execute(
            """
            SELECT DISTINCT ON (subject_key)
                subject_key, source_hash, prompt_version, payload
            FROM meta.intelligence_inference_history
            WHERE output_kind = %s AND disposition = 'accepted'
            ORDER BY subject_key, inference_id DESC
            """,
            ("municipal_evidence" if kind == "read" else "record_explanation",),
        )
        return {row["subject_key"]: dict(row) for row in cursor.fetchall()}


def proceeding_rows(database, ids=None):
    with database.dict_cursor() as cursor:
        if ids is None:
            cursor.execute(PENDING_PROCEEDINGS_QUERY)
        else:
            cursor.execute(
                f"SELECT * FROM ({PENDING_PROCEEDINGS_QUERY}) eligible "
                "WHERE eligible.id = ANY(%s)",
                (list(ids),),
            )
        return {row["id"]: dict(row) for row in cursor.fetchall()}


def run(database, args):
    author = SubscriptionAuthor(args.directory, model=args.model)
    author.check_login()
    refinements = (
        json.loads(args.unit_breaks.read_text())
        if getattr(args, "unit_breaks", None)
        else {}
    )
    reading = args.kind == "read"
    matter_accounts = args.kind == "matter"
    schema = municipal_matters.MATTERS_SCHEMA if matter_accounts else EXPLANATION_SCHEMA
    system_prompt = (
        municipal_matters.SYSTEM_PROMPT if matter_accounts else SYSTEM_PROMPT
    )
    prompt_version = (
        municipal_matters.PROMPT_VERSION if matter_accounts else PROMPT_VERSION
    )
    generate = (
        municipal_matters.generate_matters if matter_accounts else generate_explanation
    )
    persist = (
        municipal_matters.persist_matters if matter_accounts else persist_explanation
    )
    build_prompt = (
        municipal_matters.matter_prompt if matter_accounts else explanation_prompt
    )
    config = HarnessConfig(
        model_path=f"codex/subscription:{args.model}",
        json_schema=REVIEW_SCHEMA if reading else schema,
        system_prompt=REVIEW_SYSTEM_PROMPT if reading else system_prompt,
        reasoning_effort="medium",
    )
    previous = previous_reads(database, args.kind)
    authorizations = {}
    if reading:
        require_source_use(
            authorize_source(
                database,
                source_key="public_proceedings",
                acquisition_method="official_document_direct",
                asset_key="subscription_backfill",
            ),
            "derived_product",
        )
        authorizations = authorize_municipality_sources(
            database,
            entries=get_county_config().municipality_websites,
            acquisition_method="official_document_direct",
            asset_key="subscription_backfill",
        )
        sources = list(proceeding_rows(database, args.ids or None).values())
        if args.ids:
            requested = set(args.ids)
            sources = [row for row in sources if row["id"] in requested]
            if requested - {row["id"] for row in sources}:
                raise ValueError("Requested proceeding is not currently eligible")
        total = len(sources)
    else:
        total, sources = _source_bundles(
            database, args.kind, subject_keys=args.subjects, pidns=args.pidns
        )
    counts = {
        "eligible": total,
        "accepted": 0,
        "unchanged": 0,
        "errors": 0,
        "quarantined": 0,
        "api_calls": 0,
    }
    robots = RobotsPolicy(
        "CountyIQ/1.0 (+https://countyiq.app)", product_token="CountyIQ"
    )
    attempted = 0
    failures = []
    stop_reason = "scope_exhausted"
    started_at = datetime.now(UTC).isoformat()

    def write_status(*, finished=False):
        remaining = total - counts["accepted"] - counts["unchanged"]
        report = {
            **counts,
            "kind": args.kind,
            "model": args.model,
            "workers": args.workers,
            "remaining": remaining,
            "status": ("partial" if remaining else "complete")
            if finished
            else "running",
            "stop_reason": stop_reason if finished else None,
            "failures": failures,
            "started_at": started_at,
            "updated_at": datetime.now(UTC).isoformat(),
            "selectors": {
                "ids": args.ids,
                "subjects": args.subjects,
                "pidns": args.pidns,
            },
        }
        path = args.directory / f"{args.kind}-status.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(report, indent=2) + "\n")
        temporary.replace(path)
        return report

    write_status()

    def pending_sources():
        nonlocal attempted, stop_reason
        for source in sources:
            if source is None:
                counts["errors"] += 1
                continue
            subject = f"proceeding:{source['id']}" if reading else source["subject_key"]
            prior = previous.get(subject)
            if reading:
                unchanged = bool(
                    prior
                    and prior["prompt_version"] == REVIEW_VERSION
                    and prior["payload"].get("record_snapshot")
                    == record_snapshot(source)
                )
            else:
                unchanged = bool(
                    prior
                    and prior["prompt_version"] == prompt_version
                    and prior["source_hash"] == content_hash(source)
                )
            if unchanged:
                counts["unchanged"] += 1
                continue
            if attempted >= args.limit:
                stop_reason = "item_limit"
                return
            attempted += 1
            try:
                prepared = {"source": source, "subject": subject}
                if reading:
                    document, pages = prepare_source(source, authorizations, robots)
                    if str(source["id"]) in refinements:
                        document = refine_source_units(
                            document, refinements[str(source["id"])]
                        )
                    prepared.update(
                        document=document,
                        pages=pages,
                        prompt=review_prompt([], document),
                    )
                else:
                    prepared["prompt"] = build_prompt(source)
                yield prepared
            except ValueError as error:
                counts["errors"] += 1
                failures.append({"subject": subject, "error": str(error)})
                print(json.dumps({"subject": subject, "error": str(error)}), flush=True)

    with prefetched_batches(
        author,
        config,
        source_batches(pending_sources(), args.batch_size),
        workers=args.workers,
    ) as batches:
        for batch, author, prefetch in batches:
            try:
                prefetch.result()
            except SubscriptionUnavailable:
                stop_reason = "subscription_unavailable"
                break
            except (ValueError, ValidationError) as error:
                # Preserve the rejected batch artifact, then author each original
                # source separately. Never treat a missing batch item as an empty read.
                print(json.dumps({"batch_split_reason": str(error)}), flush=True)
            for prepared in batch:
                author.receipts.clear()
                source = prepared["source"]
                subject = prepared["subject"]
                try:
                    if reading:
                        document = prepared["document"]
                        reviewed = read_evidence(document, config, author)
                        # Recheck eligibility after slow authoring. Changed sources
                        # and expired rights fail before the persistence call.
                        current = proceeding_rows(database, [source["id"]]).get(
                            source["id"]
                        )
                        if current is None or record_snapshot(
                            current
                        ) != record_snapshot(source):
                            raise ValueError(
                                "Source or eligibility changed during authoring"
                            )
                        result = persist_evidence(
                            database,
                            source,
                            document,
                            prepared["pages"],
                            reviewed,
                            config,
                            provenance=author.provenance(),
                        )
                    else:
                        output, attempts = generate(source, config, author)
                        # Matter persistence checks the complete current source
                        # inside its alias transaction. Avoid rebuilding it twice.
                        if not matter_accounts:
                            selectors = (
                                {"subject_keys": [subject]}
                                if args.kind == "municipal"
                                else {"pidns": [subject.removeprefix("parcel:")]}
                            )
                            _, current_sources = _source_bundles(
                                database, args.kind, **selectors
                            )
                            current = next(iter(current_sources), None)
                            if current != source:
                                raise ValueError(
                                    "Explanation source changed during authoring"
                                )
                        result = persist(
                            database,
                            source,
                            output,
                            config,
                            attempts=attempts,
                            provenance=author.provenance(),
                        )
                    counts["accepted" if result.accepted else "quarantined"] += 1
                    print(
                        json.dumps({"subject": subject, "accepted": result.accepted}),
                        flush=True,
                    )
                except SubscriptionUnavailable:
                    stop_reason = "subscription_unavailable"
                    break
                except (ValueError, ValidationError) as error:
                    counts["errors"] += 1
                    failures.append({"subject": subject, "error": str(error)})
                    print(
                        json.dumps({"subject": subject, "error": str(error)}),
                        flush=True,
                    )
            write_status()
            if stop_reason == "subscription_unavailable":
                break
            try:
                check_error_budget(
                    logging.getLogger(__name__),
                    label="Subscription backfill",
                    errors=counts["errors"],
                    total=counts["accepted"] + counts["quarantined"] + counts["errors"],
                )
            except RuntimeError:
                stop_reason = "error_budget"
                break
    return write_status(finished=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("read", "municipal", "matter", "property"))
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--limit", type=int, required=True)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--model", default="gpt-6-astra")
    parser.add_argument("--ids", type=int, nargs="*")
    parser.add_argument(
        "--unit-breaks",
        type=Path,
        help="JSON mapping proceeding IDs to source hashes and character offsets",
    )
    parser.add_argument("--subjects", nargs="*")
    parser.add_argument("--pidns", nargs="*")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    if not 1 <= args.batch_size <= 16:
        parser.error("--batch-size must be between 1 and 16")
    if not 1 <= args.workers <= 4:
        parser.error("--workers must be between 1 and 4")
    if args.ids and args.kind != "read":
        parser.error("--ids is only supported for source reads")
    if args.unit_breaks and (args.kind != "read" or not args.ids):
        parser.error("--unit-breaks requires a source read with explicit --ids")
    if args.subjects and args.kind not in {"municipal", "matter"}:
        parser.error(
            "--subjects is only supported for municipal or matter explanations"
        )
    if args.pidns and args.kind != "property":
        parser.error("--pidns is only supported for property explanations")
    database = make_database_resource()
    database.setup_for_execution(None)
    try:
        acquired = database.execute(
            "SELECT pg_try_advisory_lock(hashtext(%s))",
            (f"countyiq:subscription-backfill:{args.kind}",),
        )[0][0]
        if not acquired:
            parser.error("Another subscription batch for this stage is already running")
        report = run(database, args)
    finally:
        database.teardown_after_execution(None)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
