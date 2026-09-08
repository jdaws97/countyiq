#!/usr/bin/env bash
# Transfer only monitoring assets; the application release remains independent.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SSH_KEY="${COUNTYIQ_SSH_KEY:-/home/jdaws/.ssh/jdawskey}"
REMOTE_HOST=ubuntu@15.204.255.199

tar -czf - -C "$SCRIPT_DIR" \
    pyproject.toml uv.lock collect.py probes.py retention.py config.alloy install.sh systemd \
    | ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes \
        "$REMOTE_HOST" \
        'sudo -n sh -c '\''set -eu; umask 077; stage=$(mktemp -d /var/tmp/countyiq-monitoring.XXXXXX); trap "rm -rf -- $stage" EXIT; tar -xzf - -C "$stage"; bash "$stage/install.sh"'\'''
