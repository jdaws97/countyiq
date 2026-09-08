# Monitoring and operator access

The monitoring source lives in `infra/monitoring/`. Application data remains on
the VPS/R2; the Grafana Cloud stack receives aggregate operational metrics and
filtered container logs. The operating policy requires the Free plan; the Cloud
Portal billing plan and post-trial status still need owner verification.

## Browser access

- Dagster: `https://dagster.countyiq.net`, through Cloudflare Tunnel and a separate
  Access application allowing only `jarod.daws@gmail.com` and
  `jarod.daws@protonmail.com`. The tester
  allowlist does not grant operator access. Dagster can launch work; the hostname
  exposes its full operator UI, not a customer-facing dashboard.
- Grafana: the private stack URL selected at account creation. The provisioner
  checks that every human stack member uses one of these two addresses; it does not invite
  people or enable public/anonymous dashboards. Verify Cloud Portal organization
  membership and any automatic role assignments as part of account setup too.
- Data health: `https://app.countyiq.net/ops/health`.

The Dagster origin stays on `127.0.0.1:3000`. Only cloudflared and the Dagster
webserver share the additional internal `countyiq-operator` bridge. No public
host port is added. Access/DNS/Tunnel configuration remains in OpenTofu.

### Installation status — 2026-09-08

The host probes are installed and all eight reported success. Dagster's Access
application, DNS record, and tunnel route are applied. Anonymous UI and GraphQL
requests redirect to Access; a Firefox check confirmed the login form. Owner
sign-in still needs an owner verification. Cloud ingestion is live: all eight
collectors were queried successfully, and a harmless synthetic log was found in
Loki with its email and query parameter redacted. The owner confirmed receipt
of the Gmail delivery-test notification. The test recovered and its temporary
rule was removed.

The dashboard at `https://eloquentbread1118.grafana.net/d/countyiq-overview` now
has readable overview cards, per-service health, a joined source health/freshness
table, external readiness, and separate capacity charts. Its rendered layout
was checked in Firefox using a temporary loopback preview; the preview does not
verify the owner's Grafana login. Native CLI backfill progress is not represented
by the cards explicitly labeled Dagster.

Production release `124ad880a0e5b4ec2b2458a1a713d37d8fc95d88` includes the
operator network and Caddy metrics setting. The release completed at
`2026-09-08T15:37:54Z` with schema `075` unchanged; all eight monitoring probes
reported success after deployment. These settings now persist across container
recreation through the deployed Compose configuration and Caddy image.
The later application release `3fa56ec5403f5b5f0c597de0aad01661b67551fb`
completed at `2026-09-08T16:10:33Z` and preserves those settings. Monitoring
configuration changes after that release did not redeploy the application.

## Components and retention

Grafana Alloy 1.19.2 is checksum-pinned. A host systemd service collects CPU,
memory, filesystems, disk I/O and network counters and tails the six known
container log files. The listener is loopback-only on port 12345. The process
has no Linux capabilities and cannot access the Docker socket or the production
environment. It runs as root solely to read root-owned Docker log files.

Short-lived probes use the existing Docker administrative boundary to collect
selected state without passing the socket to Alloy. SQL executes in read-only
transactions with an eight-second statement timeout. Existing application
libraries execute in separate probe processes and return aggregate values;
they do not change the running API or Dagster processes.

| Cadence | Probe |
| --- | --- |
| 1 minute | Containers, Dagster heartbeats/queue, Caddy request metrics |
| 5 minutes | PostgreSQL, source health, backups/restores, R2 guard, OpenRouter key usage |
| 1 hour | Docker image/build-cache/volume storage inventory |

OpenRouter reports usage for the configured runtime API key. This is not total
account billing and does not include other keys, subscription-based Codex work,
or unrelated services. No model inference is requested by monitoring.

Source health uses the application's existing freshness expectations; paused
and manual jobs are not automatically treated as missed scheduled work.
Backup success comes from the scheduled service's journal line after verified
off-host completion. Manual pre-deploy backups do not conceal a broken daily
schedule. Restore success comes from the immutable restore-drill receipt.

### Zero-cost operating policy

Keep the account on Grafana Cloud **Free**, with no payment method, marketplace
subscription, paid upgrade, or paid add-on. Provisioning has no billing API
calls. Confirm the post-trial plan in the account portal rather than mistaking
temporary trial allowances for Free capacity. Provider terms can change; the
collector/dashboard configuration is portable to another compatible backend.

Current provider allowances: 10,000 metric series, 50 GB logs/month, 14 days of
history, and three active Grafana users. The host scrape rejects over 2,500
samples. Self-monitoring keeps only a short allowlist. Avoid PIDNs, request IDs,
run IDs, arbitrary URLs, and customer identities as labels. The current host is
fixed as `countyiq-production` to avoid creating new series per release.

