"""A failed schema probe must not authorize deployment recovery."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "output,status,expected",
    [
        ("054 (head)\n", 0, "054 (head)\n"),
        ("", 0, "base\n"),
        ("", 1, ""),
        ("054 (head)\n", 1, ""),
    ],
)
def test_schema_probe_propagates_failure_even_when_errexit_is_suppressed(
    tmp_path, output, status, expected
):
    probe = tmp_path / "compose"
    probe.write_text(
        '#!/bin/bash\nprintf \'%s\' "$PROBE_OUTPUT"\nexit "$PROBE_STATUS"\n'
    )
    probe.chmod(0o755)
    result = subprocess.run(
        [
            "bash",
            "-o",
            "pipefail",
            "-c",
            'source docker/lib/operations.sh; value=$(countyiq_read_schema_revision "$1"); result=$?; printf "%s" "$value"; exit "$result"',
            "schema-test",
            str(probe),
        ],
        cwd=ROOT,
        env={**os.environ, "PROBE_OUTPUT": output, "PROBE_STATUS": str(status)},
        capture_output=True,
        text=True,
    )
    assert (result.returncode == 0) == (status == 0)
    assert result.stdout == expected.rstrip("\n")


def test_cost_stop_blocks_recovery_start(tmp_path):
    (tmp_path / "tripped").write_text("reason=manual\n")
    result = subprocess.run(
        [
            "bash",
            "-c",
            "source docker/lib/operations.sh; countyiq_require_cost_guard_clear",
        ],
        cwd=ROOT,
        env={**os.environ, "COUNTYIQ_COST_GUARD_DIR": str(tmp_path)},
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "refusing to start services" in result.stderr


@pytest.mark.integration
@pytest.mark.parametrize(
    "scenario,restarts",
    [
        ("stop_failed", True),
        ("stop_failed_latched", False),
        ("probe_failed", False),
        ("host_failed", False),
        ("account_failed", False),
        ("writer_enabled", True),
        ("writer_missing", True),
        ("writer_busy", True),
    ],
)
def test_real_deploy_script_handles_partial_stop_and_probe_failures(
    tmp_path, scenario, restarts
):
    import yaml

    bindir = tmp_path / "bin"
    bindir.mkdir()
    sha = "a" * 40
    scripts = {
        "git": '#!/bin/bash\ncase " $* " in *" rev-parse HEAD "*) echo '
        + sha
        + ";; esac\nexit 0\n",
        "docker": r"""#!/bin/bash
printf '%s\n' "$*" >> /case/events.log
case " $* " in
  *" current "*)
    [ "$REVIEW_SCENARIO" != probe_failed ] || exit 1
    echo '054 (head)' ;;
  *" stop -t 60 "*)
    case "$REVIEW_SCENARIO" in
      writer_*) exit 0 ;;
    esac
    if [ "$REVIEW_SCENARIO" = stop_failed_latched ]; then
        mkdir -p /tmp/guard
        touch /tmp/guard/tripped
    fi
    exit 1 ;;
  *" SELECT rolcanlogin "*)
    case "$REVIEW_SCENARIO" in
      writer_enabled) echo t ;;
      writer_missing) ;;
      *) echo f ;;
    esac ;;
  *" SELECT COUNT(*) FROM pg_stat_activity "*) echo 1 ;;
