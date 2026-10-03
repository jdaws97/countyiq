"""Contracts between API health, container probes, and exported metrics."""

import importlib.util
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


probes = load_module("monitoring_probes", ROOT / "probes.py")
collect = load_module("monitoring_collect", ROOT / "collect.py")


class SourceProbeTests(unittest.TestCase):
    def setUp(self):
        self.database = ModuleType("api.lib.database")
        self.database._connection_kwargs = Mock(return_value={})
        self.database.close_pool = Mock()
        self.ops = ModuleType("api.routes.ops")
        self.ops._compute_health = Mock()
        api = ModuleType("api")
        api_lib = ModuleType("api.lib")
        api_lib.database = self.database
        api_routes = ModuleType("api.routes")
        api_routes.ops = self.ops
        api.lib = api_lib
        api.routes = api_routes
        self.modules = {
            "api": api,
            "api.lib": api_lib,
            "api.lib.database": self.database,
            "api.routes": api_routes,
            "api.routes.ops": self.ops,
        }

    def test_api_record_counts_reach_metrics_without_inventing_unknown_counts(self):
        last_success = datetime(2026, 10, 3, tzinfo=UTC)
        self.ops._compute_health.return_value = {
            "sources": {
                "parcels": {
                    "status": "green",
                    "record_count": 42,
                    "last_success_at": last_success,
                },
                "zoning": {"status": "red", "record_count": 0, "stale": True},
                "unknown": {"status": "red"},
            },
            "intelligence_integrity": {"status": "green"},
        }
        with patch.dict(sys.modules, self.modules):
            health = probes.source_health()
        self.database.close_pool.assert_called_once()
        self.assertIn(
            "default_transaction_read_only=on",
            self.database._connection_kwargs()["options"],
        )

        metrics = collect.Metrics()
        with patch.object(collect, "container_probe", return_value=health):
            collect.collect_sources(metrics)
        rendered = metrics.render()
        self.assertIn('countyiq_source_records{source="parcels"} 42\n', rendered)
        self.assertIn('countyiq_source_records{source="zoning"} 0\n', rendered)
        self.assertNotIn('countyiq_source_records{source="unknown"}', rendered)
        self.assertIn('countyiq_source_stale{source="zoning"} 1\n', rendered)
        self.assertEqual(
            health["sources"]["parcels"]["last_success"], last_success.timestamp()
        )

    def test_api_failure_still_closes_the_probe_connection_pool(self):
        self.ops._compute_health.side_effect = RuntimeError("health unavailable")
        with patch.dict(sys.modules, self.modules):
            with self.assertRaisesRegex(RuntimeError, "health unavailable"):
                probes.source_health()
        self.database.close_pool.assert_called_once()


if __name__ == "__main__":
    unittest.main()
