#!/usr/bin/env bash
# Fail-closed Cloudflare R2 usage guard and manual CountyIQ kill switch.

set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=docker/lib/operations.sh
source "$SCRIPT_DIR/lib/operations.sh"

ACTION="enforce"
RESERVE_BYTES=0
TRIP_REASON="manual"
while [ "$#" -gt 0 ]; do
    case "$1" in
        --enforce|--check|--status|--reset)
            ACTION="${1#--}"
            shift
            ;;
        --trip)
            ACTION="trip"
            TRIP_REASON="${2:-manual}"
            shift 2
            ;;
        --reserve-bytes)
            RESERVE_BYTES="${2:-}"
            shift 2
            ;;
        *)
            echo "Unknown cost-guard argument: $1" >&2
            exit 2
            ;;
    esac
done

if [ "$EUID" -ne 0 ]; then
    echo "The CountyIQ cost guard must run as root" >&2
    exit 1
fi
if ! [[ "$RESERVE_BYTES" =~ ^[0-9]+$ ]]; then
    echo "--reserve-bytes must be a non-negative integer" >&2
    exit 2
fi
if ! [[ "$TRIP_REASON" =~ ^[a-z][a-z0-9_-]{0,63}$ ]]; then
    echo "The trip reason must be a lowercase machine-readable label" >&2
    exit 2
fi

ENVIRONMENT_FILE="${COUNTYIQ_ENV_FILE:-/etc/countyiq/production.env}"
GUARD_DIR="${COUNTYIQ_COST_GUARD_DIR:-/var/lib/countyiq/cost-guard}"
TRIP_FILE="$GUARD_DIR/tripped"
STATUS_FILE="$GUARD_DIR/status.env"
COMPOSE_FILE="${COUNTYIQ_COMPOSE_FILE:-/opt/countyiq/docker/docker-compose.yml}"

load_hard_limit() {
    HARD_LIMIT_BYTES="${COUNTYIQ_R2_HARD_LIMIT_BYTES:-8000000000}"
    if ! [[ "$HARD_LIMIT_BYTES" =~ ^[1-9][0-9]{9}$ ]] \
        || [ "$HARD_LIMIT_BYTES" -gt 9000000000 ]; then
        echo "COUNTYIQ_R2_HARD_LIMIT_BYTES must be between 1 GB and 9 GB" >&2
        return 1
    fi
}
load_hard_limit

# Application containers mount this directory read-only and run as UID 10001.
# They need traversal permission to observe the trip sentinel, never write access.
install -d -o root -g root -m 755 "$GUARD_DIR"
exec 7>/var/lock/countyiq-cost-guard.lock
if ! flock -n 7; then
    echo "Another CountyIQ cost-guard check is already running" >&2
    exit 1
fi

stop_everything() {
    local reason="$1"
    local observed_bytes="${2:-unknown}"
    local temporary_trip
    local stop_failed=false

    temporary_trip="$(mktemp "$GUARD_DIR/.tripped.XXXXXX")"
    {
        printf 'tripped_at=%s\n' "$(date -u -Iseconds)"
        printf 'reason=%s\n' "$reason"
        printf 'observed_bytes=%s\n' "$observed_bytes"
        printf 'hard_limit_bytes=%s\n' "$HARD_LIMIT_BYTES"
    } > "$temporary_trip"
    chmod 400 "$temporary_trip"
    mv "$temporary_trip" "$TRIP_FILE"

    systemctl stop countyiq-backup.timer >/dev/null 2>&1 || stop_failed=true
    systemctl stop countyiq-cost-guard.timer >/dev/null 2>&1 || stop_failed=true
    if [ -f "$COMPOSE_FILE" ] && [ -f "$ENVIRONMENT_FILE" ]; then
        docker compose --env-file "$ENVIRONMENT_FILE" -f "$COMPOSE_FILE" \
            stop --timeout 60 >/dev/null 2>&1 || stop_failed=true
    else
        stop_failed=true
    fi

    echo "COUNTYIQ COST GUARD TRIPPED: $reason (observed=$observed_bytes, limit=$HARD_LIMIT_BYTES)" >&2
    if [ "$stop_failed" = true ]; then
        echo "The stop is latched, but one or more services could not be stopped; verify the host immediately" >&2
        return 1
    fi
}

