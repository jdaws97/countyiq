"""Verify the release-specific operation-unit renderer."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "docker/install-operation-units.sh"


def make_systemd_analyze_stub(tmp_path: Path) -> Path:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "systemd-analyze"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        '[ "$1" = "verify" ]\n'
        'mkdir -p "$CAPTURED_UNITS"\n'
        'for unit in "${@:2}"; do\n'
        '    cp "$unit" "$CAPTURED_UNITS/$(basename "$unit")"\n'
        "done\n"
    )
    stub.chmod(0o755)
    return bindir


def test_check_only_renders_an_alternate_release_path(tmp_path):
    bindir = make_systemd_analyze_stub(tmp_path)
    release_root = tmp_path / "releases" / "20260908"
    release_root.mkdir(parents=True)
    captured = tmp_path / "rendered-units"
    environment = os.environ | {
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "CAPTURED_UNITS": str(captured),
    }

    result = subprocess.run(
        [
            str(INSTALLER),
            "--check-only",
            "--repository-root",
            str(release_root),
        ],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    backup = (captured / "countyiq-backup.service").read_text()
    cost_guard = (captured / "countyiq-cost-guard.service").read_text()
    assert f"WorkingDirectory={release_root}/docker" in backup
    assert f"ExecStart={release_root}/docker/backup.sh --reason scheduled" in backup
    assert f"ExecStart={release_root}/docker/cost-guard.sh --enforce" in cost_guard
    assert (
        f"Environment=COUNTYIQ_COMPOSE_FILE={release_root}/docker/docker-compose.yml"
        in cost_guard
    )
    assert "Environment=COUNTYIQ_ENV_FILE=/etc/countyiq/production.env" in cost_guard


def test_check_only_rejects_unsafe_release_path(tmp_path):
    bindir = make_systemd_analyze_stub(tmp_path)
    environment = os.environ | {
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "CAPTURED_UNITS": str(tmp_path / "rendered-units"),
    }

    result = subprocess.run(
        [
            str(INSTALLER),
            "--check-only",
            "--repository-root",
            "/srv/release;systemctl start countyiq-cost-guard.timer",
        ],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    assert result.returncode == 2
    assert "safe path characters" in result.stderr
    assert not (tmp_path / "rendered-units").exists()


def test_installer_reloads_units_without_arming_timers():
    text = INSTALLER.read_text()

    assert "systemctl daemon-reload" in text
    assert "systemctl enable" not in text
    assert "systemctl start" not in text


def test_cost_guard_arming_uses_the_release_unit_installer():
    arm_cost_guard = (ROOT / "docker/arm-cost-guard.sh").read_text()

    assert (
        '"$SCRIPT_DIR/install-operation-units.sh" --env-file "$ENVIRONMENT_FILE"'
        in (arm_cost_guard)
    )
    assert "systemd/countyiq-cost-guard.service" not in arm_cost_guard
