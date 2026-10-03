"""Portable acquisition must fail before an incomplete snapshot changes staging."""

import hashlib
import json
from dataclasses import asdict
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from countyiq.lib import source_snapshots as snapshots
from countyiq.resources.source_snapshots import SourceSnapshotsResource


@pytest.mark.parametrize(
    "module_name,asset_name",
    [
        ("arcgis.penndot_roads", "penndot_roads_arcgis"),
        ("arcgis.penndot_projects", "penndot_projects_arcgis"),
        ("arcgis.traffic_counts", "traffic_counts_arcgis"),
        ("arcgis.environmental_diligence", "pa_dep_environmental_diligence"),
        ("bulk.tax_claims", "tax_claims"),
    ],
)
def test_revoked_source_policy_blocks_offline_import_before_read_or_write(
    monkeypatch, module_name, asset_name
):
    import importlib

    module = importlib.import_module(f"countyiq.assets.{module_name}")
    monkeypatch.setattr(
        module, "authorize_source", Mock(side_effect=RuntimeError("policy paused"))
    )
    source = Mock()
    database = Mock()
    archive = Mock()
    asset_function = getattr(module, asset_name).node_def.compute_fn.decorated_fn
    with pytest.raises(RuntimeError, match="policy paused"):
        asset_function(
            SimpleNamespace(run_id="test-run"),
            database,
            archive,
            source,
        )
    assert not source.mock_calls
    assert not database.mock_calls
    assert not archive.mock_calls


from dagster import AssetKey


def arcgis_payload(ids=(1, 2)):
    return {
        "metadata": {"fields": [{"name": "OBJECTID", "type": "esriFieldTypeOID"}]},
        "count": len(ids),
        "features": [{"attributes": {"OBJECTID": value}} for value in ids],
    }


def make_bundle(tmp_path, *, keys=("traffic_counts",), payload=None, started_at=None):
    bundle_id = "a" * 32
    directory = tmp_path / bundle_id
    directory.mkdir()
    specs = snapshots.source_specs()
    started = started_at or snapshots.utc_now() - timedelta(minutes=5)
    entries = {}
    for key in keys:
        body = json.dumps(payload or arcgis_payload()).encode()
        (directory / f"{key}.payload").write_bytes(body)
        entries[key] = {
            "request": asdict(specs[key]),
            "sha256": hashlib.sha256(body).hexdigest(),
            "byte_count": len(body),
            "record_count": (payload or arcgis_payload())["count"],
        }
    manifest = {
        "version": snapshots.SNAPSHOT_VERSION,
        "bundle_id": bundle_id,
        "contract": snapshots.contract_fingerprint(),
        "started_at": started.isoformat(),
        "completed_at": snapshots.utc_now().isoformat(),
        "permit": {
            "issued_at": (started - timedelta(minutes=1)).isoformat(),
            "contract": snapshots.contract_fingerprint(),
            "keys": list(keys),
            "policy_receipts": {specs[key].source_key: "b" * 64 for key in keys},
        },
        "entries": entries,
    }
    return directory, manifest


def write_manifest(directory, manifest):
    body = json.dumps(manifest).encode()
    (directory / "manifest.json").write_bytes(body)
    return hashlib.sha256(body).hexdigest()


def test_offline_bundle_returns_features_and_metadata_without_network(
    tmp_path, monkeypatch
):
    directory, manifest = make_bundle(tmp_path)
    digest = write_manifest(directory, manifest)
    monkeypatch.setenv("COUNTYIQ_SOURCE_INBOX", str(tmp_path))
    monkeypatch.setattr(
        snapshots.requests,
        "get",
        Mock(side_effect=AssertionError("offline import used HTTP")),
    )
    resource = SourceSnapshotsResource(bundle_id=directory.name, manifest_sha256=digest)
    context = SimpleNamespace(
        asset_key=AssetKey("traffic_counts_arcgis"),
        instance=SimpleNamespace(
            get_latest_materialization_event=Mock(return_value=None)
        ),
        add_output_metadata=Mock(),
    )

    assert len(resource.arcgis("traffic_counts", context)) == 2
    assert resource.metadata("traffic_counts") == arcgis_payload()["metadata"]
    assert (
        context.add_output_metadata.call_args.args[0]["source_manifest_sha256"].value
        == digest
    )


