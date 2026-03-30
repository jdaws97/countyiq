# Alerting & Slack Integration

## Error Handling, Alerting & Retry Policy

### Notification Hub: Slack (Free Tier)

All pipeline and infrastructure alerts flow into a **free Slack workspace**. Slack provides push notifications on your phone, searchable history (90 days on free tier), and channel-based organization.

**Workspace:** `CountyIQ` (countyiq.slack.com)

| Channel | Purpose | Phone Notifications |
|---|---|---|
| `#alerts-critical` | Run failures after all retries exhausted, infra alarms (CPU/memory/disk) | **ON** — these need attention |
| `#alerts-warning` | Single run failures (before retries), zero-record results, schema changes | OFF — check when convenient |
| `#pipeline-runs` | Every successful run posts a one-liner | Muted — scroll through when curious |

### Integration Architecture

```
┌─────────────────────────────────────┐
│          DAGSTER (Docker)           │
│                                     │
│  Run succeeds ──▶ Slack #pipeline-runs  ("✅ parcels: 176,060 records, 4m 12s")
│  Run fails    ──▶ Retry (up to 3x)
│  All retries  ──▶ Slack #alerts-critical ("❌ parcels failed 3x: ConnectionTimeout")
│  Zero records ──▶ Slack #alerts-warning  ("⚠️ assessment returned 0 records")
│  Schema change──▶ Slack #alerts-warning  ("⚠️ parcels API has new field: XYZ")
│                                     │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│    SYSTEM HEALTH MONITOR (cron)     │
│    Runs every 5 min on VPS host     │
│                                     │
│  Container down  ──▶ Slack #alerts-critical
│  Disk > 80%      ──▶ Slack #alerts-critical
│  Memory > 85%    ──▶ Slack #alerts-critical
│  Postgres down   ──▶ Slack #alerts-critical
│                                     │
└─────────────────────────────────────┘
```

**Dagster -> Slack:** Direct webhook integration. Dagster failure/success sensors post to Slack via incoming webhook URL (stored in `.env` on the VPS). No intermediate service needed.

**System Health Monitor -> Slack:** A cron script on the VPS host checks container health, disk, and memory every 5 minutes. Posts to the Slack webhook on failure.

### Dagster Slack Integration Code

```python
# pipelines/lib/slack.py
import os
import requests
import json

# Environment variable names for each Slack channel webhook
SLACK_CHANNELS = {
    "critical": "SLACK_WEBHOOK_CRITICAL",
    "warning": "SLACK_WEBHOOK_WARNING",
    "pipeline": "SLACK_WEBHOOK_PIPELINE",
}

def get_slack_webhook_url(channel="pipeline"):
    """Retrieve Slack webhook URL from environment variable.

    Args:
        channel: One of 'critical', 'warning', 'pipeline'
    """
    env_var = SLACK_CHANNELS[channel]
    url = os.environ.get(env_var)
    if not url:
        raise ValueError(f"Missing environment variable: {env_var}")
    return url

def send_slack_message(channel: str, text: str, emoji: str = "🔔"):
    """Post a message to a Slack channel via incoming webhook."""
    webhook_url = get_slack_webhook_url(channel)
    payload = {
        "channel": channel,
        "icon_emoji": emoji,
        "username": "CountyIQ",
        "text": text
    }
    requests.post(webhook_url, json=payload, timeout=10)
```

### Dagster Sensors

```python
# pipelines/sensors/alerting.py
from dagster import (
    run_failure_sensor,
    run_status_sensor,
    DagsterRunStatus,
    RunStatusSensorContext,
    RunFailureSensorContext,
)
from lib.slack import send_slack_message


@run_status_sensor(run_status=DagsterRunStatus.SUCCESS)
def success_reporter(context: RunStatusSensorContext):
    """Post successful run summary to #pipeline-runs."""
    run = context.dagster_run
    duration = (run.end_time - run.start_time) if run.end_time else 0
    minutes = int(duration // 60)
    seconds = int(duration % 60)

    send_slack_message(
        channel="#pipeline-runs",
        text=f"✅ *{run.job_name}* completed in {minutes}m {seconds}s",
        emoji="✅"
    )


@run_failure_sensor
def failure_alerter(context: RunFailureSensorContext):
    """Post failures to #alerts-critical after all retries exhausted."""
    run = context.dagster_run
    error = context.failure_event.message[:200] if context.failure_event else "Unknown error"

    send_slack_message(
        channel="#alerts-critical",
        text=f"❌ *{run.job_name}* failed after all retries.\n```{error}```",
        emoji="🚨"
    )
```

### Retry Policy