if [ "$ACTION" = "status" ]; then
    if [ -f "$TRIP_FILE" ]; then
        echo "CountyIQ stop is latched. Verify service state on the host."
        cat "$TRIP_FILE"
    elif [ -f "$STATUS_FILE" ]; then
        echo "CountyIQ cost guard is armed."
        cat "$STATUS_FILE"
    else
        echo "CountyIQ cost guard has not completed a usage check yet."
    fi
    exit 0
fi

if [ "$ACTION" = "trip" ]; then
    stop_everything "$TRIP_REASON" "manual"
    exit 0
fi

countyiq_validate_secret_file "$ENVIRONMENT_FILE"
countyiq_load_environment "$ENVIRONMENT_FILE"
# Scheduled execution receives this setting from the production env file.
load_hard_limit
countyiq_require_command docker
countyiq_require_command flock
countyiq_require_command rclone
countyiq_validate_r2_backup_environment
countyiq_configure_r2_raw_remote

remote_bytes() {
    local remote_name="$1"
    local output
    local bytes
    output="$(rclone size "$remote_name" --json --fast-list)"
    bytes="$(printf '%s\n' "$output" \
        | sed -n 's/.*"bytes"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' \
        | head -n 1)"
    if ! [[ "$bytes" =~ ^[0-9]+$ ]]; then
        echo "Could not parse R2 usage for $remote_name" >&2
        return 1
    fi
    printf '%s\n' "$bytes"
}

if ! raw_bytes="$(remote_bytes "$COUNTYIQ_RAW_REMOTE")" \
    || ! backup_bytes="$(remote_bytes "$COUNTYIQ_BACKUP_REMOTE")"; then
    stop_everything "r2_usage_check_failed" "unknown"
    exit 75
fi

total_bytes=$(( raw_bytes + backup_bytes ))
projected_bytes=$(( total_bytes + RESERVE_BYTES ))
status_temp="$(mktemp "$GUARD_DIR/.status.XXXXXX")"
{
    printf 'checked_at=%s\n' "$(date -u -Iseconds)"
    printf 'raw_bytes=%s\n' "$raw_bytes"
    printf 'backup_bytes=%s\n' "$backup_bytes"
    printf 'total_bytes=%s\n' "$total_bytes"
    printf 'reserved_bytes=%s\n' "$RESERVE_BYTES"
    printf 'projected_bytes=%s\n' "$projected_bytes"
    printf 'hard_limit_bytes=%s\n' "$HARD_LIMIT_BYTES"
} > "$status_temp"
chmod 400 "$status_temp"
mv "$status_temp" "$STATUS_FILE"

if [ "$ACTION" = "reset" ]; then
    if [ "$projected_bytes" -ge "$HARD_LIMIT_BYTES" ]; then
        echo "Refusing reset while projected R2 usage remains at or above the hard limit" >&2
        exit 1
    fi
    rm -f -- "$TRIP_FILE"
    echo "Cost guard reset. Services and timers remain stopped until an operator starts them explicitly."
    exit 0
fi

if [ -f "$TRIP_FILE" ]; then
    stop_everything "previous_trip_still_active" "$total_bytes"
    exit 75
fi
if [ "$projected_bytes" -ge "$HARD_LIMIT_BYTES" ]; then
    stop_everything "r2_hard_limit" "$projected_bytes"
    exit 75
fi

echo "R2 cost guard OK: $total_bytes bytes used; $projected_bytes projected; limit $HARD_LIMIT_BYTES"
