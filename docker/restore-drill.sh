#!/usr/bin/env bash
# Restore one completed off-host backup set into disposable sibling databases.

set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=docker/lib/operations.sh
source "$SCRIPT_DIR/lib/operations.sh"

BACKUP_ID=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --backup-id)
            BACKUP_ID="${2:-}"
            shift 2
            ;;
        *)
            echo "Unknown restore-drill argument: $1" >&2
            exit 2
            ;;
    esac
done
if ! [[ "$BACKUP_ID" =~ ^[0-9]{8}T[0-9]{6}Z-[a-zA-Z0-9._-]+$ ]]; then
    echo "--backup-id must be the exact ID printed by backup.sh" >&2
    exit 2
fi
if [ "$EUID" -ne 0 ]; then
    echo "The restore drill must run as root" >&2
    exit 1
fi

ENVIRONMENT_FILE="${COUNTYIQ_ENV_FILE:-/opt/countyiq/.env}"
countyiq_validate_secret_file "$ENVIRONMENT_FILE"
countyiq_load_environment "$ENVIRONMENT_FILE"
countyiq_require_command docker
countyiq_require_command flock
countyiq_require_command pg_restore
countyiq_require_command rclone
countyiq_require_command sha256sum
countyiq_validate_r2_backup_environment

DATABASE_USER="${DATABASE_USER:-dagster_admin}"
PRIMARY_DATABASE="${DATABASE_NAME:-countyiq}"
DAGSTER_DATABASE="${DAGSTER_POSTGRES_DB:-dagster}"
PRIMARY_DRILL_DATABASE="${PRIMARY_DATABASE}_restore_drill"
DAGSTER_DRILL_DATABASE="${DAGSTER_DATABASE}_restore_drill"
RECEIPT_DIR="${COUNTYIQ_RESTORE_RECEIPT_DIR:-/var/lib/countyiq/restore-drills}"
REMOTE_POSTGRES_PATH="${COUNTYIQ_BACKUP_REMOTE}/postgres"
REMOTE_MANIFEST="${COUNTYIQ_BACKUP_REMOTE}/manifests/backup-${BACKUP_ID}.manifest"
WORK_DIR=""
CONTAINER_DUMP="/tmp/countyiq-restore-drill.dump"

for identifier in \
    "$DATABASE_USER" \
    "$PRIMARY_DATABASE" \
    "$DAGSTER_DATABASE" \
    "$PRIMARY_DRILL_DATABASE" \
    "$DAGSTER_DRILL_DATABASE"; do
    countyiq_require_identifier "$identifier" "restore-drill database or user"
done
if [ "$PRIMARY_DRILL_DATABASE" = "$PRIMARY_DATABASE" ] \
    || [ "$DAGSTER_DRILL_DATABASE" = "$DAGSTER_DATABASE" ]; then
    echo "Restore drill target must never equal a live database" >&2
    exit 1
fi

exec 7>/var/lock/countyiq-restore-drill.lock
if ! flock -n 7; then
    echo "Another CountyIQ restore drill is already running" >&2
    exit 1
fi
WORK_DIR="$(mktemp -d)"

cleanup() {
    local status=$?
    docker exec countyiq-postgres rm -f "$CONTAINER_DUMP" >/dev/null 2>&1 || true
    docker exec countyiq-postgres dropdb \
        -U "$DATABASE_USER" --if-exists --force "$PRIMARY_DRILL_DATABASE" \
        >/dev/null 2>&1 || true
    docker exec countyiq-postgres dropdb \
        -U "$DATABASE_USER" --if-exists --force "$DAGSTER_DRILL_DATABASE" \
        >/dev/null 2>&1 || true
    rm -rf -- "$WORK_DIR"
    return "$status"
}
trap cleanup EXIT

if [ "$(docker inspect --format '{{.State.Running}}' countyiq-postgres 2>/dev/null || true)" != "true" ]; then
    echo "countyiq-postgres must be running before a restore drill" >&2
    exit 1
fi

manifest_file="$WORK_DIR/backup-${BACKUP_ID}.manifest"
rclone copyto "$REMOTE_MANIFEST" "$manifest_file"
if ! grep -Fxq "backup_id=$BACKUP_ID" "$manifest_file"; then
    echo "The downloaded completion manifest does not match $BACKUP_ID" >&2
    exit 1
fi
BACKUP_CODE_REF="$(awk -F= '$1 == "code_ref" {print $2}' "$manifest_file")"
TARGET_DEPLOY_REF="$(awk -F= '$1 == "target_deploy_ref" {print $2}' "$manifest_file")"
PRIMARY_ROW_COUNT="unknown"
DAGSTER_TABLE_COUNT="unknown"

