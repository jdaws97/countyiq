#!/usr/bin/env bash
# PostgreSQL backups -> Cloudflare R2.
# A manifest is uploaded last and is the completion marker for one backup set.

set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=docker/lib/operations.sh
source "$SCRIPT_DIR/lib/operations.sh"

BACKUP_REASON="scheduled"
BACKUP_LABEL=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --reason)
            BACKUP_REASON="${2:-}"
            shift 2
            ;;
        --label)
            BACKUP_LABEL="${2:-}"
            shift 2
            ;;
        *)
            echo "Unknown backup argument: $1" >&2
            exit 2
            ;;
    esac
done

if ! [[ "$BACKUP_REASON" =~ ^[a-z][a-z0-9_-]{0,31}$ ]]; then
    echo "Backup reason must use lowercase letters, numbers, underscores, or dashes" >&2
    exit 2
fi
if [ "$EUID" -ne 0 ]; then
    echo "The backup job must run as root" >&2
    exit 1
fi
if [ -n "$BACKUP_LABEL" ] && ! [[ "$BACKUP_LABEL" =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$ ]]; then
    echo "Backup label contains unsupported characters" >&2
    exit 2
fi

ENVIRONMENT_FILE="${COUNTYIQ_ENV_FILE:-/etc/countyiq/production.env}"
countyiq_validate_secret_file "$ENVIRONMENT_FILE"
countyiq_load_environment "$ENVIRONMENT_FILE"
countyiq_require_command docker
countyiq_require_command flock
countyiq_require_command pg_restore
countyiq_require_command rclone
countyiq_require_command sha256sum
countyiq_validate_r2_backup_environment

# Refuse new off-host writes after a manual or automatic cost stop. This check
# also measures both R2 buckets and trips the whole stack if usage is unreadable.
# A periodic usage check may overlap any upload. Wait briefly for its lock;
# still abort before writing if capacity cannot be checked within that bound.
check_backup_capacity() {
    "$SCRIPT_DIR/cost-guard.sh" --check --lock-wait-seconds 120 "$@"
}
check_backup_capacity

countyiq_lock_backup_operations

BACKUP_TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_SUFFIX="$BACKUP_REASON"
if [ -n "$BACKUP_LABEL" ]; then
    BACKUP_SUFFIX="${BACKUP_SUFFIX}-${BACKUP_LABEL}"
fi
BACKUP_ID="${BACKUP_TIMESTAMP}-${BACKUP_SUFFIX}"
DUMP_DIR="$(mktemp -d)"
MANIFEST_FILE="$DUMP_DIR/backup-${BACKUP_ID}.manifest"
REMOTE_POSTGRES_PATH="${COUNTYIQ_BACKUP_REMOTE}/postgres"
REMOTE_MANIFEST_PATH="${COUNTYIQ_BACKUP_REMOTE}/manifests"
DATABASE_USER="${DATABASE_USER:-dagster_admin}"
PRIMARY_DATABASE="${DATABASE_NAME:-countyiq}"
BACKUP_CODE_REF="${COUNTYIQ_BACKUP_CODE_REF:-}"
if [ -z "$BACKUP_CODE_REF" ] && [ -f /var/lib/countyiq/releases/current.env ]; then
    BACKUP_CODE_REF="$(awk -F= '$1 == "deploy_ref" {print $2}' /var/lib/countyiq/releases/current.env)"
fi
BACKUP_CODE_REF="${BACKUP_CODE_REF:-unknown}"
TARGET_DEPLOY_REF="${COUNTYIQ_DEPLOY_REF:-none}"
if ! [[ "$BACKUP_CODE_REF" =~ ^([0-9a-f]{40}|unknown|none)$ ]] \
    || ! [[ "$TARGET_DEPLOY_REF" =~ ^([0-9a-f]{40}|none)$ ]]; then
    echo "Backup code references must be exact commit SHAs or explicit sentinels" >&2
    exit 1
fi

