"""Failure, missing-service, and privacy behavior of operational probes."""

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("collect", ROOT / "collect.py")
collect = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collect)


class CollectorTests(unittest.TestCase):
    def test_failure_discards_partial_values_and_does_not_leak_exception(self):
        def broken_probe(metrics):
            metrics.add("partial_result", 42)
            raise ValueError("secret-database-password")

        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with patch.dict(collect.COLLECTORS, {"broken": broken_probe}):
                with contextlib.redirect_stdout(output):
                    self.assertFalse(collect.run_collector("broken", Path(directory)))
            published = (Path(directory) / "broken.prom").read_text()
            self.assertNotIn("partial_result", published)
            self.assertNotIn("secret-database-password", output.getvalue() + published)
            self.assertIn(
                'countyiq_monitor_collector_success{collector="broken"} 0', published
            )
            self.assertIn("monitor_last_attempt_timestamp_seconds", published)

    def test_missing_service_is_explicitly_unhealthy(self):
        def fake_command(arguments, **kwargs):
            if arguments[1] == "ps":
                return "countyiq-api\n"
            if arguments[1] == "inspect":
                return json.dumps(
                    {
                        "name": "/countyiq-api",
                        "running": True,
                        "health": "healthy",
                        "pid": 123,
                    }
                )
            return json.dumps(
                {"Name": "countyiq-api", "MemUsage": "12MiB / 1GiB", "CPUPerc": "2.5%"}
            )

        metrics = collect.Metrics()
        with (
            patch.object(collect, "command", side_effect=fake_command),
            patch.object(collect, "oom_kill_count", return_value=0),
        ):
            with patch.object(collect, "atomic_write"):
                collect.collect_containers(metrics)
        self.assertIn('countyiq_container_healthy{service="api"} 1', metrics.render())
        self.assertIn(
            'countyiq_container_running{service="postgres"} 0', metrics.render()
        )

    def test_tripped_guard_is_exported_when_capacity_receipt_is_incomplete(self):
        def fake_command(arguments, **kwargs):
            if arguments[0] == "journalctl":
                return ""
            if "countyiq-backup.timer" in arguments:
                return "active\n"
            return "ExecMainStatus=0\nResult=success\n"

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            guard = base / "cost-guard"
            guard.mkdir()
            (guard / "status.env").write_text(
                "checked_at=2026-10-03T12:00:00Z\n", encoding="utf-8"
            )
            (guard / "tripped").touch()
            metrics_dir = base / "metrics"
            with patch.object(collect, "BASE_DIR", base):
                with patch.object(collect, "command", side_effect=fake_command):
                    self.assertTrue(collect.run_collector("recovery", metrics_dir))
            rendered = (metrics_dir / "recovery.prom").read_text()
        self.assertIn("countyiq_cost_guard_tripped 1\n", rendered)
        self.assertNotIn("countyiq_r2_bytes", rendered)
        self.assertNotIn("countyiq_r2_limit_bytes", rendered)
        self.assertIn(
            'countyiq_monitor_collector_success{collector="recovery"} 1\n', rendered
        )

    def test_oom_kill_counter_reads_cgroup_v2_events(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            process = root / "proc" / "123"
            events = root / "cgroup" / "system.slice" / "container" / "memory.events"
            process.mkdir(parents=True)
            events.parent.mkdir(parents=True)
            (process / "cgroup").write_text("0::/system.slice/container\n")
            events.write_text("low 0\noom 2\noom_kill 3\n")

            self.assertEqual(
                collect.oom_kill_count(
                    123,
                    proc_root=root / "proc",
                    cgroup_root=root / "cgroup",
                ),
                3,
            )

    def test_oom_kill_counter_rejects_missing_cgroup_v2_value(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            process = root / "proc" / "123"
            events = root / "cgroup" / "system.slice" / "container" / "memory.events"
            process.mkdir(parents=True)
            events.parent.mkdir(parents=True)
            (process / "cgroup").write_text("0::/system.slice/container\n")
            events.write_text("oom 2\n")

            with self.assertRaises(ValueError):
                collect.oom_kill_count(
                    123,
                    proc_root=root / "proc",
                    cgroup_root=root / "cgroup",
                )

    def test_stopped_container_omits_oom_counter_until_it_is_running(self):
        def fake_command(arguments, **kwargs):
            if arguments[1] == "ps":
                return "countyiq-api\n"
            if arguments[1] == "inspect":
                return json.dumps(
                    {"name": "/countyiq-api", "running": False, "health": "none"}
                )
            return json.dumps(
                {"Name": "countyiq-api", "MemUsage": "0B / 1GiB", "CPUPerc": "0%"}
            )

        metrics = collect.Metrics()
        with patch.object(collect, "command", side_effect=fake_command):
            with patch.object(collect, "atomic_write"):
                collect.collect_containers(metrics)
        self.assertNotIn("container_oom_kills_total", metrics.render())

    def test_oom_alert_uses_counter_increases_and_not_sticky_inspect_state(self):
        alerts = json.loads((ROOT / "alerts.json").read_text())
        alert = next(
            item for item in alerts if item["uid"] == "container-restart-or-oom"
        )
        self.assertIn("increase(countyiq_container_oom_kills_total", alert["expr"])
        self.assertNotIn("container_oom_killed", alert["expr"])

    def test_size_parser_distinguishes_decimal_and_binary_units(self):
        self.assertEqual(collect.size_bytes("1.5 GB"), 1_500_000_000)
        self.assertEqual(collect.size_bytes("1.5GiB"), 1.5 * 1024**3)
        self.assertEqual(collect.size_bytes("0B"), 0)
        with self.assertRaises(ValueError):
            collect.size_bytes("unknown")

    def test_metric_labels_cannot_inject_additional_series(self):
        metrics = collect.Metrics()
        metrics.add("example", 1, source='name"\ninjected_metric 42')
        self.assertEqual(len(metrics.render().splitlines()), 1)
        self.assertIn('name\\"\\ninjected_metric 42', metrics.render())
        with self.assertRaises(ValueError):
            metrics.add("example", float("nan"))

    def test_untrusted_log_paths_do_not_become_alloy_targets(self):
        def fake_command(arguments, **kwargs):
            if arguments[1] == "ps":
                return "countyiq-api\n"
            return json.dumps(
                {
                    "name": "/countyiq-api",
                    "running": False,
                    "log_path": "/etc/countyiq/production.env",
                }
            )

        with patch.object(collect, "command", side_effect=fake_command):
            with patch.object(collect, "atomic_write") as writer:
                collect.collect_containers(collect.Metrics())
        self.assertEqual(json.loads(writer.call_args.args[1]), [])


if __name__ == "__main__":
    unittest.main()
