"""Validation for static Grafana monitoring assets."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ASSET_ROOT = Path(__file__).resolve().parents[1]
HOST_SELECTOR = 'instance="countyiq-production",job="countyiq/host"'
FORBIDDEN_TERMS = ("password", "secret", "token", "api_key", "pidn", "run_id")
PROMTOOL = shutil.which("promtool")
REQUIRED_COLLECTORS = (
    "containers",
    "dagster",
    "caddy",
    "postgres",
    "sources",
    "recovery",
    "openrouter",
    "storage",
)


class DashboardAssetTests(unittest.TestCase):
    def load_json(self, name: str):
        with (ASSET_ROOT / name).open(encoding="utf-8") as asset_file:
            return json.load(asset_file)

    def test_dashboard_has_unique_panel_ids_and_required_data_sources(self):
        dashboard = self.load_json("dashboards/countyiq.json")
        panels = dashboard["panels"]
        panel_ids = [panel["id"] for panel in panels]
        self.assertEqual(len(panel_ids), len(set(panel_ids)))

        serialized = json.dumps(dashboard)
        log_query = next(
            panel["targets"][0]["expr"] for panel in panels if panel["type"] == "logs"
        )
        self.assertIn("${METRICS_UID}", serialized)
        self.assertIn("${LOGS_UID}", serialized)
        self.assertEqual('{job="countyiq/containers"}', log_query)
        self.assertIn("https://dagster.countyiq.net", serialized)
        self.assertIn("https://app.countyiq.net/ops/health", serialized)

    def test_alert_catalog_has_safe_unique_complete_rules(self):
        alerts = self.load_json("alerts.json")
        uids = [alert["uid"] for alert in alerts]
        self.assertLessEqual(len(alerts), 20)
        self.assertEqual(len(uids), len(set(uids)))

        for alert in alerts:
            with self.subTest(uid=alert["uid"]):
                self.assertLessEqual(len(alert["uid"]), 40)
                self.assertTrue(alert["expr"].strip())
                self.assertIn("bool", alert["expr"])
                self.assertTrue(alert["for"])
                self.assertIn(alert["severity"], {"warning", "critical"})
                self.assertTrue(alert["summary"].strip())
                self.assertTrue(alert["description"].strip())
                self.assertNotIn("=~'.*'", alert["expr"])
                self.assertNotIn('=~".*"', alert["expr"])
                self.assertFalse(
                    any(term in alert["expr"].lower() for term in FORBIDDEN_TERMS)
                )

    def test_prometheus_queries_use_the_static_host_selector(self):
        dashboard = self.load_json("dashboards/countyiq.json")
        dashboard_queries = [
            target["expr"]
            for panel in dashboard["panels"]
            if panel["type"] != "logs"
            for target in panel["targets"]
        ]
        alerts = self.load_json("alerts.json")
        all_queries = dashboard_queries + [alert["expr"] for alert in alerts]

        for query in all_queries:
            self.assertIn(HOST_SELECTOR, query)

    def test_alerts_preserve_true_conditions_when_combined(self):
        alerts = {
            alert["uid"]: alert["expr"] for alert in self.load_json("alerts.json")
        }

        for uid in (
            "collector-failed-or-stale",
            "container-unhealthy",
            "container-restart-or-oom",
            "backup-missing-or-failed",
            "r2-capacity-or-guard",
            "source-unhealthy-or-stale",
            "postgres-capacity-or-blocking",
        ):
            self.assertIn(
                ") > bool 0",
                alerts[uid],
                f"{uid} must turn its combined state into 1/0",
            )

        self.assertIn(
            'collector=~"containers|dagster|caddy|postgres|sources|recovery|openrouter|storage"',
            alerts["collector-failed-or-stale"],
        )
        self.assertIn(
            "count(countyiq_monitor_collector_success",
            alerts["collector-failed-or-stale"],
        )
        self.assertIn(
            "count(countyiq_monitor_last_attempt_timestamp_seconds",
            alerts["collector-failed-or-stale"],
        )
        self.assertIn("scalar(up", alerts["collector-failed-or-stale"])
        self.assertIn('collector="storage"', alerts["docker-storage-stale"])
        self.assertIn(
            "max_over_time(countyiq_container_oom_killed",
            alerts["container-restart-or-oom"],
        )
        self.assertIn("ignoring(bucket)", alerts["r2-capacity-or-guard"])
        self.assertIn("group_left", alerts["source-unhealthy-or-stale"])
        self.assertIn('collector="sources"', alerts["source-unhealthy-or-stale"])

    def test_filesystem_rules_are_root_only_and_forecast_has_evidence(self):
        alerts = {
            alert["uid"]: alert["expr"] for alert in self.load_json("alerts.json")
        }

        for uid in (
            "filesystem-warning",
            "filesystem-critical",
            "filesystem-low-free-space",
            "filesystem-predicted-full",
        ):
            self.assertIn('mountpoint="/"', alerts[uid])

        forecast = alerts["filesystem-predicted-full"]
        self.assertIn(">= bool 300", forecast)
        self.assertIn("time() - 18000", forecast)
        self.assertIn("*", forecast)

    @unittest.skipUnless(
        os.environ.get("PROMTOOL") or PROMTOOL,
        "promtool is unavailable; set PROMTOOL to run PromQL parser and behavior tests",
    )
    def test_promtool_parses_every_prometheus_query(self):
        dashboard = self.load_json("dashboards/countyiq.json")
        alerts = self.load_json("alerts.json")
        dashboard_rules = [
            {
                "record": f"countyiq_test_dashboard_{panel['id']}_{target['refId'].lower()}",
                "expr": target["expr"],
            }
            for panel in dashboard["panels"]
            if panel["type"] != "logs"
            for target in panel["targets"]
        ]
        alert_rules = [
            {"alert": alert["uid"], "expr": alert["expr"], "for": "0m"}
            for alert in alerts
        ]
        rules = {
            "groups": [
                {"name": "countyiq-dashboard-queries", "rules": dashboard_rules},
                {"name": "countyiq-alert-queries", "rules": alert_rules},
            ]
        }

        with tempfile.TemporaryDirectory() as temporary_directory:
            rules_path = Path(temporary_directory) / "rules.json"
            rules_path.write_text(json.dumps(rules), encoding="utf-8")
            self.run_promtool("check", "rules", str(rules_path))

    @unittest.skipUnless(
        os.environ.get("PROMTOOL") or PROMTOOL,
        "promtool is unavailable; set PROMTOOL to run PromQL behavior tests",
    )
    def test_promtool_evaluates_representative_alert_cases(self):
        alerts = {
            alert["uid"]: alert["expr"] for alert in self.load_json("alerts.json")
        }
        host_expression = alerts["host-telemetry-missing"]
        root_labels = 'instance="countyiq-production",job="countyiq/host"'
        source_labels = f'{root_labels},source="assessment"'
        service_labels = f'{root_labels},service="api"'
        r2_labels = f'{root_labels},bucket="total"'
        filesystem_labels = f'{root_labels},mountpoint="/"'
        hour_of_filesystem_samples = " ".join(["107374182400"] * 61)
        healthy_collector_inputs = self.collector_inputs(
            root_labels,
            REQUIRED_COLLECTORS,
            success="1",
            last_attempt="60",
        )
        failed_collector_inputs = self.collector_inputs(
            root_labels,
            REQUIRED_COLLECTORS,
            success="0",
            last_attempt="60",
        )
        missing_storage_inputs = self.collector_inputs(
            root_labels,
            REQUIRED_COLLECTORS[:-1],
            success="1",
            last_attempt="60",
        )

        test_file = {
            "rule_files": [],
            "evaluation_interval": "1m",
            "tests": [
                {
                    "interval": "1m",
                    "input_series": [
                        {
                            "series": f'countyiq_dagster_runs{{{root_labels},status="QUEUED"}}',
                            "values": "1 1 0",
                        },
                        {
                            "series": f'countyiq_dagster_oldest_run_seconds{{{root_labels},status="QUEUED"}}',
                            "values": "60 1801 0",
                        },
                    ],
                    "promql_expr_test": [
                        {
                            "expr": alerts["dagster-queue-delayed"],
                            "eval_time": evaluation_time,
                            "exp_samples": [
                                self.promtool_sample(
                                    f'{root_labels},status="QUEUED"', expected
                                )
                            ],
                        }
                        for evaluation_time, expected in (
                            ("0m", 0),
                            ("1m", 1),
                            ("2m", 0),
                        )
                    ],
                },
                {
                    "interval": "1m",
                    "input_series": [
                        {"series": f"up{{{root_labels}}}", "values": "1"},
                        *failed_collector_inputs,
                    ],
                    "promql_expr_test": [
                        {
                            "expr": alerts["collector-failed-or-stale"],
                            "eval_time": "1m",
                            "exp_samples": [self.promtool_sample("", 1)],
                        }
                    ],
                },
                {
                    "interval": "1m",
                    "input_series": [
                        {"series": f"up{{{root_labels}}}", "values": "1"},
                        *missing_storage_inputs,
                    ],
                    "promql_expr_test": [
                        {
                            "expr": alerts["collector-failed-or-stale"],
                            "eval_time": "1m",
                            "exp_samples": [self.promtool_sample("", 1)],
                        }
                    ],
                },
                {
                    "interval": "1m",
                    "input_series": [{"series": f"up{{{root_labels}}}", "values": "1"}],
                    "promql_expr_test": [
                        {
                            "expr": alerts["collector-failed-or-stale"],
                            "eval_time": "1m",
                            "exp_samples": [self.promtool_sample("", 1)],
                        }
                    ],
                },
                {
                    "interval": "1m",
                    "input_series": [
                        {"series": f"up{{{root_labels}}}", "values": "1"},
                        *healthy_collector_inputs,
                    ],
                    "promql_expr_test": [
                        {
                            "expr": alerts["collector-failed-or-stale"],
                            "eval_time": "1m",
                            "exp_samples": [self.promtool_sample("", 0)],
                        }
                    ],
                },
                {
                    "interval": "1m",
                    "input_series": [
                        {
                            "series": f"countyiq_container_running{{{service_labels}}}",
                            "values": "1",
                        },
                        {
                            "series": f"countyiq_container_healthy{{{service_labels}}}",
                            "values": "0",
                        },
                    ],
                    "promql_expr_test": [
                        {
                            "expr": alerts["container-unhealthy"],
                            "eval_time": "0m",
                            "exp_samples": [self.promtool_sample(service_labels, 1)],
                        }
                    ],
                },
                {
                    "interval": "1m",
                    "input_series": [
                        {
                            "series": f"countyiq_backup_last_success_timestamp_seconds{{{root_labels}}}",
                            "values": "60",
                        },
                        {
                            "series": f"countyiq_backup_last_exit_success{{{root_labels}}}",
                            "values": "0",
                        },
                        {
                            "series": f"countyiq_backup_timer_active{{{root_labels}}}",
                            "values": "1",
                        },
                    ],
                    "promql_expr_test": [
                        {
                            "expr": alerts["backup-missing-or-failed"],
                            "eval_time": "1m",
                            "exp_samples": [self.promtool_sample(root_labels, 1)],
                        }
                    ],
                },
                {
                    "interval": "1m",
                    "input_series": [
                        {"series": f"countyiq_r2_bytes{{{r2_labels}}}", "values": "90"},
                        {
                            "series": f"countyiq_r2_limit_bytes{{{root_labels}}}",
                            "values": "100",
                        },
                        {
                            "series": f"countyiq_cost_guard_tripped{{{root_labels}}}",
                            "values": "0",
                        },
                    ],
                    "promql_expr_test": [
                        {
                            "expr": alerts["r2-capacity-or-guard"],
                            "eval_time": "0m",
                            "exp_samples": [self.promtool_sample(root_labels, 1)],
                        }
                    ],
                },
                {
                    "interval": "1m",
                    "input_series": [
                        {
                            "series": f"countyiq_source_healthy{{{source_labels}}}",
                            "values": "1",
                        },
                        {
                            "series": f"countyiq_source_stale{{{source_labels}}}",
                            "values": "1",
                        },
                        {
                            "series": f'countyiq_monitor_collector_success{{{root_labels},collector="sources"}}',
                            "values": "0",
                        },
                    ],
                    "promql_expr_test": [
                        {
                            "expr": alerts["source-unhealthy-or-stale"],
                            "eval_time": "0m",
                            "exp_samples": [self.promtool_sample(source_labels, 0)],
                        }
                    ],
                },
                {
                    "interval": "1m",
                    "input_series": [],
                    "promql_expr_test": [
                        {
                            "expr": host_expression,
                            "eval_time": "10m",
                            "exp_samples": [self.promtool_sample(root_labels, 1)],
                        }
                    ],
                },
                {
                    "interval": "1m",
                    "input_series": [
                        {"series": f"up{{{root_labels}}}", "values": "1x11"}
                    ],
                    "promql_expr_test": [
                        {
                            "expr": host_expression,
                            "eval_time": "10m",
                            "exp_samples": [self.promtool_sample("", 0)],
                        }
                    ],
                },
                {
                    "interval": "1m",
                    "input_series": [
                        {"series": f"up{{{root_labels}}}", "values": "0x11"}
                    ],
                    "promql_expr_test": [
                        {
                            "expr": host_expression,
                            "eval_time": "10m",
                            "exp_samples": [self.promtool_sample("", 1)],
                        }
                    ],
                },
                {
                    "interval": "1m",
                    "input_series": [
                        {
                            "series": f"node_filesystem_avail_bytes{{{filesystem_labels}}}",
                            "values": hour_of_filesystem_samples,
                        }
                    ],
                    "promql_expr_test": [
                        {
                            "expr": alerts["filesystem-predicted-full"],
                            "eval_time": "1h",
                            "exp_samples": [self.promtool_sample(filesystem_labels, 0)],
                        }
                    ],
                },
                {
                    "interval": "1m",
                    "input_series": [
                        {
                            "series": f"countyiq_postgres_total_connections{{{root_labels}}}",
                            "values": "10",
                        },
                        {
                            "series": f"countyiq_postgres_connection_limit{{{root_labels}}}",
                            "values": "100",
                        },
                        {
                            "series": f"countyiq_postgres_blocked_sessions{{{root_labels}}}",
                            "values": "1",
                        },
                    ],
                    "promql_expr_test": [
                        {
                            "expr": alerts["postgres-capacity-or-blocking"],
                            "eval_time": "0m",
                            "exp_samples": [self.promtool_sample(root_labels, 1)],
                        }
                    ],
                },
            ],
        }

        with tempfile.TemporaryDirectory() as temporary_directory:
            test_path = Path(temporary_directory) / "test.json"
            test_path.write_text(json.dumps(test_file), encoding="utf-8")
            self.run_promtool("test", "rules", str(test_path))

    def run_promtool(self, *arguments: str):
        promtool = os.environ.get("PROMTOOL") or PROMTOOL
        completed = subprocess.run(
            [promtool, *arguments],
            check=False,
            capture_output=True,
            text=True,
        )

    @staticmethod
    def collector_inputs(
        root_labels: str,
        collectors: tuple[str, ...],
        *,
        success: str,
        last_attempt: str,
    ):
        return [
            {
                "series": f'countyiq_monitor_collector_success{{{root_labels},collector="{collector}"}}',
                "values": success,
            }
            for collector in collectors
        ] + [
            {
                "series": f'countyiq_monitor_last_attempt_timestamp_seconds{{{root_labels},collector="{collector}"}}',
                "values": last_attempt,
            }
            for collector in collectors
        ]
        self.assertEqual(
            completed.returncode,
            0,
            f"promtool {' '.join(arguments)} failed:\n{completed.stdout}\n{completed.stderr}",
        )

    @staticmethod
    def promtool_sample(labels: str, value: int):
        return {"labels": f"{{{labels}}}", "value": value}


if __name__ == "__main__":
    unittest.main()
