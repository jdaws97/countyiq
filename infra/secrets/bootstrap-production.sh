#!/usr/bin/env bash
# Generate database secrets and encrypt the production environment from hidden prompts.

set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
TEMPLATE="$REPO_ROOT/.env.example"
OUTPUT_FILE="${COUNTYIQ_SOPS_FILE:-$SCRIPT_DIR/production.sops.env}"
SSH_KEY="${COUNTYIQ_SSH_KEY:-/home/jdaws/.ssh/jdawskey}"
SOPS_BIN="${SOPS_BIN:-sops}"
ACCOUNT_ID="a37fbb717276b94bcec2a5eb2be0a8d2"

if [ "${1:-}" = "--replace" ]; then
    replace=true
elif [ "$#" -eq 0 ]; then
    replace=false
else
    echo "Usage: bootstrap-production.sh [--replace]" >&2
    exit 2
fi

if ! command -v openssl >/dev/null 2>&1; then
    echo "openssl is required" >&2
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
if [ ! -f "$TEMPLATE" ] || [ -L "$TEMPLATE" ]; then
    echo "Production environment template is missing or symlinked: $TEMPLATE" >&2
    exit 1
fi
if [ ! -f "$SSH_KEY" ] || [ -L "$SSH_KEY" ]; then
    echo "SSH private key is missing or symlinked: $SSH_KEY" >&2
    exit 1
fi
if [ -e "$OUTPUT_FILE" ] && [ "$replace" != true ]; then
    echo "Refusing to replace existing encrypted environment: $OUTPUT_FILE" >&2
    echo "Rerun with --replace only when intentionally rotating production secrets." >&2
    exit 1
fi

read -r -p "Raw bucket Access Key ID: " raw_access_key </dev/tty
read -r -s -p "Raw bucket Secret Access Key: " raw_secret_key </dev/tty
printf '\n' >/dev/tty
read -r -p "Backup bucket Access Key ID: " backup_access_key </dev/tty
read -r -s -p "Backup bucket Secret Access Key: " backup_secret_key </dev/tty
printf '\n' >/dev/tty
echo "Loading the Cloudflare Tunnel token from encrypted OpenTofu credentials."
tunnel_token="$("$REPO_ROOT/infra/cloudflare/tofu-sops.sh" output -raw tunnel_token)"

app_audience="$("$REPO_ROOT/infra/cloudflare/tofu-sops.sh" output -raw app_access_audience)"
if [ -z "$app_audience" ] || [[ "$app_audience" == *[[:space:]]* ]]; then
    echo "Apply the guarded app-host infrastructure before bootstrapping account sign-in" >&2
    exit 1
fi

for access_key in "$raw_access_key" "$backup_access_key"; do
    if ! [[ "$access_key" =~ ^[0-9A-Fa-f]{32}$ ]]; then
        echo "Each R2 Access Key ID must be a 32-character hexadecimal token ID" >&2
        exit 1
    fi
done
for secret_key in "$raw_secret_key" "$backup_secret_key"; do
    if ! [[ "$secret_key" =~ ^[0-9A-Fa-f]{64}$ ]]; then
        echo "Each R2 Secret Access Key must be a 64-character hexadecimal value" >&2
        exit 1
    fi
done
if [ -z "$tunnel_token" ]; then
    echo "Cloudflare Tunnel token cannot be empty" >&2
    exit 1
fi

database_password="$(openssl rand -hex 32)"
pipeline_password="$(openssl rand -hex 32)"
api_password="$(openssl rand -hex 32)"
temporary="$(mktemp "$SCRIPT_DIR/.production.sops.env.XXXXXX")"
cleanup() {
    rm -f -- "$temporary"
    unset raw_access_key raw_secret_key backup_access_key backup_secret_key
    unset tunnel_token database_password pipeline_password api_password
}
trap cleanup EXIT

