# Backup & Disaster Recovery

## Backup & Disaster Recovery

### What Needs Protecting

| Component | Data | Persistence | Risk |
|---|---|---|---|
| **RDS PostgreSQL** | All processed data, entity resolution, Dagster metadata | Persistent (EBS-backed) | Highest — months of scraped/processed data |
| **S3 raw snapshots** | Raw API/scraper responses | Persistent (S3) | Medium — audit trail, replay capability |
| **S3 static site** | Frontend build output | Rebuildable | Low — `npm run build` recreates it |
| **S3 vector tiles** | Pre-generated map tiles | Rebuildable | Low — regenerated from RDS data |
| **EC2 instance** | Dagster runtime, Python venv, config | Rebuildable | Low — user data script rebuilds from scratch |
| **Git repository** | All source code | GitHub (off-site) | Minimal — GitHub is the source of truth |

### RDS Backups (Already Configured)

RDS automated backups are enabled in the database Terraform module:

| Setting | Value |
|---|---|
| Backup retention | 7 days |
| Backup window | 06:00–06:30 UTC (2:00 AM ET — after all scraper jobs finish; matches RDS config in Module: Database) |
| Multi-AZ | No (single-AZ, cost optimization) |
| Storage type | gp3 (durable — replicated within AZ) |

**Point-in-time recovery:** AWS lets you restore the database to any second within the 7-day retention window. If you discover corrupted data on Wednesday, you can restore to Tuesday at 11:59 PM and lose almost nothing.

**Manual snapshots before risky operations:**

```bash
# Before running a major migration or bulk data operation:
aws rds create-db-snapshot \
  --db-instance-identifier york-county-db \
  --db-snapshot-identifier pre-migration-$(date +%Y%m%d)
```

Manual snapshots persist until you delete them (they don't expire with the 7-day window). Cost: $0.095/GB/month for snapshot storage beyond the free allocation.

### S3 Durability

S3 provides 99.999999999% (11 nines) durability. Data loss from S3 is effectively impossible. No additional backup strategy is needed for S3 buckets.

S3 versioning is enabled on the Terraform state bucket (critical — protects against accidental state corruption). S3 versioning is also enabled on `york-county-raw` for defense against accidental deletions:

```hcl
# infra/modules/database/s3_raw.tf (or wherever the raw data bucket is defined)
resource "aws_s3_bucket_versioning" "raw_data" {
  bucket = aws_s3_bucket.raw_data.id
  versioning_configuration {
    status = "Enabled"
  }
}
```

### EC2 Instance Recovery

The EC2 instance is **fully rebuildable** from the user data script (Bootstrap / User Data Script section). If the instance dies, corrupt, or needs to be replaced:

**Recovery steps:**

```bash
# Step 1: Terminate the broken instance (if still running)
aws ec2 terminate-instances --instance-ids <old-instance-id>

# Step 2: Terraform will detect the missing instance and recreate it
cd infra/
terraform plan    # Shows: 1 to add (EC2 instance)
terraform apply   # Creates new instance, runs user data script

# Step 3: User data script automatically:
#   - Installs Python, Dagster, Playwright, all dependencies
#   - Clones the git repo
#   - Configures systemd services
#   - Starts Dagster webserver + daemon
#   - Installs and configures CloudWatch agent

# Step 4: Verify Dagster is running
aws ssm start-session --target <new-instance-id>
sudo systemctl status dagster-webserver
sudo systemctl status dagster-daemon

# Step 5: Re-enable schedules in Dagster UI
# (Schedules default to OFF on fresh install — enable them manually)
```

**Time to recover:** ~10-15 minutes (instance launch + user data script execution).

**What's NOT lost:** All data is in RDS and S3 — the EC2 instance holds no persistent state. Git repo is on GitHub. Pipeline code is pulled fresh from the repo during bootstrap.

**What IS lost on instance replacement:**
- Dagster run history (stored in RDS `meta` schema — this survives)
- Schedule enabled/disabled state (must be re-enabled manually)
- Any uncommitted code changes on the instance (should not exist if CI/CD is used properly)

### Disaster Recovery Drill

Before go-live (Phase 5), validate the recovery path works:

```
1. Take a manual RDS snapshot
2. Note current record counts for key tables
3. Terminate the EC2 instance
4. Run terraform apply (recreates instance)
5. Verify Dagster starts and connects to RDS
6. Verify data is intact (compare record counts)
7. Enable schedules
8. Trigger one pipeline manually and verify it succeeds
9. Delete the manual snapshot (or keep it as the "known good" baseline)
```

This drill should be part of the Phase 5 validation checklist in the Implementation Guide.

### Recovery Time Summary

| Scenario | Recovery Method | RTO (Time to Recover) | Data Loss |
|---|---|---|---|
| EC2 instance dies | `terraform apply` (recreates) | ~15 minutes | None (no persistent data on EC2) |
| RDS corruption (bad migration, etc.) | Point-in-time restore | ~15-30 minutes | Seconds (restore to any point in last 7 days) |
| RDS instance failure | Manual restore from automated backup (single-AZ — no automatic failover) | ~30 minutes | Up to 5 minutes (last backup transaction) |
| Accidental S3 deletion | S3 versioning (restore previous version) | Minutes | None (versioned) |
| Accidental Terraform state corruption | S3 versioning on state bucket | Minutes | None (versioned) |
| Complete AWS account compromise | Contact AWS support; RDS snapshots + S3 versioning + GitHub repo | Hours–days | Minimal (code is on GitHub, data is in backups) |
| Region-wide AWS outage | Wait for recovery (single-region deployment) | Hours | None (data persists through outages) |

### What's Intentionally NOT Included

| Approach | Why Skipped |
|---|---|
| Multi-AZ RDS | Doubles RDS cost (~$25/month). Not justified for a solo-operated platform. |
| Cross-region replication | Adds complexity and cost. York County data doesn't need geographic redundancy. |
| EC2 AMI snapshots | User data script is faster and always up-to-date. AMIs become stale. |
| Backup to non-AWS storage | S3 durability (11 nines) is sufficient. Offsite backup adds cost/complexity for negligible benefit. |
