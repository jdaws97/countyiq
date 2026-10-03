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
        self.assertIn("/alerting/list", serialized)
        self.assertEqual("now-6h", dashboard["time"]["from"])
        self.assertEqual("1m", dashboard["refresh"])

    def test_dashboard_panels_have_a_non_overlapping_24_column_layout(self):
        panels = self.load_json("dashboards/countyiq.json")["panels"]
        self.assertGreaterEqual(len(panels), 14)
        self.assertLessEqual(len(panels), 23)

        rectangles = []
        for panel in panels:
            with self.subTest(panel=panel["title"]):
                grid = panel["gridPos"]
                self.assertGreater(grid["w"], 0)
                self.assertGreater(grid["h"], 0)
                self.assertGreaterEqual(grid["x"], 0)
                self.assertGreaterEqual(grid["y"], 0)
                self.assertLessEqual(grid["x"] + grid["w"], 24)
                rectangles.append((panel["id"], grid))

        for index, (left_id, left) in enumerate(rectangles):
            for right_id, right in rectangles[index + 1 :]:
                overlaps = (
                    left["x"] < right["x"] + right["w"]
                    and right["x"] < left["x"] + left["w"]
                    and left["y"] < right["y"] + right["h"]
                    and right["y"] < left["y"] + left["h"]
                )
                self.assertFalse(overlaps, f"panels {left_id} and {right_id} overlap")

    def test_dashboard_current_state_panels_use_instant_queries(self):
        panels = self.load_json("dashboards/countyiq.json")["panels"]
        for panel in panels:
            if panel["type"] in {"stat", "bargauge"}:
                with self.subTest(panel=panel["title"]):
                    self.assertTrue(panel["targets"])
                    self.assertTrue(
                        all(
                            target.get("instant") is True for target in panel["targets"]
                        )
                    )

    def test_dashboard_keeps_incompatible_units_in_separate_panels(self):
        panels = {
            panel["title"]: panel
            for panel in self.load_json("dashboards/countyiq.json")["panels"]
        }

        expected_units = {
            "Root disk free": "gbytes",
            "Host CPU utilization": "percent",
            "Host memory utilization": "percent",
            "PostgreSQL connection capacity": "percent",
            "R2 capacity": "percent",
            "Docker storage": "bytes",
            "Dagster pipeline status counts": "short",
            "Oldest Dagster pipeline run age": "s",
        }
        for title, unit in expected_units.items():
            self.assertEqual(unit, panels[title]["fieldConfig"]["defaults"]["unit"])

        panel_expressions = {
            title: " ".join(target["expr"] for target in panel.get("targets", []))
            for title, panel in panels.items()
        }
        self.assertNotIn(
            "countyiq_postgres_database_bytes",
            panel_expressions["PostgreSQL connection capacity"],
        )
        self.assertNotIn(
            "countyiq_postgres_total_connections", panel_expressions["Docker storage"]
        )
        self.assertNotIn(
            "countyiq_cost_guard_tripped", panel_expressions["R2 capacity"]
        )
        self.assertNotIn(
            "countyiq_dagster_oldest_run_seconds",
            panel_expressions["Dagster pipeline status counts"],
        )
        self.assertNotIn(
            "countyiq_dagster_runs",
            panel_expressions["Oldest Dagster pipeline run age"],
        )

        source_panel = panels["Source status"]
        self.assertEqual("joinByField", source_panel["transformations"][0]["id"])
        self.assertEqual(
            "outerTabular", source_panel["transformations"][0]["options"]["mode"]
        )
        self.assertEqual("organize", source_panel["transformations"][1]["id"])
        self.assertEqual(
            "Health",
            source_panel["transformations"][1]["options"]["renameByName"]["Value #A"],
        )
        self.assertEqual(
            "Freshness",
            source_panel["transformations"][1]["options"]["renameByName"]["Value #B"],
        )

    def test_alert_catalog_has_safe_unique_complete_rules(self):
        alerts = self.load_json("alerts.json")
        uids = [alert["uid"] for alert in alerts]
        self.assertLessEqual(len(alerts), 22)
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
            if panel["type"] not in {"logs", "text"}
            for target in panel.get("targets", [])
        ]
        alerts = self.load_json("alerts.json")
        all_queries = dashboard_queries + [alert["expr"] for alert in alerts]

        for query in all_queries:
            if "probe_success" in query:
                self.assertIn('job="countyiq-readiness"', query)
                self.assertIn('instance="https://app.countyiq.net/api/ready"', query)
                self.assertIn('probe=~"NorthVirginia|Oregon"', query)
            else:
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
            if panel["type"] not in {"logs", "text"}
            for target in panel.get("targets", [])
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
                            "exp_samples": [self.promtool_sample("", 1)],
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
                            "exp_samples": [self.promtool_sample("", 1)],
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

    @unittest.skipUnless(
        os.environ.get("PROMTOOL") or PROMTOOL,
        "promtool is unavailable; set PROMTOOL to run PromQL behavior tests",
    )
    def test_promtool_evaluates_source_attention_dashboard_card(self):
        dashboard = self.load_json("dashboards/countyiq.json")
        attention_expression = next(
            panel["targets"][0]["expr"]
            for panel in dashboard["panels"]
            if panel["title"] == "Source issues"
        )
        root_labels = 'instance="countyiq-production",job="countyiq/host"'

        test_file = {
            "rule_files": [],
            "evaluation_interval": "1m",
            "tests": [
                {
                    "interval": "1m",
                    "input_series": [
                        {
                            "series": f'countyiq_source_healthy{{{root_labels},source="parcels"}}',
                            "values": "1",
                        },
                        {
                            "series": f'countyiq_source_stale{{{root_labels},source="parcels"}}',
                            "values": "0",
                        },
                    ],
                    "promql_expr_test": [
                        {
                            "expr": attention_expression,
                            "eval_time": "0m",
                            "exp_samples": [self.promtool_sample("", 0)],
                        }
                    ],
                },
                {
                    "interval": "1m",
                    "input_series": [
                        {
                            "series": f'countyiq_source_healthy{{{root_labels},source="parcels"}}',
                            "values": "0",
                        },
                        {
                            "series": f'countyiq_source_stale{{{root_labels},source="parcels"}}',
                            "values": "0",
                        },
                        {
                            "series": f'countyiq_source_healthy{{{root_labels},source="permits"}}',
                            "values": "1",
                        },
                        {
                            "series": f'countyiq_source_stale{{{root_labels},source="permits"}}',
                            "values": "1",
                        },
                    ],
                    "promql_expr_test": [
                        {
                            "expr": attention_expression,
                            "eval_time": "0m",
                            "exp_samples": [self.promtool_sample("", 2)],
                        }
                    ],
                },
                {
                    "interval": "1m",
                    "input_series": [],
                    "promql_expr_test": [
                        {
                            "expr": attention_expression,
                            "eval_time": "0m",
                            "exp_samples": [],
                        }
                    ],
                },
            ],
        }

        with tempfile.TemporaryDirectory() as temporary_directory:
            test_path = Path(temporary_directory) / "dashboard-test.json"
            test_path.write_text(json.dumps(test_file), encoding="utf-8")
            self.run_promtool("test", "rules", str(test_path))

    @unittest.skipUnless(
        os.environ.get("PROMTOOL") or PROMTOOL,
        "promtool is unavailable; set PROMTOOL to run PromQL behavior tests",
    )
    def test_promtool_evaluates_r2_capacity_dashboard_panel(self):
        dashboard = self.load_json("dashboards/countyiq.json")
        capacity_expression = next(
            panel["targets"][0]["expr"]
            for panel in dashboard["panels"]
            if panel["title"] == "R2 capacity"
        )
        root_labels = 'instance="countyiq-production",job="countyiq/host"'
        bucket_labels = f'{root_labels},bucket="total"'

        test_file = {
            "rule_files": [],
            "evaluation_interval": "1m",
            "tests": [
                {
                    "interval": "1m",
                    "input_series": [
                        {
                            "series": f"countyiq_r2_bytes{{{bucket_labels}}}",
                            "values": "5368709120",
                        },
                        {
                            "series": f"countyiq_r2_limit_bytes{{{root_labels}}}",
                            "values": "21474836480",
                        },
                    ],
                    "promql_expr_test": [
                        {
                            "expr": capacity_expression,
                            "eval_time": "0m",
                            "exp_samples": [self.promtool_sample(root_labels, 25)],
                        }
                    ],
                },
                {
                    "interval": "1m",
                    "input_series": [
                        {
                            "series": f"countyiq_r2_bytes{{{bucket_labels}}}",
                            "values": "5368709120",
                        }
                    ],
                    "promql_expr_test": [
                        {
                            "expr": capacity_expression,
                            "eval_time": "0m",
                            "exp_samples": [],
                        }
                    ],
                },
            ],
        }

        with tempfile.TemporaryDirectory() as temporary_directory:
            test_path = Path(temporary_directory) / "r2-capacity-test.json"
            test_path.write_text(json.dumps(test_file), encoding="utf-8")
            self.run_promtool("test", "rules", str(test_path))

    @unittest.skipUnless(
        os.environ.get("PROMTOOL") or PROMTOOL,
        "promtool is unavailable; set PROMTOOL to run PromQL behavior tests",
    )
    def test_external_readiness_failure_recovery_and_missing_locations(self):
        alerts = {
            alert["uid"]: alert["expr"] for alert in self.load_json("alerts.json")
        }
        labels = (
            'job="countyiq-readiness",instance="https://app.countyiq.net/api/ready"'
        )
        tests = []
        for probes, missing in (
            (("NorthVirginia", "Oregon"), 0),
            (("NorthVirginia",), 1),
            ((), 1),
        ):
            inputs = [
                {
                    "series": f'probe_success{{{labels},probe="{probe}"}}',
                    "values": "1 0 1",
                }
                for probe in probes
            ]
            # Configuration versions must not count as additional locations.
            if probes == ("NorthVirginia",):
                inputs.append(
                    {
                        "series": f'probe_success{{{labels},probe="NorthVirginia",config_version="old"}}',
                        "values": "1 0 1",
                    }
                )
            expressions = [
                {
                    "expr": alerts["external-readiness-failed"],
                    "eval_time": time,
                    "exp_samples": [
                        self.promtool_sample(f'probe="{probe}"', expected)
                        for probe in probes
                    ],
                }
                for time, expected in (("0m", 0), ("1m", 1), ("2m", 0))
            ]
            expressions.extend(
                [
                    {
                        "expr": alerts["external-readiness-missing"],
                        "eval_time": "2m",
                        "exp_samples": [self.promtool_sample("", missing)],
                    },
                    {
                        "expr": alerts["external-readiness-missing"],
                        "eval_time": "18m",
                        "exp_samples": [self.promtool_sample("", 1)],
                    },
                ]
            )
            tests.append(
                {
                    "interval": "1m",
                    "input_series": inputs,
                    "promql_expr_test": expressions,
                }
            )
        with tempfile.TemporaryDirectory() as temporary_directory:
            test_path = Path(temporary_directory) / "external-test.json"
            test_path.write_text(
                json.dumps({"rule_files": [], "tests": tests}), encoding="utf-8"
            )
            self.run_promtool("test", "rules", str(test_path))

    @unittest.skipUnless(
        os.environ.get("PROMTOOL") or PROMTOOL,
        "promtool is unavailable; set PROMTOOL to run PromQL behavior tests",
    )
    def test_r2_guard_and_capacity_alert_independently(self):
        alerts = {alert["uid"]: alert for alert in self.load_json("alerts.json")}
        expression = alerts["r2-capacity-or-guard"]["expr"]
        cases = (
            (None, 100, 1, 1),
            (25, None, 1, 1),
            (None, None, 1, 1),
            (90, 100, None, 1),
            (25, 100, 1, 1),
            (90, 100, 0, 1),
            (25, 100, 0, 0),
            (25, 100, None, 0),
            (None, None, 0, 0),
            (None, None, None, 0),
        )
        tests = []
        for used_bytes, limit_bytes, guard_tripped, expected in cases:
            inputs = []
            for metric, labels, value in (
                ("countyiq_r2_bytes", f'{HOST_SELECTOR},bucket="total"', used_bytes),
                ("countyiq_r2_limit_bytes", HOST_SELECTOR, limit_bytes),
                ("countyiq_cost_guard_tripped", HOST_SELECTOR, guard_tripped),
            ):
                if value is not None:
                    inputs.append(
                        {"series": f"{metric}{{{labels}}}", "values": str(value)}
                    )
            tests.append(
                {
                    "interval": "1m",
                    "input_series": inputs,
                    "promql_expr_test": [
                        {
                            "expr": expression,
                            "eval_time": "0m",
                            "exp_samples": [self.promtool_sample("", expected)],
                        }
                    ],
                }
            )

        with tempfile.TemporaryDirectory() as directory:
            test_path = Path(directory) / "r2-independent-conditions.json"
            test_path.write_text(
                json.dumps({"rule_files": [], "tests": tests}), encoding="utf-8"
            )
            self.run_promtool("test", "rules", str(test_path))

    @unittest.skipUnless(
        os.environ.get("PROMTOOL") or PROMTOOL,
        "promtool is unavailable; set PROMTOOL to run PromQL behavior tests",
    )
    def test_host_outage_timing_and_identity_survive_missing_scrapes(self):
        alert = next(
            rule
            for rule in self.load_json("alerts.json")
            if rule["uid"] == "host-telemetry-missing"
        )
        histories = (
            ["1"] + ["_"] * 19 + ["1"],
            ["1"] + ["0"] * 19 + ["1"],
            ["1"] + ["0"] * 5 + ["stale"] + ["_"] * 13 + ["1"],
        )
        checkpoints = (("9m", 0), ("10m", 1), ("19m", 1), ("20m", 0))
        tests = []
        for history in histories:
            tests.append(
                {
                    "interval": "1m",
                    "input_series": [
                        {
                            "series": f"up{{{HOST_SELECTOR}}}",
                            "values": " ".join(history),
                        }
                    ],
                    "promql_expr_test": [
                        {
                            "expr": alert["expr"],
                            "eval_time": at,
                            "exp_samples": [self.promtool_sample("", expected)],
                        }
                        for at, expected in checkpoints
                    ],
                    "alert_rule_test": [
                        {
                            "alertname": "HostTelemetryMissing",
                            "eval_time": at,
                            "exp_alerts": [{"exp_labels": {}, "exp_annotations": {}}]
                            if expected
                            else [],
                        }
                        for at, expected in checkpoints
                    ],
                }
            )

        with tempfile.TemporaryDirectory() as directory:
            rules_path = Path(directory) / "host-rules.json"
            rules_path.write_text(
                json.dumps(
                    {
                        "groups": [
                            {
                                "name": "host-outage",
                                "interval": "1m",
                                "rules": [
                                    {
                                        "alert": "HostTelemetryMissing",
                                        # Grafana's C threshold fires only above zero.
                                        "expr": f"({alert['expr']}) > 0",
                                        "for": alert["for"],
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            test_path = Path(directory) / "host-outage.json"
            test_path.write_text(
                json.dumps(
                    {
                        "rule_files": [str(rules_path)],
                        "evaluation_interval": "1m",
                        "tests": tests,
                    }
                ),
                encoding="utf-8",
            )
            self.run_promtool("test", "rules", str(test_path))

    def run_promtool(self, *arguments: str):
        promtool = os.environ.get("PROMTOOL") or PROMTOOL
        completed = subprocess.run(
            [promtool, *arguments],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            completed.returncode,
            0,
            f"promtool {' '.join(arguments)} failed:\n{completed.stdout}\n{completed.stderr}",
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

    @staticmethod
    def promtool_sample(labels: str, value: int):
        return {"labels": f"{{{labels}}}", "value": value}


if __name__ == "__main__":
    unittest.main()