while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
        DATABASE_PASSWORD=*)
            printf 'DATABASE_PASSWORD=%s\n' "$database_password"
            ;;
        DATABASE_URL=*)
            printf 'DATABASE_URL=postgresql://dagster_admin:%s@postgres:5432/countyiq\n' "$database_password"
            ;;
        DATABASE_PIPELINE_PASSWORD=*)
            printf 'DATABASE_PIPELINE_PASSWORD=%s\n' "$pipeline_password"
            ;;
        DATABASE_API_PASSWORD=*)
            printf 'DATABASE_API_PASSWORD=%s\n' "$api_password"
            ;;
        R2_ACCESS_KEY_ID=*)
            printf 'R2_ACCESS_KEY_ID=%s\n' "$raw_access_key"
            ;;
        R2_SECRET_ACCESS_KEY=*)
            printf 'R2_SECRET_ACCESS_KEY=%s\n' "$raw_secret_key"
            ;;
        R2_ENDPOINT_URL=*)
            printf 'R2_ENDPOINT_URL=https://%s.r2.cloudflarestorage.com\n' "$ACCOUNT_ID"
            ;;
        COUNTYIQ_BACKUP_R2_ACCESS_KEY_ID=*)
            printf 'COUNTYIQ_BACKUP_R2_ACCESS_KEY_ID=%s\n' "$backup_access_key"
            ;;
        COUNTYIQ_BACKUP_R2_SECRET_ACCESS_KEY=*)
            printf 'COUNTYIQ_BACKUP_R2_SECRET_ACCESS_KEY=%s\n' "$backup_secret_key"
            ;;
        COUNTYIQ_BACKUP_BUCKET_LOCK_CONFIRMED=*)
            printf 'COUNTYIQ_BACKUP_BUCKET_LOCK_CONFIRMED=true\n'
            ;;
        \#\ COUNTYIQ_PUBLIC_READY_URL=*)
            printf 'COUNTYIQ_PUBLIC_READY_URL=https://app.countyiq.net/api/ready\n'
            ;;
        COUNTYIQ_ARCHIVE_STRICT=*)
            printf 'COUNTYIQ_ARCHIVE_STRICT=true\n'
            ;;
        CLOUDFLARE_TUNNEL_TOKEN=*)
            printf 'CLOUDFLARE_TUNNEL_TOKEN=%s\n' "$tunnel_token"
            ;;
        COUNTYIQ_TRUSTED_HOSTS=*)
            printf 'COUNTYIQ_TRUSTED_HOSTS=app.countyiq.net\n'
            ;;
        COUNTYIQ_AUTH_PROVIDER=*)
            printf 'COUNTYIQ_AUTH_PROVIDER=cloudflare_access\n'
            ;;
        COUNTYIQ_ACCESS_ISSUER=*)
            printf 'COUNTYIQ_ACCESS_ISSUER=https://countyiq.cloudflareaccess.com\n'
            ;;
        COUNTYIQ_ACCESS_AUD=*)
            printf 'COUNTYIQ_ACCESS_AUD=%s\n' "$app_audience"
            ;;
        COUNTYIQ_APP_URL=*)
            printf 'COUNTYIQ_APP_URL=https://app.countyiq.net\n'
            ;;
        COUNTYIQ_WORKSPACE_ORIGINS=*)
            printf 'COUNTYIQ_WORKSPACE_ORIGINS=https://app.countyiq.net\n'
            ;;
        DOMAIN=*)
            printf 'DOMAIN=countyiq.net\n'
            ;;
        *)
            printf '%s\n' "$line"
            ;;
    esac
done < "$TEMPLATE" | SOPS_AGE_SSH_PRIVATE_KEY_FILE="$SSH_KEY" \
    "$SOPS_BIN" encrypt \
    --input-type dotenv \
    --output-type dotenv \
    --filename-override "$OUTPUT_FILE" \
    /dev/stdin > "$temporary"

decrypted="$({
    SOPS_AGE_SSH_PRIVATE_KEY_FILE="$SSH_KEY" \
        "$SOPS_BIN" decrypt --input-type dotenv --output-type dotenv "$temporary"
})"
required_lines=(
    "DOMAIN=countyiq.net"
    "COUNTYIQ_TRUSTED_HOSTS=app.countyiq.net"
    "COUNTYIQ_ARCHIVE_STRICT=true"
    "COUNTYIQ_BACKUP_BUCKET_LOCK_CONFIRMED=true"
    "COUNTYIQ_PUBLIC_READY_URL=https://app.countyiq.net/api/ready"
)
for required_line in "${required_lines[@]}"; do
    if ! grep -Fxq "$required_line" <<< "$decrypted"; then
        echo "Generated environment is missing required setting: $required_line" >&2
        exit 1
    fi
done
if grep -Eq 'CHANGE_ME|ACCOUNT_ID' <<< "$decrypted"; then
    echo "Generated environment still contains a placeholder" >&2
    exit 1
fi

chmod 600 "$temporary"
mv -f -- "$temporary" "$OUTPUT_FILE"
trap - EXIT
unset decrypted raw_access_key raw_secret_key backup_access_key backup_secret_key
unset tunnel_token database_password pipeline_password api_password

echo "Created SOPS-encrypted production environment: $OUTPUT_FILE"
echo "Database passwords were generated independently; no plaintext environment file was written."
