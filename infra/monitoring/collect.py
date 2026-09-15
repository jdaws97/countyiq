"""Collect bounded operational metrics into node-exporter textfiles.

The short-lived root service can inspect Docker and protected recovery receipts.
The long-lived Alloy process does not receive a Docker socket or DB credentials.
Subprocess output is captured; failures publish a health metric, never secrets.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import tempfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path

SERVICES = (
    "postgres",
    "api",
    "dagster-webserver",
    "dagster-daemon",
    "caddy",
    "cloudflared",
)
BASE_DIR = Path("/var/lib/countyiq")
METRICS_DIR = BASE_DIR / "monitoring" / "metrics"
PROBE_FILE = Path(__file__).with_name("probes.py")
CGROUP_ROOT = Path("/sys/fs/cgroup")

POSTGRES_QUERY = """
BEGIN READ ONLY;
SET LOCAL statement_timeout = '8s';
SELECT json_build_object(
    'databases', (
        SELECT json_agg(json_build_object(
            'name', datname,
            'bytes', pg_database_size(datname),
            'connections', numbackends,
            'deadlocks', deadlocks,
            'temp_bytes', temp_bytes
        ))
        FROM pg_stat_database
        WHERE datname IN ('countyiq', 'dagster')
    ),
    'connection_limit', current_setting('max_connections')::integer,
    'connections', (SELECT count(*) FROM pg_stat_activity),
    'blocked_sessions', (
        SELECT count(*) FROM pg_stat_activity
        WHERE cardinality(pg_blocking_pids(pid)) > 0
    ),
    'oldest_transaction_seconds', (
        SELECT coalesce(max(extract(epoch FROM now() - xact_start)), 0)
        FROM pg_stat_activity
        WHERE pid <> pg_backend_pid() AND xact_start IS NOT NULL
    )
);
COMMIT;
"""


def command(arguments: list[str], *, timeout: int = 25, input_text=None) -> str:
    result = subprocess.run(
        arguments,
        input=input_text,
        text=True,
        capture_output=True,
        check=True,
        timeout=timeout,
        env={**os.environ, "LC_ALL": "C", "TZ": "UTC"},
    )
    return result.stdout


def atomic_write(path: Path, contents: str, *, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as output:
            output.write(contents)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def read_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values = {}
    for line in path.read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", 1)
            values[name] = value.strip().strip("\"'")
    return values


def timestamp(value: str | None) -> float:
    if not value:
        return 0
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def size_bytes(value: str) -> float:
    match = re.fullmatch(r"\s*([0-9.]+)\s*([kKMGTPE]?i?B)\s*", value)
    if not match:
        raise ValueError("Unrecognized Docker size")
    number, unit = match.groups()
    exponent = "BKMGTPE".index(unit[0].upper())
    base = 1024 if "i" in unit else 1000
    return float(number) * base**exponent


def oom_kill_count(
    pid: int,
    *,
    proc_root: Path = Path("/proc"),
    cgroup_root: Path = CGROUP_ROOT,
) -> int:
    """Read the cgroup-v2 OOM-kill counter for a running container process."""
    relative_path = None
    for line in (proc_root / str(pid) / "cgroup").read_text().splitlines():
        hierarchy, controllers, path = line.split(":", 2)
        if hierarchy == "0" and controllers == "":
            relative_path = path
            break
    if relative_path is None or not relative_path.startswith("/"):
        raise ValueError("Running container does not have a cgroup-v2 path")

    events_path = cgroup_root / relative_path.lstrip("/") / "memory.events"
    for line in events_path.read_text().splitlines():
        name, value = line.split(maxsplit=1)
        if name == "oom_kill" and value.isdecimal():
            return int(value)
    raise ValueError("Container cgroup does not expose an OOM-kill counter")


class Metrics:
    def __init__(self):
        self.lines: list[str] = []

    def add(self, name: str, value, **labels: str) -> None:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Non-finite monitoring value")
        suffix = ""
        if labels:
            pairs = []
            for key, label in sorted(labels.items()):
                escaped = str(label).replace("\\", "\\\\")
                escaped = escaped.replace("\n", "\\n").replace('"', '\\"')
                pairs.append(f'{key}="{escaped}"')
            suffix = "{" + ",".join(pairs) + "}"
        self.lines.append(f"countyiq_{name}{suffix} {number:.12g}\n")

    def render(self) -> str:
        return "".join(self.lines)


def collect_containers(metrics: Metrics) -> None:
    template = (
        '{"name":{{json .Name}},"running":{{.State.Running}},'
        '"health":{{if .State.Health}}{{json .State.Health.Status}}'
        '{{else}}"none"{{end}},"oom":{{.State.OOMKilled}},'
        '"pid":{{.State.Pid}},"restarts":{{.RestartCount}},'
        '"memory_limit":{{.HostConfig.Memory}},'
        '"log_path":{{json .LogPath}}}'
    )
    names = command(["docker", "ps", "-a", "--format", "{{.Names}}"])
    present = set(names.splitlines())
    expected = [f"countyiq-{service}" for service in SERVICES]
    inspect_names = [name for name in expected if name in present]
    objects = {}
    if inspect_names:
        output = command(["docker", "inspect", "--format", template, *inspect_names])
        objects = {
            item["name"].removeprefix("/countyiq-"): item
            for item in map(json.loads, output.splitlines())
        }
    log_targets = []
    for service in SERVICES:
        item = objects.get(service, {})
        running = bool(item.get("running", False))
        metrics.add("container_running", running, service=service)
        metrics.add(
            "container_healthy",
            running and item.get("health") in ("healthy", "none"),
            service=service,
        )
        if running:
            pid = item.get("pid")
            if not isinstance(pid, int) or pid < 1:
                raise ValueError("Running container does not expose a valid PID")
            metrics.add(
                "container_oom_kills_total", oom_kill_count(pid), service=service
            )
        metrics.add(
            "container_restarts_total", item.get("restarts", 0), service=service
        )
        metrics.add(
            "container_memory_limit_bytes", item.get("memory_limit", 0), service=service
        )
        log_path = item.get("log_path", "")
        if re.fullmatch(
            r"/var/lib/docker/containers/[a-f0-9]{64}/[a-f0-9]{64}-json.log", log_path
        ):
            log_targets.append(
                {"__path__": log_path, "service": service, "job": "countyiq/containers"}
            )
    running_names = [
        f"countyiq-{name}" for name, item in objects.items() if item["running"]
    ]
    if running_names:
        output = command(
            ["docker", "stats", "--no-stream", "--format", "{{json .}}", *running_names]
        )
        for item in map(json.loads, output.splitlines()):
            service = item["Name"].removeprefix("countyiq-")
            memory = size_bytes(item["MemUsage"].split("/")[0])
            metrics.add("container_memory_bytes", memory, service=service)
            metrics.add(
                "container_cpu_cores",
                float(item["CPUPerc"].rstrip("%")) / 100,
                service=service,
            )
    atomic_write(
        BASE_DIR / "monitoring/container-logs.json",
        json.dumps(log_targets, indent=2) + "\n",
    )


def collect_storage(metrics: Metrics) -> None:
    output = command(["docker", "system", "df", "--format", "{{json .}}"], timeout=90)
    kinds = {
        "Images": "images",
        "Build Cache": "build_cache",
        "Local Volumes": "volumes",
    }
    for item in map(json.loads, output.splitlines()):
        kind = kinds.get(item["Type"])
        if kind:
            metrics.add("docker_storage_bytes", size_bytes(item["Size"]), kind=kind)
            reclaimable = item["Reclaimable"].split(" (")[0]
            metrics.add("docker_reclaimable_bytes", size_bytes(reclaimable), kind=kind)


def collect_caddy(metrics: Metrics) -> None:
    output = command(
        [
            "docker",
            "exec",
            "countyiq-caddy",
            "wget",
            "-qO-",
            "http://127.0.0.1:2019/metrics",
        ]
    )
    # Caddy emits bounded handler/method/status/server labels. Exclude Go,
    # process, admin API and certificate metrics from this HTTP-only probe.
    selected = []
    for line in output.splitlines():
        if re.match(
            r"(?:# (?:HELP|TYPE) )?caddy_http_(?:requests_total|request_duration_seconds|response_size_bytes)(?:[_{ ]|$)",
            line,
        ):
            selected.append(line + "\n")
    if not selected:
        raise ValueError("Caddy HTTP metrics are not enabled")
    metrics.lines.extend(selected)


def collect_postgres(metrics: Metrics) -> None:
    output = command(
        [
            "docker",
            "exec",
            "countyiq-postgres",
            "psql",
            "-X",
            "-qAt",
            "-U",
            "dagster_admin",
            "-d",
            "countyiq",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            POSTGRES_QUERY,
        ]
    )
    result = json.loads(output)
    for database in result["databases"] or []:
        for source, target in (
            ("bytes", "database_bytes"),
            ("connections", "connections"),
            ("deadlocks", "deadlocks_total"),
            ("temp_bytes", "temp_bytes_total"),
        ):
            metrics.add(
                f"postgres_{target}", database[source], database=database["name"]
            )
    for key in ("connection_limit", "blocked_sessions", "oldest_transaction_seconds"):
        metrics.add(f"postgres_{key}", result[key])
    metrics.add("postgres_total_connections", result["connections"])


def container_probe(service: str, probe: str) -> dict:
    interpreter = (
        "/app/.venv/bin/python"
        if service == "api"
        else "/opt/pipelines/.venv/bin/python"
    )
    output = command(
        ["docker", "exec", "-i", f"countyiq-{service}", interpreter, "-", probe],
        input_text=PROBE_FILE.read_text(),
        timeout=75,
    )
    return json.loads(output)


def collect_dagster(metrics: Metrics) -> None:
    result = container_probe("dagster-webserver", "dagster")
    for daemon, heartbeat in result["daemons"].items():
        metrics.add(
            "dagster_heartbeat_timestamp_seconds", heartbeat["timestamp"], daemon=daemon
        )
        metrics.add("dagster_heartbeat_errors", heartbeat["errors"], daemon=daemon)
    for status, runs in result["runs"].items():
        metrics.add("dagster_runs", runs["count"], status=status)
        metrics.add("dagster_oldest_run_seconds", runs["oldest_seconds"], status=status)
    metrics.add("dagster_failures_24h", result["failures_24h"])


def collect_sources(metrics: Metrics) -> None:
    result = container_probe("api", "sources")
    for source, item in result["sources"].items():
        metrics.add("source_healthy", item["healthy"], source=source)
        metrics.add("source_stale", item["stale"], source=source)
        metrics.add(
            "source_last_success_timestamp_seconds", item["last_success"], source=source
        )
        if item["records"] is not None:
            metrics.add("source_records", item["records"], source=source)
    metrics.add("intelligence_integrity_healthy", result["integrity_healthy"])


def collect_recovery(metrics: Metrics) -> None:
    state = command(
        [
            "systemctl",
            "show",
            "countyiq-backup.service",
            "-p",
            "ExecMainStatus",
            "-p",
            "Result",
        ]
    )
    properties = dict(line.split("=", 1) for line in state.splitlines() if "=" in line)
    metrics.add(
        "backup_last_exit_success",
        properties.get("Result") == "success"
        and properties.get("ExecMainStatus") == "0",
    )
    timer = command(
        ["systemctl", "show", "countyiq-backup.timer", "-p", "ActiveState", "--value"]
    )
    metrics.add("backup_timer_active", timer.strip() == "active")
    # The success line is printed only after both off-host dumps and the manifest
    # have been verified. Journal timestamps survive monitor restarts and installs.
    journal = command(
        [
            "journalctl",
            "-u",
            "countyiq-backup.service",
            "--since",
            "7 days ago",
            "-n",
            "1000",
            "-o",
            "json",
            "--no-pager",
        ]
    )
    latest = 0.0
    for line in journal.splitlines():
        entry = json.loads(line)
        if re.search(
            r"Backup complete: [0-9]{8}T[0-9]{6}Z-", str(entry.get("MESSAGE", ""))
        ):
            latest = max(latest, int(entry["__REALTIME_TIMESTAMP"]) / 1_000_000)
    metrics.add("backup_last_success_timestamp_seconds", latest)
    receipt = read_values(BASE_DIR / "restore-drills/current.env")
    metrics.add("restore_drill_timestamp_seconds", timestamp(receipt.get("drilled_at")))
    guard = read_values(BASE_DIR / "cost-guard/status.env")
    metrics.add("cost_guard_timestamp_seconds", timestamp(guard.get("checked_at")))
    metrics.add("cost_guard_tripped", (BASE_DIR / "cost-guard/tripped").exists())
    for key, bucket in (
        ("raw_bytes", "raw"),
        ("backup_bytes", "backups"),
        ("total_bytes", "total"),
    ):
        if key in guard:
            metrics.add("r2_bytes", guard[key], bucket=bucket)
    if "hard_limit_bytes" in guard:
        metrics.add("r2_limit_bytes", guard["hard_limit_bytes"])


def collect_openrouter(metrics: Metrics) -> None:
    key = read_values(Path("/etc/countyiq/production.env")).get("OPENROUTER_API_KEY")
    metrics.add("openrouter_configured", bool(key))
    if not key:
        return
    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {key}"}
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        data = json.load(response)["data"]
    for field, period in (
        ("usage", "total"),
        ("usage_daily", "day"),
        ("usage_monthly", "month"),
    ):
        if data.get(field) is not None:
            metrics.add("openrouter_usage_usd", data[field], period=period)


COLLECTORS = {
    "containers": collect_containers,
    "storage": collect_storage,
    "caddy": collect_caddy,
    "postgres": collect_postgres,
    "dagster": collect_dagster,
    "sources": collect_sources,
    "recovery": collect_recovery,
    "openrouter": collect_openrouter,
}
GROUPS = {
    "fast": ("containers", "dagster", "caddy"),
    "slow": ("postgres", "sources", "recovery", "openrouter"),
    "storage": ("storage",),
}


def run_collector(name: str, directory: Path = METRICS_DIR) -> bool:
    started = time.time()
    metrics = Metrics()
    succeeded = False
    try:
        COLLECTORS[name](metrics)
        succeeded = True
    except Exception as error:
        # Discard partial results. Never print subprocess output or exception
        # messages: either may contain connection strings or source payloads.
        metrics = Metrics()
        print(f"Collector {name} failed ({type(error).__name__})", flush=True)
    metrics.add("monitor_collector_success", succeeded, collector=name)
    metrics.add("monitor_last_attempt_timestamp_seconds", started, collector=name)
    metrics.add(
        "monitor_collection_duration_seconds", time.time() - started, collector=name
    )
    atomic_write(directory / f"{name}.prom", metrics.render())
    return succeeded


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("group", choices=GROUPS)
    arguments = parser.parse_args()
    successful = [run_collector(name) for name in GROUPS[arguments.group]]
    raise SystemExit(0 if all(successful) else 1)
