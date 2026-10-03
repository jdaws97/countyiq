"""Short-lived SSH session for a PC pipeline and the VPS writer lease."""

from __future__ import annotations

import ipaddress
import json
import os
import select
import shlex
import signal
import socket
import subprocess
import time
from pathlib import Path


def checkout_reference(root: Path) -> str:
    dirty = subprocess.check_output(
        ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
        text=True,
    )
    if dirty:
        raise ValueError(
            "Production runs require a clean checkout of the deployed commit"
        )
    return subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def read_message(stream, timeout: float) -> dict:
    readable, _, _ = select.select([stream], [], [], timeout)
    if not readable:
        raise RuntimeError("The protected VPS session did not respond")
    line = stream.readline(65537)
    if not line or len(line) > 65536:
        raise RuntimeError(
            "The protected VPS session ended or sent an invalid response"
        )
    try:
        message = json.loads(line)
    except (ValueError, TypeError):
        raise RuntimeError(
            "The protected VPS session sent an invalid response"
        ) from None
    if not isinstance(message, dict):
        raise RuntimeError(  # noqa: TRY004 — a malformed protocol response is a session failure.
            "The protected VPS session sent an invalid response"
        )
    return message


def stop_process_group(process) -> None:
    if process is None:
        return
    # The group can outlive its leader after a crash or interrupted Dagster run.
    # Always address the group, even when Popen has already reaped the leader.
    try:
        os.killpg(process.pid, signal.SIGINT)
    except ProcessLookupError:
        process.wait()
        return
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        process.poll()
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=5)


class PipelineSession:
    """Keep the SSH tunnel, writer permission and deployment exclusion together."""

    def __init__(self, *, root: Path, target: str, identity: Path):
        self.reference = checkout_reference(root)
        self.port = free_port()
        self.process = None
        self.last_heartbeat = 0.0
        self.environment = {}
        ssh = [
            "ssh",
            "-T",
            "-i",
            str(identity),
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "ConnectTimeout=15",
        ]
        inspect = [
            "sudo",
            "-n",
            "docker",
            "inspect",
            "--format",
            '{{(index .NetworkSettings.Networks "countyiq_database").IPAddress}}',
            "countyiq-postgres",
        ]
        address = subprocess.check_output(
            [*ssh, target, shlex.join(inspect)], text=True, timeout=25
        ).strip()
        parsed = ipaddress.ip_address(address)
        if parsed.version != 4 or not parsed.is_private:
            raise ValueError("The database must have a private Docker IPv4 address")
        self.database_address = address
        command = [
            "sudo",
            "-n",
            "python3",
            "/opt/countyiq/docker/pipeline_session.py",
            "--ref",
            self.reference,
        ]
        self.arguments = [
            *ssh,
            "-o",
            "ServerAliveInterval=5",
            "-o",
            "ServerAliveCountMax=2",
            "-o",
            "ExitOnForwardFailure=yes",
            "-L",
            f"127.0.0.1:{self.port}:{address}:5432",
            target,
            shlex.join(command),
        ]

    def __enter__(self):
        self.process = subprocess.Popen(
            self.arguments,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        try:
            response = read_message(self.process.stdout, timeout=25)
            values = response.get("environment")
            if (
                response.get("type") != "session"
                or response.get("reference") != self.reference
                or response.get("database_address") != self.database_address
                or not isinstance(values, dict)
                or any(not isinstance(value, str) for value in values.values())
            ):
                raise RuntimeError("The VPS did not authorize this release")
            self.environment = {
                **values,
                "DATABASE_HOST": "127.0.0.1",
                "DATABASE_PORT": str(self.port),
            }
            self.heartbeat(force=True)
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def heartbeat(self, *, force: bool = False) -> None:
        if self.process.poll() is not None:
            raise RuntimeError("The protected VPS session ended")
        if not force and time.monotonic() - self.last_heartbeat < 2:
            return
        self.process.stdin.write("ping\n")
        self.process.stdin.flush()
        if read_message(self.process.stdout, timeout=8).get("type") != "heartbeat":
            raise RuntimeError("The VPS stopped the local pipeline")
        self.last_heartbeat = time.monotonic()

    def __exit__(self, *_):
        if self.process is None:
            return
        if self.process.stdin and not self.process.stdin.closed:
            try:
                self.process.stdin.close()
            except BrokenPipeError:
                pass
        try:
            self.process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.process.stdout.close()


def run_command(command: list[str], environment: dict, session=None) -> int:
    process = None
    try:
        process = subprocess.Popen(command, env=environment, start_new_session=True)
        while process.poll() is None:
            if session is not None:
                session.heartbeat()
            time.sleep(0.2)
        return process.returncode
    finally:
        # Stop all Dagster subprocesses before SSH releases the database role
        # and host lock. This also handles Ctrl-C and a lost/cost-stopped lease.
        stop_process_group(process)
