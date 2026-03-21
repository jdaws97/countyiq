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
│          DAGSTER (EC2)              │
│                                     │
│  Run succeeds ──▶ Slack #pipeline-runs  ("✅ parcels: 176,060 records, 4m 12s")
│  Run fails    ──▶ Retry (up to 3x)
│  All retries  ──▶ Slack #alerts-critical ("❌ parcels failed 3x: ConnectionTimeout")
│  Zero records ──▶ Slack #alerts-warning  ("⚠️ assessment returned 0 records")
│  Schema change──▶ Slack #alerts-warning  ("⚠️ parcels API has new field: XYZ")
│                                     │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│        CLOUDWATCH (AWS)             │
│                                     │
│  CPU > 90% 5min  ──▶ SNS ──▶ Slack #alerts-critical
│  Memory > 85%    ──▶ SNS ──▶ Slack #alerts-critical
│  Disk > 80%      ──▶ SNS ──▶ Slack #alerts-critical
│  RDS connections ──▶ SNS ──▶ Slack #alerts-critical
│  RDS storage     ──▶ SNS ──▶ Slack #alerts-critical
│                                     │
└─────────────────────────────────────┘
```

**Dagster → Slack:** Direct webhook integration. Dagster failure/success sensors post to Slack via incoming webhook URL (stored in Parameter Store). No intermediate Lambda needed.

**CloudWatch → Slack:** CloudWatch Alarm → SNS Topic → Lambda (tiny forwarder) → Slack webhook. The Lambda is a ~20 line Python function that reformats the SNS message and posts to Slack. Runs within the permanent Lambda free tier.

### Dagster Slack Integration Code

```python
# pipelines/lib/slack.py
import requests
import json
import boto3

# SSM parameter names for each Slack channel
SLACK_CHANNELS = {
    "critical": "/countyiq/slack-webhook-critical",
    "warning": "/countyiq/slack-webhook-warning",
    "pipeline": "/countyiq/slack-webhook-pipeline",
}

_webhook_cache = {}

def get_slack_webhook_url(channel="pipeline"):
    """Retrieve Slack webhook URL from Parameter Store.

    Args:
        channel: One of 'critical', 'warning', 'pipeline'
    """
    if channel in _webhook_cache:
        return _webhook_cache[channel]

    ssm = boto3.client("ssm", region_name="us-east-1")
    response = ssm.get_parameter(
        Name=SLACK_CHANNELS[channel],
        WithDecryption=True,
    )
    url = response["Parameter"]["Value"]
    _webhook_cache[channel] = url
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
| Infra alarm | `#alerts-critical` | CloudWatch → SNS → Lambda → Slack | "🔴 EC2 CPU > 90% for 5 minutes" |
| Successful run | `#pipeline-runs` | Dagster success sensor | "✅ parcels_arcgis: 176,060 records, 4m 12s" |

### CloudWatch → Slack Forwarder Lambda

```python
# infra/lambda/cloudwatch_to_slack.py
import json
import os
import urllib.request

def handler(event, context):
    """Forward CloudWatch alarm SNS messages to Slack."""
    webhook_url = os.environ["SLACK_WEBHOOK_URL"]

    for record in event["Records"]:
        message = json.loads(record["Sns"]["Message"])
        alarm_name = message.get("AlarmName", "Unknown")
        state = message.get("NewStateValue", "Unknown")
        reason = message.get("NewStateReason", "")[:200]

        slack_msg = {
            "channel": "#alerts-critical",
            "username": "CloudWatch",
            "icon_emoji": "🔴" if state == "ALARM" else "✅",
            "text": f"{'🔴' if state == 'ALARM' else '✅'} *{alarm_name}*: {state}\n```{reason}```"
        }

        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(slack_msg).encode(),
            headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req)
```

**Note:** The CloudWatch forwarder Lambda runs **outside** the VPC (unlike the API Lambda), so it could call Parameter Store. However, using an environment variable (`SLACK_WEBHOOK_URL`) is simpler for a single-purpose function. Terraform sets this to the `#alerts-critical` webhook URL.

This Lambda is subscribed to the existing SNS topic used by CloudWatch alarms. Add it to the `monitoring` Terraform module.

### Parameter Store Values (New)

One webhook per channel — Dagster sensors and the CloudWatch forwarder Lambda pick the right URL based on alert severity.

| Parameter | Channel | Used By |
|---|---|---|
| `/countyiq/slack-webhook-critical` | `#alerts-critical` | CloudWatch forwarder Lambda, Dagster failure sensor (after all retries exhausted) |
| `/countyiq/slack-webhook-warning` | `#alerts-warning` | Dagster failure sensor (single failure, before retries) |
| `/countyiq/slack-webhook-pipeline` | `#pipeline-runs` | Dagster success sensor (all completions) |
