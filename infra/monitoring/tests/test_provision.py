"""Credential boundaries and preservation of existing Grafana routes."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configure import validate_url
from provision import notification_policy, select_datasource, verify_owner


class ProvisioningTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