on_exit() {
    local status=$?
    rm -rf -- "$DUMP_DIR"
    if [ "$status" -ne 0 ] && [ -n "${SLACK_WEBHOOK_CRITICAL:-}" ]; then
        curl --fail --silent --show-error --max-time 10 \
            -H 'Content-Type: application/json' \
            --data '{"text":"CountyIQ backup failed."}' \
            "$SLACK_WEBHOOK_CRITICAL" >/dev/null 2>&1 || true
    fi
}
trap on_exit EXIT

countyiq_require_identifier "$DATABASE_USER" "DATABASE_USER"
countyiq_require_identifier "$PRIMARY_DATABASE" "DATABASE_NAME"

if [ "$(docker inspect --format '{{.State.Running}}' countyiq-postgres 2>/dev/null || true)" != "true" ]; then
    echo "countyiq-postgres must be running before backup" >&2
    exit 1
fi

{
    printf 'backup_id=%s\n' "$BACKUP_ID"
    printf 'created_at=%s\n' "$(date -u -Iseconds)"
    printf 'reason=%s\n' "$BACKUP_REASON"
    printf 'code_ref=%s\n' "$BACKUP_CODE_REF"
    printf 'target_deploy_ref=%s\n' "$TARGET_DEPLOY_REF"
} > "$MANIFEST_FILE"

echo "[$(date -Iseconds)] Starting backup $BACKUP_ID..."
dump_name="${PRIMARY_DATABASE}-${BACKUP_ID}.dump"
dump_file="$DUMP_DIR/$dump_name"
checksum_file="${dump_file}.sha256"
docker exec countyiq-postgres \
    pg_dump -U "$DATABASE_USER" --format=custom "$PRIMARY_DATABASE" > "$dump_file"
pg_restore --list "$dump_file" >/dev/null
(
    cd "$DUMP_DIR"
    sha256sum "$dump_name" > "${dump_name}.sha256"
)
dump_sha256="$(cut -d ' ' -f 1 "$checksum_file")"
dump_bytes="$(stat -c '%s' "$dump_file")"
{
    printf 'database.%s.file=%s\n' "$PRIMARY_DATABASE" "$dump_name"
    printf 'database.%s.bytes=%s\n' "$PRIMARY_DATABASE" "$dump_bytes"
    printf 'database.%s.sha256=%s\n' "$PRIMARY_DATABASE" "$dump_sha256"
} >> "$MANIFEST_FILE"

# Reserve the entire dump before its first remote write so a single backup
# cannot carry the account through the configured storage safety margin.
checksum_bytes="$(stat -c '%s' "$checksum_file")"
check_backup_capacity \
    --reserve-bytes "$(( dump_bytes + checksum_bytes ))"

rclone copyto --immutable "$dump_file" "${REMOTE_POSTGRES_PATH}/${dump_name}"
rclone copyto --immutable "$checksum_file" "${REMOTE_POSTGRES_PATH}/${dump_name}.sha256"
rclone check "$DUMP_DIR" "$REMOTE_POSTGRES_PATH" \
    --include "/$dump_name" \
    --include "/${dump_name}.sha256" \
    --download --one-way --checkers 1
echo "[$(date -Iseconds)] $PRIMARY_DATABASE verified off-host: $dump_bytes bytes"

# Publish the completion marker only after the primary dump is verified off-host.
manifest_name="$(basename "$MANIFEST_FILE")"
remote_manifest_copy="$DUMP_DIR/remote-$manifest_name"
manifest_bytes="$(stat -c '%s' "$MANIFEST_FILE")"
check_backup_capacity --reserve-bytes "$manifest_bytes"
rclone copyto --immutable "$MANIFEST_FILE" "${REMOTE_MANIFEST_PATH}/${manifest_name}"
rclone copyto "${REMOTE_MANIFEST_PATH}/${manifest_name}" "$remote_manifest_copy"
cmp --silent "$MANIFEST_FILE" "$remote_manifest_copy"

echo "[$(date -Iseconds)] Backup complete: $BACKUP_ID"
echo "COUNTYIQ_BACKUP_ID=$BACKUP_ID"
