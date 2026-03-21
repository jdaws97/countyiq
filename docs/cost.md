# Cost Breakdown

## Cost Breakdown

### Year 1 (Free Tier Active)

| Resource | Monthly Cost |
|---|---|
| EC2 t3.micro | $0.00 |
| RDS db.t3.micro (PostgreSQL 16) | $0.00 |
| EBS 20 GB gp3 (EC2) | $0.00 |
| RDS 20 GB gp3 storage | $0.00 |
| RDS automated backups (20 GB) | $0.00 |
| S3 (raw data + static site + tiles, < 5 GB) | $0.00 |
| CloudFront (< 1 TB transfer) | $0.00 (free tier: 1 TB/month) |
| API Gateway (< 1M calls) | $0.00 (free tier: 1M/month) |
| Lambda (< 1M requests) | $0.00 (permanent free tier) |
| Session Manager | $0.00 |
| CloudWatch Logs (~500 MB/month ingest) | $0.00 (free tier: 5 GB) |
| CloudWatch Alarms (5) | $0.00 (free tier: 10) |
| SNS (email) | $0.00 |
| Budgets (1) | $0.00 (free tier: 2) |
| S3 state locking | $0.00 (included in S3) |
| WAF | **$0.00 — deferred to public launch** |
| **Total** | **$0.00/month** |

> **WAF is deferred.** The Terraform for WAF is written but not applied at MVP (~$6.60/month when enabled). Add it when the platform goes public. Year 1 cost is $0 with free tier covering all active services.

### Year 2+ (Post Free Tier)

| Resource | Monthly Cost |
|---|---|
| EC2 t3.micro (on-demand) | $7.49 |
| RDS db.t3.micro (on-demand) | $12.41 |
| EBS 20 GB gp3 (EC2) | $1.60 |
| RDS 20 GB gp3 storage | $1.60 |
| RDS backup storage (20 GB, beyond free allocation) | $0.00 (first 100% of DB size is free) |
| S3 (est. 10 GB across all buckets) | $0.23 |
| CloudFront (est. 10–50 GB transfer) | $0.85–4.25 |
| API Gateway (est. 10K–100K calls) | $0.04–0.35 |
| Lambda (within permanent free tier for low traffic) | $0.00 |
| CloudWatch Logs (~500 MB ingest + storage) | $0.25–0.50 |
| CloudWatch Alarms (5) | $0.50 |
| SNS | $0.00 |
| Budgets | $0.00 |
| S3 state locking | ~$0.00 |
| WAF (1 Web ACL + 1 rule + request inspection) | ~$6.60 |
| **Total** | **~$32–36/month** |

### Year 2+ Cost Reduction Options

If $24–25/month feels steep after free tier expires, consider:

| Option | Savings | Notes |
|---|---|---|
| RDS Reserved Instance (1-year, no upfront) | ~35% on RDS compute | Drops RDS to ~$8/month |
| EC2 Reserved Instance (1-year, no upfront) | ~35% on EC2 compute | Drops EC2 to ~$5/month |
| Both reserved | Combined ~$13/month total | vs ~$20 on-demand for both |
| Migrate to db.t4g.micro (Graviton/ARM) | ~15% cheaper | $10.66/month on-demand |

**With both 1-year reserved instances: ~$22–24/month total for the entire platform (including WAF).**

---
