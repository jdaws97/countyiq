"""Reconcile one authenticated readiness check on two external public probes."""

from __future__ import annotations

import base64
import json
import shlex
import subprocess
from pathlib import Path

from configure import ROOT, read_secrets, save_secrets
from errors import ConfigurationError
from provision import FOLDER_UID, Grafana

STACK_ID = 1822659
NAMESPACE = f"stacks-{STACK_ID}"
DATASOURCE_UID = "countyiq-synthetic-monitoring"
JOB = "countyiq-readiness"
PROBE_NAMES = ("NorthVirginia", "Oregon")


def readiness_credentials() -> dict[str, str]:
    result = subprocess.run(
        [
            "bash",
            str(ROOT / "infra/cloudflare/tofu-sops.sh"),
            "output",
            "-json",
            "public_ready_curl_config",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    headers = {}
    for line in json.loads(result.stdout).splitlines():
        parts = shlex.split(line)
        if len(parts) == 3 and parts[:2] == ["header", "="]:
            name, value = parts[2].split(":", 1)
            headers[name.lower()] = value.strip()
    return {
        "countyiq-health-client-id": headers["cf-access-client-id"],
        "countyiq-health-client-secret": headers["cf-access-client-secret"],
    }


def configure_secret_store(api: Grafana) -> None:
    base = f"/apis/secret.grafana.app/v1beta1/namespaces/{NAMESPACE}/securevalues"
    # Check namespace/permissions before reading the protected health credential.
    api.request("GET", base)
    for name, value in readiness_credentials().items():
        existing = api.request("GET", f"{base}/{name}", allow_missing=True)
        metadata = {"name": name}
        if existing:
            metadata["resourceVersion"] = existing["metadata"]["resourceVersion"]
        payload = {
            "metadata": metadata,
            "spec": {
                "description": "CountyIQ readiness access",
                "value": value,
                "decrypters": ["synthetic-monitoring"],
            },
        }
        api.request(
            "PUT" if existing else "POST",
            f"{base}/{name}" if existing else base,
            payload,
        )


def configure_datasource(api: Grafana, settings: dict[str, str]) -> None:
    if api.request("GET", f"/api/datasources/uid/{DATASOURCE_UID}", allow_missing=True):
        return
    linked = {}
    for kind, uid, tenant in (
        ("metrics", "grafanacloud-prom", "GRAFANA_METRICS_USER"),
        ("logs", "grafanacloud-logs", "GRAFANA_LOGS_USER"),
    ):
        source = api.request("GET", f"/api/datasources/uid/{uid}")
        linked[kind] = {
            "uid": uid,
            "grafanaName": source["name"],
            "type": source["type"],
            "hostedId": int(settings[tenant]),
        }
    api.request(
        "POST",
        "/api/datasources",
        {
            "uid": DATASOURCE_UID,
            "name": "Synthetic Monitoring",
            "type": "synthetic-monitoring-datasource",
            "access": "proxy",
            "isDefault": False,
            "jsonData": {
                "apiHost": settings["GRAFANA_SYNTHETIC_URL"],
                "initialized": True,
                **linked,
            },
            "secureJsonData": {"accessToken": settings["GRAFANA_SYNTHETIC_TOKEN"]},
        },
    )


def run() -> None:
    settings = read_secrets()
    api = Grafana(settings["GRAFANA_STACK_URL"], settings["GRAFANA_PROVISION_TOKEN"])
    if not settings.get("GRAFANA_SYNTHETIC_TOKEN"):
        plugin = api.request(
            "GET", "/api/plugins/grafana-synthetic-monitoring-app/settings"
        )
        result = api.request(
            "POST",
            "/api/plugin-proxy/grafana-synthetic-monitoring-app/install",
            {
                "stackId": STACK_ID,
                "metricsInstanceId": int(settings["GRAFANA_METRICS_USER"]),
                "logsInstanceId": int(settings["GRAFANA_LOGS_USER"]),
            },
        )
        settings["GRAFANA_SYNTHETIC_TOKEN"] = result["accessToken"]
        settings["GRAFANA_SYNTHETIC_URL"] = plugin["jsonData"]["apiHost"]
        save_secrets(settings)
    configure_datasource(api, settings)
    configure_secret_store(api)
    sm = Grafana(settings["GRAFANA_SYNTHETIC_URL"], settings["GRAFANA_SYNTHETIC_TOKEN"])
    probes = {
        probe["name"]: probe["id"]
        for probe in sm.request("GET", "/api/v1/probe")
        if probe["public"]
        and probe["online"]
        and not probe["deprecated"]
        and not probe.get("capabilities", {}).get("disableScriptedChecks")
    }
    if any(name not in probes for name in PROBE_NAMES):
        raise ConfigurationError("A selected external probe is unavailable.")
    script = Path(__file__).with_name("readiness.js").read_bytes()
    payload = {
        "job": JOB,
        "target": "https://app.countyiq.net/api/ready",
        "description": "Authenticated HTTP 200 and database readiness from two locations.",
        "enabled": True,
        "frequency": 300000,
        "timeout": 30000,
        "probes": [probes[name] for name in PROBE_NAMES],
        "labels": [{"name": "service", "value": "countyiq"}],
        "folderUid": FOLDER_UID,
        "basicMetricsOnly": True,
        "alertSensitivity": "none",
        "settings": {"scripted": {"script": base64.b64encode(script).decode()}},
    }
    existing = [
        check for check in sm.request("GET", "/api/v1/check") if check["job"] == JOB
    ]
    if len(existing) > 1:
        raise ConfigurationError(
            "Multiple CountyIQ readiness checks need reconciliation."
        )
    path = f"/api/v1/check/{existing[0]['id']}" if existing else "/api/v1/check"
    sm.request("PUT" if existing else "POST", path, payload)
    print(
        "External readiness configured: two locations, one request each every five minutes."
    )
    print(
        "Verify successful executions and alert delivery before relying on the check."
    )


if __name__ == "__main__":
    try:
        run()
    except ConfigurationError as error:
        print(f"Synthetic monitoring stopped: {error}")
        raise SystemExit(1)
    except (KeyError, ValueError, OSError, subprocess.SubprocessError) as error:
        print(f"Synthetic monitoring stopped ({type(error).__name__}).")
        raise SystemExit(1)
