"""Run the actual root-only restore script in a network-isolated container.

Docker and R2 operations inside that container are fixtures, never real hosts.
This checks cleanup ownership on early failures, not just script text ordering.
"""

import hashlib
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
BACKUP_ID = "20260904T120000Z-test"


@pytest.mark.integration
@pytest.mark.parametrize("scenario,expected_drops", [
    ("download_failed", []),
    ("occupied", []),
    ("restore_failed", ["countyiq_restore_drill"]),
    ("success", ["countyiq_restore_drill", "dagster_restore_drill"]),
])
def test_restore_script_only_cleans_databases_it_created(tmp_path, scenario, expected_drops):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    remote = tmp_path / "remote"
    remote.mkdir()
    manifest = [f"backup_id={BACKUP_ID}", "code_ref=none", "target_deploy_ref=none"]
    for name in ("countyiq", "dagster"):
        filename = f"{name}-{BACKUP_ID}.dump"
        payload = f"fixture dump for {name}".encode()
        digest = hashlib.sha256(payload).hexdigest()
        (remote / filename).write_bytes(payload)
        (remote / f"{filename}.sha256").write_text(f"{digest}  {filename}\n")
        manifest += [f"database.{name}.file={filename}", f"database.{name}.sha256={digest}", f"database.{name}.bytes={len(payload)}"]
    (remote / f"backup-{BACKUP_ID}.manifest").write_text("\n".join(manifest) + "\n")
    (tmp_path / "environment").write_text("\n".join([
        "DATABASE_USER=dagster_admin", "DATABASE_NAME=countyiq",
        "COUNTYIQ_RESTORE_RECEIPT_DIR=/tmp/receipts",
        "COUNTYIQ_BACKUP_R2_ACCESS_KEY_ID=test-backup-id",
        "COUNTYIQ_BACKUP_R2_SECRET_ACCESS_KEY=test-backup-secret",
        "COUNTYIQ_BACKUP_R2_BUCKET=countyiq-backups",
        "R2_ENDPOINT_URL=https://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.r2.cloudflarestorage.com",
    ]) + "\n")
    scripts = {
        "docker": r'''#!/bin/bash
printf '%s\n' "$*" >> /case/events.log
case " $* " in
  *" inspect "*) echo true ;;
  *" createdb "*) [ "$REVIEW_SCENARIO" != occupied ] || exit 1 ;;
  *" pg_restore "*) [ "$REVIEW_SCENARIO" != restore_failed ] || exit 1 ;;
  *" psql "*) echo 42 ;;
esac
exit 0
''',
        "rclone": r'''#!/bin/bash
[ "$REVIEW_SCENARIO" != download_failed ] || exit 1
cp "/case/remote/$(basename "$2")" "$3"
''',
        "pg_restore": "#!/bin/bash\nexit 0\n",
    }
    for name, script in scripts.items():
        path = bindir / name
        path.write_text(script)
        path.chmod(0o755)
    logfile = tmp_path / "events.log"
    logfile.touch()
    logfile.chmod(0o666)
    image = yaml.safe_load((ROOT / "pipelines/docker-compose.yml").read_text())["services"]["postgres-test"]["image"]
    result = subprocess.run([
        "docker", "run", "--rm", "--network", "none",
        "-v", f"{ROOT}:/repo:ro", "-v", f"{tmp_path}:/case",
        "-e", f"REVIEW_SCENARIO={scenario}", "--entrypoint", "bash", image,
        "-c", 'cp /case/environment /tmp/restore.env; chmod 600 /tmp/restore.env; '
        'export COUNTYIQ_ENV_FILE=/tmp/restore.env PATH=/case/bin:$PATH; '
        f'/repo/docker/restore-drill.sh --backup-id {BACKUP_ID}',
    ], capture_output=True, text=True, timeout=30)
    assert (result.returncode == 0) == (scenario == "success"), result.stderr
    drops = [line.split()[-1] for line in logfile.read_text().splitlines() if " dropdb " in f" {line} "]
    assert drops == expected_drops, logfile.read_text()
