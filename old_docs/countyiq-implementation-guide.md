# CountyIQ — Implementation Guide

> **Purpose:** Step-by-step playbook for building CountyIQ from scratch. Hand this document + the Infrastructure Plan + the Data Source Feasibility Report to Claude Code and execute in order.
> **Author:** Jarod Daws
> **Created:** March 20, 2026
> **Companion docs:**
> - `york-county-infrastructure-plan.md` — Architecture reference (all design decisions, code samples, Terraform modules)
> - `york-county-data-source-feasibility-report.md` — Data source inventory (URLs, access methods, legal analysis, field inventories)

---

## How to Use This Document

**Phases 0–5 are sequential.** Each phase has prerequisites that must be true before starting. Do not skip ahead — dependencies will break.

**The Expansion Roadmap is modular.** After Phase 5, you have a working MVP. Expansion items can be tackled in any order, whenever you're ready.

**Every step has a verification checkpoint.** Don't move to the next step until the checkpoint passes. This prevents cascading failures.

---

## Table of Contents

### MVP Build
- [Phase 0: Local Environment Setup](#phase-0-local-environment-setup)
- [Phase 1: AWS Account Bootstrap & Terraform Infrastructure](#phase-1-aws-account-bootstrap--terraform-infrastructure)
- [Phase 2: Database Schema & Migrations](#phase-2-database-schema--migrations)
- [Phase 3: Dagster Pipelines & MVP Data Sources](#phase-3-dagster-pipelines--mvp-data-sources)
- [Phase 4: API, Frontend & Operations Stack](#phase-4-api-frontend--operations-stack)
- [Phase 5: CI/CD, Validation & Go-Live](#phase-5-cicd-validation--go-live)

### Expansion Roadmap
- [Expansion A: Phase 2 Data Sources](#expansion-a-phase-2-data-sources)
- [Expansion B: Phase 3 Data Sources](#expansion-b-phase-3-data-sources)
- [Expansion C: Platform Upgrades](#expansion-c-platform-upgrades)

---

## Phase 0: Local Environment Setup

**Goal:** Your local machine has everything needed to develop, test, and deploy CountyIQ.

**Time estimate:** 30 minutes

### Step 0.1: Install Required Tools

| Tool | Version | Purpose |
|---|---|---|
| **Terraform** | >= 1.7 | Infrastructure as Code |
| **AWS CLI v2** | Latest | AWS account interaction |
| **Python** | 3.12+ | Dagster pipelines, API |
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
mkdir -p pipelines/{assets/{arcgis,scrapers,bulk,pdf,enrichment},lib,sensors,tests/fixtures,jobs}
mkdir -p api/{routes,lib}
mkdir -p frontend
mkdir -p .github/workflows

# Create placeholder files
touch infra/main.tf infra/variables.tf infra/outputs.tf infra/terraform.tfvars
touch pipelines/pyproject.toml pipelines/definitions.py
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

# Create DynamoDB table for state locking
aws dynamodb create-table \
  --table-name countyiq-terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1
```

> **Checkpoint:** `aws s3 ls | grep countyiq` shows the bucket. `aws dynamodb list-tables` shows the lock table.

### Step 1.2: Write Terraform Backend Configuration

```hcl
# infra/backend.tf
terraform {
  backend "s3" {
    bucket         = "countyiq-terraform-state"
    key            = "prod/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "countyiq-terraform-locks"
    encrypt        = true
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

### Step 1.4: Generate RDS Password and Store All SSM Parameters

The EC2 bootstrap script retrieves 4 parameters from Parameter Store at boot time. Create them all now — the password is generated manually, and the other 3 come from Terraform outputs after `terraform apply` in the next step. **For the first apply, create the password first (Terraform references it), then come back and create the other 3 after Terraform outputs the RDS endpoint.**

```bash
# 1. Generate and store the password BEFORE terraform apply
RDS_PASSWORD=$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)

aws ssm put-parameter \
  --name "/york-county/rds-password" \
  --value "$RDS_PASSWORD" \
  --type SecureString \
  --region us-east-1

# 2. After terraform apply completes, store the remaining 3 parameters
#    (values come from terraform output)
aws ssm put-parameter \
  --name "/york-county/rds-host" \
  --value "$(terraform -chdir=infra output -raw rds_endpoint)" \
  --type String \
  --region us-east-1

aws ssm put-parameter \
  --name "/york-county/rds-dbname" \
  --value "york_county_intel" \
  --type String \
  --region us-east-1

aws ssm put-parameter \
  --name "/york-county/rds-username" \
  --value "dagster_admin" \
  --type String \
  --region us-east-1

# Verify all 4 parameters exist
aws ssm get-parameters \
  --names "/york-county/rds-host" "/york-county/rds-password" \
         "/york-county/rds-dbname" "/york-county/rds-username" \
  --query 'Parameters[].Name'
```

> **Note:** The password is stored in SSM for EC2 bootstrap. Lambda gets the same credentials via Terraform-set encrypted environment variables (NOT from SSM at runtime — see Infrastructure Plan, VPC networking constraint).

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

### Step 1.7: Run Database Init Script

Connect to the instance via SSM and run the init.sql script that creates extensions and schemas:

```bash
# SSM into the EC2 instance
aws ssm start-session --target <instance-id>

# On the instance, connect to RDS and run init.sql
psql -h <rds-endpoint> -U dagster_admin -d york_county_intel -f /opt/york-county/init.sql
```

The init.sql script (defined in Infrastructure Plan, Module: Database section) creates:
- `postgis` extension
- `pg_trgm` extension
- `staging`, `meta` schemas (the `public` schema exists by default in PostgreSQL)
- The separate `dagster` database (for Dagster internals)
- **No `raw` schema** — raw data goes to S3 only (see Infrastructure Plan, Schema Strategy)

> **Checkpoint:** Connect to RDS and verify: `\dx` shows postgis and pg_trgm. `\dn` shows staging and meta. `\l` shows both `york_county_intel` and `dagster` databases.

---

## Phase 2: Database Schema & Migrations

**Goal:** All database tables exist. Alembic is configured. The schema matches what the pipelines expect.

**Time estimate:** 1-2 hours

**Prerequisites:** Phase 1 complete. RDS is available. Extensions and schemas are created.

### Step 2.1: Set Up Alembic

Reference: Infrastructure Plan, Schema Migrations (Alembic) section.

```bash
cd pipelines/

# Alembic is already in pyproject.toml dependencies
pip install -e ".[dev]"

# Initialize Alembic
alembic init migrations
```

Configure `alembic.ini` and `migrations/env.py` as specified in the Infrastructure Plan.

### Step 2.2: Create the Initial Migration

This is the "baseline" migration that creates all tables needed for MVP sources.

**Tables to create (in this migration):**

**`staging` schema:** (Cleaned, normalized, change-tracked — NO `raw` schema; raw data goes to S3 only)
- `parcels` — GIS parcel data with SCD Type 2 (valid_from/valid_to)
- `assessment_properties` — Assessment database records (SCD Type 2)
- `flood_zones` — FEMA flood hazard boundaries
- `pa_open_data` — State-level datasets
- `penndot_roads` — PennDOT road/bridge data
- `penndot_projects` — PennDOT project records
- `municipalities` — Municipal boundaries from GIS
- `school_districts` — School district boundaries from GIS
- `zoning_districts` — Zoning boundaries from GIS

**`public` schema:** (Entity-resolved, query-ready)
- `owners` — Resolved owner entities (entity resolution output)
- `owner_source_links` — Links between owners and source records
- `properties` — **VIEW** (not a table) joining staging.parcels + staging.assessment_properties on PIDN

**`meta` schema:** (Application metadata — NOT Dagster internals. Dagster has its own `dagster` database.)
- `pipeline_status` — One row per source, updated by Dagster sensor after each run
- `infra_metrics` — EC2/RDS CloudWatch metrics, written by Dagster sensor every 5 min
- `data_quality_checks` — Pass/fail results from Dagster asset checks
- See Infrastructure Plan, **Meta Schema DDL** section for full CREATE TABLE statements

```bash
# Generate the migration
alembic revision -m "initial_schema_mvp_sources"

# Edit the generated file with the table definitions
# (reference Infrastructure Plan: Entity Resolution schema + Pipeline Code Structure)

# Test locally first with Docker Postgres
docker compose up -d postgres
alembic upgrade head
alembic downgrade base
alembic upgrade head
docker compose down
```

### Step 2.3: Apply Migration to RDS

```bash
# Set up SSM port forwarding to RDS
aws ssm start-session \
  --target <instance-id> \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters '{"host":["<rds-endpoint>"],"portNumber":["5432"],"localPortNumber":["5433"]}'

# In another terminal:
cd pipelines/
DATABASE_URL="postgresql://dagster_admin:<password>@localhost:5433/york_county_intel" \
  alembic upgrade head
```

> **Checkpoint:** Connect to RDS. `\dt staging.*` shows all staging tables. `\dt public.*` shows owners, owner_source_links, properties. All tables have the expected columns including `valid_from`/`valid_to` on SCD Type 2 tables.

---

## Phase 3: Dagster Pipelines & MVP Data Sources

**Goal:** All 6 MVP data sources (per Feasibility Report: #1, #2, #3, #4, #5, #13) are ingesting data, plus PLCB (#22, technically Phase 2 but trivially easy — CSV download — so it's built here to validate the pipeline framework). Entity resolution is running. The database is populated with real data.

**Time estimate:** 2-3 days (this is the bulk of the coding work)

**Prerequisites:** Phase 2 complete. All tables exist in RDS.

### Step 3.1: Build the Pipeline Framework

Before writing individual source assets, build the shared infrastructure:

| File | Purpose | Infra Plan Reference |
|---|---|---|
| `pipelines/definitions.py` | Dagster top-level definitions | Pipeline Code Structure → definitions.py |
| `pipelines/lib/database.py` | PostgreSQL connection helper | Pipeline Code Structure → lib/ utilities |
| `pipelines/lib/arcgis.py` | ArcGIS REST API pagination helper | Pipeline Code Structure → lib/ utilities |
| `pipelines/lib/scraper.py` | Playwright browser session manager | Pipeline Code Structure → lib/ utilities |
| `pipelines/lib/parsers/` | Per-source parsing functions | Pipeline Code Structure → asset examples |
| `pipelines/lib/slack.py` | Slack webhook integration | Error Handling → Dagster Slack Integration Code |
| `pipelines/lib/retry.py` | Default retry policy | Error Handling → Retry Policy |
| `pipelines/lib/checks.py` | Reusable asset check helpers | Testing Strategy → Layer 3 |
| `pipelines/sensors/alerting.py` | Success/failure Slack sensors | Error Handling → Dagster Sensors |
| `pipelines/lib/scd.py` | SCD Type 2 upsert helper | Data Retention → Schema pattern |

> **Checkpoint:** `python -c "from definitions import defs; print(len(defs.get_all_asset_keys()))"` runs without import errors (even though no source assets exist yet).

### Step 3.2: Implement MVP Source Assets (One at a Time)

Build each source, test it locally, then move to the next. Start with the simplest (bulk API) and progress to the hardest (Playwright scrapers).

**Recommended order:**

| Order | Source | # | Type | Difficulty | Notes |
|---|---|---|---|---|---|
| 1 | PLCB Liquor Licenses | 22 | CSV download | Easy | Bulk CSV; simplest possible pipeline. Good first test. |
| 2 | FEMA Flood Hazard Layer | 3 | Direct download | Easy | Single file download + PostGIS import |
| 3 | York County GIS Portal (Parcels) | 1 | ArcGIS REST API | Medium | Pagination, coordinate transform, 176K records. Core dataset. |
| 4 | York County GIS Portal (Other layers) | 1 | ArcGIS REST API | Medium | Same pattern as parcels, just different endpoints |
| 5 | PA Open Data Portal | 4 | SODA API | Medium | Different API pattern (SODA vs ArcGIS) |
| 6 | PennDOT Open Data | 5 | ArcGIS REST API | Medium | Same ArcGIS pattern as #3. ⚠️ Not live-tested — verify the endpoint responds before building. If it's down, skip and revisit; the other 5 MVP sources are sufficient for launch. |
| 7 | PennDOT Projects | 13 | ArcGIS MapServer | Medium | MapServer (slightly different from FeatureServer) |
| 8 | Assessment Database | 2 | Playwright scraper | Hard | ASP.NET Web Forms, session-based, 176K properties, throttling needed |
| 9 | Entity Resolution (MVP scope) | — | SQL enrichment | Medium | MVP: parcels + assessment only. Matches GIS owner_full against assessment owner_name using PIDN join + pg_trgm fallback. Phase 2 sources added incrementally. |
| 10 | Vector Tile Generation | — | PostGIS → S3 | Medium | ST_AsMVT, upload to S3 |

**For each source, the workflow is:**

```
1. Write the asset file:        pipelines/assets/<type>/<source>.py
2. Write the parser:            pipelines/lib/parsers/<source>.py
3. Write the schema test:       pipelines/tests/test_<source>_parser.py
4. Save a test fixture:         pipelines/tests/fixtures/<source>_sample.json
5. Write asset checks:          (in the asset file or lib/checks.py)
6. Add the schedule:            pipelines/jobs/schedules.py
7. Run pytest locally:          pytest pipelines/tests/test_<source>_parser.py -v
8. Test against live API:       dagster asset materialize -a <asset_name>  (local Dagster)
9. Verify data in RDS:          psql → SELECT COUNT(*) FROM staging.<table>;
10. Commit and push
```

### Step 3.3: Run Day 1 Backfill

Once all MVP sources are implemented and tested individually:

Reference: Infrastructure Plan, Backfill Strategy section.

```
Phase 1 (parallel where possible):
  - GIS Portal (all 49 layers)       ~30 min
  - FEMA Flood Layer                  ~2 min
  - PA Open Data                      ~5 min
  - PennDOT (Open Data + Projects)    ~10 min
  - PLCB Licenses                     ~1 min

Phase 2 (sequential — Playwright memory):
  - Assessment Database               ~2-4 hours

Phase 3 (enrichment):
  - Entity Resolution                 ~20 min

Phase 4 (frontend data):
  - Vector Tile Generation            ~15 min
```

Trigger from the Dagster UI with `full_history: true` config.

> **Checkpoint:** `SELECT COUNT(*) FROM staging.parcels WHERE valid_to IS NULL;` returns ~176,000. Entity resolution `owners` table is populated. Vector tiles are in S3. All Dagster runs show SUCCESS in the UI.

---

## Phase 4: API, Frontend & Operations Stack

**Goal:** The public frontend is live. The API serves data. The ops health dashboard works. Slack alerts are flowing.

**Time estimate:** 2-3 days

**Prerequisites:** Phase 3 complete. Database is populated with real data.

### Step 4.1: Build the FastAPI Lambda API

Reference: Infrastructure Plan, Frontend Architecture → Lambda Configuration section.

| File | Purpose |
|---|---|
| `api/main.py` | FastAPI app with routes |
| `api/handler.py` | Mangum adapter for Lambda |
| `api/requirements.txt` | Python dependencies |
| `api/routes/parcels.py` | Parcel search/detail endpoints |
| `api/routes/properties.py` | Unified property view endpoints |
| `api/routes/owners.py` | Owner entity endpoints |
| `api/routes/search.py` | Cross-entity search |
| `api/routes/ops.py` | Health dashboard endpoint |
| `api/lib/database.py` | RDS connection (reads DATABASE_* env vars set by Terraform — NOT Parameter Store at runtime; see Infra Plan, VPC networking constraint) |

**API endpoints to implement:**

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/parcels?bbox=...` | Parcels within map bounding box |
| GET | `/api/parcels/{pidn}` | Single parcel detail with history |
| GET | `/api/owners/{id}` | Owner entity with all linked properties/records |
| GET | `/api/search?q=...` | Full-text search across owners, addresses, PIDNs |
| GET | `/api/ops/health` | System health dashboard data (React frontend at `/ops/health` calls this) |

**Test locally:**

```bash
cd api/
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Test endpoints
curl http://localhost:8000/api/parcels?bbox=-76.8,39.9,-76.7,40.0
curl http://localhost:8000/api/ops/health
```

**Package and deploy to Lambda:**

```bash
cd api/
pip install -r requirements.txt -t package/
cp -r *.py routes/ lib/ package/
cd package && zip -r ../lambda.zip .

aws lambda update-function-code \
  --function-name york-county-api \
  --zip-file fileb://lambda.zip
```

> **Checkpoint:** Hit the API Gateway URL in a browser. `/api/ops/health` returns JSON with source statuses. `/api/parcels/{pidn}` returns a real parcel record.
>
> **Note on tiles:** Vector tiles are NOT served by Lambda. They're pre-generated by the Dagster tile pipeline and uploaded to S3. CloudFront routes `/tiles/*` directly to the S3 tiles bucket (7-day cache). The API has no tile routes.

### Step 4.2: Build the React Frontend

Reference: Infrastructure Plan, Frontend Architecture section (UI mockup, core views, stack table).

**Core views to implement:**

| View | Description |
|---|---|
| **Map View** (default) | MapLibre GL JS map with Deck.gl data layers. Parcel boundaries, color-coded by type. Click a parcel → sidebar with details. |
| **Search** | Search bar that queries `/api/search`. Results show on map and in a list. |
| **Property Detail** | Sidebar/panel showing parcel info, owner, assessment, history timeline, linked records. |
| **Owner Detail** | Entity view showing all properties, businesses, permits, court records linked to a resolved entity. |
| **Ops Health** | `/ops/health` — the operational dashboard (see Operational Visibility section in Infra Plan). |

```bash
cd frontend/

# Initialize React app with Vite
npm create vite@latest . -- --template react
npm install
npm install maplibre-gl deck.gl @deck.gl/mapbox @deck.gl/layers
npm install react-router-dom

# Develop
npm run dev
```

**Deploy to S3/CloudFront:**

```bash
npm run build
aws s3 sync dist/ s3://york-county-frontend --delete
aws cloudfront create-invalidation \
  --distribution-id <distribution-id> \
  --paths "/*"
```

> **Checkpoint:** Open the CloudFront URL in a browser. The map loads. Parcels render on the map. Click a parcel and see real data in the sidebar. Search returns results. `/ops/health` page shows green/yellow/red statuses.

### Step 4.3: Set Up Slack Workspace & Integrations

1. ~~Create a free Slack workspace~~ **Done** — workspace is `CountyIQ` (countyiq.slack.com)
2. Create channels: `#alerts-critical`, `#alerts-warning`, `#pipeline-runs`
3. Turn ON phone notifications for `#alerts-critical` (this is the only channel that should buzz your phone)
4. Create a Slack App at [api.slack.com/apps](https://api.slack.com/apps) → "Create New App" → "From scratch" → name it `CountyIQ`
5. Enable Incoming Webhooks in the app settings, then "Add New Webhook to Workspace" **three times** — once per channel. Each gives a separate URL.
6. Store all three webhook URLs in Parameter Store:

```bash
aws ssm put-parameter \
  --name "/york-county/slack-webhook-critical" \
  --value "https://hooks.slack.com/services/T.../B.../..." \
  --type SecureString

aws ssm put-parameter \
  --name "/york-county/slack-webhook-warning" \
  --value "https://hooks.slack.com/services/T.../B.../..." \
  --type SecureString

aws ssm put-parameter \
  --name "/york-county/slack-webhook-pipeline" \
  --value "https://hooks.slack.com/services/T.../B.../..." \
  --type SecureString
```

7. Test each webhook: `curl -X POST -H 'Content-type: application/json' --data '{"text":"Test from CountyIQ"}' YOUR_WEBHOOK_URL`
8. Deploy the CloudWatch → Slack forwarder Lambda (see Infrastructure Plan, Error Handling section)
9. Subscribe the Lambda to the SNS topic used by CloudWatch alarms

> **Checkpoint:** Manually trigger a test message to each Slack channel. Verify phone push notifications work for `#alerts-critical`. Stop and restart Dagster to trigger the success sensor — verify `#pipeline-runs` gets a message.

---

## Phase 5: CI/CD, Validation & Go-Live

**Goal:** GitHub Actions deploys automatically on push. Everything is tested end-to-end. The platform is production-ready.

**Time estimate:** 1 day

**Prerequisites:** Phase 4 complete. Frontend, API, and Dagster are all deployed and working.

### Step 5.1: Set Up GitHub Actions Workflows

Reference: Infrastructure Plan, CI/CD section.

Create the four workflow files:

| File | Trigger | Purpose |
|---|---|---|
| `.github/workflows/ci.yml` | PR to main | Lint, type check, schema tests, frontend build |
| `.github/workflows/deploy-frontend.yml` | Push to main (frontend/**) | Build → S3 sync → CloudFront invalidation |
| `.github/workflows/deploy-api.yml` | Push to main (api/**) | Package → Lambda update |
| `.github/workflows/deploy-dagster.yml` | Push to main (pipelines/**) | SSM → git pull → pip install → restart |

### Step 5.2: Store GitHub Secrets

```bash
# Get values from Terraform outputs
ROLE_ARN=$(cd infra && terraform output -raw github_actions_role_arn)
CF_DIST_ID=$(cd infra && terraform output -raw cloudfront_distribution_id)
EC2_ID=$(cd infra && terraform output -raw ec2_instance_id)

# Store in GitHub
gh secret set AWS_DEPLOY_ROLE_ARN --body "$ROLE_ARN"
gh secret set CLOUDFRONT_DISTRIBUTION_ID --body "$CF_DIST_ID"
gh secret set EC2_INSTANCE_ID --body "$EC2_ID"
```

### Step 5.3: Test CI/CD End-to-End

```bash
# Create a test branch
git checkout -b test/ci-cd

# Make a trivial change to each directory
echo "# test" >> frontend/README.md
echo "# test" >> api/README.md
echo "# test" >> pipelines/README.md

# Push and open PR (triggers CI)
git add -A && git commit -m "test: verify CI/CD pipelines"
git push -u origin test/ci-cd
gh pr create --title "Test CI/CD" --body "Verify all workflows trigger correctly"

# Watch CI run
gh pr checks test/ci-cd --watch

# Merge PR (triggers all three deploy workflows)
gh pr merge test/ci-cd --merge

# Watch deploys
gh run list --limit 3
```

> **Checkpoint:** CI workflow passes on the PR. All three deploy workflows complete successfully after merge. Frontend shows updated content. Lambda serves the new API code. Dagster restarts cleanly (check Slack `#pipeline-runs`).

### Step 5.4: End-to-End Validation

Run through this checklist to verify everything works together:

**Data layer:**
- [ ] All MVP source Dagster assets show last successful run in Dagster UI
- [ ] `staging.parcels` has ~176K current records
- [ ] `public.owners` has resolved entities
- [ ] Entity resolution linked owners across sources (spot-check 5 owners)
- [ ] Vector tiles are in S3 and accessible via CloudFront

**API layer:**
- [ ] `/api/parcels?bbox=...` returns parcels within bounding box
- [ ] `/api/parcels/{pidn}` returns full parcel detail with history
- [ ] `/api/search?q=smith` returns owner/property matches
- [ ] `/ops/health` returns current status for all sources

**Frontend:**
- [ ] Map loads with parcel boundaries rendered
- [ ] Clicking a parcel shows detail panel with real data
- [ ] Search works and results highlight on map
- [ ] Ops health page shows correct statuses
- [ ] Site loads in < 3 seconds (CloudFront caching)

**Operations:**
- [ ] Slack `#alerts-critical` receives test notification
- [ ] Slack `#pipeline-runs` receives success messages from scheduled runs
- [ ] CloudWatch alarms are in OK state
- [ ] Budget alert is configured (check AWS Budgets console)
- [ ] SSM port forwarding to Dagster UI works
- [ ] SSM port forwarding to RDS works

**CI/CD:**
- [ ] PR to main triggers CI (lint + type check + tests)
- [ ] Push to main triggers correct deploy workflow based on changed files
- [ ] Dagster smoke test passes after deploy

**Security (WAF is optional at launch — $6.60/month, no free tier, can defer until public launch):**
- [ ] If WAF enabled: Web ACL is associated with CloudFront distribution
- [ ] If WAF enabled: Rate-based rule is active (check AWS WAF console)
- [ ] If WAF deferred: Terraform for WAF is ready but commented out; uncomment and apply when ready

**Disaster recovery drill:**
- [ ] Take a manual RDS snapshot
- [ ] Note current record counts for key tables
- [ ] Terminate the EC2 instance
- [ ] Run `terraform apply` — verify instance recreates (~15 min)
- [ ] Verify Dagster starts and connects to RDS
- [ ] Verify data is intact (compare record counts)
- [ ] Re-enable Dagster schedules
- [ ] Trigger one pipeline manually — verify success
- [ ] Delete the manual snapshot (or keep as "known good" baseline)

### Step 5.5: Enable Scheduled Runs

Until now, all runs have been manual. Enable only the **MVP weekly schedules** — daily schedules stay disabled until Phase 2 pipelines are built.

```python
# In the Dagster UI → Schedules:
# Toggle ON only these 5 MVP weekly schedules:
#   - gis_portal_all_layers     (Sunday 2 AM)
#   - fema_flood_hazard         (Sunday 4 AM)
#   - pa_open_data              (Monday 2 AM)
#   - penndot_open_data         (Monday 3 AM)
#   - penndot_projects          (Tuesday 2 AM)
#
# Also enable the entity resolution sensor (dependency-driven, runs after weekly sources)
#
# Do NOT enable daily schedules — those are Phase 2 target configs.
# Do NOT use `dagster schedule start --all` — it would enable Phase 2 schedules too.
```

> **Checkpoint:** Wait until after the next Sunday 4 AM run. Check Slack `#pipeline-runs` — you should see success messages from the GIS and FEMA weekly sources. Check `#alerts-critical` — should be empty (no failures). The platform is live.

---

## Expansion Roadmap

Everything below is modular. Tackle in any order, whenever you're ready. The MVP is fully functional without any of these.

---

## Expansion A: Phase 2 Data Sources

### Adding a New Source — Standard Checklist

Every new source follows the same pattern established in Phase 3. Use this checklist:

```
□ 1. Review the source in the Data Source Feasibility Report
       - Verify URL is still accessible
       - Confirm access method and any changes since testing

□ 2. Create Alembic migration for new staging table(s)
       - Include valid_from/valid_to if change-tracked
       - Test locally with Docker Postgres
       - Apply to RDS via SSM tunnel

□ 3. Write the parser
       - pipelines/lib/parsers/<source>.py
       - Handle nulls, encoding, edge cases

□ 4. Save a test fixture
       - pipelines/tests/fixtures/<source>_sample.json (or .html, .csv)
       - Small sample from real API/page response

□ 5. Write schema validation test
       - pipelines/tests/test_<source>_parser.py
       - Verify required fields present, types correct

□ 6. Write the Dagster asset
       - pipelines/assets/<type>/<source>.py
       - Include backfill config (full_history flag)
       - Apply default retry policy

□ 7. Write asset checks
       - Record count > 0
       - Required fields not null
       - Count within expected range

□ 8. Add the schedule
       - Reference Data Refresh Schedules section for cron expression

□ 9. Update entity resolution
       - If source contains owner/business names, add it as a new source_type
       - Update owner_source_links mapping

□ 10. Run locally against live API/site
        - dagster asset materialize -a <asset_name>
        - Verify data in local Postgres

□ 11. Push and deploy
        - PR → CI passes → merge → auto-deploy

□ 12. Run backfill in production
        - Trigger from Dagster UI with full_history: true
        - Monitor in Slack

□ 13. Verify in /ops/health
        - New source appears with green status
```

### Phase 2 Source Priority Order

Recommended order based on value-add and difficulty. Tackle the highest-value, easiest sources first.

| Priority | Source | # | Method | Difficulty | Value-Add |
|---|---|---|---|---|---|
| 1 | PA DOS Business Entities | 8 | data.pa.gov API | Easy | Links businesses to owners via entity resolution |
| 2 | PLCB Liquor Licenses | 22 | CSV download | Easy | Already have CSV pattern from MVP; adds license data layer |
| — | **🔒 AUTH & GOVERNANCE GATE** | — | — | Medium | **Before adding person-level or sensitive data (sources 3–5, 13–15 below), implement: Cognito/Clerk auth, role-based tiers, query audit logging (`meta.query_audit_log`), rate-limited person lookups. See Infra Plan: Privacy & Access Control section.** |
| 3 | CRIMEWATCH (Police Blotters) | 19 | Playwright + pagination | Medium | High-demand data; incident mapping on frontend |
| 4 | Sheriff Sales / Tax Claim | 9 | Scraper + PDF | Medium | Financial distress indicators; property investment intel |
| 5 | Tax Claim Bureau | 14 | HTML + PDF | Medium | Delinquent property identification |
| 6 | County Bids | 12 | BeautifulSoup | Easy | Government spending visibility |
| 7 | York City RFPs | 18 | BeautifulSoup | Easy | City-level procurement |
| 8 | Commissioners Meetings | 15 | HTML + PDF | Medium | Government decision tracking |
| 9 | YCPC Subdivision Activity | 16 | HTML + PDF | Medium | Development pipeline intel |
| 10 | Conservation District (YCCD) | 11 | PDF download | Medium | Environmental planning data |
| 11 | PA DEP eFACTS | 17 | Playwright (ASP.NET) | Hard | Environmental compliance; complex scraper |
| 12 | PALS Professional Licenses | 21 | Playwright (AngularJS) | Hard | Professional license data; complex SPA scraping |
| 13 | UJS Portal (Court Records) | 6 | AOPC request + Playwright | Hard | Requires formal application; high value once obtained |
| 14 | Recorder of Deeds | 7 | RTK request | N/A | Depends on RTK response format/timeline |
| 15 | Inmate Records | 20 | TBD | TBD | Pending URL verification |

> **⚠️ Auth Gate:** Sources 1–2 (PA DOS, PLCB) are safe to add without auth — they're business/license data with no person-level sensitivity. Sources 3+ involve crime data, financial distress, and eventually court records. The auth gate between priorities 2 and 3 ensures access controls, query auditing, and rate limiting are in place before sensitive aggregated data is exposed. If you want to move faster, you can build the pipelines for sources 3–5 in parallel with the auth work, but don't expose them through the public API until auth is live.

### Source-Specific Notes

**Source 8 — PA DOS Business Entities:**
- Two access paths: data.pa.gov SODA API (easier) and file.dos.pa.gov (behind Cloudflare)
- Start with data.pa.gov; fall back to file.dos.pa.gov if data.pa.gov doesn't have York County-specific data
- Entity resolution: match business officer names to parcel owners

**Source 19 — CRIMEWATCH:**
- Playwright required — JavaScript-rendered pagination
- Paginate through all available pages on backfill
- Geolocation: incidents have addresses that need geocoding to map coordinates
- Frontend: add a "Recent Incidents" layer to the map with clustering

**Sources 9 + 14 — Sheriff Sales + Tax Claim:**
- These are related — tax delinquency → tax claim → sheriff sale
- Build together; they share a frontend view ("Properties in Financial Distress")
- Sheriff sales URL needs verification (county site reorganized)
- PDF parsing needed for some sale documents

**Source 17 — PA DEP eFACTS:**
- ASP.NET application with session state — Playwright required
- Search by county = "York" to get all records
- Paginate through results
- Links to parcels via facility address

**Source 21 — PALS Professional Licenses:**
- AngularJS SPA — Playwright required, wait for Angular to load
- Search by county/profession
- Large dataset — will need pagination and throttling

**Sources 6 + 7 — UJS Court Records + Recorder of Deeds:**
- Both require formal applications (AOPC and RTK respectively)
- Start the application process early — they take weeks/months
- Build the pipeline infrastructure in parallel while waiting for access
- Court records are the highest-value Phase 2 source for entity resolution

**Source 20 — Inmate Records:**
- `inmatelocator.yorkcountypa.gov` had DNS failure during feasibility testing
- First step: verify URL from a local browser
- If unreachable, check if the county moved it to a different domain

---

## Expansion B: Phase 3 Data Sources

### Source 10 — Municipal Meeting Minutes (72 Municipalities)

This is the highest-effort data source in the entire platform. York County has 72 municipalities, each with their own website (if they have one at all).

**Approach:**

1. **Inventory phase** — Catalog all 72 municipality websites. Identify which ones post meeting minutes online, in what format (PDF, HTML, embedded doc), and at what URL pattern. This is a manual research task — expect 2-3 hours.

2. **Template scrapers** — Group municipalities by website platform:
   - Many small townships use the same CMS (e.g., Civic Plus, WordPress)
   - Write one scraper template per CMS, parameterized by URL
   - Custom scrapers only for unique sites

3. **PDF extraction** — Most meeting minutes are PDFs. Use pdfplumber to extract text. NLP processing to identify:
   - Zoning decisions (approvals, denials, variances)
   - Development plan approvals
   - Utility projects
   - Budget items

4. **Phased rollout** — Don't try to do all 72 at once:
   - Start with the 10 largest municipalities (York City, Spring Garden, West Manchester, etc.)
   - Add 10-15 per sprint
   - Some tiny townships don't have websites — skip them

5. **Entity resolution** — Link meeting content to parcels/owners when addresses or names are mentioned.

**Estimated effort:** 2-4 weeks for the first 10 municipalities. 1-2 months for comprehensive coverage.

---

## Expansion C: Platform Upgrades

These are infrastructure improvements, not data sources. Tackle when the trigger condition is met.

| Upgrade | Trigger | Effort | Infra Plan Reference |
|---|---|---|---|
| Automated Cost Kill Switch | After free tier expires, if costs become unpredictable | 2-3 hours | Future Enhancements → #1 |
| NAIP Imagery Pipeline | When aerial imagery analysis becomes a priority | 1-2 days | Future Enhancements → #2 |
| Upgrade to t3.small | CloudWatch shows memory > 80% consistently | 30 min (Terraform variable change) | Future Enhancements → #3 |
| Private VPC + NAT Gateway | Security audit requires no public IP on EC2 | 2-3 hours | Future Enhancements → #4 |
| Dagster Cloud Hybrid | Multiple users need Dagster UI access | 1-2 days | Future Enhancements → #5 |
| ALB + Cognito for Dagster UI | Browser-based multi-user Dagster access | 1 day | Future Enhancements → #6 |
| Custom domain | When you want `countyiq.com` instead of CloudFront URL | 1-2 hours | Frontend Architecture → Custom Domain |
| Authentication on frontend | When you want to restrict access or add user accounts | 1-2 days | Not yet designed — consider Cognito or Clerk |
| Zingg entity resolution | pg_trgm matching produces too many false positives/negatives | 2-3 days | Entity Resolution → Zingg Upgrade Path |
| Multi-county expansion | When you want to add Lancaster, Adams, or other counties | 1-2 weeks | Entity Resolution → Why It Scales |

### Multi-County Expansion Notes

The entity resolution schema was designed to be source-agnostic (see Infrastructure Plan, Entity Resolution section). Expanding to another county means:

1. Create a new RDS database (or schema per county within the same instance)
2. Copy the Dagster asset templates — most sources (ArcGIS, PA state portals) work the same way across counties
3. Update ArcGIS endpoints for the new county's GIS portal
4. The county-specific scrapers (assessment, sheriff sales) need new implementations per county
5. Entity resolution runs per-county initially; cross-county matching is a future capability

The hardest part isn't the code — it's finding and verifying each county's data source URLs and access methods. Budget 1-2 weeks per new county for the research + implementation.

---

## Quick Reference: File Inventory

When the MVP is complete, your repository should contain:

```
countyiq/
├── .github/
│   └── workflows/
│       ├── ci.yml                          # PR checks (lint, type check, tests)
│       ├── deploy-frontend.yml             # Frontend → S3/CloudFront
│       ├── deploy-api.yml                  # API → Lambda
│       └── deploy-dagster.yml              # Pipelines → EC2 via SSM
│
├── infra/
│   ├── main.tf                             # Root module
│   ├── variables.tf                        # Input variables
│   ├── outputs.tf                          # Outputs (instance IDs, endpoints, ARNs)
│   ├── backend.tf                          # S3 state backend config
│   ├── terraform.tfvars                    # Variable values (gitignored)
│   └── modules/
│       ├── networking/                     # Security groups
│       ├── iam/                            # Roles, policies, instance profile
│       ├── compute/                        # EC2 instance, user data script
│       ├── database/                       # RDS, parameter group, init.sql
│       ├── monitoring/                     # Budgets, alarms, SNS, log groups
│       ├── frontend/                       # S3 bucket, CloudFront, OAC
│       ├── api/                            # Lambda, API Gateway
│       └── cicd/                           # OIDC provider, GitHub Actions role
│
├── pipelines/
│   ├── pyproject.toml                      # Dependencies (dagster, playwright, etc.)
│   ├── definitions.py                      # Dagster top-level definitions
│   ├── migrations/                         # Alembic migrations
│   │   ├── env.py
│   │   └── versions/
│   │       └── 001_initial_schema.py
│   ├── assets/
│   │   ├── arcgis/
│   │   │   ├── parcels.py                  # Source 1: GIS parcels
│   │   │   ├── gis_layers.py              # Source 1: Other GIS layers
│   │   │   └── penndot.py                 # Sources 5, 13: PennDOT
│   │   ├── bulk/
│   │   │   ├── fema_flood.py              # Source 3: FEMA
│   │   │   ├── pa_open_data.py            # Source 4: PA Open Data
│   │   │   └── plcb_licenses.py           # Source 22: PLCB (if added)
│   │   ├── scrapers/
│   │   │   └── assessment.py              # Source 2: Assessment DB
│   │   └── enrichment/
│   │       ├── entity_resolution.py       # Owner matching + clustering
│   │       └── vector_tiles.py            # PostGIS → S3 tile generation
│   ├── jobs/
│   │   └── schedules.py                   # All cron schedules
│   ├── sensors/
│   │   └── alerting.py                    # Slack success/failure sensors
│   ├── lib/
│   │   ├── database.py                    # PostgreSQL connection helper
│   │   ├── arcgis.py                      # ArcGIS API helper
│   │   ├── scraper.py                     # Playwright session manager
│   │   ├── slack.py                       # Slack webhook helper
│   │   ├── retry.py                       # Default retry policy
│   │   ├── checks.py                      # Reusable asset checks
│   │   ├── scd.py                         # SCD Type 2 upsert helper
│   │   └── parsers/
│   │       ├── arcgis.py                  # ArcGIS response parser
│   │       ├── assessment.py              # Assessment HTML parser
│   │       ├── fema.py                    # FEMA shapefile parser
│   │       └── ...
│   └── tests/
│       ├── conftest.py
│       ├── fixtures/
│       │   ├── parcels_sample.json
│       │   ├── assessment_sample.html
│       │   └── ...
│       ├── test_arcgis_parser.py
│       ├── test_assessment_parser.py
│       └── ...
│
├── api/
│   ├── main.py                             # FastAPI app
│   ├── handler.py                          # Mangum Lambda adapter
│   ├── requirements.txt                    # Python dependencies
│   ├── routes/
│   │   ├── parcels.py                     # Parcel endpoints
│   │   ├── properties.py                  # Unified property view
│   │   ├── owners.py                      # Owner entity endpoints
│   │   ├── search.py                      # Cross-entity search
│   │   └── ops.py                         # Health dashboard
│   └── lib/
│       ├── database.py                    # RDS connection
│       └── cloudwatch.py                  # CW metrics helper
│
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   └── src/
│       ├── App.jsx                        # Router + layout
│       ├── components/
│       │   ├── Map.jsx                    # MapLibre + Deck.gl
│       │   ├── SearchBar.jsx
│       │   ├── ParcelDetail.jsx
│       │   ├── OwnerDetail.jsx
│       │   └── OpsHealth.jsx
│       └── lib/
│           └── api.js                     # API client helper
│
├── .gitignore
└── README.md
```
