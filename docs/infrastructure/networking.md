# Networking & IAM

## Module: Networking

### What it creates

| Resource | Configuration |
|---|---|
| Data source: default VPC | References `aws_vpc.default` |
| Data source: default VPC subnets | For EC2, RDS, and Lambda placement (public subnets with internet gateway, but no public IPs assigned to RDS/Lambda) |
| Security group: `dagster-ec2-sg` | **No inbound rules** (Session Manager needs none); all outbound allowed |
| Security group: `api-lambda-sg` | **No inbound rules** (invoked by API Gateway, not network); outbound to RDS |
| Security group: `dagster-rds-sg` | Inbound PostgreSQL (5432) **from `dagster-ec2-sg` and `api-lambda-sg`** |
| RDS subnet group: `dagster-rds-subnets` | Default VPC subnets (minimum 2 AZs required by RDS) |

### Security group relationship

```
┌──────────────────┐         ┌──────────────────┐
│  dagster-ec2-sg  │         │  dagster-rds-sg   │
│                  │         │                   │
│  Inbound: NONE   │────────▶│  Inbound: 5432    │
│  Outbound: ALL   │  (ref)  │  from ec2-sg      │
│                  │         │  AND lambda-sg    │
└──────────────────┘         │  Outbound: NONE   │
                             └──────────────────┘
┌──────────────────┐                  ▲
│  api-lambda-sg   │                  │
│                  │──────────────────┘
│  Inbound: NONE   │  (ref)
│  Outbound: 5432  │
│   to rds-sg only │
└──────────────────┘
```

Both the EC2 security group and the Lambda security group are allowed to reach RDS on port 5432. Lambda's outbound is scoped to only RDS — it doesn't need general internet access since it's only querying the database. RDS and Lambda security is enforced by security groups (which services can connect), not by subnet isolation — they run in the default VPC's public subnets.

**⚠️ VPC networking constraint:** Lambda in a VPC can reach RDS (private), but CANNOT reach AWS service endpoints (Parameter Store, CloudWatch API, etc.) without either a NAT Gateway (~$32/month) or VPC Endpoints (~$7/month each). To avoid this cost:

1. **RDS credentials:** Passed to Lambda as encrypted environment variables (set by Terraform, encrypted with default KMS key). Lambda does NOT call Parameter Store at runtime.
2. **CloudWatch Logs:** Lambda's built-in log shipping works regardless of VPC placement (handled by the Lambda control plane, not the function's network path).
3. **CloudWatch metrics for /ops/health:** Lambda does NOT call the CloudWatch API. Instead, a Dagster sensor on EC2 polls CloudWatch every 5 minutes and writes infra metrics to a `meta.infra_metrics` table in RDS. The /ops/health endpoint queries only RDS.

This means Lambda has exactly one network dependency: RDS on port 5432. No NAT Gateway, no VPC Endpoints, no extra cost.

### Why no inbound rules on EC2

Session Manager connects through the SSM agent on the instance, which initiates an **outbound** connection to the SSM service endpoint. No inbound ports need to be open — not even SSH. This is the primary security advantage over traditional SSH access.

---

## Module: IAM

### Resources

| Resource | Purpose |
|---|---|
| IAM Role: `dagster-ec2-role` | Assumed by EC2 instance |
| Instance Profile: `dagster-instance-profile` | Attaches role to EC2 |
| Managed Policy: `AmazonSSMManagedInstanceCore` | Required for Session Manager |
| Managed Policy: `CloudWatchAgentServerPolicy` | Required for memory/disk metrics |
| Inline Policy: `dagster-s3-access` | Read/write to the raw data S3 bucket only |
| Inline Policy: `dagster-ssm-params` | Read-only access to Parameter Store (for RDS credentials) |

### GitHub Actions OIDC Role

GitHub Actions authenticates to AWS via OIDC federation — no stored credentials.

| Resource | Value |
|---|---|
| OIDC Provider | `token.actions.githubusercontent.com` |
| IAM Role | `countyiq-github-actions` |
| Trust Policy | Only `jarod/countyiq` repo, `main` branch |

The role needs permissions for: S3 (frontend + tiles upload), Lambda (update function code), SSM (send-command to EC2 for Dagster deploys). These are scoped to specific resource ARNs — see `docs/infrastructure/cicd.md` for the deploy workflow details.

This role is created in the `cicd` Terraform module (`infra/modules/cicd/`). It is NOT in the networking or IAM module.

### S3 Policy (scoped to single bucket)

```json
{
  "Effect": "Allow",
  "Action": [
    "s3:GetObject",
    "s3:PutObject",
    "s3:ListBucket"
  ],
  "Resource": [
    "arn:aws:s3:::countyiq-raw",
    "arn:aws:s3:::countyiq-raw/*"
  ]
}
```

### Parameter Store Policy

```json
{
  "Effect": "Allow",
  "Action": [
    "ssm:GetParameter",
    "ssm:GetParameters"
  ],
  "Resource": "arn:aws:ssm:us-east-1:*:parameter/countyiq/*"
}
```

---
