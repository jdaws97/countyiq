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
mkdir -p /opt/york-county
chown dagster:dagster /opt/york-county

# --- Create Python virtual environment ---
sudo -u dagster python3.11 -m venv /opt/york-county/venv

# --- Install Python packages ---
sudo -u dagster /opt/york-county/venv/bin/pip install --upgrade pip
sudo -u dagster /opt/york-county/venv/bin/pip install \
  dagster dagster-webserver dagster-postgres \
  psycopg2-binary \
  alembic \
  requests beautifulsoup4 \
  pdfplumber \
  playwright \
  boto3

# --- Install Playwright Chromium ---
sudo -u dagster /opt/york-county/venv/bin/playwright install chromium
/opt/york-county/venv/bin/playwright install-deps chromium

# --- Retrieve RDS credentials from Parameter Store ---
RDS_HOST=$(aws ssm get-parameter --name "/york-county/rds-host" --region "$AWS_REGION" --query "Parameter.Value" --output text)
RDS_PASSWORD=$(aws ssm get-parameter --name "/york-county/rds-password" --region "$AWS_REGION" --with-decryption --query "Parameter.Value" --output text)
RDS_DBNAME=$(aws ssm get-parameter --name "/york-county/rds-dbname" --region "$AWS_REGION" --query "Parameter.Value" --output text)
RDS_USERNAME=$(aws ssm get-parameter --name "/york-county/rds-username" --region "$AWS_REGION" --query "Parameter.Value" --output text)

# --- Write environment file ---
cat > /opt/york-county/.env << EOF
DATABASE_HOST=$RDS_HOST
DATABASE_NAME=$RDS_DBNAME
DATABASE_USER=$RDS_USERNAME
DATABASE_PASSWORD=$RDS_PASSWORD
DAGSTER_HOME=/opt/york-county
AWS_DEFAULT_REGION=$AWS_REGION
EOF
chown dagster:dagster /opt/york-county/.env
chmod 600 /opt/york-county/.env

# --- Clone application code ---
# Deploy key must be added to GitHub repo settings after first boot.
# For initial provisioning, clone via HTTPS (public) or set up deploy key first.
# The repo clone is attempted here; if it fails (private repo, no key yet),
# the init-gate below will still block Dagster from starting.
sudo -u dagster git clone https://github.com/jarod/countyiq.git /opt/york-county/repo || true

# Install the pipelines package if clone succeeded
if [ -d /opt/york-county/repo/pipelines ]; then
  sudo -u dagster /opt/york-county/venv/bin/pip install -e /opt/york-county/repo/pipelines
fi

# --- Write Dagster workspace config ---
cat > /opt/york-county/workspace.yaml << 'WORKSPACE'
load_from:
  - python_package: york_county
WORKSPACE
chown dagster:dagster /opt/york-county/workspace.yaml

# --- Write dagster.yaml (Postgres storage backend) ---
cat > /opt/york-county/dagster.yaml << DAGSTERYAML
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
chown dagster:dagster /opt/york-county/dagster.yaml
chmod 600 /opt/york-county/dagster.yaml

# --- Create systemd service: dagster-webserver ---
cat > /etc/systemd/system/dagster-webserver.service << 'EOF'
[Unit]
Description=Dagster Webserver
After=network.target
# Only start if init.sql has been run (creates the gate file)
ConditionPathExists=/opt/york-county/.initialized

[Service]
Type=simple
User=dagster
WorkingDirectory=/opt/york-county
Environment=DAGSTER_HOME=/opt/york-county
EnvironmentFile=/opt/york-county/.env
ExecStart=/opt/york-county/venv/bin/dagster-webserver -h 127.0.0.1 -p 3000
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
ConditionPathExists=/opt/york-county/.initialized

[Service]
Type=simple
User=dagster
WorkingDirectory=/opt/york-county
Environment=DAGSTER_HOME=/opt/york-county
EnvironmentFile=/opt/york-county/.env
ExecStart=/opt/york-county/venv/bin/dagster-daemon run
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# --- Create initialization helper script ---
# Run this after SSM-ing into the instance and running init.sql:
#   sudo /opt/york-county/initialize.sh
cat > /opt/york-county/initialize.sh << 'INITSCRIPT'
#!/bin/bash
set -euxo pipefail

source /opt/york-county/.env

# Step 1: Run init.sql — extensions, schemas, dagster database
# (Things Alembic can't own)
PGPASSWORD="$DATABASE_PASSWORD" psql \
  -h "$DATABASE_HOST" \
  -U "$DATABASE_USER" \
  -d "$DATABASE_NAME" \
  -f /opt/york-county/repo/infra/modules/database/init.sql

# Step 2: Run Alembic migrations — all table-level objects
# (staging.*, public.*, meta.*, functions, indexes)
export DATABASE_URL="postgresql://${DATABASE_USER}:${DATABASE_PASSWORD}@${DATABASE_HOST}:5432/${DATABASE_NAME}"
cd /opt/york-county/repo/pipelines
/opt/york-county/venv/bin/alembic upgrade head

# Step 3: Create the gate file so systemd services can start
touch /opt/york-county/.initialized

# Start Dagster services
systemctl daemon-reload
systemctl start dagster-webserver dagster-daemon

echo "Initialization complete. Dagster services started."
INITSCRIPT
chmod +x /opt/york-county/initialize.sh

# --- Install and configure CloudWatch Agent ---
dnf install -y amazon-cloudwatch-agent

cat > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json << 'CWCONFIG'
{
  "agent": {
    "metrics_collection_interval": 300,
    "run_as_user": "root"
  },
  "metrics": {
    "namespace": "YorkCounty/EC2",
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
            "log_group_name": "/york-county/system",
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
# CloudWatch Agent starts now; Dagster waits for /opt/york-county/.initialized
