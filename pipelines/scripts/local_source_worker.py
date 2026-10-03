"""Acquire approved public snapshots locally, then submit normal VPS Dagster work.

Run ``authorize`` and ``submit`` on the VPS. Only ``fetch`` runs on the PC;
it needs public network access and a recent permit, never database credentials.
Transfer the immutable bundle directory over authenticated SSH before submit.
"""

import argparse
import hashlib
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

import requests
from countyiq.lib.http_retry import get_with_retry
from countyiq.lib.source_rights import authorize_source, require_source_use
from countyiq.lib.source_snapshots import (
    MAX_PAYLOAD_BYTES,
    SNAPSHOT_VERSION,
    AcquisitionPermit,
    SnapshotEntry,
    SnapshotManifest,
    SourceBundle,
    contract_fingerprint,
    fetch_arcgis,
    source_specs,
    utc_now,
)
from countyiq.resources.database import make_database_resource
from dagster import DagsterInstance, RunsFilter


def authorize_assets(assets: list[str]) -> AcquisitionPermit:
    specs = source_specs()
    if not assets or not set(assets) <= {spec.asset for spec in specs.values()}:
        raise ValueError("Select only supported local source assets")
    keys = sorted(key for key, spec in specs.items() if spec.asset in assets)
    attempt_id = f"local-worker:{uuid4().hex}"
    receipts = {}
    with make_database_resource().process_config_and_initialize_cm() as database:
        for key in keys:
            spec = specs[key]
            if spec.source_key in receipts:
                continue
            authorization = authorize_source(
                database,
                source_key=spec.source_key,
                acquisition_method=spec.method,
                asset_key="local_source_worker",
                dagster_run_id=attempt_id,
            )
            require_source_use(authorization, "raw_retention")
            require_source_use(authorization, "derived_product")
            receipts[spec.source_key] = database.execute(
                "SELECT policy_fingerprint FROM meta.source_rights_audit "
                "WHERE dagster_run_id = %s AND source_key = %s ORDER BY id DESC LIMIT 1",
                (attempt_id, spec.source_key),
            )[0][0]
    return AcquisitionPermit(
        issued_at=utc_now(),
        contract=contract_fingerprint(),
        keys=keys,
        policy_receipts=receipts,
    )


def fetch_bundle(permit_path: Path, output: Path) -> dict:
    permit = AcquisitionPermit.model_validate_json(permit_path.read_bytes())
    permit.validate_for_acquisition()
    clock_lead = (permit.issued_at - utc_now()).total_seconds()
    if clock_lead > 5:
        raise ValueError(
            "PC clock is behind the VPS; synchronize it before acquisition"
        )
    if clock_lead > 0:
        # Preserve strict timestamp ordering across small PC/VPS clock offsets.
        time.sleep(clock_lead)
    bundle_id = uuid4().hex
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = output / f".{bundle_id}.partial"
    temporary.mkdir(mode=0o700)
    started_at = utc_now()
    entries = {}
    specs = source_specs()
    for key in permit.keys:
        # Recheck the permit before each request, including long acquisitions.
        permit.validate_for_acquisition()
        spec = specs[key]
        print(f"Acquiring {key}", file=sys.stderr, flush=True)
        if spec.method == "official_pdf":
            body = get_with_retry(spec.url, timeout=120).content
            record_count = None
        else:
            payload = fetch_arcgis(spec)
            body = json.dumps(payload, separators=(",", ":")).encode()
            record_count = payload["count"]
        if not body or len(body) > MAX_PAYLOAD_BYTES:
            raise ValueError(f"Source payload exceeds its size bound: {key}")
        path = temporary / f"{key}.payload"
        path.write_bytes(body)
        path.chmod(0o600)
        entries[key] = SnapshotEntry(
            request=asdict(spec),
            sha256=hashlib.sha256(body).hexdigest(),
            byte_count=len(body),
            record_count=record_count,
        )
    manifest = SnapshotManifest(
        version=SNAPSHOT_VERSION,
        bundle_id=bundle_id,
        contract=contract_fingerprint(),
        started_at=started_at,
        completed_at=utc_now(),
        permit=permit,
        entries=entries,
    )
    manifest_bytes = manifest.model_dump_json(indent=2).encode()
    manifest_path = temporary / "manifest.json"
    manifest_path.write_bytes(manifest_bytes)
    manifest_path.chmod(0o600)
    digest = hashlib.sha256(manifest_bytes).hexdigest()
    completed = output / bundle_id
    temporary.rename(completed)
    try:
        bundle = SourceBundle(output, bundle_id, digest)
    except Exception:
        completed.rename(temporary)
        raise
    return {
        "bundle_id": bundle_id,
        "manifest_sha256": digest,
        "directory": str(bundle.directory.resolve()),
        "assets": sorted(bundle.assets),
        "entries": {key: entry.model_dump() for key, entry in entries.items()},
    }


