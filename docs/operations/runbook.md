# Operational Runbook

These procedures describe the reviewed single-host Compose deployment. Confirm
the current release receipt and host state before operating it. Host, user and
SSH key are recorded in infra/ansible/inventory/production.yml; examples below
assume an SSH alias named countyiq points to that inventory entry.

## Operator shell

Connect with the configured key, then enter a root shell. The production
environment is root-readable and Docker access is administrative.

    ssh countyiq
    sudo -i

Define the Compose command for this shell:

    ciq() {
      docker compose --env-file /etc/countyiq/production.env \
        -f /opt/countyiq/docker/docker-compose.yml "$@"
    }

Keep the checkout at the recorded release commit. Commands must use the
protected environment's persisted image tag. Do not print environment values
or enable shell tracing around credentials.

## Routine checks

    ciq ps
    ciq logs --tail=100 api dagster-webserver dagster-daemon
    systemctl status countyiq-cost-guard.timer countyiq-backup.timer
    /opt/countyiq/docker/cost-guard.sh --status
    docker stats --no-stream
    df -h
    docker system df
    free -m

Inspect failed Dagster runs and source freshness. A running daemon alone does
not prove that county ingestion or intelligence coverage is current.

Postgres is reachable inside Compose; it has no published host TCP port:

    ciq exec -T postgres psql -U dagster_admin -d countyiq \
      -c "SELECT pg_size_pretty(pg_database_size('countyiq'));"

For an interactive database session:

    ciq exec postgres psql -U dagster_admin -d countyiq

Use read-only transactions for investigation. Database changes require a
specific incident or migration procedure.

## Host and release preflight

Run the independent read-only host check as root:

    /opt/countyiq/docker/check-host.sh

It checks effective default SSH authentication and actual application-UID
access to the cost-stop directory. Apply the reviewed Ansible bootstrap if
these fail. Verify a fresh key-based SSH session after SSH changes. This check
does not certify provider firewall rules, every possible SSH Match context,
backup recovery, or application readiness.

Prepare the reviewed commit:

    cd /opt/countyiq
    git fetch --prune origin
    git log --oneline --decorate HEAD..origin/main
    export COUNTYIQ_DEPLOY_REF=<reviewed-40-character-commit-sha>
    git checkout --detach "$COUNTYIQ_DEPLOY_REF"
    /opt/countyiq/docker/deploy.sh --check

Configuration preflight validates the exact clean checkout, environment,
Compose graph, disabled inference passes, role separation, R2 targets and the
bucket-lock declaration. Actual deployment also enforces the host gate before
building images or changing services.

    /opt/countyiq/docker/deploy.sh

Use --initial only before the first recorded release. Ordinary releases
require a recent successful restore-drill receipt and authenticated public
readiness configuration. The script builds commit-tagged images, stops writers,
verifies the backup, migrates, checks readiness, and promotes the release
receipt and protected image tag. A failure after migration starts leaves
application services stopped for reviewed recovery.

Retain all release receipts and images. Complete the first backup and
off-host restore drill before enabling the daily backup timer. See
[Backup and restore](backup-and-restore.md). Paid intelligence rollout remains
a separate procedure in [Intelligence rollout](intelligence-rollout.md).

## Restarting a recorded release

Before restarting a service, establish that no deployment/recovery operation
is in progress and that the checkout and protected image tag match the release
receipt. Check the cost guard first; a failed check must stop the procedure.

    /opt/countyiq/docker/check-host.sh
    /opt/countyiq/docker/cost-guard.sh --check
    ciq restart dagster-webserver dagster-daemon

Verify container health and the relevant Dagster run state after a restart.

## Emergency stop

Latch a manual stop so scheduled work cannot silently resume:

    /opt/countyiq/docker/cost-guard.sh --trip manual

Check the command exit status, container state and timers. A failed stop
operation still records the latch but needs operator follow-up. In-flight work
may be interrupted. Keep named volumes intact.

After resolving the incident, review the stop reason and measured usage.
The cost-guard reset command rechecks usage; it does not restart services or
timers. Start them explicitly only after the incident recovery is verified.
Never remove production volumes as part of routine stop or restart.

## Code-only rollback

Review schema compatibility with the last-good commit and the schema_after
value in the current release receipt. Keep the current checkout and migrations;
select retained commit-tagged images for compatible services. Establish
exclusive incident ownership before changing services.

    LAST_GOOD=<recorded-last-good-40-character-sha>
    /opt/countyiq/docker/check-host.sh
    /opt/countyiq/docker/cost-guard.sh --check
    docker image inspect "countyiq-api:$LAST_GOOD"
    COUNTYIQ_IMAGE_TAG="$LAST_GOOD" ciq up -d --no-deps --wait api

For Dagster, inspect the corresponding countyiq-dagster image and update both
dagster-webserver and dagster-daemon together. For the frontend, inspect the
countyiq-web image and update the caddy service. Recheck API/frontend contracts
when mixing service versions. Record the affected services and image IDs in the
incident record; these commands do not promote a new release receipt or rewrite
the persisted default image tag. Do not perform later routine restarts until
the incident's version choices have been reconciled with a reviewed release.

Verify public readiness using the configured Access machine credentials:

    source /opt/countyiq/docker/lib/operations.sh
    countyiq_load_environment /etc/countyiq/production.env
    countyiq_check_public_readiness "$COUNTYIQ_PUBLIC_READY_URL"

## Migration or source-data recovery

Inspect both schema revisions and the stopped failure state:

    ciq run --rm migrate alembic -c /opt/pipelines/alembic.ini current

Keep writers stopped. Restore the recorded pre-deploy backup into a new
database or volume, validate it, and cut over under the incident plan. Do not
automatically downgrade or restore destructively over the only database.
See [Backup and restore](backup-and-restore.md).

For bad source ingestion, identify the affected source records, SCD versions,
downstream projections and inference receipts first. Closing current SCD rows
alone does not restore the prior projection. Prepare and verify the specific
repair against an isolated database before applying it to production.
