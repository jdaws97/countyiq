#!/usr/bin/env bash
# Render and install operation units for the exact CountyIQ release checkout.

set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_DIR="$SCRIPT_DIR/systemd"
DEFAULT_REPOSITORY_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
REPOSITORY_ROOT="$DEFAULT_REPOSITORY_ROOT"
ENVIRONMENT_FILE="${COUNTYIQ_ENV_FILE:-/etc/countyiq/production.env}"
CHECK_ONLY=false

usage() {
    cat <<'USAGE'
Usage: install-operation-units.sh [--check-only] [--repository-root PATH] [--env-file PATH]
USAGE
}

validate_absolute_path() {
    local path="$1"
    local description="$2"

    if [[ ! "$path" =~ ^/[A-Za-z0-9._/-]+$ ]]; then
        echo "$description must be an absolute path using only safe path characters" >&2
        exit 2
    fi
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --check-only)
            CHECK_ONLY=true
            shift
            ;;
        --repository-root)
            REPOSITORY_ROOT="${2:-}"
            shift 2
            ;;
        --env-file)
            ENVIRONMENT_FILE="${2:-}"
            shift 2
            ;;
        --help)
            usage
            exit 0
            ;;
        *)
            usage >&2
            exit 2
            ;;
    esac
done

validate_absolute_path "$REPOSITORY_ROOT" "Repository root"
validate_absolute_path "$ENVIRONMENT_FILE" "Environment file"

if [ ! -d "$REPOSITORY_ROOT" ]; then
    echo "Repository root does not exist: $REPOSITORY_ROOT" >&2
    exit 2
fi

REPOSITORY_ROOT="$(realpath -e -- "$REPOSITORY_ROOT")"
validate_absolute_path "$REPOSITORY_ROOT" "Resolved repository root"

for unit_name in \
    countyiq-backup.service \
    countyiq-backup.timer \
    countyiq-cost-guard.service \
    countyiq-cost-guard.timer; do
    if [ ! -f "$TEMPLATE_DIR/$unit_name" ]; then
        echo "Missing unit template: $TEMPLATE_DIR/$unit_name" >&2
        exit 1
    fi
done

RENDER_DIRECTORY="$(mktemp -d)"
trap 'rm -rf -- "$RENDER_DIRECTORY"' EXIT

render_unit() {
    local unit_name="$1"
    local output_path="$RENDER_DIRECTORY/$unit_name"

    sed "s|/opt/countyiq|$REPOSITORY_ROOT|g" "$TEMPLATE_DIR/$unit_name" \
        > "$output_path"

    if [ "$unit_name" = "countyiq-cost-guard.service" ]; then
        sed -i \
            "/^Environment=COUNTYIQ_ENV_FILE=/a Environment=COUNTYIQ_COMPOSE_FILE=$REPOSITORY_ROOT/docker/docker-compose.yml" \
            "$output_path"
    fi

    sed -i \
        "s|^Environment=COUNTYIQ_ENV_FILE=.*$|Environment=COUNTYIQ_ENV_FILE=$ENVIRONMENT_FILE|" \
        "$output_path"
}

for unit_name in \
    countyiq-backup.service \
    countyiq-backup.timer \
    countyiq-cost-guard.service \
    countyiq-cost-guard.timer; do
    render_unit "$unit_name"
done

systemd-analyze verify \
    "$RENDER_DIRECTORY/countyiq-backup.service" \
    "$RENDER_DIRECTORY/countyiq-backup.timer" \
    "$RENDER_DIRECTORY/countyiq-cost-guard.service" \
    "$RENDER_DIRECTORY/countyiq-cost-guard.timer"

if [ "$CHECK_ONLY" = true ]; then
    echo "CountyIQ operation units render and verify for $REPOSITORY_ROOT"
    exit 0
fi

if [ "$EUID" -ne 0 ]; then
    echo "Operation-unit installation must run as root" >&2
    exit 1
fi

for unit_name in \
    countyiq-backup.service \
    countyiq-backup.timer \
    countyiq-cost-guard.service \
    countyiq-cost-guard.timer; do
    destination="/etc/systemd/system/$unit_name"
    temporary_destination="$(mktemp "/etc/systemd/system/.${unit_name}.XXXXXX")"
    install -o root -g root -m 644 "$RENDER_DIRECTORY/$unit_name" "$temporary_destination"
    mv -f -- "$temporary_destination" "$destination"
done

systemctl daemon-reload
echo "Installed CountyIQ operation units for $REPOSITORY_ROOT"
