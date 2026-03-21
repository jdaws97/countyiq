# AWS Services Used

## AWS Infrastructure

### Account Details

- **Account:** Fresh account with $100 credit
- **Free tier:** 12 months from account creation
- **Region:** `us-east-1` (closest to York County, PA; cheapest region)

### Services Used

| Service | Purpose | Free Tier Allowance |
|---|---|---|
| EC2 (t3.micro) | Dagster + scrapers | 750 hrs/month for 12 months |
| RDS (db.t3.micro) | PostgreSQL 16 + PostGIS | 750 hrs/month for 12 months + 20 GB storage |
| EBS (gp3) | EC2 instance storage (20 GB) | 30 GB for 12 months |
| S3 | Raw data archival + static site hosting | 5 GB for 12 months |
| CloudFront | CDN + HTTPS for public frontend | 1 TB transfer/month for 12 months |
| API Gateway | REST API for frontend → Lambda | 1M calls/month for 12 months |
| Lambda | FastAPI backend for public API | 1M requests + 400K GB-sec/month (permanent free tier) |
| ACM | TLS certificate for HTTPS | Free (always) |
| Systems Manager | Instance access (Session Manager) | Free |
| CloudWatch Logs | Dagster + system logs | 5 GB ingest/month + 5 GB storage (free tier) |
| CloudWatch Alarms | Infrastructure health | 10 alarms free |
| SNS | Budget alert notifications | First 1,000 email notifications free |
| AWS Budgets | Cost monitoring | First 2 budgets free |
| AWS WAF | Rate limiting on CloudFront (2,000 req/5min per IP). ~$6.60/month. See `docs/infrastructure/waf.md` | No free tier |
| S3 (state locking) | Terraform state locking via S3 native `use_lockfile` (no DynamoDB needed). Effectively free. | Included in S3 pricing |
| IAM | Roles, policies, instance profiles | Free |
