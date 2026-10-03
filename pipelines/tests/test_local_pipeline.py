"""Local execution retains checks, health receipts and the protected SSH lease."""

import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from countyiq import run_job
from countyiq.lib.remote_pipeline import run_command, stop_process_group
from countyiq.resources.database import make_database_resource
from countyiq.resources.storage import make_s3_resource
from dagster import (
    AssetCheckResult,
    Definitions,
    MaterializeResult,
    asset,
    asset_check,
    define_asset_job,
    multiprocess_executor,
)

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "pipeline_session", ROOT / "docker/pipeline_session.py"
)
host = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(host)


@asset
def plcb_licenses():
    return MaterializeResult(metadata={"record_count": 12})


@asset
def tax_claims():
    raise AssertionError("The unselected sibling must not execute")


@asset_check(asset=plcb_licenses)
def verified_rows():
    mode = os.environ["COUNTYIQ_TEST_CHECK_MODE"]
    if mode == "error":
        raise RuntimeError("The quality service did not answer")
    return AssetCheckResult(passed=mode == "passed")


def fixture_job():
    return Definitions(
        assets=[plcb_licenses, tax_claims],
        asset_checks=[verified_rows],
        jobs=[define_asset_job("local_contract")],
        executor=multiprocess_executor.configured({"max_concurrent": 1}),
    ).resolve_job_def("local_contract")


@pytest.mark.parametrize("mode", ["passed", "failed", "error"])
def test_local_runner_preserves_checks_for_selected_assets(
    tmp_path, monkeypatch, capsys, mode
):
    monkeypatch.chdir(ROOT / "pipelines")
    monkeypatch.setenv("DAGSTER_HOME", str(tmp_path))
    monkeypatch.setenv("COUNTYIQ_TEST_CHECK_MODE", mode)
    (tmp_path / "dagster.yaml").write_text("telemetry:\n  enabled: false\n")
    database = Mock()

    @contextmanager
    def resource():
        yield database

    factory = Mock()
    factory.process_config_and_initialize_cm = resource
    monkeypatch.setattr(run_job, "make_database_resource", lambda: factory)
    monkeypatch.setattr(run_job, "selected_job", fixture_job)
    status = run_job.run(
        SimpleNamespace(report_run=None, job="local_contract", assets=["plcb_licenses"])
    )

    success = mode == "passed"
    assert status == (0 if success else 1)
    report = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert report["status"] == ("success" if success else "failure")
    assert report["checks"] == [
        {
            "asset": "plcb_licenses",
            "name": "verified_rows",
            "passed": success,
            "severity": "ERROR",
            "evaluated": mode != "error",
        }
    ]
    writes = [call.args[1] for call in database.execute.call_args_list]
    assert len(writes) == 2
    assert writes[0]["asset_key"] == "plcb_licenses"
    if not success:
        assert writes[0]["failure_reason"] == "check_failed"
    assert all(write["status"] == report["status"] for write in writes)


def test_dagster_snapshots_do_not_store_borrowed_credentials(monkeypatch):
    secrets = {
        "DATABASE_PASSWORD": "private-database-sentinel",
        "R2_ACCESS_KEY_ID": "private-access-sentinel",
        "R2_SECRET_ACCESS_KEY": "private-storage-sentinel",
    }
    for key, value in secrets.items():
        monkeypatch.setenv(key, value)
    resources = {
        "database": make_database_resource(defer_secrets=True),
        "s3": make_s3_resource(defer_secrets=True),
    }
    definition = Definitions(
        assets=[plcb_licenses],
        jobs=[define_asset_job("secret_contract")],
        resources=resources,
    ).resolve_job_def("secret_contract")
    snapshot = str(definition.get_job_snapshot())
    for value in secrets.values():
        assert value not in snapshot
    with resources["database"].process_config_and_initialize_cm() as database:
        assert database.password == secrets["DATABASE_PASSWORD"]
    with resources["s3"].process_config_and_initialize_cm() as storage:
        assert storage.secret_access_key == secrets["R2_SECRET_ACCESS_KEY"]


def production_values():
    return {
        "DATABASE_NAME": "countyiq",
        "DATABASE_USER": "admin",
        "DATABASE_PASSWORD": "administrator-secret",
        "DATABASE_API_USER": "api",
        "DATABASE_API_PASSWORD": "api-secret",
        "DATABASE_PIPELINE_USER": "writer",
        "DATABASE_PIPELINE_PASSWORD": "writer-secret",
        "COUNTYIQ_ARCHIVE_STRICT": "true",
        "R2_ACCESS_KEY_ID": "raw-key",
        "R2_SECRET_ACCESS_KEY": "raw-secret",
        "R2_ENDPOINT_URL": "https://example.test",
        "S3_RAW_BUCKET": "raw",
        "COUNTYIQ_BACKUP_R2_SECRET_ACCESS_KEY": "backup-secret",
        "COUNTYIQ_PASS0_ENABLED": "true",
        "COUNTYIQ_PASS0_BACKFILL_AUTHORIZATION_FILE": "/host/authorization.json",
        "COUNTYIQ_PASS0_QUALITY_RECEIPT": "/host/quality.json",
        "CODEX_HOME": "/host/codex-auth",
    }


