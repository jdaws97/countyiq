#!/usr/bin/env python3
"""Hold the deployment lock and lend pipeline credentials to a local SSH client.

Only the first protocol message contains credentials. The client keeps that
message in memory. Closing SSH releases the lock; a missing heartbeat or cost
stop ends the session. This program runs briefly on the VPS, never a pipeline.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import select
import signal
import stat
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

ENVIRONMENT_FILE = Path("/etc/countyiq/production.env")
RELEASE_FILE = Path("/var/lib/countyiq/releases/current.env")
DEPLOY_LOCK = Path("/var/lock/countyiq-deploy.lock")
COST_STOP = Path("/var/lib/countyiq/cost-guard/tripped")
PIPELINE_KEYS = {
    "COUNTY",
    "COUNTYIQ_ARCHIVE_STRICT",
    "COUNTYIQ_LLM_ARCHIVE_RETENTION_DAYS",
    "COUNTYIQ_ERROR_BUDGET",
    "COUNTYIQ_LLM_BACKEND",
    "COUNTYIQ_CODEX_MODEL",
    "COUNTYIQ_CODEX_TIMEOUT_SECONDS",
    "COUNTYIQ_OPENROUTER_MODEL",
    "COUNTYIQ_STRICT_SCHEMA",
    "COUNTYIQ_ALLOW_SCHEMA_FALLBACK",
    "COUNTYIQ_PROVIDER_ONLY",
    "COUNTYIQ_PROVIDER_ORDER",
    "COUNTYIQ_PROVIDER_ALLOW_FALLBACKS",
    "COUNTYIQ_THINKING",
    "COUNTYIQ_MAX_PRICE_PROMPT",
    "COUNTYIQ_MAX_PRICE_COMPLETION",
    "COUNTYIQ_ZDR",
    "COUNTYIQ_CONTRADICTION_MAX_AGE_HOURS",
    "COUNTYIQ_PROCEEDINGS_MAX_DOCUMENT_REQUESTS",
    "COUNTYIQ_PROCEEDINGS_MAX_DOCUMENTS_PER_BODY",
    "COUNTYIQ_PROCEEDINGS_MAX_FUTURE_DAYS",
    "COUNTYIQ_PA_DOS_MAX_NAMES_PER_RUN",
    "COUNTYIQ_PA_DOS_FOUND_TTL_DAYS",
    "COUNTYIQ_PA_DOS_NOT_FOUND_TTL_DAYS",
    "OPENROUTER_API_KEY",
    "SODA_APP_TOKEN",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_ENDPOINT_URL",
    "S3_RAW_BUCKET",
    "AWS_DEFAULT_REGION",
}
PASS_SETTING = re.compile(r"COUNTYIQ_PASS[0-4]_[A-Z0-9_]+")


def read_environment(path: Path) -> dict[str, str]:
    metadata = path.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != 0
        or stat.S_IMODE(metadata.st_mode) not in {0o400, 0o600}
    ):
        raise ValueError("Production environment must be a protected root-owned file")
    result = subprocess.run(
        ["bash", "-c", 'set -a; source "$1"; env -0', "pipeline-session", str(path)],
        check=True,
        capture_output=True,
        timeout=10,
    )
    return dict(
        entry.decode().split("=", 1) for entry in result.stdout.split(b"\0") if entry
    )


def pipeline_environment(values: dict[str, str]) -> dict[str, str]:
    """Exclude administrator/API/backup credentials and VPS-local file paths."""
    selected = {}
    for key, value in values.items():
        if key in PIPELINE_KEYS or (
            PASS_SETTING.fullmatch(key)
            and not key.endswith(("_FILE", "_QUALITY_RECEIPT"))
        ):
            selected[key] = value
    selected.update(
        DATABASE_NAME=values["DATABASE_NAME"],
        DATABASE_USER=values["DATABASE_PIPELINE_USER"],
        DATABASE_PASSWORD=values["DATABASE_PIPELINE_PASSWORD"],
    )
    if selected["DATABASE_USER"] in {
        values["DATABASE_USER"],
        values["DATABASE_API_USER"],
    }:
        raise ValueError("Local pipelines require the separate writer role")
    if selected.get("COUNTYIQ_ARCHIVE_STRICT") != "true":
        raise ValueError("Production pipeline archives must remain strict")
    for key in (
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_ENDPOINT_URL",
        "S3_RAW_BUCKET",
    ):
        if not selected.get(key):
            raise ValueError("Raw archive configuration is incomplete")
    # A source refresh cannot inherit a temporarily enabled inference pass.
    for pass_number in range(5):
        selected[f"COUNTYIQ_PASS{pass_number}_ENABLED"] = "false"
    return selected


def verify_release(reference: str) -> None:
    receipt = {}
    for line in RELEASE_FILE.read_text().splitlines():
        key, separator, value = line.partition("=")
        if separator:
            receipt[key] = value
    root = Path(__file__).resolve().parents[1]
    checkout = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True, timeout=10
    ).strip()
    image = subprocess.check_output(
        ["docker", "inspect", "--format", "{{.Config.Image}}", "countyiq-api"],
        text=True,
        timeout=10,
    ).strip()
    if (
        receipt.get("deploy_ref") != reference
        or checkout != reference
        or image != f"countyiq-api:{reference}"
    ):
        raise ValueError("Use the clean pipeline checkout matching the active release")


def message(value: dict) -> None:
    print(json.dumps(value), flush=True)


def writer_login(values: dict[str, str], *, enabled: bool) -> None:
    identifiers = [
        values[key]
        for key in ("DATABASE_USER", "DATABASE_NAME", "DATABASE_PIPELINE_USER")
    ]
    if any(not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", value) for value in identifiers):
        raise ValueError("Pipeline database names must be simple identifiers")
    owner, database, writer = identifiers
    login = "LOGIN" if enabled else "NOLOGIN"
    sql_commands = ["-c", f'ALTER ROLE "{writer}" {login};']
    if not enabled:
        # Separate -c commands commit NOLOGIN before selecting sessions to stop.
        # A single multi-statement transaction would leave a connection race.
        sql_commands.extend(
            [
                "-c",
                (
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    f"WHERE usename = '{writer}' AND pid <> pg_backend_pid();"
                ),
            ]
        )
    subprocess.run(
        [
            "docker",
            "exec",
            "countyiq-postgres",
            "psql",
            "-X",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            owner,
            "-d",
            database,
            *sql_commands,
        ],
        check=True,
        capture_output=True,
        timeout=15,
    )


@contextmanager
def writer_access(values: dict[str, str]):
    # The host lock is held throughout. Revoke abandoned sessions before lending
    # the role, and stop new connections before terminating this session's writes.
    writer_login(values, enabled=False)
    try:
        writer_login(values, enabled=True)
        yield
    finally:
        writer_login(values, enabled=False)


def serve(reference: str) -> None:
    if os.geteuid() != 0:
        raise ValueError("Pipeline sessions require the operator's sudo access")
    with DEPLOY_LOCK.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError(
                "A pipeline, deployment or restore already holds the VPS lock"
            ) from None
        if COST_STOP.exists():
            raise ValueError("CountyIQ's cost stop is active")
        verify_release(reference)
        values = read_environment(ENVIRONMENT_FILE)
        environment = pipeline_environment(values)
        with writer_access(values):
            message(
                {"type": "session", "reference": reference, "environment": environment}
            )
            while True:
                ready, _, _ = select.select([sys.stdin], [], [], 20)
                if not ready:
                    raise ValueError("The local pipeline heartbeat expired")
                command = sys.stdin.readline(32)
                if not command:
                    return
                if command != "ping\n":
                    raise ValueError("Invalid local pipeline heartbeat")
                if COST_STOP.exists():
                    raise ValueError("CountyIQ's cost stop became active")
                message({"type": "heartbeat"})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", required=True)
    arguments = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", arguments.ref):
        parser.error("--ref must be a complete reviewed Git commit")
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    try:
        serve(arguments.ref)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        # Never print environment values or a subprocess's captured output.
        if isinstance(error, ValueError):
            print(str(error), file=sys.stderr)
        else:
            print("Could not maintain the protected pipeline session", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
