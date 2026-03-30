#!/bin/bash
# pg_dump → Cloudflare R2 daily backup
# Add to crontab: 0 4 * * * /opt/countyiq/docker/backup.sh >> /var/log/countyiq-backup.log 2>&1

set -euo pipefail

DUMP_FILE="/tmp/countyiq-$(date +%F).dump"
R2_PATH="r2:countyiq-backups/postgres/"

echo "[$(date -Iseconds)] Starting backup..."

# Dump
docker exec countyiq-postgres pg_dump -U dagster_admin -Fc countyiq > "$DUMP_FILE"
echo "[$(date -Iseconds)] Dump complete: $(du -h "$DUMP_FILE" | cut -f1)"

# Upload to R2
rclone copy "$DUMP_FILE" "$R2_PATH"
echo "[$(date -Iseconds)] Uploaded to R2"

# Clean local dump
rm -f "$DUMP_FILE"

# Prune backups older than 30 days
rclone delete --min-age 30d "$R2_PATH"
echo "[$(date -Iseconds)] Pruned old backups"

echo "[$(date -Iseconds)] Backup complete"
