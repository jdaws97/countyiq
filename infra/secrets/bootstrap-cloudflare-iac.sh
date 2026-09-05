#!/usr/bin/env bash
# Create the encrypted Cloudflare/OpenTofu credential file without a plaintext file.

set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_FILE="${COUNTYIQ_CLOUDFLARE_SOPS_FILE:-$SCRIPT_DIR/cloudflare-iac.sops.env}"
SSH_KEY="${COUNTYIQ_SSH_KEY:-/home/jdaws/.ssh/jdawskey}"
SOPS_BIN="${SOPS_BIN:-sops}"
ACCOUNT_ID="a37fbb717276b94bcec2a5eb2be0a8d2"

if [ "${1:-}" = "--replace" ]; then
    replace=true
elif [ "$#" -eq 0 ]; then
    replace=false
else
    echo "Usage: bootstrap-cloudflare-iac.sh [--replace]" >&2
    exit 2
fi

if ! command -v "$SOPS_BIN" >/dev/null 2>&1; then
    if [ "$SOPS_BIN" = "sops" ] && [ -x "$HOME/.local/bin/sops" ]; then
        SOPS_BIN="$HOME/.local/bin/sops"
    else
        echo "SOPS is required" >&2
        exit 1
    fi
fi
if [ ! -f "$SSH_KEY" ] || [ -L "$SSH_KEY" ]; then
    echo "SSH private key is missing or symlinked: $SSH_KEY" >&2
    exit 1
fi
if [ -e "$OUTPUT_FILE" ] && [ "$replace" != true ]; then
    echo "Refusing to replace existing encrypted credentials: $OUTPUT_FILE" >&2
    echo "Rerun with --replace only when intentionally rotating them." >&2
    exit 1
fi

read -r -s -p "Cloudflare IaC API token: " cloudflare_token </dev/tty
printf '\n' >/dev/tty
read -r -p "R2 state-bucket Access Key ID: " state_access_key </dev/tty
read -r -s -p "R2 state-bucket Secret Access Key: " state_secret_key </dev/tty
printf '\n' >/dev/tty

if [ -z "$cloudflare_token" ]; then
    echo "Cloudflare API token cannot be empty" >&2
    exit 1
fi
if ! [[ "$state_access_key" =~ ^[0-9A-Fa-f]{32}$ ]]; then
    echo "R2 Access Key ID must be a 32-character hexadecimal token ID" >&2
    exit 1
fi
if ! [[ "$state_secret_key" =~ ^[0-9A-Fa-f]{64}$ ]]; then
    echo "R2 Secret Access Key must be a 64-character hexadecimal value" >&2
    exit 1
fi

temporary="$(mktemp "$SCRIPT_DIR/.cloudflare-iac.sops.env.XXXXXX")"
cleanup() {
    rm -f -- "$temporary"
    unset cloudflare_token state_access_key state_secret_key
}
trap cleanup EXIT

{
    printf 'CLOUDFLARE_API_TOKEN=%s\n' "$cloudflare_token"
    printf 'AWS_ACCESS_KEY_ID=%s\n' "$state_access_key"
    printf 'AWS_SECRET_ACCESS_KEY=%s\n' "$state_secret_key"
} | SOPS_AGE_SSH_PRIVATE_KEY_FILE="$SSH_KEY" \
    "$SOPS_BIN" encrypt \
    --input-type dotenv \
    --output-type dotenv \
    --filename-override "$OUTPUT_FILE" \
    /dev/stdin > "$temporary"

SOPS_AGE_SSH_PRIVATE_KEY_FILE="$SSH_KEY" \
    "$SOPS_BIN" decrypt --input-type dotenv --output-type dotenv "$temporary" \
    | grep -Eq '^CLOUDFLARE_API_TOKEN=.+$'

chmod 600 "$temporary"
mv -f -- "$temporary" "$OUTPUT_FILE"
trap - EXIT
unset cloudflare_token state_access_key state_secret_key

echo "Created SOPS-encrypted Cloudflare credentials: $OUTPUT_FILE"
echo "No plaintext credential file was written."
