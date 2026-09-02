#!/bin/bash
# CountyIQ VPS provisioning script
# Run as root on a fresh Ubuntu 24.04 Hetzner VPS (Netcup fallback)
#
# Prerequisites:
#   - Add your SSH public key to the VPS provider before creating the server
#   - Add a deploy key to the GitHub repo (read-only)
#   - Install GitHub's published SSH host keys in /root/.ssh/known_hosts after
#     verifying them through an independent channel
#
# Usage: copy this reviewed script to the host, then run it with the full
# commit SHA that has been approved for deployment:
#   sudo COUNTYIQ_DEPLOY_REF=<40-character-commit-sha> ./setup.sh

set -euo pipefail
umask 077

DEPLOY_REF="${COUNTYIQ_DEPLOY_REF:-}"
if [[ ! "$DEPLOY_REF" =~ ^[0-9a-f]{40}$ ]]; then
    echo "COUNTYIQ_DEPLOY_REF must be the reviewed 40-character Git commit SHA" >&2
    exit 1
fi

echo "=== CountyIQ VPS Setup ==="

# 1. System updates
echo "[1/5] Updating system and installing signed Ubuntu packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get upgrade -y
apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    docker-compose-v2 \
    docker.io \
    git \
    openssl \
    openssh-client \
    postgresql-client \
    rclone \
    util-linux \
    unattended-upgrades

# 2. Install Docker
echo "[2/5] Enabling Docker and unattended security updates..."
systemctl enable --now docker
systemctl enable --now unattended-upgrades

# 4. Clone repo
echo "[3/5] Checking out reviewed repository revision..."
if [ ! -f /root/.ssh/known_hosts ] \
    || ! ssh-keygen -F github.com -f /root/.ssh/known_hosts >/dev/null; then
    echo "Install GitHub's independently verified SSH host keys in /root/.ssh/known_hosts" >&2
    echo "Refusing an interactive trust-on-first-use repository clone" >&2
    exit 1
fi
export GIT_SSH_COMMAND="ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/root/.ssh/known_hosts"
mkdir -p /opt/countyiq
cd /opt/countyiq
if [ ! -d ".git" ]; then
    git clone git@github.com:jarod/countyiq.git .
else
    if [ -n "$(git status --porcelain --untracked-files=all)" ]; then
        echo "Refusing to replace a dirty deployment checkout" >&2
        exit 1
    fi
    git fetch origin --prune
fi
git checkout --detach "$DEPLOY_REF"
if [ "$(git rev-parse HEAD)" != "$DEPLOY_REF" ]; then
    echo "Checked-out commit does not match COUNTYIQ_DEPLOY_REF" >&2
    exit 1
fi

# 5. Setup .env
echo "[4/5] Setting up environment..."
if [ -L .env ]; then
    echo "Refusing a symlinked production environment file" >&2
    exit 1
fi
if [ ! -f .env ]; then
    cp .env.example .env
    DB_PASS=$(openssl rand -hex 32)
    PIPELINE_DB_PASS=$(openssl rand -hex 32)
    API_DB_PASS=$(openssl rand -hex 32)
    sed -i "s/CHANGE_ME_STRONG_PASSWORD/$DB_PASS/g" .env
    sed -i "s/CHANGE_ME_PIPELINE_PASSWORD/$PIPELINE_DB_PASS/g" .env
    sed -i "s/CHANGE_ME_API_PASSWORD/$API_DB_PASS/g" .env
    chmod 600 .env
    echo "Generated independent database credentials in root-readable .env"
else
    chmod 600 .env
    if ! grep -q '^DATABASE_PIPELINE_USER=' .env; then
        printf '\nDATABASE_PIPELINE_USER=countyiq_pipeline\n' >> .env
    fi
    if ! grep -q '^DATABASE_PIPELINE_PASSWORD=' .env; then
        printf 'DATABASE_PIPELINE_PASSWORD=%s\n' "$(openssl rand -hex 32)" >> .env
    elif grep -Eq '^DATABASE_PIPELINE_PASSWORD=(|CHANGE_ME_PIPELINE_PASSWORD)$' .env; then
        sed -i "s/^DATABASE_PIPELINE_PASSWORD=.*/DATABASE_PIPELINE_PASSWORD=$(openssl rand -hex 32)/" .env
    fi
    if ! grep -q '^DATABASE_API_USER=' .env; then
        printf 'DATABASE_API_USER=countyiq_api\n' >> .env
    fi
    if ! grep -q '^DATABASE_API_PASSWORD=' .env; then
        printf 'DATABASE_API_PASSWORD=%s\n' "$(openssl rand -hex 32)" >> .env
    elif grep -Eq '^DATABASE_API_PASSWORD=(|CHANGE_ME_API_PASSWORD)$' .env; then
        sed -i "s/^DATABASE_API_PASSWORD=.*/DATABASE_API_PASSWORD=$(openssl rand -hex 32)/" .env
    fi
    echo "Preserved existing .env and ensured separate runtime credentials exist"
fi
chown root:root .env
install -d -o 10001 -g 10001 -m 700 /opt/countyiq/archives
install -d -o root -g root -m 700 \
    /var/lib/countyiq/releases \
    /var/lib/countyiq/restore-drills

# Install the timer definition but do not enable it until the first backup has
# completed and restore-drill.sh has produced a receipt.
install -o root -g root -m 644 \
    /opt/countyiq/docker/systemd/countyiq-backup.service \
    /etc/systemd/system/countyiq-backup.service
install -o root -g root -m 644 \
    /opt/countyiq/docker/systemd/countyiq-backup.timer \
    /etc/systemd/system/countyiq-backup.timer
systemctl daemon-reload

# Symlink .env into docker/ for compose variable interpolation
ln -sf /opt/countyiq/.env /opt/countyiq/docker/.env

echo "[5/5] Validating Compose configuration..."
docker compose -f /opt/countyiq/docker/docker-compose.yml config --quiet

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Next steps:"
echo "  1. Review .env:          nano /opt/countyiq/.env"
echo "  2. Create the private R2 backup bucket and fill the R2/backup variables."
echo "     Enable bucket lock + lifecycle, then set COUNTYIQ_BACKUP_BUCKET_LOCK_CONFIRMED=true."
echo "  3. Initial release:      sudo env COUNTYIQ_DEPLOY_REF=$DEPLOY_REF COUNTYIQ_ENV_FILE=/opt/countyiq/.env /opt/countyiq/docker/deploy.sh --initial"
echo "  4. Backup current state: sudo /opt/countyiq/docker/backup.sh --reason restore-drill"
echo "  5. Restore that exact ID with /opt/countyiq/docker/restore-drill.sh --backup-id <id>."
echo "  6. Enable backups:       systemctl enable --now countyiq-backup.timer"
echo "  7. Verify timer:         systemctl list-timers countyiq-backup.timer"
echo "  8. Restrict origin TCP 80/443 to Cloudflare's published IP ranges; keep SSH key-only."
echo "  9. Enable Hetzner server deletion/rebuild protection and backups; record a protected snapshot."
echo " 10. After DNS/TLS is live, set COUNTYIQ_PUBLIC_READY_URL=https://<DOMAIN>/api/ready."