Container logs omit routine health checks, debug lines, SQL/payload dumps and
common credential-bearing messages; remaining connection strings, query values,
emails and credential formats are redacted. Lines over 4 KB are dropped. One
global limiter permits one log line/second with a burst of ten, bounding message
payload to roughly 11 GB/month before label/transport overhead. This deliberately
drops excess logs; inspect drop counters when diagnosing a busy incident.
Redaction is defense in depth, not permission to log raw secrets or records.

Metrics buffer at most about 30 minutes by age; logs use bounded batches and
three retries rather than a persistent log queue. Alloy memory is capped at
512 MB and CPU at half a core. Probe service memory is capped at 160 MB. This
limits monitoring overhead but is not a filesystem quota: monitor Alloy's state
directory as part of root-disk capacity. No application data or rollback images
are deleted by monitoring.

## Install and connect

Deploy host probes and the pinned collector from the reviewed source:

```bash
bash infra/monitoring/deploy.sh
```

This installs a Python 3.11 project environment using checksum-pinned uv 0.10.7,
then enables the three probe timers. Without `/etc/countyiq/monitoring.env`,
Grafana export stays disabled; local aggregate metrics still update.

In the Grafana Cloud account, retrieve the stack URL, metrics remote-write URL
and numeric tenant ID, Loki push URL and tenant ID, and create a stack-scoped
Cloud Access Policy token with only `metrics:write` and `logs:write`. Use a
separate Grafana service-account token for dashboard and alert provisioning.
The legacy alert provisioning endpoints require suitable provisioning rights
(Admin is the documented basic role that covers these endpoints). Keep that
credential off the VPS and revoke it after initial setup if automated future
reconciliation is not needed.

Enter credentials through hidden local prompts, never chat or repository text:

```bash
pipelines/.venv/bin/python infra/monitoring/configure.py capture
pipelines/.venv/bin/python infra/monitoring/configure.py resolve
pipelines/.venv/bin/python infra/monitoring/provision.py --check
pipelines/.venv/bin/python infra/monitoring/provision.py --apply
pipelines/.venv/bin/python infra/monitoring/configure.py publish
bash infra/monitoring/deploy.sh
```

Only encrypted `infra/secrets/monitoring.sops.env` is stored in Git. Publishing
streams ingestion-only credentials over verified SSH to a root-owned 0600 file.
Capture saves the verified service-account token before asking for the Cloud
Access Policy token, and saves both before datasource discovery. If setup is
interrupted or discovery fails, rerun `capture` to resume or `resolve` to retry
discovery without entering tokens again. The first token belongs to the Grafana
service account (`glsa_`); the second belongs to the Cloud Access Policy (`glc_`).
Dashboards and alert rules reconcile by fixed UIDs. Notification routing adds
only the CountyIQ route and preserves unrelated routes. Initial routing is
email to the operator's Gmail address; a Slack contact point remains optional and requires
the user's selected destination.

Grafana currently accepts email contact points only for existing organization
members. Gmail is the initial registered member. ProtonMail is in the approved
owner allowlist, but must join the Grafana Cloud organization before it can be
used for Grafana sign-in or alert delivery.

## External checks and browser telemetry

External readiness must exercise `https://app.countyiq.net/api/ready`, require
HTTP 200 and `{"status":"ok"}`, and use the existing path-scoped Access health
credential. A 200 login page does not count as readiness. Keep redirects off.
Store the credential in Grafana Synthetic Monitoring's secret store and use a
k6 scripted check: current official docs only guarantee secret support for
scripted/browser checks, not basic HTTP header fields.

Use two probes at five-minute intervals initially, well below the current
100,000 API executions/month allowance. Alert on failed checks and missing probe
data. These checks must run outside the VPS; local probes cannot notify when
the entire host disappears.

Check `5293` is live from North Virginia and Oregon every five minutes; both
reported success for authenticated HTTP 200 and the readiness JSON assertion.
The owner explicitly approved storing the path-scoped Cloudflare credential in
Grafana's encrypted secret store. The committed k6 script contains secret names,
not credentials. Reconcile with:

```bash
pipelines/.venv/bin/python infra/monitoring/synthetic.py
```

The 22 permanent alert rules include external failure and missing-location
alerts. Promtool verifies failure, recovery, absent probes, and duplicate
configuration versions; no production outage was injected.

Browser error collection needs the Grafana frontend collector endpoint and a
restricted allowed-origin configuration. It is not enabled by the host collector
and remains a separate account-dependent connection step; do not claim browser
error coverage from Caddy metrics alone. Authenticated customer-journey checks
also require a dedicated test identity and test data; the readiness credential
cannot log in as a customer.

Browser telemetry remains unconfigured. Its documented provisioning API needs
a separate Cloud Access Policy with frontend-observability permissions; the
captured ingestion policy was created for metrics and logs. No frontend SDK or
customer-session collection has been enabled.

## Acceptance and operations

Before calling the installation complete:

1. Verify the exact Free plan and that human access is limited to the owner's
   two approved email addresses in Grafana and Cloudflare.
