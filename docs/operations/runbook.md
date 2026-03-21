# Operational Runbook

## Operational Runbook

### Daily operations (automated)

Dagster daemon evaluates schedules and sensors every 30 seconds. No manual intervention needed. Check Dagster UI periodically for failed runs.

### Checking Dagster status

```bash
# Connect to instance
aws ssm start-session --target <instance-id>

# Check services
sudo systemctl status dagster-webserver
sudo systemctl status dagster-daemon

# View recent logs
journalctl -u dagster-webserver --since "1 hour ago"
journalctl -u dagster-daemon --since "1 hour ago"
```

### Restarting Dagster

```bash
sudo systemctl restart dagster-webserver
sudo systemctl restart dagster-daemon
```

### Emergency stop (manual cost control)

```bash
# Stop the EC2 instance from your local machine
aws ec2 stop-instances --instance-ids <instance-id>

# Verify it stopped
aws ec2 describe-instances --instance-ids <instance-id> \
  --query 'Reservations[].Instances[].State.Name'
```

**Note:** Stopping the instance stops all Dagster jobs, scrapers, and scheduled runs. No data is lost — EBS volume persists. Restart with `aws ec2 start-instances`.

### Updating pipeline code

```bash
# Connect to instance
aws ssm start-session --target <instance-id>

# Pull latest code
cd /opt/countyiq/repo
git pull origin main

# Install updated package + run any pending database migrations
source /opt/countyiq/venv/bin/activate
pip install -e pipelines/
cd pipelines && alembic upgrade head

# Restart Dagster to pick up changes
sudo systemctl restart dagster-webserver
sudo systemctl restart dagster-daemon
```

### Monitoring RDS storage usage

```bash
# Check RDS storage from your local machine
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name FreeStorageSpace \
  --dimensions Name=DBInstanceIdentifier,Value=countyiq-db \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Average \
  --query 'Datapoints[0].Average'
```

Or check the RDS console in AWS. Plan to increase storage (online, no downtime) when usage exceeds 15 GB of 20 GB allocated.

### Connecting to the database

```bash
# Port-forward RDS through EC2 via Session Manager
aws ssm start-session \
  --target <instance-id> \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters '{"host":["<rds-endpoint>"],"portNumber":["5432"],"localPortNumber":["5433"]}'

# In another terminal, connect with psql or any SQL client
psql -h localhost -p 5433 -U dagster_admin -d countyiq
```

### Rollback procedures

**Bad Lambda deploy (API broken):**

```bash
# Lambda keeps previous versions. Roll back to the last working version:
aws lambda update-function-code \
  --function-name countyiq-api \
  --s3-bucket <if using S3 deploy> \
  # Or re-deploy from git:
cd api/
git checkout HEAD~1 -- .
pip install -r requirements.txt -t package/
cp -r *.py routes/ lib/ package/
cd package && zip -r ../lambda.zip .
aws lambda update-function-code \
  --function-name countyiq-api \
  --zip-file fileb://lambda.zip
```

**Bad Dagster deploy (pipelines broken):**

```bash
# On EC2 via SSM:
aws ssm start-session --target <instance-id>

cd /opt/countyiq/repo
git log --oneline -5                    # Find the last good commit
git checkout <last-good-sha>            # Roll back
source /opt/countyiq/venv/bin/activate
pip install -e pipelines/
sudo systemctl restart dagster-webserver dagster-daemon
```

**Bad migration (schema broken):**

```bash
# Alembic supports reversible migrations:
cd /opt/countyiq/repo/pipelines
source /opt/countyiq/venv/bin/activate

# See current migration state
alembic current

# Roll back one migration
alembic downgrade -1

# If the downgrade itself fails, restore from RDS point-in-time recovery:
# AWS Console → RDS → Restore to point in time → pick a timestamp before the migration
```

**Corrupted pipeline data (bad scrape wrote garbage):**

```bash
# SCD Type 2 means bad records don't overwrite good ones — they create new rows.
# Fix by marking the bad rows as superseded:
UPDATE staging.<table>
SET valid_to = NOW()
WHERE valid_from > '<timestamp-of-bad-run>'
AND valid_to IS NULL;

# The previous good rows (with valid_to = timestamp of the bad run) are still there.
# Re-run the pipeline to get fresh data.
```

**Frontend broken (bad React build):**

```bash
# Re-deploy from the previous commit:
cd frontend
git checkout HEAD~1 -- .
npm run build
aws s3 sync dist/ s3://countyiq-frontend --delete
aws cloudfront create-invalidation --distribution-id <dist-id> --paths "/*"
```
