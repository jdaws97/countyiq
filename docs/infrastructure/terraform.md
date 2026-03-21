# Terraform Project Structure

## Terraform Project Structure

```
infra/
├── main.tf                    # Provider config, backend, module calls
├── variables.tf               # Top-level input variables
├── terraform.tfvars           # Actual values (GITIGNORED)
├── outputs.tf                 # Instance ID, connection commands, S3 bucket name
├── backend.tf                 # S3 remote state configuration
│
├── modules/
│   ├── networking/
│   │   ├── main.tf            # Security groups (EC2 + RDS), subnet group
│   │   ├── variables.tf
│   │   └── outputs.tf         # Security group IDs, default VPC/subnet IDs, subnet group name
│   │
│   ├── iam/
│   │   ├── main.tf            # Instance profile, role, policies
│   │   ├── variables.tf
│   │   └── outputs.tf         # Instance profile ARN
│   │
│   ├── database/
│   │   ├── main.tf            # RDS instance, parameter group
│   │   ├── variables.tf       # Instance class, storage, credentials
│   │   ├── outputs.tf         # RDS endpoint, port, database name
│   │   └── init.sql           # Post-provisioning initialization script
│   │
│   ├── compute/
│   │   ├── main.tf            # EC2 instance, EBS
│   │   ├── variables.tf
│   │   ├── outputs.tf         # Instance ID, SSM connect command
│   │   └── user_data.sh       # Bootstrap script
│   │
│   ├── frontend/
│   │   ├── main.tf            # S3 static site, CloudFront, ACM cert
│   │   ├── variables.tf
│   │   └── outputs.tf         # CloudFront URL, S3 bucket name
│   │
│   ├── api/
│   │   ├── main.tf            # Lambda function, API Gateway, IAM role
│   │   ├── variables.tf
│   │   └── outputs.tf         # API Gateway URL, Lambda function name
│   │
│   └── monitoring/
│       ├── main.tf            # Budgets, alarms, SNS, log groups
│       ├── variables.tf
│       └── outputs.tf         # SNS topic ARN, budget name
│
└── .gitignore                 # terraform.tfvars, .terraform/, *.tfstate*
```

### State Backend (bootstrap manually before first `terraform apply`)

```
S3 bucket:    countyiq-terraform-state
Locking:      S3 native (use_lockfile = true, requires Terraform >= 1.10)
Region:       us-east-1
Encryption:   AES-256 (SSE-S3)
Versioning:   Enabled
```

**Bootstrap steps** (one-time, done via AWS CLI before Terraform):
1. Create the S3 bucket for state (with versioning enabled)
2. Run `terraform init` with the backend config

---