@pytest.mark.parametrize(
    "change",
    [
        "hash",
        "size",
        "contract",
        "county",
        "permit",
        "unexpected_file",
        "symlink",
        "future",
    ],
)
def test_tampered_or_mismatched_bundle_is_rejected(tmp_path, change):
    directory, manifest = make_bundle(tmp_path)
    entry = manifest["entries"]["traffic_counts"]
    path = directory / "traffic_counts.payload"
    if change == "hash":
        entry["sha256"] = "0" * 64
    elif change == "size":
        entry["byte_count"] += 1
    elif change == "contract":
        manifest["contract"] = "0" * 64
    elif change == "county":
        entry["request"]["where"] = "CTY_CODE='01'"
    elif change == "permit":
        manifest["permit"]["keys"] = []
    elif change == "unexpected_file":
        (directory / "extra.json").write_text("{}")
    elif change == "symlink":
        payload = path.read_bytes()
        path.unlink()
        target = tmp_path / "outside.json"
        target.write_bytes(payload)
        path.symlink_to(target)
    else:
        manifest["completed_at"] = (
            snapshots.utc_now() + timedelta(hours=1)
        ).isoformat()
    digest = write_manifest(directory, manifest)
    with pytest.raises(ValueError):
        snapshots.SourceBundle(tmp_path, directory.name, digest)


def test_trusted_manifest_digest_is_required(tmp_path):
    directory, manifest = make_bundle(tmp_path)
    write_manifest(directory, manifest)
    with pytest.raises(ValueError, match="manifest hash"):
        snapshots.SourceBundle(tmp_path, directory.name, "0" * 64)


def test_missing_project_layer_is_rejected(tmp_path):
    directory, manifest = make_bundle(tmp_path, keys=("penndot_projects_1",))
    digest = write_manifest(directory, manifest)
    with pytest.raises(ValueError, match="every layer"):
        snapshots.SourceBundle(tmp_path, directory.name, digest)


@pytest.mark.parametrize("bundle_id", ["../outside", "/tmp/bundle", "a" * 31])
def test_inbox_paths_are_not_caller_controlled(tmp_path, bundle_id):
    with pytest.raises(ValueError, match="bundle ID"):
        snapshots.SourceBundle(tmp_path, bundle_id, "b" * 64)


def test_old_snapshot_cannot_be_replayed(tmp_path):
    directory, manifest = make_bundle(
        tmp_path, started_at=snapshots.utc_now() - timedelta(days=2)
    )
    digest = write_manifest(directory, manifest)
    with pytest.raises(ValueError, match="last 24 hours"):
        snapshots.SourceBundle(tmp_path, directory.name, digest)


def test_newer_materialization_blocks_older_snapshot(tmp_path, monkeypatch):
    directory, manifest = make_bundle(tmp_path)
    digest = write_manifest(directory, manifest)
    monkeypatch.setenv("COUNTYIQ_SOURCE_INBOX", str(tmp_path))
    resource = SourceSnapshotsResource(bundle_id=directory.name, manifest_sha256=digest)
    context = SimpleNamespace(
        asset_key=AssetKey("traffic_counts_arcgis"),
        instance=SimpleNamespace(
            get_latest_materialization_event=Mock(
                return_value=SimpleNamespace(timestamp=snapshots.utc_now().timestamp())
            )
        ),
        add_output_metadata=Mock(),
    )
    with pytest.raises(ValueError, match="already materialized"):
        resource.arcgis("traffic_counts", context)
    context.add_output_metadata.assert_not_called()


def test_duplicate_object_ids_do_not_hide_missing_pages(tmp_path):
    directory, manifest = make_bundle(tmp_path, payload=arcgis_payload(ids=(1, 1)))
    digest = write_manifest(directory, manifest)
    with pytest.raises(ValueError, match="duplicate"):
        snapshots.SourceBundle(tmp_path, directory.name, digest)


@pytest.mark.parametrize("counts", [(3, 3), (2, 3)])
def test_incomplete_or_changing_upstream_count_rejects_acquisition(monkeypatch, counts):
    monkeypatch.setattr(
        snapshots, "fetch_metadata", Mock(return_value=arcgis_payload()["metadata"])
    )
    monkeypatch.setattr(
        snapshots, "query_all_features", Mock(return_value=arcgis_payload()["features"])
    )
    monkeypatch.setattr(
        snapshots.requests,
        "get",
        Mock(
            side_effect=[
                Mock(json=Mock(return_value={"count": count})) for count in counts
            ]
        ),
    )
    with pytest.raises(ValueError):
        snapshots.fetch_arcgis(snapshots.source_specs()["traffic_counts"])
