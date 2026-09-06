"""Read-only release checks reject ineffective SSH and inaccessible cost stops."""

import os
from pathlib import Path
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.integration
@pytest.mark.parametrize(
    "ssh_override,mode,private_parent,passes",
    [
        ("", "755", False, True),
        ("passwordauthentication yes", "755", False, False),
        ("kbdinteractiveauthentication yes", "755", False, False),
        ("permitrootlogin prohibit-password", "755", False, False),
        ("pubkeyauthentication no", "755", False, False),
        ("", "700", False, False),
        ("", "775", False, False),
        ("", "755", True, False),
    ],
)
def test_actual_uid_permissions_and_effective_ssh(
    tmp_path, ssh_override, mode, private_parent, passes
):
    expected = [
        "passwordauthentication no",
        "kbdinteractiveauthentication no",
        "permitrootlogin no",
        "pubkeyauthentication yes",
    ]
    if ssh_override:
        expected = [
            ssh_override if line.split()[0] == ssh_override.split()[0] else line
            for line in expected
        ]
    sshd = tmp_path / "sshd"
    sshd.write_text(
        "#!/bin/sh\ncat <<'SETTINGS'\n" + "\n".join(expected) + "\nSETTINGS\n"
    )
    sshd.chmod(0o755)
    image = yaml.safe_load((ROOT / "pipelines/docker-compose.yml").read_text())[
        "services"
    ]["postgres-test"]["image"]
    parent = "/tmp/private" if private_parent else "/tmp/public"
    command = (
        "mkdir -p /tmp/bin; cp /case/sshd /tmp/bin/sshd; "
        f"mkdir -p {parent}/guard; chmod {'700' if private_parent else '755'} {parent}; "
        f"chmod {mode} {parent}/guard; "
        f"export COUNTYIQ_COST_GUARD_DIR={parent}/guard PATH=/tmp/bin:$PATH; "
        "/repo/docker/check-host.sh"
    )
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
        timeout=20,
    )
    assert (result.returncode == 0) is passes, result.stdout + result.stderr
    if passes:
        assert "checks passed" in result.stdout
    else:
        assert "checks passed" not in result.stdout