Applied globally to all Dagster assets via a default policy. Individual assets can override if needed.

```python
# pipelines/lib/retry.py
from dagster import RetryPolicy, Backoff

default_retry_policy = RetryPolicy(
    max_retries=3,
    delay=300,                    # 5 minutes between retries
    backoff=Backoff.EXPONENTIAL,  # 5min → 10min → 20min
)
```

| Attempt | Wait Before | What Happens |
|---|---|---|
| 1st try | — | Normal run |
| 2nd try | 5 minutes | Retry after transient failure |
| 3rd try | 10 minutes | Retry with exponential backoff |
| 4th try | 20 minutes | Final retry |
| All failed | — | `#alerts-critical` notification fires |

**Why exponential backoff:** If a website is down or rate-limiting you, hammering it every 30 seconds makes things worse. Spreading retries over ~35 minutes gives the upstream source time to recover.

### Alert Types

| Alert Type | Channel | Trigger | Example Message |
|---|---|---|---|
| Run failure (all retries) | `#alerts-critical` | Dagster failure sensor | "❌ crimewatch_incidents failed 3x: TimeoutError" |
| Consecutive failures | `#alerts-critical` | Custom sensor (3+ days of failures for same source) | "🔴 assessment_properties has failed 3 days in a row" |
| Zero records returned | `#alerts-warning` | Asset check in Dagster | "⚠️ sheriff_sales returned 0 records (expected 50+)" |
| Schema change detected | `#alerts-warning` | Asset check comparing field names | "⚠️ parcels API returned unknown field: NEW_COLUMN" |
| Container down | `#alerts-critical` | VPS cron health monitor | "🔴 countyiq-postgres is not running" |
| Disk usage high | `#alerts-critical` | VPS cron health monitor | "🔴 Disk usage at 83% on /opt/countyiq" |
| Memory usage high | `#alerts-critical` | VPS cron health monitor | "🔴 Memory usage at 88%" |
| Successful run | `#pipeline-runs` | Dagster success sensor | "✅ parcels_arcgis: 176,060 records, 4m 12s" |

### System Health Monitor

A shell script on the VPS host runs via cron every 5 minutes. It checks container health, disk, memory, and Postgres connectivity, and posts to Slack on any failure.

```bash
#!/usr/bin/env bash
# /opt/countyiq/scripts/health-check.sh
# Crontab: */5 * * * * /opt/countyiq/scripts/health-check.sh

set -euo pipefail
source /opt/countyiq/.env

WEBHOOK_URL="${SLACK_WEBHOOK_CRITICAL}"

alert() {
    local msg="$1"
    curl -s -X POST "$WEBHOOK_URL" \
        -H 'Content-Type: application/json' \
        -d "{\"channel\": \"#alerts-critical\", \"username\": \"VPS Monitor\", \"icon_emoji\": \"🔴\", \"text\": \"$msg\"}"
}

# 1. Check all Docker containers are running and healthy
UNHEALTHY=$(docker compose -f /opt/countyiq/docker-compose.yml ps --format json | \
    jq -r 'select(.State != "running") | .Name' 2>/dev/null)
if [ -n "$UNHEALTHY" ]; then
    alert "🔴 Containers not running: $UNHEALTHY"
fi

# 2. Check disk usage (alert if > 80%)
DISK_PCT=$(df /opt/countyiq --output=pcent | tail -1 | tr -d ' %')
if [ "$DISK_PCT" -gt 80 ]; then
    alert "🔴 Disk usage at ${DISK_PCT}% on /opt/countyiq"
fi

# 3. Check memory usage (alert if > 85%)
MEM_PCT=$(free | awk '/Mem:/ {printf "%.0f", $3/$2 * 100}')
if [ "$MEM_PCT" -gt 85 ]; then
    alert "🔴 Memory usage at ${MEM_PCT}%"
fi

# 4. Check Postgres connectivity
if ! docker exec countyiq-postgres pg_isready -q 2>/dev/null; then
    alert "🔴 Postgres is not responding (pg_isready failed)"
fi
```

### Environment Variables (`.env`)

One webhook URL per channel. Dagster sensors and the health monitor script read these from `/opt/countyiq/.env`.

| Variable | Channel | Used By |
|---|---|---|
| `SLACK_WEBHOOK_CRITICAL` | `#alerts-critical` | VPS health monitor cron, Dagster failure sensor (after all retries exhausted) |
| `SLACK_WEBHOOK_WARNING` | `#alerts-warning` | Dagster failure sensor (single failure, before retries) |
| `SLACK_WEBHOOK_PIPELINE` | `#pipeline-runs` | Dagster success sensor (all completions) |
