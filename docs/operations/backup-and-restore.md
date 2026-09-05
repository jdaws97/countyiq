# Backup and Restore

`docker/backup.sh` creates one uniquely named custom-format dump for the
CountyIQ product database and one for Dagster. It validates each dump locally,
adds a portable SHA-256 sidecar, uploads immutable objects to private R2,
download-checks them, and uploads/read-backs a manifest last. Only a backup ID
with that completion manifest is eligible for restore.

The host script never deletes remote objects. Configure
[R2 lifecycle rules](https://developers.cloudflare.com/r2/reference/wrangler-commands/)
for expiry and an
[R2 bucket-lock rule](https://developers.cloudflare.com/r2/buckets/bucket-locks/)
for at least the required recovery window. Set
`COUNTYIQ_BACKUP_BUCKET_LOCK_CONFIRMED=true` only after reviewing that lock.
The dedicated `COUNTYIQ_BACKUP_R2_*` storage credential in
`/etc/countyiq/production.env` should be scoped to the private backup bucket and must be
different from Dagster's raw-archive credential. Bucket-configuration
authority belongs to a third, operator-only credential that is not stored on
the VPS.

Use the checksum-pinned upstream rclone build installed by the Ansible playbook.
Ubuntu 24.04's older 1.60.1 build reported HTTP 501 after successful R2 uploads;
1.75.1 passed first-attempt uploads and exact download checks on this host.
Do not enable rclone debug logging with environment-defined credentials: the
old build printed credential values during remote configuration.

## First-host gate

After `deploy.sh --initial` succeeds, create and drill a post-migration backup
before enabling the schedule:

```bash
ssh countyiq
sudo /opt/countyiq/docker/backup.sh --reason restore-drill
# Copy the exact COUNTYIQ_BACKUP_ID printed above.
sudo /opt/countyiq/docker/restore-drill.sh \
  --backup-id <YYYYMMDDTHHMMSSZ-restore-drill>
sudo systemctl enable --now countyiq-backup.timer
sudo systemctl start countyiq-backup.service
systemctl status countyiq-backup.service --no-pager
systemctl list-timers countyiq-backup.timer --no-pager
```

The restore script downloads the completion manifest, dump, and checksum for
both databases, restores them into exact disposable sibling databases, runs
sanity queries, drops only those drill databases, and writes a root-readable
receipt under `/var/lib/countyiq/restore-drills/`. It never targets the live
database names.

## Daily verification

The persistent systemd timer runs daily at 04:00 UTC with a randomized delay.
Alert on a failed `countyiq-backup.service`; `SLACK_WEBHOOK_CRITICAL` provides a
secondary notification when configured. A healthy check includes:

```bash
systemctl is-enabled countyiq-backup.timer
systemctl is-active countyiq-backup.timer
systemctl --failed --no-legend countyiq-backup.service
journalctl -u countyiq-backup.service --since '2 days ago' --no-pager
```

Confirm that a new manifest and its referenced database objects exist in R2.
Do not count orphan dumps without a manifest as successful. Run a restore drill
at least quarterly, after PostgreSQL/PostGIS or backup changes, and before the
configured receipt age can block a deployment.

## Production recovery

Recovery is intentionally not automated because choosing a backup and cutting
over production are destructive decisions:

1. Keep API, Dagster daemon, and Dagster webserver stopped. Preserve the failed
   volume and release receipts; take a provider snapshot when the disk is
   healthy enough to do so.
2. Select a completed backup ID from R2 and run `restore-drill.sh` first. This
   proves the exact off-host set is readable without touching production.
3. Restore the selected dump to a new database, new Docker volume, or
   replacement host. Never restore over the only production database.
4. Run Alembic only to the reviewed application's revision, refresh both
   runtime roles, and execute readiness/contract smoke checks against the new
   target.
5. Cut over only after the checks pass. Retain the failed database until the
   recovery is accepted and a new completed off-host backup exists.

Do not use `pg_restore --clean` against the only production database. Do not
treat a Hetzner server image as the database recovery oracle: according to
[Hetzner's backup documentation](https://docs.hetzner.com/cloud/servers/backups-snapshots/faq/),
a live image may be crash-inconsistent, provider backups are coupled to the
server lifecycle, and attached Hetzner Volumes are not included. Logical R2
dumps and tested restores remain the primary data-recovery path.
