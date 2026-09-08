"""Capture Grafana connection details without displaying or storing plaintext secrets."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import shutil
import subprocess
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from errors import ConfigurationError

ROOT = Path(__file__).resolve().parents[2]
SECRET_PATH = ROOT / "infra/secrets/monitoring.sops.env"
STACK = json.loads(Path(__file__).with_name("stack.json").read_text())
OPERATOR_EMAIL = STACK["operator_email"]
ALLOWED_EMAILS = frozenset(STACK["allowed_emails"])
INGEST_KEYS = (
    "GRAFANA_METRICS_URL",
    "GRAFANA_METRICS_USER",
    "GRAFANA_LOGS_URL",
    "GRAFANA_LOGS_USER",
    "GRAFANA_INGEST_TOKEN",
)


def validate_url(value: str, *, path: str | None = None) -> str:
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not parsed.hostname.endswith(".grafana.net")
        or parsed.username
        or parsed.password
        or parsed.port
        or parsed.query
        or parsed.fragment
    ):
        raise ConfigurationError(
            "Use the exact HTTPS endpoint from your Grafana Cloud stack."
        )
    if path is not None and parsed.path.rstrip("/") != path:
        raise ConfigurationError("Grafana datasource endpoint has an unexpected path.")
    return value.rstrip("/")


def sops_environment() -> dict:
    return {
        **os.environ,
        "SOPS_AGE_SSH_PRIVATE_KEY_FILE": str(Path.home() / ".ssh/jdawskey"),
    }


def sops_binary() -> str:
    return shutil.which("sops") or str(Path.home() / ".local/bin/sops")


def read_secrets() -> dict[str, str]:
    result = subprocess.run(
        [
            sops_binary(),
            "decrypt",
            "--input-type",
            "dotenv",
            "--output-type",
            "dotenv",
            str(SECRET_PATH),
        ],
        text=True,
        capture_output=True,
        check=True,
        env=sops_environment(),
    )
    return {
        name: value
        for line in result.stdout.splitlines()
        if line and not line.startswith("#") and "=" in line
        for name, value in [line.split("=", 1)]
    }


def capture() -> None:
    if SECRET_PATH.exists():
        raise ValueError(
            "Monitoring secrets already exist; use SOPS to edit or rotate them."
        )
    print("Use Grafana Cloud Free. Secret input is hidden and streamed into SOPS.")
    from provision import Grafana, select_datasource, verify_owner

    stack_url = validate_url(STACK["url"], path="")
    print(
        f"Connecting {stack_url}; allowed accounts: {', '.join(sorted(ALLOWED_EMAILS))}."
    )
    provision_token = getpass.getpass(
        "Grafana service-account provisioning token (hidden): "
    ).strip()
    api = Grafana(stack_url, provision_token)
    verify_owner(api.request("GET", "/api/org/users"), ALLOWED_EMAILS)
    sources = api.request("GET", "/api/datasources")
    by_uid = {source["uid"]: source for source in sources}
    metrics = by_uid[select_datasource(sources, "prometheus")]
    logs = by_uid[select_datasource(sources, "loki")]
    values = {
        "GRAFANA_STACK_URL": stack_url,
        "GRAFANA_METRICS_URL": validate_url(
            metrics["url"].rstrip("/") + "/push", path="/api/prom/push"
        ),
        "GRAFANA_METRICS_USER": metrics["basicAuthUser"],
        "GRAFANA_LOGS_URL": validate_url(
            logs["url"].rstrip("/") + "/loki/api/v1/push", path="/loki/api/v1/push"
        ),
        "GRAFANA_LOGS_USER": logs["basicAuthUser"],
        "GRAFANA_INGEST_TOKEN": getpass.getpass(
            "Cloud metrics:write + logs:write token (hidden): "
        ).strip(),
        "GRAFANA_PROVISION_TOKEN": provision_token,
        "COUNTYIQ_OPERATOR_EMAIL": OPERATOR_EMAIL,
    }
    for name in ("GRAFANA_METRICS_USER", "GRAFANA_LOGS_USER"):
        if not values[name].isdigit():
            raise ConfigurationError(
                "Grafana metrics/logs instance IDs must be numeric."
            )
    if any(not value or re.search(r"[\s\"'`$]", value) for value in values.values()):
        raise ConfigurationError(
            "Connection values must be nonempty, single-line values."
        )
    plaintext = "".join(f"{name}={value}\n" for name, value in values.items())
    result = subprocess.run(
        [
            sops_binary(),
            "encrypt",
            "--input-type",
            "dotenv",
            "--output-type",
            "dotenv",
            "--filename-override",
            str(SECRET_PATH.relative_to(ROOT)),
            "/dev/stdin",
        ],
        input=plaintext,
        text=True,
        capture_output=True,
        check=True,
        cwd=ROOT,
        env=sops_environment(),
    )
    with SECRET_PATH.open("x") as output:
        output.write(result.stdout)
    print("Saved encrypted monitoring credentials. No credentials were printed.")


def publish() -> None:
    values = read_secrets()
    validate_url(values["GRAFANA_METRICS_URL"], path="/api/prom/push")
    validate_url(values["GRAFANA_LOGS_URL"], path="/loki/api/v1/push")
    selected = {name: values[name] for name in INGEST_KEYS}
    if any(not value or re.search(r"[\s\"'`$]", value) for value in selected.values()):
        raise ConfigurationError("Ingestion settings contain invalid values.")
    remote_command = (
        "sudo -n sh -c 'set -eu; umask 077; "
        "install -d -m 700 /etc/countyiq; "
        "temporary=$(mktemp /etc/countyiq/.monitoring.XXXXXX); "
        'trap "rm -f -- $temporary" EXIT; '
        'cat > "$temporary"; chmod 600 "$temporary"; '
        'chown root:root "$temporary"; '
        'mv "$temporary" /etc/countyiq/monitoring.env; '
        "trap - EXIT'"
    )
    subprocess.run(
        [
            "ssh",
            "-i",
            str(Path.home() / ".ssh/jdawskey"),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "ubuntu@15.204.255.199",
            remote_command,
        ],
        input="".join(f"{name}={value}\n" for name, value in selected.items()),
        text=True,
        check=True,
    )
    print(
        "Published ingestion-only credentials to the VPS; provisioning token stays local."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("capture", "publish"))
    args = parser.parse_args()
    try:
        {"capture": capture, "publish": publish}[args.action]()
    except ConfigurationError as error:
        print(f"Monitoring configuration failed: {error}")
        raise SystemExit(1)
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
        # Do not expose captured subprocess output or plaintext values.
        print(f"Monitoring configuration failed ({type(error).__name__}).")
        raise SystemExit(1)
