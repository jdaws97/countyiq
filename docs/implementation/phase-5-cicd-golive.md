# Phase 5: CI/CD, Validation & Go-Live

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
