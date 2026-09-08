"""Run local subscription authoring against the exact deployed CountyIQ release.

Database traffic uses a temporary loopback-only SSH tunnel. Database credentials
are read into process memory from the existing container environment, never
written to an artifact or passed to the Codex child process.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import shlex
import socket
import subprocess
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ssh-target", required=True)
    parser.add_argument("--identity-file", type=Path, required=True)
    parser.add_argument("--local-port", type=int, default=5544)
    parser.add_argument(
        "--rebind",
        action="store_true",
        help="Replay accepted receipts with rebind_subscription_reads.py",
    )
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not 1024 <= args.local_port <= 65535:
        parser.error("--local-port must be between 1024 and 65535")
    arguments = args.arguments
    if arguments[:1] == ["--"]:
        arguments = arguments[1:]
    if not arguments:
        parser.error("Provide subscription_backfill.py arguments after --")
    ssh = [
        "ssh",
        "-i",
        str(args.identity_file),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "ConnectTimeout=15",
    ]

    def remote(command):
        return subprocess.run(
            [*ssh, args.ssh_target, shlex.join(command)],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.strip()

    root = Path(__file__).resolve().parents[2]
    local_ref = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    dirty = subprocess.check_output(
        ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
        text=True,
    )
    image = remote(
        [
            "sudo",
            "docker",
            "inspect",
            "countyiq-dagster-webserver",
            "--format",
            "{{.Config.Image}}",
        ]
    )
    if dirty or image.rsplit(":", 1)[-1] != local_ref:
        parser.error("Use a clean checkout matching the deployed Dagster image commit")
    networks = json.loads(
        remote(
            [
                "sudo",
                "docker",
                "inspect",
                "countyiq-postgres",
                "--format",
                "{{json .NetworkSettings.Networks}}",
            ]
        )
    )
    addresses = [
        network["IPAddress"]
        for network in networks.values()
        if network.get("IPAddress")
    ]
    if len(addresses) != 1:
        parser.error("Expected one private PostgreSQL container network address")
    address = str(ipaddress.IPv4Address(addresses[0]))
    # Fixed command, no user interpolation and no output copied to our logs.
    credentials = remote(
        [
            "sudo",
            "docker",
            "exec",
            "countyiq-postgres",
            "sh",
            "-c",
            'printf "%s\\n%s\\n%s" "$DATABASE_PIPELINE_USER" "$DATABASE_PIPELINE_PASSWORD" "$POSTGRES_DB"',
        ]
    ).splitlines()
    if len(credentials) != 3 or not all(credentials):
        parser.error("Pipeline database credentials are unavailable")
    environment = {
        **os.environ,
        "PYTHONPATH": str(root / "pipelines"),
        "DATABASE_HOST": "127.0.0.1",
        "DATABASE_PORT": str(args.local_port),
        "DATABASE_USER": credentials[0],
        "DATABASE_PASSWORD": credentials[1],
        "DATABASE_NAME": credentials[2],
    }
    tunnel = subprocess.Popen(
        [
            *ssh,
            "-o",
            "ExitOnForwardFailure=yes",
            "-N",
            "-L",
            f"127.0.0.1:{args.local_port}:{address}:5432",
            args.ssh_target,
        ],
        stdin=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 20
        while True:
            if tunnel.poll() is not None:
                raise RuntimeError("SSH database tunnel failed to start")
            try:
                with socket.create_connection(
                    ("127.0.0.1", args.local_port), timeout=1
                ):
                    break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        "SSH database tunnel did not become ready"
                    ) from None
                time.sleep(0.1)
        operation = "receipt replay" if args.rebind else "authoring"
        script = (
            "rebind_subscription_reads.py"
            if args.rebind
            else "subscription_backfill.py"
        )
        print(
            f"Subscription {operation} against deployed release {local_ref}", flush=True
        )
        return subprocess.run(
            [
                sys.executable,
                str(Path(__file__).with_name(script)),
                *arguments,
            ],
            env=environment,
            check=False,
        ).returncode
    finally:
        tunnel.terminate()
        try:
            tunnel.wait(timeout=10)
        except subprocess.TimeoutExpired:
            tunnel.kill()
            tunnel.wait()


if __name__ == "__main__":
    raise SystemExit(main())
