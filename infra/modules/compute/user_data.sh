#!/bin/bash
set -euxo pipefail

AWS_REGION="${aws_region}"

# --- System updates ---
dnf update -y

# --- Create dagster system user ---
useradd --system --create-home --shell /bin/bash dagster

# --- Install Python 3.11 and development tools ---
dnf install -y python3.11 python3.11-pip python3.11-devel gcc gcc-c++ \
  postgresql16 git

# --- Set up application directory ---
mkdir -p /opt/countyiq
chown dagster:dagster /opt/countyiq

# --- Create Python virtual environment ---
sudo -u dagster python3.11 -m venv /opt/countyiq/venv

# --- Install Python packages ---
sudo -u dagster /opt/countyiq/venv/bin/pip install --upgrade pip
sudo -u dagster /opt/countyiq/venv/bin/pip install \
  dagster dagster-webserver dagster-postgres \
  psycopg2-binary \
  alembic \
  requests beautifulsoup4 \
  pdfplumber \
  playwright \
  boto3

# --- Install Playwright Chromium ---
sudo -u dagster /opt/countyiq/venv/bin/playwright install chromium
/opt/countyiq/venv/bin/playwright install-deps chromium

# --- Retrieve RDS credentials from Parameter Store ---
RDS_HOST=$(aws ssm get-parameter --name "/countyiq/rds-host" --region "$AWS_REGION" --query "Parameter.Value" --output text)
RDS_PASSWORD=$(aws ssm get-parameter --name "/countyiq/rds-password" --region "$AWS_REGION" --with-decryption --query "Parameter.Value" --output text)
RDS_DBNAME=$(aws ssm get-parameter --name "/countyiq/rds-dbname" --region "$AWS_REGION" --query "Parameter.Value" --output text)
RDS_USERNAME=$(aws ssm get-parameter --name "/countyiq/rds-username" --region "$AWS_REGION" --query "Parameter.Value" --output text)

# --- Write environment file ---
cat > /opt/countyiq/.env << EOF
DATABASE_HOST=$RDS_HOST
DATABASE_NAME=$RDS_DBNAME
DATABASE_USER=$RDS_USERNAME
DATABASE_PASSWORD=$RDS_PASSWORD
DAGSTER_HOME=/opt/countyiq
AWS_DEFAULT_REGION=$AWS_REGION
EOF
chown dagster:dagster /opt/countyiq/.env
chmod 600 /opt/countyiq/.env

# --- Clone application code ---
# Deploy key must be added to GitHub repo settings after first boot.
# For initial provisioning, clone via HTTPS (public) or set up deploy key first.
# The repo clone is attempted here; if it fails (private repo, no key yet),
# the init-gate below will still block Dagster from starting.
sudo -u dagster git clone https://github.com/jarod/countyiq.git /opt/countyiq/repo || true

# Install the pipelines package if clone succeeded
if [ -d /opt/countyiq/repo/pipelines ]; then
  sudo -u dagster /opt/countyiq/venv/bin/pip install -e /opt/countyiq/repo/pipelines
fi

# --- Write Dagster workspace config ---
cat > /opt/countyiq/workspace.yaml << 'WORKSPACE'
load_from:
  - python_package: countyiq
WORKSPACE
chown dagster:dagster /opt/countyiq/workspace.yaml

# --- Write dagster.yaml (Postgres storage backend) ---
cat > /opt/countyiq/dagster.yaml << DAGSTERYAML
run_storage:
  module: dagster_postgres.run_storage
  class: PostgresRunStorage
  config:
    postgres_db:
      hostname: $RDS_HOST
      username: $RDS_USERNAME
      password: $RDS_PASSWORD
      db_name: dagster
      port: 5432

event_log_storage:
  module: dagster_postgres.event_log
  class: PostgresEventLogStorage
  config:
    postgres_db:
      hostname: $RDS_HOST
      username: $RDS_USERNAME
      password: $RDS_PASSWORD
      db_name: dagster
      port: 5432

schedule_storage:
  module: dagster_postgres.schedule_storage
  class: PostgresScheduleStorage
  config:
    postgres_db:
      hostname: $RDS_HOST
      username: $RDS_USERNAME
      password: $RDS_PASSWORD
      db_name: dagster
      port: 5432
