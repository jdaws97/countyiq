"""Account configuration fails before an ordinary release changes services."""

import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
VALID = {
    "DOMAIN": "countyiq.test",
    "COUNTYIQ_AUTH_PROVIDER": "cloudflare_access",
    "COUNTYIQ_ACCESS_ISSUER": "https://team.cloudflareaccess.com",
    "COUNTYIQ_ACCESS_AUD": "reviewed-application-audience",
    "COUNTYIQ_APP_URL": "https://app.countyiq.test",
    "COUNTYIQ_WORKSPACE_ORIGINS": "https://app.countyiq.test",
    "COUNTYIQ_WATCH_SYNC_ENABLED": "true",
}


@pytest.mark.parametrize(
    "overrides,passes",
    [
        ({}, True),
        (
            {
                "COUNTYIQ_AUTH_PROVIDER": "disabled",
                "COUNTYIQ_WATCH_SYNC_ENABLED": "false",
            },
            True,
        ),
        ({"COUNTYIQ_AUTH_PROVIDER": "disabled"}, False),
        ({"COUNTYIQ_AUTH_PROVIDER": "unsigned"}, False),
        ({"COUNTYIQ_WATCH_SYNC_ENABLED": "tru"}, False),
        (
            {
                "COUNTYIQ_ACCESS_ISSUER": "https://team.cloudflareaccess.com.attacker.test"
            },
            False,
        ),
        ({"COUNTYIQ_ACCESS_AUD": ""}, False),
        ({"COUNTYIQ_ACCESS_AUD": "<Application Audience>"}, False),
        ({"COUNTYIQ_APP_URL": "http://countyiq.test"}, False),
        ({"COUNTYIQ_APP_URL": "https://other.test"}, False),
        ({"COUNTYIQ_APP_URL": "https://countyiq.test"}, False),
        ({"COUNTYIQ_WORKSPACE_ORIGINS": "https://countyiq.test"}, False),
        ({"COUNTYIQ_WORKSPACE_ORIGINS": ""}, False),
        ({"COUNTYIQ_WORKSPACE_ORIGINS": "https://other.test"}, False),
    ],
)
def test_account_deployment_configuration(overrides, passes):
    result = subprocess.run(
        [
            "bash",
            "-c",
            "source docker/lib/operations.sh; countyiq_validate_account_environment",
        ],
        cwd=ROOT,
        env={**os.environ, **VALID, **overrides},
        text=True,
        capture_output=True,
    )
    assert (result.returncode == 0) is passes, result.stderr
    if not passes:
        assert result.stderr


@pytest.mark.parametrize(
    "trusted_host,passes", [("app.countyiq.net", True), ("countyiq.net", False)]
)
def test_environment_publisher_accepts_product_host_before_contacting_remote(
    tmp_path, trusted_host, passes
):
    import json
    import sys

    # Substitute both external commands: no real secrets, keys, or network.
    fake_sops = tmp_path / "sops"
    fake_ssh = tmp_path / "ssh"
    encrypted = tmp_path / "production.sops.env"
    key = tmp_path / "review-key"
    calls = tmp_path / "ssh-calls"
    captured = tmp_path / "published-env"
    encrypted.write_text("synthetic encrypted placeholder")
    key.write_text("synthetic key placeholder")
    fields = {
        "DOMAIN": "countyiq.net",
        "COUNTYIQ_TRUSTED_HOSTS": trusted_host,
        "COUNTYIQ_ARCHIVE_STRICT": "true",
        "COUNTYIQ_BACKUP_BUCKET_LOCK_CONFIRMED": "true",
        "COUNTYIQ_R2_HARD_LIMIT_BYTES": "8000000000",
        **{f"COUNTYIQ_PASS{i}_ENABLED": "false" for i in range(5)},
        **{
            name: "synthetic-value"
            for name in (
                "DATABASE_PASSWORD",
                "DATABASE_PIPELINE_PASSWORD",
                "DATABASE_API_PASSWORD",
                "R2_ACCESS_KEY_ID",
                "R2_SECRET_ACCESS_KEY",
                "COUNTYIQ_BACKUP_R2_ACCESS_KEY_ID",
                "COUNTYIQ_BACKUP_R2_SECRET_ACCESS_KEY",
                "CLOUDFLARE_TUNNEL_TOKEN",
            )
        },
    }
    payload = "\n".join(f"{name}={value}" for name, value in fields.items()) + "\n"
    fake_sops.write_text(
        f"#!{sys.executable}\nimport sys\nsys.stdout.write({payload!r})\n"
    )
    fake_ssh.write_text(
        f"#!{sys.executable}\n"
        + "import os,sys,json\nfrom pathlib import Path\n"
        + "with Path(os.environ['REVIEW_SSH_CALLS']).open('a') as f: f.write(json.dumps(sys.argv[1:])+'\\n')\n"
        + "body=sys.stdin.read()\nif body: Path(os.environ['REVIEW_PUBLISHED_ENV']).write_text(body)\n"
    )
    fake_sops.chmod(0o700)
    fake_ssh.chmod(0o700)
    result = subprocess.run(
        ["bash", "docker/publish-production-env.sh"],
        cwd=ROOT,
        env={
            **os.environ,
            "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
            "SOPS_BIN": str(fake_sops),
            "COUNTYIQ_SOPS_FILE": str(encrypted),
            "COUNTYIQ_SSH_KEY": str(key),
            "COUNTYIQ_REMOTE_HOST": "review@invalid.test",
            "REVIEW_SSH_CALLS": str(calls),
            "REVIEW_PUBLISHED_ENV": str(captured),
        },
        input="",
        text=True,
        capture_output=True,
    )
    assert (result.returncode == 0) is passes, result.stderr
    if passes:
        assert captured.read_text() == payload
        invocations = [json.loads(line) for line in calls.read_text().splitlines()]
        assert len(invocations) == 2
        assert all("StrictHostKeyChecking=yes" in args for args in invocations)
    else:
        assert not calls.exists()
        assert "required fail-closed setting" in result.stderr
    assert "synthetic-value" not in result.stdout + result.stderr