for database_name in "$PRIMARY_DATABASE" "$DAGSTER_DATABASE"; do
    if [ "$database_name" = "$PRIMARY_DATABASE" ]; then
        drill_database="$PRIMARY_DRILL_DATABASE"
    else
        drill_database="$DAGSTER_DRILL_DATABASE"
    fi
    dump_name="$(awk -F= -v key="database.${database_name}.file" '$1 == key {print $2}' "$manifest_file")"
    if [ "$dump_name" != "${database_name}-${BACKUP_ID}.dump" ]; then
        echo "Manifest has no safe dump filename for $database_name" >&2
        exit 1
    fi
    dump_file="$WORK_DIR/$dump_name"
    checksum_file="${dump_file}.sha256"
    manifest_sha256="$(awk -F= -v key="database.${database_name}.sha256" '$1 == key {print $2}' "$manifest_file")"
    manifest_bytes="$(awk -F= -v key="database.${database_name}.bytes" '$1 == key {print $2}' "$manifest_file")"
    if ! [[ "$manifest_sha256" =~ ^[0-9a-f]{64}$ ]] \
        || ! [[ "$manifest_bytes" =~ ^[0-9]+$ ]]; then
        echo "Manifest integrity metadata is invalid for $database_name" >&2
        exit 1
    fi
    rclone copyto "${REMOTE_POSTGRES_PATH}/${dump_name}" "$dump_file"
    rclone copyto "${REMOTE_POSTGRES_PATH}/${dump_name}.sha256" "$checksum_file"
    sidecar_sha256="$(awk 'NR == 1 {print $1}' "$checksum_file")"
    sidecar_name="$(awk 'NR == 1 {print $2}' "$checksum_file")"
    actual_sha256="$(sha256sum "$dump_file" | awk '{print $1}')"
    if [ "$sidecar_name" != "$dump_name" ] \
        || [ "$sidecar_sha256" != "$manifest_sha256" ] \
        || [ "$actual_sha256" != "$manifest_sha256" ] \
        || [ "$(stat -c '%s' "$dump_file")" != "$manifest_bytes" ]; then
        echo "Downloaded dump does not match completion manifest for $database_name" >&2
        exit 1
    fi
    pg_restore --list "$dump_file" >/dev/null

    docker exec countyiq-postgres dropdb \
        -U "$DATABASE_USER" --if-exists --force "$drill_database"
    docker exec countyiq-postgres createdb -U "$DATABASE_USER" "$drill_database"
    docker cp "$dump_file" "countyiq-postgres:$CONTAINER_DUMP" >/dev/null
    docker exec countyiq-postgres pg_restore \
        -U "$DATABASE_USER" --exit-on-error --no-owner \
        -d "$drill_database" "$CONTAINER_DUMP"
    if [ "$database_name" = "$PRIMARY_DATABASE" ]; then
        PRIMARY_ROW_COUNT="$(docker exec countyiq-postgres psql \
            -U "$DATABASE_USER" -d "$drill_database" -v ON_ERROR_STOP=1 \
            -Atc "SELECT COUNT(*) FROM public.properties;")"
    else
        table_count="$(
            docker exec countyiq-postgres psql \
                -U "$DATABASE_USER" -d "$drill_database" -v ON_ERROR_STOP=1 \
                -Atc "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';"
        )"
        if [ "$table_count" -lt 1 ]; then
            echo "Restored Dagster database contains no public tables" >&2
            exit 1
        fi
        DAGSTER_TABLE_COUNT="$table_count"
    fi
    docker exec countyiq-postgres rm -f "$CONTAINER_DUMP"
    docker exec countyiq-postgres dropdb \
        -U "$DATABASE_USER" --if-exists --force "$drill_database"
    echo "Restored and verified $database_name in disposable database $drill_database"
done

install -d -m 700 "$RECEIPT_DIR"
receipt_timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
receipt_file="$RECEIPT_DIR/${receipt_timestamp}-${BACKUP_ID}.env"
if [ -e "$receipt_file" ]; then
    echo "Refusing to overwrite an existing restore-drill receipt" >&2
    exit 1
fi
receipt_temp="$(mktemp "$RECEIPT_DIR/.restore.XXXXXX")"
{
    printf 'backup_id=%s\n' "$BACKUP_ID"
    printf 'drilled_at=%s\n' "$(date -u -Iseconds)"
    printf 'deploy_ref=%s\n' "${COUNTYIQ_DEPLOY_REF:-unknown}"
    printf 'backup_code_ref=%s\n' "$BACKUP_CODE_REF"
    printf 'backup_target_deploy_ref=%s\n' "$TARGET_DEPLOY_REF"
    printf 'databases=%s,%s\n' "$PRIMARY_DATABASE" "$DAGSTER_DATABASE"
    printf 'primary_property_rows=%s\n' "$PRIMARY_ROW_COUNT"
    printf 'dagster_public_tables=%s\n' "$DAGSTER_TABLE_COUNT"
} > "$receipt_temp"
chmod 400 "$receipt_temp"
mv "$receipt_temp" "$receipt_file"
current_temp="$(mktemp "$RECEIPT_DIR/.current.XXXXXX")"
cp "$receipt_file" "$current_temp"
chmod 400 "$current_temp"
mv "$current_temp" "$RECEIPT_DIR/current.env"

echo "Restore drill complete: $receipt_file"
