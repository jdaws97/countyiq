"""Exercise manual stop failures and non-root sentinel visibility safely."""

import json
import shlex
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.integration
@pytest.mark.parametrize("wait_seconds,expected_status", [(5, 0), (0, 1)])
def test_cost_guard_waits_for_overlapping_check(
    tmp_path, wait_seconds, expected_status
):
    image = yaml.safe_load((ROOT / "pipelines/docker-compose.yml").read_text())[
        "services"
    ]["postgres-test"]["image"]
    command = r"""export COUNTYIQ_COST_GUARD_DIR=/tmp/guard
(
    flock 8
    touch /tmp/lock-held
    sleep 1
) 8>/var/lock/countyiq-cost-guard.lock &
holder=$!
while [ ! -e /tmp/lock-held ]; do sleep 0.01; done
bash /repo/docker/cost-guard.sh --status --lock-wait-seconds "$1"
result=$?
wait "$holder"
exit "$result"
"""
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "-v",
            f"{ROOT}:/repo:ro",
            "--entrypoint",
            "bash",
            image,
            "-c",
            command,
            "lock-test",
            str(wait_seconds),
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == expected_status, result.stderr
    if expected_status:
        assert "still running" in result.stderr
    else:
        assert "has not completed a usage check yet" in result.stdout


@pytest.mark.integration
@pytest.mark.parametrize("scenario", ["success", "docker_failed", "timer_failed"])
def test_cost_guard_latches_stop_and_reports_failures(tmp_path, scenario):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name, failure in (("docker", "docker_failed"), ("systemctl", "timer_failed")):
        path = bindir / name
        path.write_text(f'#!/bin/bash\n[ "$REVIEW_SCENARIO" != "{failure}" ]\n')
        path.chmod(0o755)
    (tmp_path / "environment").write_text("# synthetic test environment\n")
    (tmp_path / "compose.yml").write_text("services: {}\n")
    image = yaml.safe_load((ROOT / "pipelines/docker-compose.yml").read_text())[
        "services"
    ]["postgres-test"]["image"]
    command = r"""export PATH=/case/bin:$PATH
export COUNTYIQ_ENV_FILE=/case/environment COUNTYIQ_COMPOSE_FILE=/case/compose.yml
export COUNTYIQ_COST_GUARD_DIR=/tmp/guard
/repo/docker/cost-guard.sh --trip manual
result=$?
# Inspect as the production application UID. Trip-file content remains private.
setpriv --reuid=10001 --regid=10001 --clear-groups bash -c 'test -x /tmp/guard && test -e /tmp/guard/tripped && test ! -w /tmp/guard'
visibility=$?
if [ "$visibility" != 0 ]; then echo SENTINEL_INACCESSIBLE; exit 99; fi
cat /tmp/guard/tripped
exit "$result"
"""
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "-v",
            f"{ROOT}:/repo:ro",
            "-v",
            f"{tmp_path}:/case:ro",
            "-e",
            f"REVIEW_SCENARIO={scenario}",
            "--entrypoint",
            "bash",
            image,
            "-c",
            command,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert "SENTINEL_INACCESSIBLE" not in result.stdout, result.stderr
    assert "reason=manual" in result.stdout, result.stderr
    assert (result.returncode == 0) == (scenario == "success"), result.stderr
    if scenario != "success":
        assert "could not be stopped" in result.stderr


def test_backup_sandbox_allows_its_guard_subprocess_to_update_state():
    text = (ROOT / "docker/systemd/countyiq-backup.service").read_text()
    writable = next(
        line.split("=", 1)[1].split()
        for line in text.splitlines()
        if line.startswith("ReadWritePaths=")
    )
    assert "/var/lib/countyiq/cost-guard" in writable


@pytest.mark.integration
@pytest.mark.parametrize(
    "limit,bucket_bytes,expected_status",
    [
        ("3000000000", 2000000000, 75),
        ("8000000000", 2000000000, 0),
        ("20000000000", 9000000000, 0),
        ("20000000000", 10000000000, 75),
    ],
)
def test_cost_guard_honors_limit_from_production_environment(
    tmp_path, limit, bucket_bytes, expected_status
):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name in ("docker", "systemctl", "rclone"):
        path = bindir / name
        path.write_text(
            "#!/bin/bash\n"
            + (
                "echo " + shlex.quote(json.dumps({"bytes": bucket_bytes})) + "\n"
                if name == "rclone"
                else "exit 0\n"
            )
        )
        path.chmod(0o755)
    (tmp_path / "environment").write_text(
        "\n".join(
            [
                f"COUNTYIQ_R2_HARD_LIMIT_BYTES={limit}",
                "COUNTYIQ_BACKUP_R2_ACCESS_KEY_ID=backup-id",
                "COUNTYIQ_BACKUP_R2_SECRET_ACCESS_KEY=backup-secret",
                "R2_ACCESS_KEY_ID=raw-id",
                "R2_SECRET_ACCESS_KEY=raw-secret",
                "COUNTYIQ_BACKUP_R2_BUCKET=countyiq-backups",
                "S3_RAW_BUCKET=countyiq-raw",
                "R2_ENDPOINT_URL=https://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.r2.cloudflarestorage.com",
            ]
        )
        + "\n"
    )
    (tmp_path / "compose.yml").write_text("services: {}\n")
    image = yaml.safe_load((ROOT / "pipelines/docker-compose.yml").read_text())[
        "services"
    ]["postgres-test"]["image"]
    command = r"""cp /case/environment /tmp/production.env
chmod 600 /tmp/production.env
export PATH=/case/bin:$PATH COUNTYIQ_ENV_FILE=/tmp/production.env
export COUNTYIQ_COMPOSE_FILE=/case/compose.yml COUNTYIQ_COST_GUARD_DIR=/tmp/guard
/repo/docker/cost-guard.sh --check
result=$?
cat /tmp/guard/status.env
exit "$result"
"""
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "-v",
            f"{ROOT}:/repo:ro",
            "-v",
            f"{tmp_path}:/case:ro",
            "--entrypoint",
            "bash",
            image,
            "-c",
            command,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == expected_status, result.stderr
    assert f"hard_limit_bytes={limit}" in result.stdout
    assert f"projected_bytes={bucket_bytes * 2}" in result.stdout