2. Observe all eight probe success gauges and fresh node metrics in Grafana.
3. Verify a synthetic harmless log arrives with redaction and bounded labels.
4. Trigger an isolated monitoring test alert and receive its recovery email.
5. Prove that a missing collector and an external failed HTTP check alert.
6. Open Dagster in a real browser, complete the owner's Access sign-in, and
   verify run details. Confirm anonymous requests cannot read the UI or GraphQL.

Routine host checks:

```bash
systemctl status countyiq-alloy.service
systemctl list-timers 'countyiq-monitor-*'
journalctl -u 'countyiq-monitor@*.service' --since '1 hour ago'
curl --fail http://127.0.0.1:12345/-/ready
```

Alloy readiness proves process configuration, not cloud ingestion. Check the
remote-write success/drop counters and query Grafana for fresh data.

Disk alerts start at 75% and 85%, with a separate 10 GiB free-space floor and
a forecast that requires at least five hours of observed samples. Docker sizes
overlap; never sum images and build cache as guaranteed recoverable space.
Review rollback requirements before any image cleanup. A stale-source alert
calls for source/run inspection, not an automatic expensive backfill. Backup
failures require verifying the off-host completion manifest; never restore over
the live database as an alert response.

### Disk investigation — 2026-09-08 16:22 UTC

The root filesystem had about 19 GiB available of 72 GiB. Docker's containerd
store grew from roughly 33 GiB earlier in the session to 42 GiB after application
releases. PostgreSQL remained about 1.6 GiB; Dagster file storage was 36 KiB,
application support files 58 MiB, system logs 122 MiB, and container logs 364 KiB.
Monitoring binaries/runtime used 674 MiB and the Alloy buffer was under 1 MiB.
Docker reported 24.3 GB reclaimable build cache and 11.84 GB reclaimable images;
these overlap and must not be added as guaranteed recoverable bytes. No cleanup
was performed during that read-only investigation. The owner subsequently
authorized the retention policy below.

### Docker retention

`countyiq-docker-retention.timer` runs hourly with up to five minutes of jitter.
The monitoring installer deploys it independently of application releases.
It acquires `/var/lock/countyiq-deploy.lock`, which is also held by the production
deployment script, and skips if another deployment or cleanup is running.

The policy protects the current and previous release receipts, verifies all
three application image tags against their recorded image identities, and
protects images referenced by any container, including stopped containers.
Missing or mismatched rollback images stop the cleanup before any deletion.
Only full-commit tags in `countyiq-api`, `countyiq-dagster`, and `countyiq-web`
are eligible, with a one-hour grace period after image creation. Images are
removed by exact tag without forced deletion or parent pruning. Unrelated
images, manual tags, volumes, containers, application state, and backups are
outside the image cleanup scope.

Unused Docker build cache is pruned toward a **4 GB** retention target using
`docker builder prune --all --force --keep-storage 4GB`. Active or image-shared
layers can keep reported cache above that target; it is not a filesystem quota.
The next build may take longer when previously cached intermediate layers have
been retired. No Docker daemon restart is required.

To keep an additional rollback release, add its full commit SHA to the
root-managed `/etc/countyiq/retained-releases.txt`, one per line. Its saved
release receipt and three matching image tags must exist. Comments are allowed.

Read-only inspection and service verification:

```bash
sudo /opt/countyiq-monitoring/.venv/bin/python /opt/countyiq-monitoring/retention.py
systemctl list-timers countyiq-docker-retention.timer
systemctl status countyiq-docker-retention.service
journalctl -u countyiq-docker-retention.service --since '1 day ago'
```

The R2 capacity panel divides the `bucket="total"` byte series by the configured
guard limit using `ignoring(bucket)`. The limit metric has no bucket label;
ordinary vector matching previously discarded the result. A real PromQL
regression verifies the percentage and preserves no-data behavior when the
limit is absent. This panel describes the configured storage guard limit, not
the provider's free allowance.

The first authorized retention run completed successfully at
`2026-09-08T16:37:04Z`, retiring 53 old application image tags and reclaiming
33,084,231,680 filesystem bytes (30.8 GiB). Root usage dropped to 32%, with about
50 GiB available. Docker reported 10 remaining images and 4.849 GB of build
cache. All six containers remained running, and current/previous release image
identities were verified again after cleanup. The R2 query returned 7.91 GB of
20 GB configured capacity (39.5%).

## Validation

```bash
pipelines/.venv/bin/ruff format --check infra/monitoring
PROMTOOL=/path/to/promtool pipelines/.venv/bin/python -m unittest discover -s infra/monitoring/tests
GRAFANA_METRICS_URL=https://validation.grafana.net/api/prom/push \
GRAFANA_LOGS_URL=https://validation.grafana.net/loki/api/v1/push \
  /path/to/alloy validate infra/monitoring/config.alloy
```

Sources: [Grafana pricing](https://grafana.com/pricing/),
[Alloy components](https://grafana.com/docs/alloy/latest/reference/components/),
[Synthetic secrets](https://grafana.com/docs/grafana-cloud/observe-and-act/testing/synthetic-monitoring/create-checks/manage-secrets/),
[Cloudflare operator access](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/).
