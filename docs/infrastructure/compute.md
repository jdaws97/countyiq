# Compute & Monitoring

## Module: Compute

### EC2 Instance

| Setting | Value |
|---|---|
| AMI | Amazon Linux 2023 (latest, `al2023-ami-kernel-default-x86_64`) |
| Instance type | `t3.micro` (2 vCPU burstable, 1 GB RAM) |
| Subnet | Default VPC, `us-east-1a` (or any default subnet) |
| Security group | `dagster-ec2-sg` (no inbound — see Module: Networking) |
| IAM instance profile | `dagster-instance-profile` |
| EBS root volume | 20 GB gp3 (encrypted, `gp3` baseline: 3000 IOPS, 125 MB/s) |
| Monitoring | Detailed monitoring disabled (free tier basic is sufficient) |
| User data | Bootstrap script (see below) |
| Tags | `Name=countyiq-dagster`, `Project=countyiq`, `Environment=production` |

### Elastic IP

**Not using.** Session Manager doesn't need a static IP for access, and no data source requires IP whitelisting. The instance gets a dynamic public IP from the default VPC that works fine for outbound scraping. Add an Elastic IP later only if a data source requires a static IP (note: Elastic IPs now cost $3.65/month even on stopped instances as of Feb 2024).

### Key Pair

**Not needed.** Session Manager replaces SSH entirely. No key pair to generate, store, rotate, or lose.

---

## Module: Monitoring

### AWS Budgets

| Budget | Type | Threshold | Action |
|---|---|---|---|
| `countyiq-monthly` | Cost | Actual spend | Email alert at $10, $25, $50, $75 |
| (same budget) | Cost | Forecasted spend | Email alert if forecast exceeds $50 |

**Alert recipient:** jarod.daws@gmail.com (via SNS)

### CloudWatch Log Groups

| Log Group | Retention | Purpose |
|---|---|---|
| `/countyiq/dagster` | 7 days | Dagster webserver + daemon + run logs |
| `/countyiq/system` | 7 days | System logs (syslog, cloud-init) |

### CloudWatch Alarms

| Alarm | Metric | Threshold | Period | Action |
|---|---|---|---|---|
| `high-cpu` | CPUUtilization | > 80% for 15 min | 5 min | SNS notification |
| `high-memory` | mem_used_percent (CW Agent) | > 85% for 10 min | 5 min | SNS notification |
| `high-disk` | disk_used_percent (CW Agent) | > 80% | 5 min | SNS notification |
| `instance-status` | StatusCheckFailed | ≥ 1 | 5 min | SNS notification |
| `dagster-health` | Custom (process check) | 0 (process not running) | 5 min | SNS notification |

**Note:** Memory, disk, and process metrics require the CloudWatch Agent to be installed on the instance. EC2 basic monitoring only provides CPU, network, and disk I/O — not memory/disk usage percentage or process counts. The bootstrap script installs and configures the agent with `mem`, `disk`, and `procstat` (dagster process PID count) collection.

### SNS Topic

| Setting | Value |
|---|---|
| Topic name | `countyiq-alerts` |
| Protocol | Email |
| Endpoint | jarod.daws@gmail.com |

---
