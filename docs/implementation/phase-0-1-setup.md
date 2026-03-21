# Phase 0–1: Environment Setup & Terraform Infrastructure

## Phase 0: Local Environment Setup

**Goal:** Your local machine has everything needed to develop, test, and deploy CountyIQ.

**Time estimate:** 30 minutes

### Step 0.1: Install Required Tools

| Tool | Version | Purpose |
|---|---|---|
| **Terraform** | >= 1.7 | Infrastructure as Code |
| **AWS CLI v2** | Latest | AWS account interaction |
| **Python** | 3.11 | Dagster pipelines, API (matches Lambda runtime) |
| **Node.js** | 20 LTS | React frontend |
| **Docker Desktop** | Latest | Local Postgres for migration testing |
| **Git** | Latest | Version control |
| **psql** (PostgreSQL client) | Latest | Database inspection via SSM tunnel |

```bash
# Verify all tools are installed
terraform --version
aws --version
python3 --version
node --version
docker --version
git --version
psql --version
```

### Step 0.2: Configure AWS CLI

```bash
aws configure
# AWS Access Key ID: <your-key>
# AWS Secret Access Key: <your-secret>
# Default region: us-east-1
# Default output format: json
```

> **Note:** This is the only time long-lived AWS credentials are used. GitHub Actions will use OIDC (no stored credentials). Your local CLI is for Terraform and SSM access.

### Step 0.3: Create the GitHub Repository

```bash
mkdir countyiq && cd countyiq
git init

# Create the monorepo structure
mkdir -p infra/modules/{networking,iam,compute,database,frontend,api,monitoring,cicd}
mkdir -p pipelines/york_county/{assets/{arcgis,scrapers,bulk,pdf,enrichment},lib/parsers,sensors,jobs,schedules,resources}
mkdir -p pipelines/{alembic/versions,tests/fixtures}
mkdir -p api/{routes,lib}
mkdir -p frontend
mkdir -p .github/workflows

# Create placeholder files
touch infra/main.tf infra/variables.tf infra/outputs.tf infra/terraform.tfvars
touch pipelines/pyproject.toml pipelines/setup.py pipelines/docker-compose.yml
touch pipelines/york_county/__init__.py pipelines/york_county/definitions.py
touch pipelines/alembic/alembic.ini pipelines/alembic/env.py
touch api/main.py api/handler.py api/requirements.txt
touch frontend/package.json
touch .gitignore README.md

# Initial commit
git add -A
git commit -m "Initial monorepo scaffold"
```

**`.gitignore` contents:**

```
# Terraform
*.tfstate
*.tfstate.backup
.terraform/
*.tfvars
!terraform.tfvars.example

# Python
__pycache__/
*.pyc
.venv/
*.egg-info/
dist/

# Node
node_modules/
frontend/dist/

# IDE
.vscode/
.idea/

# Environment
.env
.env.local

# OS
.DS_Store
```

### Step 0.4: Push to GitHub

```bash
gh repo create countyiq --private --source=. --push
```

> **Checkpoint:** `gh repo view` shows your repository. All directories exist. AWS CLI returns your account ID with `aws sts get-caller-identity`.

---

## Phase 1: AWS Account Bootstrap & Terraform Infrastructure

**Goal:** All AWS resources are provisioned and accessible. EC2 is running. RDS is available. S3 buckets exist. No application code is deployed yet.

**Time estimate:** 2-3 hours

**Prerequisites:** Phase 0 complete.

### Step 1.1: Create Terraform State Backend (Manual — One Time)

This is the one thing that can't be Terraformed because it's where Terraform stores its own state.

```bash
# Create S3 bucket for Terraform state
aws s3api create-bucket \
  --bucket countyiq-terraform-state \
  --region us-east-1

# Enable versioning (so you can recover from bad state)
aws s3api put-bucket-versioning \
  --bucket countyiq-terraform-state \
  --versioning-configuration Status=Enabled
```

> **Note:** No DynamoDB table needed. Terraform >= 1.10 supports S3 native locking via `use_lockfile = true`, which uses S3 conditional writes instead.

> **Checkpoint:** `aws s3 ls | grep countyiq` shows the bucket.

### Step 1.2: Write Terraform Backend Configuration

```hcl
# infra/backend.tf
terraform {
  backend "s3" {
    bucket       = "countyiq-terraform-state"
    key          = "prod/terraform.tfstate"
    region       = "us-east-1"
    use_lockfile = true
    encrypt      = true
  }
}
```

### Step 1.3: Write Terraform Modules

Implement each module using the code and specifications in the Infrastructure Plan. Build them in this order (each may reference outputs from previous modules):

