"""Authenticate the private Dagster Codex runtime without exposing credentials."""

import argparse
import fcntl
import os
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("login", "status", "logout"), default="login", nargs="?"
    )
    args = parser.parse_args()
    value = os.environ.get("CODEX_HOME", "").strip()
    if not value:
        parser.error("CODEX_HOME must point to the private persistent login directory")
    home = Path(value)
    home.mkdir(parents=True, exist_ok=True)
    environment = {
        key: value
        for key, value in os.environ.items()
        if key
        in {
            "PATH",
            "CODEX_HOME",
            "HOME",
            "LANG",
            "TERM",
            "SSL_CERT_FILE",
            "SSL_CERT_DIR",
        }
    }
    command = ["codex", "-c", 'cli_auth_credentials_store="file"']
    command.extend(
        ["login", "--device-auth"]
        if args.action == "login"
        else ["login", "status"]
        if args.action == "status"
        else ["logout"]
    )
    with (home / ".countyiq-auth.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return subprocess.run(command, env=environment, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