def test_only_writer_and_raw_archive_credentials_leave_the_host():
    selected = host.pipeline_environment(production_values())
    assert selected["DATABASE_USER"] == "writer"
    assert selected["DATABASE_PASSWORD"] == "writer-secret"
    assert selected["R2_SECRET_ACCESS_KEY"] == "raw-secret"
    serialized = json.dumps(selected)
    for forbidden in ("administrator-secret", "api-secret", "backup-secret", "/host/"):
        assert forbidden not in serialized
    for number in range(5):
        assert selected[f"COUNTYIQ_PASS{number}_ENABLED"] == "false"


@pytest.mark.parametrize("end", ["disconnect", "cost_stop", "heartbeat_timeout"])
def test_session_revokes_writer_on_every_exit(tmp_path, monkeypatch, capsys, end):
    from io import StringIO

    monkeypatch.setattr(host.os, "geteuid", lambda: 0)
    monkeypatch.setattr(host, "DEPLOY_LOCK", tmp_path / "deploy.lock")
    stop = tmp_path / "tripped"
    monkeypatch.setattr(host, "COST_STOP", stop)
    monkeypatch.setattr(host, "verify_release", lambda reference: None)
    monkeypatch.setattr(host, "read_environment", lambda path: production_values())
    permission_changes = []
    monkeypatch.setattr(
        host,
        "writer_login",
        lambda values, *, enabled: permission_changes.append(enabled),
    )
    stream = StringIO("ping\n" if end == "cost_stop" else "")
    monkeypatch.setattr(host.sys, "stdin", stream)

    def ready(*args):
        if end == "cost_stop":
            stop.touch()
        return ([] if end == "heartbeat_timeout" else [stream], [], [])

    monkeypatch.setattr(host.select, "select", ready)
    if end == "disconnect":
        host.serve("a" * 40)
    else:
        with pytest.raises(ValueError):
            host.serve("a" * 40)
    assert permission_changes == [False, True, False]
    assert json.loads(capsys.readouterr().out)["type"] == "session"


def test_busy_host_never_lends_writer_credentials(tmp_path, monkeypatch, capsys):
    import fcntl

    path = tmp_path / "deploy.lock"
    monkeypatch.setattr(host.os, "geteuid", lambda: 0)
    monkeypatch.setattr(host, "DEPLOY_LOCK", path)
    with path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match="holds the VPS lock"):
            host.serve("a" * 40)
    assert capsys.readouterr().out == ""


def test_different_release_is_rejected(tmp_path, monkeypatch):
    receipt = tmp_path / "current.env"
    receipt.write_text(f"deploy_ref={'a' * 40}\n")
    monkeypatch.setattr(host, "RELEASE_FILE", receipt)
    monkeypatch.setattr(
        host.subprocess,
        "check_output",
        Mock(side_effect=["a" * 40, f"countyiq-api:{'a' * 40}"]),
    )
    with pytest.raises(ValueError, match="matching the active release"):
        host.verify_release("b" * 40)


def test_lost_ssh_session_stops_local_work(tmp_path):
    marker = tmp_path / "still-running"
    session = Mock()
    session.heartbeat.side_effect = RuntimeError("SSH stopped")
    command = [
        sys.executable,
        "-c",
        """import pathlib
import sys
import time

time.sleep(0.5)
pathlib.Path(sys.argv[1]).touch()
""",
        str(marker),
    ]
    with pytest.raises(RuntimeError, match="SSH stopped"):
        run_command(command, dict(os.environ), session)
    time.sleep(0.6)
    assert not marker.exists()


def test_exited_leader_does_not_leave_running_children(tmp_path):
    marker = tmp_path / "child-pid"
    child_code = """import signal
import time

signal.signal(signal.SIGINT, signal.SIG_IGN)
time.sleep(30)
"""
    parent_code = (
        "import pathlib, subprocess, sys\n"
        "child = subprocess.Popen([sys.executable, '-c', sys.argv[2]])\n"
        "pathlib.Path(sys.argv[1]).write_text(str(child.pid))\n"
    )
    leader = subprocess.Popen(
        [sys.executable, "-c", parent_code, str(marker), child_code],
        start_new_session=True,
    )
    leader.wait(timeout=5)
    child_pid = int(marker.read_text())
    try:
        stop_process_group(leader)
        process_state = Path(f"/proc/{child_pid}/stat")
        deadline = time.monotonic() + 2
        while process_state.exists() and process_state.read_text().split()[2] != "Z":
            assert time.monotonic() < deadline, "orphan child is still executing"
            time.sleep(0.05)
    finally:
        try:
            os.kill(child_pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
