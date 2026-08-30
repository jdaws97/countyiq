# Run Notifications

CountyIQ registers two optional Dagster sensors:

- `success_reporter` posts a job name and duration to the pipeline webhook.
- `failure_alerter` posts the failed job and a truncated failure message to the
  critical webhook.

They read `SLACK_WEBHOOK_PIPELINE` and `SLACK_WEBHOOK_CRITICAL` from the
runtime environment. If a webhook is absent, the notification is logged and
skipped; the pipeline result is unchanged. `SLACK_WEBHOOK_WARNING` is reserved
for warning-class notifications but has no registered producer today.

The helper is environment-only. It does not call AWS SSM, require an AWS
runtime, or invent a Slack workspace/channel name. Webhook URLs are secrets and
must remain in the production `.env`, never in git.

The failure sensor reports a failed Dagster run. CountyIQ does not currently
apply a global Dagster retry policy, so notifications must not claim that all
retries were exhausted. Individual HTTP ingestion helpers perform their own
bounded retries where implemented.

Container, disk, memory, PostgreSQL, and backup-failure alerting are not
implemented by this repository. Use provider monitoring or add a supervised
host check explicitly rather than relying on the old aspirational examples.
