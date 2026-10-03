# Run Notifications

CountyIQ registers three Dagster sensors:

- `success_reporter` posts a job name and duration to the pipeline webhook.
- `failure_alerter` posts the failed job and a truncated failure message to the
  critical webhook.
- `intelligence_integrity_guard` checks the aggregate integrity view every five
  minutes. It posts new contradictions to the warning webhook, stale queues or
  projection/provenance failures to the critical webhook, and one recovery
  message when health returns to green. A model output rejected by a
  deterministic gate in the last 24 hours is also a warning. A persisted
  sensor cursor suppresses unchanged repeats.

They read `SLACK_WEBHOOK_PIPELINE` and `SLACK_WEBHOOK_CRITICAL` from the
runtime environment. If a webhook is absent, the notification is logged and
skipped; the pipeline result is unchanged. Integrity warning messages use
`SLACK_WEBHOOK_WARNING`.

The helper is environment-only. It does not call AWS SSM, require an AWS
runtime, or invent a Slack workspace/channel name. Webhook URLs are secrets and
must remain in the production `.env`, never in git.

The failure sensor reports a failed Dagster run. CountyIQ does not currently
apply a global Dagster retry policy, so notifications must not claim that all
retries were exhausted. Individual HTTP ingestion helpers perform their own
bounded retries where implemented.

Grafana handles host telemetry, containers, disk, memory, PostgreSQL, backups,
source freshness, and external readiness through the committed monitoring
collector and 22-rule catalog. See [Monitoring](monitoring.md) for deployment,
notification routing, runbooks, and validation. Dagster run notifications and
Grafana alerts cover different failure paths; a running daemon alone does not
establish that sources or customer intelligence are current.
