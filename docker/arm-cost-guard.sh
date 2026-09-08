#!/usr/bin/env bash
# Install and arm the fail-closed Cloudflare R2 cost guard on the VPS.

set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=docker/lib/operations.sh
source "$SCRIPT_DIR/lib/operations.sh"

if [ "$EUID" -ne 0 ]; then
    echo "Cost-guard installation must run as root" >&2
    exit 1
fi

ENVIRONMENT_FILE="${COUNTYIQ_ENV_FILE:-/etc/countyiq/production.env}"
countyiq_validate_secret_file "$ENVIRONMENT_FILE"

# Refuse to arm a timer that has never successfully read both R2 buckets.
COUNTYIQ_ENV_FILE="$ENVIRONMENT_FILE" "$SCRIPT_DIR/cost-guard.sh" --check

"$SCRIPT_DIR/install-operation-units.sh" --env-file "$ENVIRONMENT_FILE"
systemctl enable --now countyiq-cost-guard.timer

echo "CountyIQ R2 cost guard is armed."
echo "Backup units are installed but remain disabled until the first restore drill succeeds."
COUNTYIQ_ENV_FILE="$ENVIRONMENT_FILE" "$SCRIPT_DIR/cost-guard.sh" --status
