"""Provision CountyIQ dashboards and alert routing without touching billing.

Use --check for authenticated preflight or --apply to reconcile the named
CountyIQ resources. Existing unrelated dashboards and notification routes stay
intact. The provisioning credential is never installed on the VPS.
"""

from __future__ import annotations

import argparse
import copy
import json
import urllib.error
import urllib.request
from pathlib import Path

from configure import ALLOWED_EMAILS, OPERATOR_EMAIL, read_secrets, validate_url
from errors import ConfigurationError

ROOT = Path(__file__).resolve().parent
FOLDER_UID = "countyiq-monitoring"
CONTACT_UID = "countyiq-owner-email"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


class Grafana:
    def __init__(self, url: str, token: str):
        self.url = validate_url(url, path="")
        self.token = token
        self.opener = urllib.request.build_opener(NoRedirect)

    def request(self, method: str, path: str, payload=None, *, allow_missing=False):
        if not path.startswith("/api/") and not path.startswith("/apis/"):
            raise ValueError("Unexpected Grafana API path")
        request = urllib.request.Request(
            self.url + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method=method,
        )
        try:
            with self.opener.open(request, timeout=30) as response:
                body = response.read(5_000_000)
                return json.loads(body) if body else None
        except urllib.error.HTTPError as error:
            if allow_missing and error.code == 404:
                return None
            if error.code == 401:
                raise ConfigurationError(
                    "Grafana rejected the service-account token (HTTP 401). "
                    "Use a current glsa_ token from this Grafana stack."
                ) from None
            if error.code == 403:
                raise ConfigurationError(
                    "Grafana denied this operation (HTTP 403). Check the token's "
                    "permissions and the target stack or namespace."
                ) from None
            # API error bodies may contain secrets or saved contact settings.
            raise ConfigurationError(
                f"Grafana {method} {path} failed with HTTP {error.code}."
            ) from None


def select_datasource(datasources: list[dict], kind: str) -> str:
    matches = [
        item
        for item in datasources
        if item["type"] == kind and "usage" not in item["name"].lower()
    ]
    defaults = [item for item in matches if item.get("isDefault")]
    if len(defaults) == 1:
        return defaults[0]["uid"]
    suffix = {"prometheus": "-prom", "loki": "-logs"}.get(kind)
    cloud_sources = [
        item
        for item in matches
        if suffix
        and item["name"].startswith("grafanacloud-")
        and item["name"].endswith(suffix)
    ]
    if len(cloud_sources) == 1:
        return cloud_sources[0]["uid"]
    if len(matches) != 1:
        raise ConfigurationError(
            f"Expected one unambiguous {kind} datasource; found {len(matches)}. "
            "Check the datasource names in Grafana Connections > Data sources."
        )
    return matches[0]["uid"]


def verify_owner(users: list[dict], allowed_emails: frozenset[str]) -> None:
    humans = [user for user in users if not user.get("isServiceAccount", False)]
    if not humans or any(
        user.get("email", "").lower() not in allowed_emails for user in humans
    ):
        raise ConfigurationError(
            "Grafana has a human member outside the approved email allowlist, "
            "or no human owner. Confirm account membership before connecting."
        )


def notification_policy(existing: dict) -> dict:
    policy = copy.deepcopy(existing)
    matcher = [["countyiq_monitoring", "=", "true"]]
    routes = policy.setdefault("routes", [])
    owned = [route for route in routes if route.get("object_matchers") == matcher]
    if len(owned) > 1:
        raise ValueError("Multiple CountyIQ notification routes need reconciliation")
    route = {
        "receiver": "CountyIQ owner email",
        "object_matchers": matcher,
        "group_by": ["grafana_folder", "alertname"],
        "group_wait": "30s",
        "group_interval": "5m",
        "repeat_interval": "4h",
        "continue": False,
        "routes": [
            {
                "receiver": "CountyIQ owner email",
                "object_matchers": [["severity", "=", "warning"]],
                "group_by": ["grafana_folder", "severity"],
                "group_wait": "30s",
                # Warn promptly once, then batch changes and reminders daily.
                # Critical incidents retain the parent route's faster cadence.
                "group_interval": "24h",
                "repeat_interval": "24h",
                "continue": False,
            }
        ],
    }
    if owned:
        routes[routes.index(owned[0])] = route
    else:
        # The specific route precedes any existing broad route; other alerts
        # continue through the original policy tree unchanged.
        routes.insert(0, route)
    return policy


