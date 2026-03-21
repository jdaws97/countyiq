# CI/CD & GitHub Actions

> **Note:** The workflows below handle **deployment only**. Pre-merge CI checks (ruff lint, mypy type checking, pytest parser tests) run in a separate workflow defined in `docs/operations/testing.md`. All three deploy workflows require the CI workflow to pass before merging to `main`.

### Three Deployment Workflows

All workflows live in `.github/workflows/` at the repo root. Each uses **path filters** so pushing changes to `frontend/` only triggers the frontend deploy, etc.

#### Workflow 1: Frontend Deploy

**Trigger:** Push to `main` that changes files in `frontend/`
**Steps:** Install deps → Build React app → Sync to S3 → Invalidate CloudFront
**Time:** ~60 seconds

```yaml
# .github/workflows/deploy-frontend.yml
name: Deploy Frontend

on:
  push:
    branches: [main]
    paths: ['frontend/**']

permissions:
  id-token: write   # Required for OIDC
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json

      - name: Install and build
        working-directory: frontend
        run: |
          npm ci
          npm run build

      - name: Configure AWS credentials (OIDC)
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_DEPLOY_ROLE_ARN }}
          aws-region: us-east-1

      - name: Sync to S3
        run: aws s3 sync frontend/dist/ s3://york-county-frontend --delete

      - name: Invalidate CloudFront cache
        run: |
          aws cloudfront create-invalidation \
            --distribution-id ${{ secrets.CLOUDFRONT_DISTRIBUTION_ID }} \
            --paths "/*"
```

#### Workflow 2: API Deploy (Lambda)

**Trigger:** Push to `main` that changes files in `api/`
**Steps:** Install Python deps into package dir → Zip everything → Upload to Lambda
**Time:** ~90 seconds

```yaml
# .github/workflows/deploy-api.yml
name: Deploy API

on:
  push:
    branches: [main]
    paths: ['api/**']

permissions:
  id-token: write
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'  # Must match Lambda runtime

      - name: Package Lambda
        working-directory: api
        run: |
          pip install -r requirements.txt -t package/
          # Copy ALL application code — top-level .py files AND subdirectories
          cp -r *.py routes/ lib/ package/
          cd package && zip -r ../lambda.zip .

      - name: Configure AWS credentials (OIDC)
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_DEPLOY_ROLE_ARN }}
          aws-region: us-east-1

      - name: Deploy to Lambda
        run: |
          aws lambda update-function-code \
            --function-name york-county-api \
            --zip-file fileb://api/lambda.zip
```

#### Workflow 3: Dagster Deploy (EC2 via SSM)

**Trigger:** Push to `main` that changes files in `pipelines/`
**Steps:** Send SSM command to EC2 → EC2 pulls code, installs deps, restarts Dagster
**Time:** ~2-3 minutes

```yaml
# .github/workflows/deploy-dagster.yml
name: Deploy Dagster

on:
  push:
    branches: [main]
    paths: ['pipelines/**']

permissions:
  id-token: write
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Configure AWS credentials (OIDC)
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_DEPLOY_ROLE_ARN }}
          aws-region: us-east-1

      - name: Deploy via SSM
        run: |
          COMMAND_ID=$(aws ssm send-command \
            --instance-ids ${{ secrets.EC2_INSTANCE_ID }} \
            --document-name "AWS-RunShellScript" \
            --parameters 'commands=[
              "cd /opt/york-county/pipelines",
              "git pull origin main",
              "source /opt/york-county/venv/bin/activate",
              "pip install -e .",
              "cd /opt/york-county/pipelines && alembic upgrade head",
              "sudo systemctl restart dagster-webserver dagster-daemon"
            ]' \
            --query "Command.CommandId" \
            --output text)

          # Wait for completion
          aws ssm wait command-executed \
            --command-id $COMMAND_ID \
            --instance-id ${{ secrets.EC2_INSTANCE_ID }}

          echo "✅ Dagster deploy complete"
```

### GitHub Repository Secrets

Even though OIDC eliminates AWS credentials, you still need a few non-sensitive reference values stored as GitHub Secrets:

| Secret Name | Value | Sensitive? |
|---|---|---|
| `AWS_DEPLOY_ROLE_ARN` | `arn:aws:iam::role/york-county-github-actions` | No (just a resource identifier) |
| `CLOUDFRONT_DISTRIBUTION_ID` | CloudFront distribution ID | No |
| `EC2_INSTANCE_ID` | `i-xxxxxxxxxxxxxxxxx` | No |

These are resource identifiers, not credentials. They tell the workflow where to deploy to, but they can't be used to authenticate or access anything on their own.

### Branch Strategy

| Branch | Purpose |
|---|---|
| `main` | Production. Pushes here trigger deploys. |
| `feature/*` | Development branches. No deploys triggered. |

**Workflow:** Create feature branch → make changes → push → open PR → merge to `main` → auto-deploy.

For a solo developer, this is sufficient. If you ever add collaborators, you can add required PR reviews and status checks later.

**Acknowledged tradeoff:** There is no staging environment. `main` is production and pushes deploy directly. This is the biggest unmitigated operational risk — a bad merge can break the live platform. Mitigation: CI runs lint + type checks + parser tests before deploy, and the Dagster smoke test catches pipeline breaks after deploy. If this becomes uncomfortable, add a `staging` branch with a parallel set of AWS resources (a second CloudFront distribution pointing at a staging S3 bucket, etc.), but that doubles cost.

### What About Terraform Changes?

Terraform runs **manually from your local machine** via SSM port forwarding. This is intentional:

- Infrastructure changes are rare and high-impact
- You want to review `terraform plan` output before applying
- Automating `terraform apply` risks accidental resource destruction
- Solo dev doesn't need the overhead of Atlantis or Terraform Cloud

```bash
# From your local machine:
cd infra/
terraform plan       # Review changes
terraform apply      # Apply when satisfied
```

### Deployment Flow Summary

```
                    ┌──────────────────┐
                    │   git push main  │
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
         frontend/**    pipelines/**     api/**
              │              │              │
              ▼              ▼              ▼
       ┌────────────┐ ┌───────────┐ ┌───────────┐
       │ npm build  │ │ SSM cmd   │ │ pip + zip  │
       │ S3 sync    │ │ git pull  │ │ Lambda     │
       │ CF inval.  │ │ pip inst. │ │ upload     │
       │            │ │ restart   │ │            │
       └─────┬──────┘ └─────┬─────┘ └─────┬─────┘
             │              │              │
             ▼              ▼              ▼
          S3/CDN          EC2           Lambda
        (frontend)     (Dagster)        (API)
```

### Cost

GitHub Actions: **$0/month** (free tier provides 2,000 minutes/month; these three workflows combined will use ~10-20 minutes/month at typical push frequency).

---

### Integration with deployment

When you deploy new pipeline code to the EC2 instance, the deployment process should include:

```bash
# After pulling new code
cd /opt/york-county/pipelines
git pull origin main

# Run any pending migrations
alembic upgrade head

# Restart Dagster
sudo systemctl restart dagster-webserver
sudo systemctl restart dagster-daemon
```

This ensures the database schema is always in sync with the pipeline code. If a pipeline expects a new column, the migration that adds that column runs before the pipeline does.
