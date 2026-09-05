#!/usr/bin/env bash
# Read-only host gate; run independently before preparing a release.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/operations.sh"
if [ "$EUID" -ne 0 ]; then
    echo "Host preflight must run as root" >&2
    exit 1
fi
countyiq_validate_host
echo "Host SSH and cost-guard checks passed"