esac
exit 0
""",
    }
    scripts["sshd"] = (
        "#!/bin/bash\nprintf '%s\\n' 'passwordauthentication no' 'kbdinteractiveauthentication no' 'permitrootlogin no' 'pubkeyauthentication yes'\n"
    )
    if scenario == "host_failed":
        scripts["sshd"] = scripts["sshd"].replace(
            "passwordauthentication no", "passwordauthentication yes"
        )
    for name in ("curl", "pg_restore", "rclone"):
        scripts[name] = "#!/bin/bash\nexit 0\n"
    for name, script in scripts.items():
        path = bindir / name
        path.write_text(script)
        path.chmod(0o755)
    values = {
        "COUNTYIQ_DEPLOY_REF": sha,
        "DATABASE_NAME": "countyiq",
        "DATABASE_USER": "dagster_admin",
        "DATABASE_PASSWORD": "a" * 40,
        "DATABASE_URL": "postgresql://dagster_admin:"
        + "a" * 40
        + "@postgres:5432/countyiq",
        "DATABASE_PIPELINE_USER": "countyiq_pipeline",
        "DATABASE_PIPELINE_PASSWORD": "b" * 40,
        "DATABASE_API_USER": "countyiq_api",
        "DATABASE_API_PASSWORD": "c" * 40,
        "DOMAIN": "countyiq.test",
        "COUNTYIQ_TRUSTED_HOSTS": "app.countyiq.test",
        "CLOUDFLARE_TUNNEL_TOKEN": "t" * 128,
        "COUNTYIQ_AUTH_PROVIDER": "cloudflare_access",
        "COUNTYIQ_ACCESS_ISSUER": "https://team.cloudflareaccess.com",
        "COUNTYIQ_ACCESS_AUD": "reviewed-app-audience",
        "COUNTYIQ_APP_URL": "https://app.countyiq.test",
        "COUNTYIQ_WORKSPACE_ORIGINS": "https://app.countyiq.test",
        "COUNTYIQ_ARCHIVE_STRICT": "true",
        "COUNTYIQ_BACKUP_BUCKET_LOCK_CONFIRMED": "true",
        "R2_ACCESS_KEY_ID": "raw-id",
        "R2_SECRET_ACCESS_KEY": "raw-secret",
        "S3_RAW_BUCKET": "countyiq-raw",
        "COUNTYIQ_BACKUP_R2_ACCESS_KEY_ID": "backup-id",
        "COUNTYIQ_BACKUP_R2_SECRET_ACCESS_KEY": "backup-secret",
        "COUNTYIQ_BACKUP_R2_BUCKET": "countyiq-backups",
        "R2_ENDPOINT_URL": "https://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.r2.cloudflarestorage.com",
        "COUNTYIQ_RELEASE_DIR": "/tmp/releases",
        "COUNTYIQ_RESTORE_RECEIPT_DIR": "/tmp/receipts",
        "COUNTYIQ_COST_GUARD_DIR": "/tmp/guard",
    }
    if scenario == "account_failed":
        values["COUNTYIQ_WATCH_SYNC_ENABLED"] = "true"
        values["COUNTYIQ_AUTH_PROVIDER"] = "disabled"
    (tmp_path / "environment").write_text(
        "\n".join(f"{key}={value}" for key, value in values.items()) + "\n"
    )
    logfile = tmp_path / "events.log"
    logfile.touch()
    logfile.chmod(0o666)
    image = yaml.safe_load((ROOT / "pipelines/docker-compose.yml").read_text())[
        "services"
    ]["postgres-test"]["image"]
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
            f"{tmp_path}:/case",
            "-e",
            f"REVIEW_SCENARIO={scenario}",
            "-e",
            f"COUNTYIQ_DEPLOY_REF={sha}",
            "--entrypoint",
            "bash",
            image,
            "-c",
            "cp /case/environment /tmp/production.env; chmod 600 /tmp/production.env; "
            "mkdir -p /tmp/guard; chmod 755 /tmp/guard; "
            "export COUNTYIQ_ENV_FILE=/tmp/production.env PATH=/case/bin:$PATH; "
            "/repo/docker/deploy.sh --initial",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    events = logfile.read_text()
    if scenario == "account_failed":
        assert "requires a configured authentication provider" in result.stderr
        assert (
            " build " not in events and " up " not in events and " stop " not in events
        )
        return
    if scenario == "host_failed":
        assert "Host SSH policy is not effective" in result.stderr
        assert (
            " build " not in events and " up " not in events and " stop " not in events
        )
        return
    assert " current" in events, result.stderr
    assert (" start api" in events) == restarts, events
    if scenario == "probe_failed":
        assert " stop -t 60 " not in events
    if scenario in {"writer_enabled", "writer_missing"}:
        assert "confirmed NOLOGIN pipeline writer" in result.stderr
    if scenario == "writer_busy":
        assert "database session(s) remain" in result.stderr