def alert_group(catalog: list[dict], metrics_uid: str) -> dict:
    rules = []
    for alert in catalog:
        rules.append(
            {
                "uid": f"ciq-{alert['uid']}",
                "title": alert["title"],
                "condition": "C",
                "for": alert["for"],
                # The explicit missing-host and collector checks own data absence.
                "noDataState": "OK",
                "execErrState": "Error",
                "isPaused": False,
                "annotations": {
                    "summary": alert["summary"],
                    "description": alert["description"],
                    "runbook_url": "https://github.com/jdaws97/countyiq/blob/main/docs/operations/monitoring.md",
                    "dashboard_url": "https://eloquentbread1118.grafana.net/d/countyiq-overview",
                },
                "labels": {
                    "countyiq_monitoring": "true",
                    "severity": alert["severity"],
                },
                "data": [
                    {
                        "refId": "A",
                        "datasourceUid": metrics_uid,
                        "relativeTimeRange": {"from": 600, "to": 0},
                        "model": {
                            "refId": "A",
                            "expr": alert["expr"],
                            "instant": True,
                            "range": False,
                            "intervalMs": 1000,
                            "maxDataPoints": 43200,
                            "datasource": {"type": "prometheus", "uid": metrics_uid},
                        },
                    },
                    {
                        "refId": "B",
                        "datasourceUid": "__expr__",
                        "relativeTimeRange": {"from": 0, "to": 0},
                        "model": {
                            "refId": "B",
                            "type": "reduce",
                            "expression": "A",
                            "reducer": "last",
                            "datasource": {"type": "__expr__", "uid": "__expr__"},
                        },
                    },
                    {
                        "refId": "C",
                        "datasourceUid": "__expr__",
                        "relativeTimeRange": {"from": 0, "to": 0},
                        "model": {
                            "refId": "C",
                            "type": "threshold",
                            "expression": "B",
                            "datasource": {"type": "__expr__", "uid": "__expr__"},
                            "conditions": [
                                {
                                    "evaluator": {"type": "gt", "params": [0]},
                                    "operator": {"type": "and"},
                                    "query": {"params": ["C"]},
                                    "reducer": {"type": "last", "params": []},
                                    "type": "query",
                                }
                            ],
                        },
                    },
                ],
            }
        )
    return {
        "title": "CountyIQ",
        "folderUid": FOLDER_UID,
        "interval": 60,
        "rules": rules,
    }


def run(*, apply: bool) -> None:
    settings = read_secrets()
    if settings.get("COUNTYIQ_OPERATOR_EMAIL") != OPERATOR_EMAIL:
        raise ValueError("Unexpected operator email in protected settings")
    api = Grafana(settings["GRAFANA_STACK_URL"], settings["GRAFANA_PROVISION_TOKEN"])
    verify_owner(api.request("GET", "/api/org/users"), ALLOWED_EMAILS)
    sources = api.request("GET", "/api/datasources")
    metrics_uid = select_datasource(sources, "prometheus")
    logs_uid = select_datasource(sources, "loki")
    catalog = json.loads((ROOT / "alerts.json").read_text())
    original_policy = api.request("GET", "/api/v1/provisioning/policies")
    contacts = api.request("GET", "/api/v1/provisioning/contact-points")
    contact = {
        "uid": CONTACT_UID,
        "name": "CountyIQ owner email",
        "type": "email",
        "settings": {"addresses": OPERATOR_EMAIL},
        "disableResolveMessage": False,
    }
    existing_contact = next(
        (item for item in contacts if item["uid"] == CONTACT_UID), None
    )
    if not apply:
        print(
            f"Preflight passed: approved human membership verified; {len(catalog)} alert rules ready."
        )
        return
    if api.request("GET", f"/api/folders/{FOLDER_UID}", allow_missing=True) is None:
        api.request("POST", "/api/folders", {"uid": FOLDER_UID, "title": "CountyIQ"})
    dashboard_text = (ROOT / "dashboards/countyiq.json").read_text()
    dashboard = json.loads(
        dashboard_text.replace("${METRICS_UID}", metrics_uid).replace(
            "${LOGS_UID}", logs_uid
        )
    )
    api.request(
        "POST",
        "/api/dashboards/db",
        {
            "dashboard": dashboard,
            "folderUid": FOLDER_UID,
            "overwrite": True,
            "message": "Reconcile reviewed CountyIQ monitoring configuration",
        },
    )
    if existing_contact:
        api.request(
            "PUT", f"/api/v1/provisioning/contact-points/{CONTACT_UID}", contact
        )
    else:
        api.request("POST", "/api/v1/provisioning/contact-points", contact)
    api.request(
        "PUT", "/api/v1/provisioning/policies", notification_policy(original_policy)
    )
    api.request(
        "PUT",
        f"/api/v1/provisioning/folder/{FOLDER_UID}/rule-groups/CountyIQ",
        alert_group(catalog, metrics_uid),
    )
    actual = api.request(
        "GET", f"/api/v1/provisioning/folder/{FOLDER_UID}/rule-groups/CountyIQ"
    )
    if len(actual["rules"]) != len(catalog):
        raise RuntimeError("Grafana rule-group verification failed")
    print(
        f"Provisioned dashboard and {len(catalog)} rules. Verify a controlled alert and recovery."
    )
    print(f"Dashboard: {api.url}/d/countyiq-overview")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true")
    action.add_argument("--apply", action="store_true")
    arguments = parser.parse_args()
    try:
        run(apply=arguments.apply)
    except ConfigurationError as error:
        print(f"Grafana provisioning stopped: {error}")
        raise SystemExit(1)
    except Exception as error:
        # Never print API bodies, credentials, or protected contact settings.
        print(f"Grafana provisioning stopped ({type(error).__name__}).")
        raise SystemExit(1)
