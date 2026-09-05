"""Nested deployment backups share a lock; independent backups cannot enter."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_backup_lock_is_inherited_but_excludes_independent_operations(tmp_path):
    lock = tmp_path / "backup.lock"
    script = r'''source docker/lib/operations.sh
countyiq_lock_backup_operations "$1" || exit 1
bash -c 'source docker/lib/operations.sh; countyiq_lock_backup_operations "$1"' nested "$1" || exit 2
echo ready
read -r finish
'''
    holder = subprocess.Popen(["bash", "-c", script, "holder", str(lock)], cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "ready"
        contender = subprocess.run([
            "bash", "-c", 'source docker/lib/operations.sh; countyiq_lock_backup_operations "$1"', "contender", str(lock),
        ], cwd=ROOT, capture_output=True, text=True, timeout=5)
        assert contender.returncode != 0
        assert "snapshot boundary" in contender.stderr
    finally:
        holder.communicate("finish\n", timeout=5)
    released = subprocess.run([
        "bash", "-c", 'source docker/lib/operations.sh; countyiq_lock_backup_operations "$1"', "released", str(lock),
    ], cwd=ROOT, capture_output=True, text=True, timeout=5)
    assert released.returncode == 0, released.stderr
