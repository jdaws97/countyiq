#!/bin/bash
# CountyIQ VPS provisioning script
# Run as root on a fresh Ubuntu 24.04 VPS (Hostinger, Hetzner, or similar)
#
# Prerequisites:
#   - Add your SSH public key to the VPS provider before creating the server
#   - Add a deploy key to the GitHub repo (read-only)
#
# Usage:
#   ssh root@<VPS_IP>
#   curl -sL https://raw.githubusercontent.com/jarod/countyiq/main/docker/setup.sh | bash
#   (or copy this script to the server and run it)

set -euo pipefail

echo "=== CountyIQ VPS Setup ==="

# 1. System updates
echo "[1/6] Updating system..."
apt update && apt upgrade -y

# 2. Install Docker
if ! command -v docker &> /dev/null; then
    echo "[2/6] Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
else
    echo "[2/6] Docker already installed"
fi

# 3. Install rclone
if ! command -v rclone &> /dev/null; then
    echo "[3/6] Installing rclone..."
    curl https://rclone.org/install.sh | bash
else
    echo "[3/6] rclone already installed"
fi

# 4. Fix docker config (prevent watchtower mount errors)
echo "[4/6] Setting up Docker config..."
rm -rf /root/.docker/config.json
mkdir -p /root/.docker
echo '{}' > /root/.docker/config.json

# 5. Clone repo
echo "[5/6] Cloning repository..."
mkdir -p /opt/countyiq
cd /opt/countyiq
if [ ! -d ".git" ]; then
    git clone git@github.com:jarod/countyiq.git .
else
    echo "Repo already cloned, pulling latest..."
    git pull
fi

# 6. Setup .env
echo "[6/6] Setting up environment..."
if [ ! -f .env ]; then
    cp .env.example .env
    # Generate a random password
    DB_PASS=$(openssl rand -base64 24)
    sed -i "s/CHANGE_ME_STRONG_PASSWORD/$DB_PASS/g" .env
    mkdir -p /opt/countyiq/archives
    echo "Generated database password and wrote .env"
    echo ">>> SAVE THIS PASSWORD: $DB_PASS"
else
    echo ".env already exists, skipping"
fi

# Symlink .env into docker/ for compose variable interpolation
ln -sf /opt/countyiq/.env /opt/countyiq/docker/.env

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Next steps:"
echo "  1. Review .env:          nano /opt/countyiq/.env"
echo "  2. Start services:       cd /opt/countyiq/docker && docker compose up -d"
echo "  3. Wait for healthy:     docker compose ps  (wait for all 'healthy')"
echo "  4. Create dagster DB:    docker exec countyiq-postgres createdb -U dagster_admin dagster"
echo "  5. Init schemas:         docker exec -i countyiq-postgres psql -U dagster_admin -d countyiq < /opt/countyiq/pipelines/init-db/01-extensions-schemas.sql"
echo "  6. Run migrations:       docker exec countyiq-dagster alembic upgrade head"
echo "  7. Verify API:           curl -s http://localhost:8000/api/health"
echo "  8. Setup firewall:       Provider firewall / security group -> TCP 22, 80, 443"
echo "  9. Setup backup cron:    crontab -e → 0 4 * * * /opt/countyiq/docker/backup.sh >> /var/log/countyiq-backup.log 2>&1"
