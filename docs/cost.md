# Cost Breakdown

## Cost Breakdown

### Year 1 (Free Tier Active)

| Resource | Monthly Cost |
|---|---|
| EC2 t3.micro | $0.00 (750 hrs/mo free) |
| Public IPv4 address | $0.00 (750 hrs/mo free for 12 months) |
| RDS db.t3.micro (PostgreSQL 16) | $0.00 (750 hrs/mo free) |
| EBS 20 GB gp3 (EC2) | $0.00 (30 GB free) |
| RDS 20 GB gp3 storage | $0.00 (20 GB free) |
| RDS automated backups (20 GB) | $0.00 |
| S3 (raw data + static site + tiles, < 5 GB) | $0.00 (5 GB free) |
| CloudFront (< 1 TB transfer) | $0.00 (1 TB/mo free) |
| API Gateway (< 1M calls) | $0.00 (1M/mo free) |
| Lambda (< 1M requests) | $0.00 (permanent free tier) |
| CloudFront Function | $0.00 (2M invocations/mo free, permanent) |
| Session Manager | $0.00 |
| CloudWatch Logs (~500 MB/month ingest) | $0.00 (5 GB free) |
| CloudWatch Alarms (5) | $0.00 (10 free) |
| SNS (email) | $0.00 |
| Budgets (1) | $0.00 (2 free) |
| S3 state locking | $0.00 |
| **Total** | **$0.00/month** |

> **WAF is deferred.** Add it when the platform goes public (~$6.60/month). See `docs/infrastructure/waf.md`.

### Year 2+ (Post Free Tier)

| Resource | Monthly Cost |
|---|---|
| EC2 t3.micro (on-demand, $0.0104/hr) | $7.59 |
| Public IPv4 address ($0.005/hr, since Feb 2024) | $3.65 |
| RDS db.t3.micro (on-demand, $0.018/hr) | $13.14 |
| EBS 20 GB gp3 (EC2, $0.08/GB) | $1.60 |
| RDS 20 GB gp3 storage ($0.115/GB) | $2.30 |
| RDS automated backups (20 GB) | $0.00 (first 100% of DB size free) |
| CloudWatch Alarms (5, $0.10/alarm) | $0.50 |
| **Fixed subtotal** | **$28.78** |
| S3 (est. 10 GB across all buckets) | ~$0.23 |
| CloudFront (est. 10–50 GB transfer) | ~$0.85–4.25 |
| API Gateway (est. 10K–100K calls) | ~$0.04–0.35 |
| CloudWatch Logs (~500 MB ingest + storage) | ~$0.25–0.50 |
| Lambda, SNS, Budgets, SSM, EventBridge | $0.00 |
| **Realistic steady state** | **~$30–35/month** |

> **Note:** RDS gp3 storage pricing ($0.115/GB) is higher than EBS gp3 ($0.08/GB). The public IPv4 charge applies to any EC2 instance with a public IP in the default VPC (required for outbound internet without a NAT Gateway).

> **WAF adds ~$6.60/month** when enabled (1 Web ACL + 1 rate-based rule + request inspection). Budget ~$37–42/month with WAF.

### Cost Mitigation Built Into Terraform

| Mitigation | What it prevents |
|---|---|
| EC2 and RDS pinned to same AZ | Cross-AZ data transfer ($0.01/GB each direction) |
| Raw bucket: no lifecycle rule (intentional) | Historical snapshots kept indefinitely for replay/audit (~$0.35/mo at 15 GB) |
| Lambda reserved concurrency capped at 10 | Runaway Lambda invocations |
| No NAT Gateway | $32/month avoided |
| No VPC Endpoints | $7/month each avoided |

### Year 2+ Cost Reduction Options

| Option | Savings | Notes |
|---|---|---|
| RDS Reserved Instance (1-year, no upfront) | ~35% on RDS compute | Drops RDS to ~$8.50/month |
| EC2 Reserved Instance (1-year, no upfront) | ~35% on EC2 compute | Drops EC2 to ~$4.90/month |
| Both reserved | Combined ~$13.40/month total | vs ~$20.73 on-demand for both |
| Migrate to db.t4g.micro (Graviton/ARM) | ~15% cheaper | ~$11.17/month on-demand |

**With both 1-year reserved instances: ~$25–28/month total (without WAF), ~$32–35/month (with WAF).**

---
