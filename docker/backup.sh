#!/bin/bash
# PostgreSQL + intelligence archives → Cloudflare R2 daily backup
# Add to crontab: 0 4 * * * /opt/countyiq/docker/backup.sh >> /var/log/countyiq-backup.log 2>&1

set -euo pipefail
umask 077

if [ -f /opt/countyiq/.env ]; then
    set -a
    # shellcheck disable=SC1091
    source /opt/countyiq/.env
    set +a
fi

exec 9>/var/lock/countyiq-backup.lock
if ! flock -n 9; then
    echo "A CountyIQ backup is already running" >&2
    exit 1
fi

BACKUP_DATE="$(date +%F)"
DUMP_DIR="$(mktemp -d)"
R2_POSTGRES_PATH="r2:countyiq-backups/postgres/"
R2_ARCHIVE_PATH="r2:countyiq-backups/intelligence-archives/"
LLM_ARCHIVE_RETENTION_DAYS="${COUNTYIQ_LLM_ARCHIVE_RETENTION_DAYS:-90}"
DATABASE_USER="${DATABASE_USER:-dagster_admin}"
PRIMARY_DATABASE="${DATABASE_NAME:-countyiq}"
DAGSTER_DATABASE="${DAGSTER_POSTGRES_DB:-dagster}"
trap 'rm -rf -- "$DUMP_DIR"' EXIT

if ! [[ "$LLM_ARCHIVE_RETENTION_DAYS" =~ ^[0-9]+$ ]]; then
    echo "COUNTYIQ_LLM_ARCHIVE_RETENTION_DAYS must be a non-negative integer" >&2
    exit 1
fi
for identifier in "$DATABASE_USER" "$PRIMARY_DATABASE" "$DAGSTER_DATABASE"; do
    if ! [[ "$identifier" =~ ^[a-z_][a-z0-9_]{0,62}$ ]]; then
        echo "Database names and users must be simple PostgreSQL identifiers" >&2
        exit 1
    fi
done

echo "[$(date -Iseconds)] Starting backup..."

for database_name in "$PRIMARY_DATABASE" "$DAGSTER_DATABASE"; do
    dump_file="$DUMP_DIR/${database_name}-${BACKUP_DATE}.dump"
    docker exec countyiq-postgres pg_dump -U "$DATABASE_USER" -Fc "$database_name" > "$dump_file"
    pg_restore --list "$dump_file" >/dev/null
    (
        cd "$DUMP_DIR"
        sha256sum "$(basename "$dump_file")" > "$(basename "$dump_file").sha256"
    )
    echo "[$(date -Iseconds)] ${database_name} dump complete: $(du -h "$dump_file" | cut -f1)"
    rclone copy "$dump_file" "$R2_POSTGRES_PATH"
    rclone copy "${dump_file}.sha256" "$R2_POSTGRES_PATH"
done

if [ -d /opt/countyiq/archives ]; then
    if [ "$LLM_ARCHIVE_RETENTION_DAYS" -gt 0 ]; then
        find /opt/countyiq/archives -mindepth 3 -maxdepth 3 -type f \
            -regextype posix-extended \
            -regex '.*/[0-9a-f]{16}_[0-9]{6}_[0-9]{6}\.json' \
            -mtime "+$LLM_ARCHIVE_RETENTION_DAYS" -delete
        find /opt/countyiq/archives -mindepth 1 -type d -empty -delete
    fi
    rclone copy /opt/countyiq/archives "$R2_ARCHIVE_PATH"
fi
if [ "$LLM_ARCHIVE_RETENTION_DAYS" -gt 0 ]; then
    rclone delete --min-age "${LLM_ARCHIVE_RETENTION_DAYS}d" "$R2_ARCHIVE_PATH"
fi
echo "[$(date -Iseconds)] Uploaded databases and intelligence archives to R2"

# Prune backups older than 30 days
rclone delete --min-age 30d "$R2_POSTGRES_PATH"
echo "[$(date -Iseconds)] Pruned old backups"

echo "[$(date -Iseconds)] Backup complete"
