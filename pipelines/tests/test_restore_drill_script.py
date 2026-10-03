"""Run root-only backup and restore scripts in network-isolated containers.

Docker and R2 operations inside that container are fixtures, never real hosts.
This checks cleanup ownership on early failures, not just script text ordering.
"""

import hashlib
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
BACKUP_ID = "20260904T120000Z-test"


def prepare_case(tmp_path, scripts):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (tmp_path / "remote").mkdir()
    (tmp_path / "environment").write_text(
        "DATABASE_USER=dagster_admin\n"
        "DATABASE_NAME=countyiq\n"
        "COUNTYIQ_RESTORE_RECEIPT_DIR=/tmp/receipts\n"
        "COUNTYIQ_BACKUP_R2_ACCESS_KEY_ID=test-backup-id\n"
        "COUNTYIQ_BACKUP_R2_SECRET_ACCESS_KEY=test-backup-secret\n"
        "COUNTYIQ_BACKUP_R2_BUCKET=countyiq-backups\n"
        "R2_ENDPOINT_URL=https://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.r2.cloudflarestorage.com\n"
    )
    for name, script in scripts.items():
        path = bindir / name
        path.write_text(textwrap.dedent(script).lstrip())
        path.chmod(0o755)
    logfile = tmp_path / "events.log"
    logfile.touch()
    logfile.chmod(0o666)
    return logfile


def run_case(tmp_path, scenario, command):
    image = yaml.safe_load((ROOT / "pipelines/docker-compose.yml").read_text())[
        "services"
    ]["postgres-test"]["image"]
    setup = """
set -e
cp /case/environment /tmp/operations.env
chmod 600 /tmp/operations.env
export COUNTYIQ_ENV_FILE=/tmp/operations.env PATH=/case/bin:$PATH
case "$REVIEW_SCENARIO" in
    deployment_locked)
        exec 6>/var/lock/countyiq-deploy.lock
        flock -n 6
        ;;
    restore_locked)
        exec 6>/var/lock/countyiq-restore-drill.lock
        flock -n 6
        ;;
    backup_locked)
        exec 6>/var/lock/countyiq-backup.lock
        flock -n 6
        ;;
    inherited_backup_lock)
        exec 9>/var/lock/countyiq-backup.lock
        flock -n 9
        ;;
esac
"""
    return subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "-v",
            f"{ROOT}:/repo:ro",
            "-v",
            f"{tmp_path}:/case",
            "-e",
            f"REVIEW_SCENARIO={scenario}",
            "--entrypoint",
            "bash",
            image,
            "-c",
            setup + command,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    "scenario,expected_drops",
    [
        ("download_failed", []),
        ("occupied", []),
        ("restore_failed", ["countyiq_restore_drill"]),
        ("success", ["countyiq_restore_drill"]),
        ("legacy_success", ["countyiq_restore_drill"]),
        ("hash_mismatch", []),
        ("sidecar_mismatch", []),
        ("size_mismatch", []),
        ("deployment_locked", []),
        ("restore_locked", []),
    ],
)
def test_restore_script_only_cleans_databases_it_created(
    tmp_path, scenario, expected_drops
):
    scripts = {
        "docker": r"""#!/bin/bash
printf '%s\n' "$*" >> /case/events.log
case " $* " in
    *" inspect "*)
        echo true
        ;;
    *" createdb "*)
        [ "$REVIEW_SCENARIO" != occupied ] || exit 1
        ;;
    *" pg_restore "*)
        [ "$REVIEW_SCENARIO" != restore_failed ] || exit 1
        ;;
    *" psql "*)
        echo 42
        ;;
esac
exit 0
""",
        "rclone": r"""#!/bin/bash
printf 'rclone %s\n' "$*" >> /case/events.log
[ "$REVIEW_SCENARIO" != download_failed ] || exit 1
cp "/case/remote/$(basename "$2")" "$3"
""",
        "pg_restore": "#!/bin/bash\nexit 0\n",
    }
    logfile = prepare_case(tmp_path, scripts)
    remote = tmp_path / "remote"
    filename = f"countyiq-{BACKUP_ID}.dump"
    payload = b"fixture dump for countyiq"
    digest = hashlib.sha256(payload).hexdigest()
    (remote / filename).write_bytes(payload)
    (remote / f"{filename}.sha256").write_text(f"{digest}  {filename}\n")
    manifest = [
        f"backup_id={BACKUP_ID}",
        "code_ref=none",
        "target_deploy_ref=none",
        f"database.countyiq.file={filename}",
        f"database.countyiq.sha256={digest}",
        f"database.countyiq.bytes={len(payload)}",
    ]
    if scenario == "legacy_success":
        # The old manifest remains useful even without downloading its Dagster dump.
        manifest.extend(
            [
                f"database.dagster.file=dagster-{BACKUP_ID}.dump",
                f"database.dagster.sha256={'a' * 64}",
                "database.dagster.bytes=123",
            ]
        )
    elif scenario == "hash_mismatch":
        (remote / filename).write_bytes(b"tampered dump for countyiq")
    elif scenario == "sidecar_mismatch":
        (remote / f"{filename}.sha256").write_text(f"{'b' * 64}  {filename}\n")
    elif scenario == "size_mismatch":
        manifest[-1] = "database.countyiq.bytes=999"
    (remote / f"backup-{BACKUP_ID}.manifest").write_text("\n".join(manifest) + "\n")
    result = run_case(
        tmp_path,
        scenario,
        f"""
/repo/docker/restore-drill.sh --backup-id {BACKUP_ID}
stat -c '%u:%a' /tmp/receipts/current.env > /case/receipt-mode
cp /tmp/receipts/current.env /case/receipt.env
chmod 644 /case/receipt.env
""",
    )
    succeeded = scenario in {"success", "legacy_success"}
    assert (result.returncode == 0) == succeeded, result.stderr
    drops = [
        line.split()[-1]
        for line in logfile.read_text().splitlines()
        if " dropdb " in f" {line} "
    ]
    assert drops == expected_drops, logfile.read_text()
    if succeeded:
        receipt = (tmp_path / "receipt.env").read_text()
        assert "databases=countyiq\n" in receipt
        assert "primary_property_rows=42\n" in receipt
        assert "dagster" not in receipt
        assert (tmp_path / "receipt-mode").read_text().strip() == "0:400"
    else:
        assert not (tmp_path / "receipt.env").exists()
    for line in logfile.read_text().splitlines():
        if "rclone" in line:
            assert "dagster-" not in line
    if scenario in {"hash_mismatch", "sidecar_mismatch", "size_mismatch"}:
        assert " createdb " not in logfile.read_text()
    if scenario in {"deployment_locked", "restore_locked"}:
        assert not logfile.read_text()


