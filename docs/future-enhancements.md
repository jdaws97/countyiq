# Future Enhancements

## Future Enhancements (Not Implemented)

These are documented for future reference. None are needed for the MVP.

### 1. Automated Cost Kill Switch

**Concept:** A Lambda function triggered by a Budget Action (via SNS) that automatically stops the EC2 instance when spend exceeds a threshold (e.g., $80). This provides a hard stop beyond email alerts.

**Implementation outline:**
- Budget Action triggers SNS topic at $80 threshold
- SNS triggers Lambda function
- Lambda calls `ec2:StopInstances` on the Dagster instance
- Optional: Lambda also attaches a deny-all IAM policy to freeze all resource access
- CloudWatch alarm detects instance stopped → sends notification email

**Why deferred:** Email alerts at $10/$25/$50/$75 provide adequate early warning. The $100 account credit and free tier make runaway costs unlikely in Year 1. Revisit if costs become less predictable.

### 2. NAIP Imagery Pipeline (Phase 2)

**Concept:** Download NAIP orthophotos for York County, store in S3, and serve as a tile layer for change detection analysis.

**Estimated storage:** 10–20 GB per year of coverage, 30–60 GB for multi-year comparison.

### 3. Upgrade to t3.small

**Trigger:** Consistent memory usage > 80% as reported by CloudWatch alarms, especially during concurrent Playwright jobs.

**Cost impact:** $14.98/month (vs $7.49 for t3.micro) post free tier.

### 4. Private VPC with NAT Gateway

**Trigger:** Security requirements demand the EC2 instance has no public IP at all.

**Cost impact:** NAT Gateway costs ~$32/month. Not justified for current scale.

### 5. Dagster Cloud Hybrid

**Trigger:** Need for multi-user access to Dagster UI, or desire to offload webserver/daemon hosting.

**Cost:** Free tier available (limited concurrent runs).

### 6. ALB + Cognito for Dagster UI

**Trigger:** Multiple users need browser access to Dagster UI without SSH/Session Manager.

**Cost:** ALB ~$16/month minimum + Cognito (free tier: 50,000 MAU).

### 7. WAF Rate Limiting on CloudFront

**Trigger:** Platform goes public and needs protection against API abuse, scraping, or DDoS.

**Cost:** ~$6.60/month (1 Web ACL + 1 rate-based rule + request inspection at ~1M req/month).

**Implementation:** Terraform is documented in `docs/infrastructure/waf.md`. Add `infra/modules/frontend/waf.tf` and set `web_acl_id` on the CloudFront distribution. Rate limit: 2,000 requests per 5 minutes per IP.

**Why deferred:** No public users at MVP. Lambda concurrency cap (10) and CloudFront itself already provide basic protection. Add WAF when the platform is publicly advertised.