def submit_bundle(bundle_id: str, digest: str) -> dict:
    root = Path(os.environ.get("COUNTYIQ_SOURCE_INBOX", "/opt/countyiq/source-inbox"))
    bundle = SourceBundle(root, bundle_id, digest)
    with DagsterInstance.get() as instance:
        previous = instance.get_runs(
            filters=RunsFilter(
                job_name="local_source_refresh",
                tags={
                    "countyiq/source_bundle": bundle_id,
                    "countyiq/source_manifest_sha256": digest,
                },
            ),
            limit=1,
        )
    if previous:
        return {
            "bundle_id": bundle_id,
            "runId": previous[0].run_id,
            "status": previous[0].status.value,
            "reused": True,
        }
    authorize_assets(sorted(bundle.assets))
    # Dagster's queued run coordinator enforces the production one-run limit.
    # A successful submission is only queued work, never a success receipt.
    response = requests.post(
        "http://127.0.0.1:3000/graphql",
        json={
            "query": """
                mutation Launch($executionParams: ExecutionParams!) {
                    launchRun(executionParams: $executionParams) {
                        __typename
                        ... on LaunchRunSuccess { run { runId status } }
                        ... on PythonError { message }
                        ... on RunConfigValidationInvalid { errors { message } }
                    }
                }
            """,
            "variables": {
                "executionParams": {
                    "selector": {
                        "repositoryLocationName": "countyiq.definitions",
                        "repositoryName": "__repository__",
                        "jobName": "local_source_refresh",
                        "assetSelection": [
                            {"path": [asset]} for asset in sorted(bundle.assets)
                        ],
                    },
                    "runConfigData": {
                        "resources": {
                            "source_snapshots": {
                                "config": {
                                    "bundle_id": bundle_id,
                                    "manifest_sha256": digest,
                                }
                            },
                        },
                    },
                    "executionMetadata": {
                        "tags": [
                            {"key": "countyiq/source_bundle", "value": bundle_id},
                            {"key": "countyiq/source_manifest_sha256", "value": digest},
                        ],
                    },
                },
            },
        },
        timeout=60,
    )
    response.raise_for_status()
    result = response.json()
    launch = (result.get("data") or {}).get("launchRun") or {}
    if launch.get("__typename") != "LaunchRunSuccess":
        raise RuntimeError(f"Dagster rejected the source import: {result}")
    return {"bundle_id": bundle_id, **launch["run"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    authorize = commands.add_parser("authorize")
    authorize.add_argument("--assets", nargs="+", required=True)
    fetch = commands.add_parser("fetch")
    fetch.add_argument("--permit", type=Path, required=True)
    fetch.add_argument("--output", type=Path, required=True)
    submit = commands.add_parser("submit")
    submit.add_argument("--bundle-id", required=True)
    submit.add_argument("--manifest-sha256", required=True)
    args = parser.parse_args()
    if args.command == "authorize":
        print(authorize_assets(args.assets).model_dump_json(indent=2))
    elif args.command == "fetch":
        print(json.dumps(fetch_bundle(args.permit, args.output), indent=2))
    else:
        print(json.dumps(submit_bundle(args.bundle_id, args.manifest_sha256), indent=2))


if __name__ == "__main__":
    main()