| Order | Module | Infra Plan Reference Section | Key Resources |
|---|---|---|---|
| 1 | `networking` | Module: Networking | Security groups (dagster-ec2-sg, api-lambda-sg, dagster-rds-sg) |
| 2 | `iam` | Module: IAM | EC2 instance profile, managed policies (SSM, CloudWatch), inline policies (S3, Parameter Store) |
| 3 | `database` | Module: Database | RDS instance (db.t3.micro, PostgreSQL 16), parameter group, init.sql |
| 4 | `compute` | Module: Compute | EC2 instance (t3.micro), EBS volume, user data script |
| 5 | `monitoring` | Module: Monitoring | Budgets, CloudWatch log groups, 5 alarms, SNS topic |
| 6 | `frontend` | Frontend Architecture (S3/CloudFront section) | S3 bucket (static site), CloudFront distribution, OAC |
| 7 | `api` | Frontend Architecture (Lambda section) | Lambda function, API Gateway, CloudFront route |
| 8 | `cicd` | CI/CD (OIDC section) | IAM OIDC provider, GitHub Actions role, scoped deploy policy |

**Root module (`infra/main.tf`)** wires them together, passing outputs from one module as inputs to the next.

### Step 1.4: SSM Parameters (Automated by Terraform)

All 4 SSM parameters are created automatically by `terraform apply`:

| Parameter | Source |
|---|---|
| `/york-county/rds-password` | Auto-generated by `random_password` resource (24 chars, no special chars) |
| `/york-county/rds-host` | RDS endpoint from `aws_db_instance` output |
| `/york-county/rds-dbname` | `york_county_intel` |
| `/york-county/rds-username` | `dagster_admin` |

**No manual steps needed.** The password is generated at `terraform apply` time, passed to RDS and Lambda as variables, and stored in SSM Parameter Store for EC2 bootstrap — all in a single apply.

```bash
# Verify after terraform apply
aws ssm get-parameters \
  --names "/york-county/rds-host" "/york-county/rds-password" \
         "/york-county/rds-dbname" "/york-county/rds-username" \
  --query 'Parameters[].Name'
```

> **Note:** Lambda gets DB credentials as Terraform-set encrypted environment variables (NOT from SSM at runtime — see Infrastructure Plan, VPC networking constraint). EC2 reads from SSM at boot time via the IAM instance profile.

### Step 1.5: Terraform Init, Plan, Apply

```bash
cd infra/

# Initialize (connects to S3 backend)
terraform init

# Review what will be created
terraform plan -out=plan.tfplan

# Apply (review output carefully before confirming)
terraform apply plan.tfplan
```

> ⚠️ **This takes ~10-15 minutes.** RDS instance creation is the slowest part.

### Step 1.6: Verify Infrastructure

```bash
# EC2 instance is running
aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=york-county-dagster" \
  --query 'Reservations[].Instances[].{ID:InstanceId,State:State.Name,IP:PublicIpAddress}'

# RDS is available
aws rds describe-db-instances \
  --db-instance-identifier york-county-db \
  --query 'DBInstances[].{Status:DBInstanceStatus,Endpoint:Endpoint.Address}'

# SSM can reach the instance
aws ssm start-session --target <instance-id>
# (type 'exit' to disconnect)

# S3 buckets exist
aws s3 ls | grep york-county
```

> **Checkpoint:** EC2 state is "running". RDS state is "available". SSM session connects successfully. S3 buckets for frontend, raw data, and vector tiles exist.

### Step 1.7: Initialize Database and Start Dagster

After `terraform apply`, EC2 is running but Dagster is **not started** — the services are gated on `/opt/york-county/.initialized` (see `docs/infrastructure/bootstrap.md`). Run the initialization script:

```bash
# SSM into the EC2 instance
aws ssm start-session --target <instance-id>

# Run the initialization script (runs init.sql + starts Dagster)
sudo /opt/york-county/initialize.sh
```

The script runs `init.sql` against RDS, which creates:
- `postgis`, `pg_trgm`, `pg_stat_statements` extensions
- `staging`, `meta` schemas (the `public` schema exists by default in PostgreSQL)
- The separate `dagster` database (for Dagster internals)
- `meta.pipeline_status`, `meta.infra_metrics`, `meta.data_quality_checks` tables
- **No `raw` schema** — raw data goes to S3 only (see Infrastructure Plan, Schema Strategy)

Then it creates the gate file and starts both Dagster services.

> **Checkpoint:** Connect to RDS and verify: `\dx` shows postgis and pg_trgm. `\dn` shows staging and meta. `\l` shows both `york_county_intel` and `dagster` databases. `systemctl status dagster-webserver dagster-daemon` shows both services running.

---