@pytest.mark.integration
@pytest.mark.parametrize(
    "scenario",
    [
        "success",
        "verification_failed",
        "manifest_mismatch",
        "backup_locked",
        "inherited_backup_lock",
    ],
)
def test_backup_verifies_primary_dump_before_completion(tmp_path, scenario):
    scripts = {
        "docker": r"""#!/bin/bash
printf 'docker %s\n' "$*" >> /case/events.log
case " $* " in
    *" inspect "*)
        echo true
        ;;
    *" pg_dump "*)
        echo "fixture primary database dump"
        ;;
esac
""",
        "rclone": r"""#!/bin/bash
set -euo pipefail
printf 'rclone %s\n' "$*" >> /case/events.log
if [ "$1" = check ]; then
    [ "$REVIEW_SCENARIO" != verification_failed ] || exit 1
    for file in "$2"/*.dump "$2"/*.dump.sha256; do
        cmp "$file" "/case/remote/$(basename "$file")"
    done
    exit 0
fi
[ "$1" = copyto ] || exit 1
shift
immutable=false
if [ "$1" = --immutable ]; then
    immutable=true
    shift
fi
source_file="$1"
target_file="$2"
if [[ "$source_file" == *:* ]]; then
    source_file="/case/remote/$(basename "$source_file")"
fi
if [[ "$target_file" == *:* ]]; then
    target_file="/case/remote/$(basename "$target_file")"
fi
if [ "$immutable" = true ] && [ -e "$target_file" ]; then
    exit 1
fi
cp "$source_file" "$target_file"
if [[ "$target_file" == /case/remote/* ]]; then
    # Mock R2 objects must be readable by the host test process.
    chmod 644 "$target_file"
fi
if [ "$REVIEW_SCENARIO" = manifest_mismatch ] \
    && [[ "$target_file" == */remote-backup-*.manifest ]]; then
    echo tampered >> "$target_file"
fi
""",
        "pg_restore": "#!/bin/bash\nexit 0\n",
    }
    logfile = prepare_case(tmp_path, scripts)
    program = tmp_path / "program"
    (program / "lib").mkdir(parents=True)
    shutil.copy(ROOT / "docker/backup.sh", program / "backup.sh")
    shutil.copy(ROOT / "docker/lib/operations.sh", program / "lib/operations.sh")
    cost_guard = program / "cost-guard.sh"
    cost_guard.write_text(
        "#!/bin/bash\nprintf 'capacity %s\\n' \"$*\" >> /case/events.log\n"
    )
    cost_guard.chmod(0o755)
    result = run_case(tmp_path, scenario, "/case/program/backup.sh --reason test\n")
    succeeded = scenario in {"success", "inherited_backup_lock"}
    assert (result.returncode == 0) == succeeded, result.stderr
    events = logfile.read_text().splitlines()
    dump_commands = [line for line in events if " pg_dump " in line]
    if scenario == "backup_locked":
        assert not dump_commands
        assert not list((tmp_path / "remote").iterdir())
        return
    assert len(dump_commands) == 1
    assert dump_commands[0].endswith("--format=custom countyiq")
    uploads = [line for line in events if line.startswith("rclone copyto --immutable")]
    assert len(uploads) == (2 if scenario == "verification_failed" else 3)
    assert all("dagster-" not in line for line in uploads)
    verification_index = next(
        index for index, line in enumerate(events) if line.startswith("rclone check ")
    )
    assert "--download --one-way --checkers 1" in events[verification_index]
    if scenario == "verification_failed":
        assert not list((tmp_path / "remote").glob("*.manifest"))
    else:
        manifest_upload_index = events.index(uploads[-1])
        assert verification_index < manifest_upload_index
    if succeeded:
        manifest_path = next((tmp_path / "remote").glob("*.manifest"))
        fields = dict(
            line.split("=", 1) for line in manifest_path.read_text().splitlines()
        )
        dump = tmp_path / "remote" / fields["database.countyiq.file"]
        assert (
            fields["database.countyiq.sha256"]
            == hashlib.sha256(dump.read_bytes()).hexdigest()
        )
        assert int(fields["database.countyiq.bytes"]) == dump.stat().st_size
        assert not any(key.startswith("database.dagster.") for key in fields)
        assert "Backup complete:" in result.stdout
    else:
        assert "Backup complete:" not in result.stdout
