#!/bin/bash
# CountyIQ VPS provisioning script
# Run as root on a fresh Ubuntu 24.04 Hetzner VPS (Netcup fallback)
#
# Prerequisites:
#   - Add your SSH public key to the VPS provider before creating the server
#   - Add a deploy key to the GitHub repo (read-only)
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
    postgresql-client \
    rclone \
    unattended-upgrades

# 2. Install Docker
echo "[2/5] Enabling Docker and unattended security updates..."
systemctl enable --now docker
systemctl enable --now unattended-upgrades

# 4. Clone repo
echo "[3/5] Checking out reviewed repository revision..."
mkdir -p /opt/countyiq
cd /opt/countyiq
if [ ! -d ".git" ]; then
    git clone git@github.com:jarod/countyiq.git .
else
    git fetch origin --prune
fi
git checkout --detach "$DEPLOY_REF"
if [ "$(git rev-parse HEAD)" != "$DEPLOY_REF" ]; then
    echo "Checked-out commit does not match COUNTYIQ_DEPLOY_REF" >&2
    exit 1
fi

# 5. Setup .env
echo "[4/5] Setting up environment..."
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
install -d -o 10001 -g 10001 -m 700 /opt/countyiq/archives

# Symlink .env into docker/ for compose variable interpolation
ln -sf /opt/countyiq/.env /opt/countyiq/docker/.env

echo "[5/5] Validating Compose configuration..."
docker compose -f /opt/countyiq/docker/docker-compose.yml config --quiet

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Next steps:"
echo "  1. Review .env:          nano /opt/countyiq/.env"
echo "  2. Start Postgres:       cd /opt/countyiq/docker && docker compose up -d postgres"
echo "  3. Build runtime images: docker compose build --pull api dagster-webserver dagster-daemon"
echo "  4. Apply migrations:     docker compose run --rm migrate"
echo "  5. Refresh role grants:  docker compose exec -T postgres /docker-entrypoint-initdb.d/02-runtime-role.sh && docker compose exec -T postgres /docker-entrypoint-initdb.d/03-api-role.sh"
echo "  6. Start services:       docker compose up -d"
echo "  7. Verify readiness:     docker compose ps && docker compose exec -T api curl --fail http://localhost:8000/api/ready"
echo "  8. Restrict origin TCP 80/443 to Cloudflare's published IP ranges; keep SSH key-only."
echo "  9. Run the restore drill in docs/operations/backup-and-restore.md before adding the backup cron."
echo " 10. Setup backup cron:    0 4 * * * /opt/countyiq/docker/backup.sh >> /var/log/countyiq-backup.log 2>&1"
