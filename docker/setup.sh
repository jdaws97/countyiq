#!/bin/bash
# Initial VPS provisioning script for CountyIQ
# Run as root on a fresh Ubuntu 24.04 Hetzner CX23

set -euo pipefail

echo "=== CountyIQ VPS Setup ==="

# System updates
apt update && apt upgrade -y

# Install Docker
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    echo "Docker installed"
else
    echo "Docker already installed"
fi

# Install rclone
if ! command -v rclone &> /dev/null; then
    curl https://rclone.org/install.sh | bash
    echo "rclone installed"
else
    echo "rclone already installed"
fi

# Create app directory
mkdir -p /opt/countyiq
echo "Created /opt/countyiq"

# Reminder for manual steps
echo ""
echo "=== Manual steps remaining ==="
echo "1. Clone repo:        cd /opt/countyiq && git clone https://github.com/jarod/countyiq.git ."
echo "2. Create .env:       cp .env.example .env && nano .env"
echo "3. Configure rclone:  rclone config (add R2 remote)"
echo "4. Start services:    cd docker && docker compose up -d"
echo "5. Init database:     docker exec -i countyiq-postgres psql -U dagster_admin -d countyiq < pipelines/init-db/01-extensions-schemas.sql"
echo "6. Run migrations:    docker exec countyiq-dagster alembic upgrade head"
echo "7. Create dagster db: docker exec countyiq-postgres createdb -U dagster_admin dagster"
echo "8. Setup backup cron: crontab -e → 0 4 * * * /opt/countyiq/docker/backup.sh >> /var/log/countyiq-backup.log 2>&1"
