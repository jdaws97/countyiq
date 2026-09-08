#!/usr/bin/env bash
# Decrypt the committed SOPS environment locally and stream it to the VPS.

set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
SOPS_FILE="${COUNTYIQ_SOPS_FILE:-$REPO_ROOT/infra/secrets/production.sops.env}"
SSH_KEY="${COUNTYIQ_SSH_KEY:-/home/jdaws/.ssh/jdawskey}"
REMOTE_HOST="${COUNTYIQ_REMOTE_HOST:-ubuntu@15.204.255.199}"
SOPS_BIN="${SOPS_BIN:-sops}"

if ! command -v "$SOPS_BIN" >/dev/null 2>&1; then
    if [ "$SOPS_BIN" = "sops" ] && [ -x "$HOME/.local/bin/sops" ]; then
        SOPS_BIN="$HOME/.local/bin/sops"
    else
        echo "SOPS is required to publish production secrets" >&2
        exit 1
    fi
fi
if [ ! -f "$SOPS_FILE" ] || [ -L "$SOPS_FILE" ]; then
    echo "Encrypted production environment is missing or symlinked: $SOPS_FILE" >&2
    exit 1
fi
if [ ! -f "$SSH_KEY" ] || [ -L "$SSH_KEY" ]; then
    echo "SSH private key is missing or symlinked: $SSH_KEY" >&2
    exit 1
fi
if ! [[ "$REMOTE_HOST" =~ ^[a-z_][a-z0-9_-]*@([a-zA-Z0-9.-]+|\[[0-9a-fA-F:]+\])$ ]]; then
    echo "COUNTYIQ_REMOTE_HOST must be an explicit user@host value" >&2
    exit 1
fi

decrypted="$({
    SOPS_AGE_SSH_PRIVATE_KEY_FILE="$SSH_KEY" \
        "$SOPS_BIN" decrypt --input-type dotenv --output-type dotenv "$SOPS_FILE"
})"

required_lines=(
    "DOMAIN=countyiq.net"
    "COUNTYIQ_TRUSTED_HOSTS=app.countyiq.net"
    "COUNTYIQ_ARCHIVE_STRICT=true"
    "COUNTYIQ_BACKUP_BUCKET_LOCK_CONFIRMED=true"
    "COUNTYIQ_R2_HARD_LIMIT_BYTES=20000000000"
    "COUNTYIQ_PASS0_ENABLED=false"
    "COUNTYIQ_PASS1_ENABLED=false"
    "COUNTYIQ_PASS2_ENABLED=false"
    "COUNTYIQ_PASS3_ENABLED=false"
    "COUNTYIQ_PASS4_ENABLED=false"
)
for required_line in "${required_lines[@]}"; do
    if ! grep -Fxq "$required_line" <<< "$decrypted"; then
        echo "Encrypted environment is missing required fail-closed setting: $required_line" >&2
        exit 1
    fi
done
if grep -Eq 'CHANGE_ME|ACCOUNT_ID' <<< "$decrypted"; then
    echo "Encrypted environment still contains a placeholder" >&2
    exit 1
fi
required_credentials=(
    DATABASE_PASSWORD
    DATABASE_PIPELINE_PASSWORD
    DATABASE_API_PASSWORD
    R2_ACCESS_KEY_ID
    R2_SECRET_ACCESS_KEY
    COUNTYIQ_BACKUP_R2_ACCESS_KEY_ID
    COUNTYIQ_BACKUP_R2_SECRET_ACCESS_KEY
    CLOUDFLARE_TUNNEL_TOKEN
)
for required_credential in "${required_credentials[@]}"; do
    if ! grep -Eq "^${required_credential}=.+$" <<< "$decrypted"; then
        echo "Encrypted environment has an empty required credential: $required_credential" >&2
        exit 1
    fi
done

REMOTE_INSTALL_COMMAND="$(cat <<'REMOTE_COMMAND'
sudo -n sh -c 'set -eu; umask 077; install -d -o root -g root -m 700 /etc/countyiq; temporary=$(mktemp /etc/countyiq/.production.env.XXXXXX); trap "rm -f -- $temporary" EXIT; cat > "$temporary"; chown root:root "$temporary"; chmod 600 "$temporary"; mv -f -- "$temporary" /etc/countyiq/production.env; trap - EXIT'
REMOTE_COMMAND
)"
printf '%s\n' "$decrypted" | ssh \
    -i "$SSH_KEY" \
    -o BatchMode=yes \
    -o StrictHostKeyChecking=yes \
    "$REMOTE_HOST" \
    "$REMOTE_INSTALL_COMMAND"
unset decrypted
unset REMOTE_INSTALL_COMMAND

ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes \
    "$REMOTE_HOST" \
    "sudo -n sh -c 'test \"\$(stat -Lc %U:%G /etc/countyiq/production.env)\" = root:root && test \"\$(stat -Lc %a /etc/countyiq/production.env)\" = 600'"
echo "Published root-only production environment to $REMOTE_HOST:/etc/countyiq/production.env"
