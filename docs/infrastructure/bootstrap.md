# Bootstrap / User Data Script

## Bootstrap / User Data Script

The EC2 user data script runs on first boot and sets up the entire Dagster environment. This is referenced by the compute module as `user_data.sh`.

### What it installs

| Software | Purpose |
|---|---|
| Python 3.11+ | Dagster + pipeline code runtime |
| pip + venv | Python package management |
| Dagster (webserver, daemon, postgres client libs) | Orchestration |
| Playwright + Chromium | JavaScript-heavy scraping (eFACTS, CRIMEWATCH, PALS, Assessment) |
| pdfplumber | PDF table extraction (YCCD, commissioners minutes, YCPC reports) |
| BeautifulSoup4 + requests | HTML scraping + HTTP client |
| psycopg2-binary | PostgreSQL driver for RDS |
| Alembic | Schema migration management |
| CloudWatch Agent | Memory, disk, and process metrics |
| SSM Agent | Already included in Amazon Linux 2023 |

### What it configures

1. Creates a `dagster` system user (non-root)
2. Sets up a Python virtual environment at `/opt/york-county/venv`
3. Retrieves RDS credentials from Parameter Store
4. Clones the `jarod/countyiq` repo to `/opt/york-county/repo` and installs the pipelines package
5. Writes Dagster workspace and dagster.yaml configuration
6. Creates systemd services for `dagster-webserver` and `dagster-daemon` (enabled but **not started** — gated on `/opt/york-county/.initialized`)
7. Creates `/opt/york-county/initialize.sh` helper script (runs init.sql, creates gate file, starts Dagster)
8. Installs and configures CloudWatch Agent (memory, disk, and procstat metrics)

### Dagster as systemd services

```ini
# /etc/systemd/system/dagster-webserver.service
[Unit]
Description=Dagster Webserver
After=network.target
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
```

```ini
# /etc/systemd/system/dagster-daemon.service
[Unit]
Description=Dagster Daemon
After=network.target
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
```

**Note:** The webserver binds to `127.0.0.1:3000` (localhost only). It is not accessible from the network. Access is via Session Manager port forwarding.

### Initialization Gate

Both Dagster services have `ConditionPathExists=/opt/york-county/.initialized`. This prevents them from starting until the database has been initialized (extensions, schemas, `dagster` database). On first boot, cloud-init installs everything but Dagster stays stopped.

**To complete initialization after `terraform apply`:**

```bash
aws ssm start-session --target <instance-id>
sudo /opt/york-county/initialize.sh
```

This script runs `init.sql` against RDS, creates the gate file, and starts both Dagster services. On subsequent reboots, the gate file already exists and services start automatically.

### Accessing Dagster UI

```bash
# Start a port-forwarding session via Session Manager
aws ssm start-session \
  --target <instance-id> \
  --document-name AWS-StartPortForwardingSession \
  --parameters '{"portNumber":["3000"],"localPortNumber":["3000"]}'

# Then open in browser:
# http://localhost:3000
```

### Git Authentication for Deployments

The bootstrap script clones the repo via HTTPS to `/opt/york-county/repo` during first boot. For a **private** repo, you need to set up a deploy key for ongoing `git pull` operations (both manual and CI/CD):

1. SSM into the instance: `aws ssm start-session --target <instance-id>`
2. Generate a key: `sudo -u dagster ssh-keygen -t ed25519 -f /home/dagster/.ssh/countyiq_deploy -N ""`
3. Add the public key as a deploy key in GitHub → repo Settings → Deploy keys (read-only)
4. Configure SSH for the dagster user:
   ```
   # /home/dagster/.ssh/config
   Host github.com
     IdentityFile /home/dagster/.ssh/countyiq_deploy
   ```
5. Switch the remote to SSH: `cd /opt/york-county/repo && git remote set-url origin git@github.com:jarod/countyiq.git`

**CI/CD context:** The Dagster deploy workflow (Workflow 3 in `docs/infrastructure/cicd.md`) runs `git pull` on EC2 via SSM `send-command`. The deploy key enables this without storing a PAT or GitHub App credentials. The key lives only on the EC2 instance and grants read-only access to the single repo.

---
