"""Credential boundaries and preservation of existing Grafana routes."""

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import configure
from configure import validate_url
from provision import notification_policy, select_datasource, verify_owner


class ProvisioningTests(unittest.TestCase):
    def test_discovery_reads_tenant_ids_from_detailed_datasources(self):
        settings = {
            "GRAFANA_STACK_URL": "https://stack.grafana.net",
            "GRAFANA_PROVISION_TOKEN": "glsa_fixture",
            "GRAFANA_INGEST_TOKEN": "glc_fixture",
        }
        responses = {
            "/api/org/users": [{"email": "jarod.daws@gmail.com"}],
            "/api/datasources": [
                {
                    "uid": "metrics",
                    "name": "grafanacloud-stack-prom",
                    "type": "prometheus",
                },
                {"uid": "logs", "name": "grafanacloud-stack-logs", "type": "loki"},
            ],
            "/api/datasources/uid/metrics": {
                "url": "https://metrics.grafana.net/api/prom",
                "basicAuthUser": "123",
            },
            "/api/datasources/uid/logs": {
                "url": "https://logs.grafana.net",
                "basicAuthUser": "456",
            },
        }
        api = MagicMock()
        api.request.side_effect = lambda method, path: responses[path]
        with (
            patch("configure.read_secrets", return_value=settings),
            patch("provision.Grafana", return_value=api),
            patch("configure.save_secrets") as save,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            configure.resolve()
        saved = save.call_args.args[0]
        self.assertEqual(saved["GRAFANA_METRICS_USER"], "123")
        self.assertEqual(saved["GRAFANA_LOGS_USER"], "456")
        self.assertEqual(saved["GRAFANA_INGEST_TOKEN"], "glc_fixture")

    def test_capture_keeps_encrypted_credentials_when_discovery_fails(self):
        api = MagicMock()
        api.request.return_value = [{"email": "jarod.daws@gmail.com"}]
        encrypted = "GRAFANA_PROVISION_TOKEN=ENC[encrypted-fixture]\n"
        tokens = ["glsa_provision_fixture", "glc_ingestion_fixture"]
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            secret = root / "monitoring.sops.env"
            with (
                patch.object(configure, "ROOT", root),
                patch.object(configure, "SECRET_PATH", secret),
                patch("provision.Grafana", return_value=api),
                patch("configure.getpass.getpass", side_effect=tokens),
                patch(
                    "configure.subprocess.run", return_value=MagicMock(stdout=encrypted)
                ),
                patch("configure.resolve", side_effect=KeyError("basicAuthUser")),
                contextlib.redirect_stdout(output),
            ):
                with self.assertRaises(KeyError):
                    configure.capture()
            self.assertEqual(secret.read_text(), encrypted)
            self.assertEqual(secret.stat().st_mode & 0o777, 0o600)
            for token in tokens:
                self.assertNotIn(token, secret.read_text())
                self.assertNotIn(token, output.getvalue())

    def test_notification_routing_preserves_unrelated_routes(self):
        existing = {
            "receiver": "original",
            "routes": [
                {"receiver": "other", "object_matchers": [["team", "=", "other"]]}
            ],
        }
        updated = notification_policy(existing)
        self.assertEqual(updated["receiver"], "original")
        self.assertEqual(updated["routes"][1], existing["routes"][0])
        self.assertEqual(len(existing["routes"]), 1)
        self.assertEqual(notification_policy(updated), updated)

    def test_daily_coverage_emails_do_not_delay_other_sources_or_outages(self):
        policy = notification_policy({"receiver": "original"})
        county_route = policy["routes"][0]
        coverage_route = county_route["routes"][0]
        for labels, expected_interval in (
            (
                {
                    "alertname": "Source unhealthy or stale",
                    "source": "municipal_proceedings",
                },
                "24h",
            ),
            ({"alertname": "Source unhealthy or stale", "source": "parcels"}, "4h"),
            ({"alertname": "External readiness failed"}, "4h"),
        ):
            matches = all(
                operator == "=" and labels.get(label) == value
                for label, operator, value in coverage_route["object_matchers"]
            )
            selected = coverage_route if matches else county_route
            with self.subTest(labels=labels):
                self.assertEqual(selected["repeat_interval"], expected_interval)
                self.assertEqual(selected["group_interval"], "24h" if matches else "5m")

    def test_service_account_does_not_grant_another_human_access(self):
        owner = {"email": "jarod.daws@protonmail.com"}
        service = {"email": "", "isServiceAccount": True}
        allowed = frozenset((owner["email"], "jarod.daws@gmail.com"))
        verify_owner([owner, service], allowed)
        verify_owner([{"email": "jarod.daws@gmail.com"}, service], allowed)
        verify_owner([owner, {"email": "jarod.daws@gmail.com"}, service], allowed)
        with self.assertRaises(ValueError):
            verify_owner([owner, {"email": "someone@example.com"}], allowed)
        with self.assertRaises(ValueError):
            verify_owner([service], allowed)

    def test_credential_urls_cannot_target_another_provider(self):
        for url in (
            "http://stack.grafana.net",
            "https://stack.grafana.net.attacker.example",
            "https://user:password@stack.grafana.net",
            "https://stack.grafana.net/?token=abc",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_url(url)
        self.assertEqual(
            validate_url("https://stack.grafana.net/", path=""),
            "https://stack.grafana.net",
        )

    def test_usage_datasource_is_not_selected_for_application_metrics(self):
        sources = [
            {"uid": "usage", "type": "prometheus", "name": "grafanacloud-usage"},
            {"uid": "metrics", "type": "prometheus", "name": "grafanacloud-stack-prom"},
        ]
        self.assertEqual(select_datasource(sources, "prometheus"), "metrics")

    def test_cloud_logs_are_selected_over_alert_state_history(self):
        sources = [
            {
                "uid": "alert-history",
                "type": "loki",
                "name": "grafanacloud-countyiq-alert-state-history",
            },
            {
                "uid": "application-logs",
                "type": "loki",
                "name": "grafanacloud-countyiq-logs",
            },
        ]
        self.assertEqual(select_datasource(sources, "loki"), "application-logs")
        sources.append(
            {
                "uid": "another-stack",
                "type": "loki",
                "name": "grafanacloud-another-logs",
            }
        )
        with self.assertRaises(ValueError):
            select_datasource(sources, "loki")


if __name__ == "__main__":
    unittest.main()