DAGSTERYAML
chown dagster:dagster /opt/countyiq/dagster.yaml
chmod 600 /opt/countyiq/dagster.yaml

# --- Create systemd service: dagster-webserver ---
cat > /etc/systemd/system/dagster-webserver.service << 'EOF'
[Unit]
Description=Dagster Webserver
After=network.target
# Only start if init.sql has been run (creates the gate file)
ConditionPathExists=/opt/countyiq/.initialized

[Service]
Type=simple
User=dagster
WorkingDirectory=/opt/countyiq
Environment=DAGSTER_HOME=/opt/countyiq
EnvironmentFile=/opt/countyiq/.env
ExecStart=/opt/countyiq/venv/bin/dagster-webserver -h 127.0.0.1 -p 3000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# --- Create systemd service: dagster-daemon ---
cat > /etc/systemd/system/dagster-daemon.service << 'EOF'
[Unit]
Description=Dagster Daemon
After=network.target
# Only start if init.sql has been run (creates the gate file)
ConditionPathExists=/opt/countyiq/.initialized

[Service]
Type=simple
User=dagster
WorkingDirectory=/opt/countyiq
Environment=DAGSTER_HOME=/opt/countyiq
EnvironmentFile=/opt/countyiq/.env
ExecStart=/opt/countyiq/venv/bin/dagster-daemon run
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# --- Create initialization helper script ---
# Run this after SSM-ing into the instance and running init.sql:
#   sudo /opt/countyiq/initialize.sh
cat > /opt/countyiq/initialize.sh << 'INITSCRIPT'
#!/bin/bash
set -euxo pipefail

source /opt/countyiq/.env

# Step 1: Run init.sql — extensions, schemas, dagster database
# (Things Alembic can't own)
PGPASSWORD="$DATABASE_PASSWORD" psql \
  -h "$DATABASE_HOST" \
  -U "$DATABASE_USER" \
  -d "$DATABASE_NAME" \
  -f /opt/countyiq/repo/infra/modules/database/init.sql

# Step 2: Run Alembic migrations — all table-level objects
# (staging.*, public.*, meta.*, functions, indexes)
export DATABASE_URL="postgresql://${DATABASE_USER}:${DATABASE_PASSWORD}@${DATABASE_HOST}:5432/${DATABASE_NAME}"
cd /opt/countyiq/repo/pipelines
/opt/countyiq/venv/bin/alembic upgrade head

# Step 3: Create the gate file so systemd services can start
touch /opt/countyiq/.initialized

# Start Dagster services
systemctl daemon-reload
systemctl start dagster-webserver dagster-daemon

echo "Initialization complete. Dagster services started."
INITSCRIPT
chmod +x /opt/countyiq/initialize.sh

# --- Install and configure CloudWatch Agent ---
dnf install -y amazon-cloudwatch-agent

cat > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json << 'CWCONFIG'
{
  "agent": {
    "metrics_collection_interval": 300,
    "run_as_user": "root"
  },
  "metrics": {
    "namespace": "CountyIQ/EC2",
    "metrics_collected": {
      "mem": {
        "measurement": ["mem_used_percent"],
        "metrics_collection_interval": 300
      },
      "disk": {
        "measurement": ["disk_used_percent"],
        "resources": ["/"],
        "metrics_collection_interval": 300
      },
      "procstat": [
        {
          "exe": "dagster",
          "measurement": ["pid_count"],
          "metrics_collection_interval": 300
        }
      ]
    }
  },
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/messages",
            "log_group_name": "/countyiq/system",
            "log_stream_name": "{instance_id}/syslog",
            "retention_in_days": 7
          }
        ]
      }
    }
  }
}
CWCONFIG

/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config -m ec2 \
  -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json -s

# --- Enable services (but do NOT start Dagster — blocked by ConditionPathExists) ---
systemctl daemon-reload
systemctl enable dagster-webserver dagster-daemon amazon-cloudwatch-agent
# CloudWatch Agent starts now; Dagster waits for /opt/countyiq/.initialized
