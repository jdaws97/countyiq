#!/usr/bin/env bash
# Run OpenTofu with SOPS-decrypted Cloudflare and state-backend credentials.

set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
SOPS_FILE="${COUNTYIQ_CLOUDFLARE_SOPS_FILE:-$REPO_ROOT/infra/secrets/cloudflare-iac.sops.env}"
SSH_KEY="${COUNTYIQ_SSH_KEY:-/home/jdaws/.ssh/jdawskey}"
SOPS_BIN="${SOPS_BIN:-sops}"

if [ "$#" -eq 0 ]; then
    echo "Usage: tofu-sops.sh <init|plan|apply|validate|output|state> [arguments...]" >&2
    exit 2
fi
case "$1" in
    init|plan|apply|validate|output|state|show|providers|fmt)
        ;;
    destroy)
        echo "OpenTofu destroy is prohibited for CountyIQ Cloudflare infrastructure" >&2
        exit 2
        ;;
    *)
        echo "Unsupported OpenTofu action: $1" >&2
        exit 2
        ;;
esac
if ! command -v tofu >/dev/null 2>&1; then
    echo "OpenTofu is required" >&2
    exit 1
fi
if ! command -v "$SOPS_BIN" >/dev/null 2>&1; then
    if [ "$SOPS_BIN" = "sops" ] && [ -x "$HOME/.local/bin/sops" ]; then
        SOPS_BIN="$HOME/.local/bin/sops"
    else
        echo "SOPS is required" >&2
        exit 1
    fi
fi
if [ ! -f "$SOPS_FILE" ] || [ -L "$SOPS_FILE" ]; then
    echo "Encrypted Cloudflare IaC credentials are missing or symlinked: $SOPS_FILE" >&2
    exit 1
fi
if [ ! -f "$SSH_KEY" ] || [ -L "$SSH_KEY" ]; then
    echo "SSH private key is missing or symlinked: $SSH_KEY" >&2
    exit 1
fi

printf -v tofu_command '%q ' tofu "-chdir=$SCRIPT_DIR" "$@"
SOPS_AGE_SSH_PRIVATE_KEY_FILE="$SSH_KEY" \
    "$SOPS_BIN" exec-env "$SOPS_FILE" "$tofu_command"
