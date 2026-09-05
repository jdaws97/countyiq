# CountyIQ Cloudflare infrastructure

OpenTofu owns the public DNS record, outbound Tunnel, private-alpha Access
policy, R2 buckets, lifecycle expiry, and backup immutability. No Worker,
Pages Function, Argo, Cache Reserve, or other usage-priced request path is
created.

Private-alpha sign-in uses Cloudflare Access email one-time PINs and an exact
allowlist of tester addresses. There is no CountyIQ password database to run,
and knowing an uninvited email address does not grant access.

## One-time account bootstrap

1. Enable R2 in the Cloudflare dashboard. Cloudflare requires an interactive
   billing acceptance before its API will create buckets.
2. Create the private `countyiq-iac-state` R2 bucket with the Eastern North
   America (`enam`) location hint and default jurisdiction. The current
   Cloudflare provider cannot apply lifecycle and lock resources to the newer
   `us` jurisdiction, so the application buckets use the same reviewed mode.
3. Create a bucket-scoped R2 API key for that state bucket.
4. Create a Cloudflare API token scoped to this account and zone with Tunnel,
   Access Apps/Policies, Access Organizations, R2 Storage, DNS Write, and Zone
   Read permissions. Store it as `CLOUDFLARE_API_TOKEN` in the same encrypted
   `cloudflare-iac.sops.env` file.
5. Capture both credentials through hidden prompts, then initialize:

```bash
../../infra/secrets/bootstrap-cloudflare-iac.sh
./tofu-sops.sh init -backend-config=backend.hcl
./tofu-sops.sh plan -out=countyiq.tfplan
./tofu-sops.sh apply countyiq.tfplan
```

The state key and Cloudflare token are secrets. They belong in SOPS/password
manager storage and process environment only, never in `.tfvars` or Git.

## Cost stop

All buckets use Standard storage because the [R2 free allowance][r2-pricing]
does not apply to Infrequent Access. The allowance currently includes 10
GB-month of storage, one million Class A operations, ten million Class B
operations, and free egress each month. Public browser/API requests do not
touch R2 and there is no Worker in this design, so tester traffic is not an R2
or Workers request meter.

Lifecycle rules expire raw/intelligence archives after 90 days and daily
database backups after 7 days. Raw objects receive a three-day bucket lock and
are not duplicated into the backup bucket. The VPS independently measures
both buckets every 15 minutes and hard-stops the entire CountyIQ stack at 8 GB,
leaving 2 GB of safety margin below the 10 GB allowance. A trip never
automatically resumes services.

The 7-day value is based on a 2026-09-04 measurement, not a generic estimate:
the current CountyIQ and Dagster custom-format dumps total about 222 MB, while
the one-time raw archive corpus is about 2.744 GB. Keeping one locked raw copy
plus seven daily dumps projects to about 4.30 GB; the first day is about 2.97
GB. A new bulk backfill therefore requires a fresh measurement; the
8 GB tripwire intentionally prevents it from silently consuming the remaining
free-tier margin.

After the SOPS-managed production environment has been rendered on the VPS,
arm the enforcement timer:

```bash
sudo COUNTYIQ_ENV_FILE=/etc/countyiq/production.env \
  /opt/countyiq/docker/arm-cost-guard.sh
```

The operator kill switch uses the exact same persistent trip state:

```bash
sudo /opt/countyiq/docker/cost-guard.sh --trip manual
sudo /opt/countyiq/docker/cost-guard.sh --status
```

Tripping also stops both operations timers, eliminating even the periodic R2
listing calls. Resetting only removes the trip after a successful below-limit
R2 read. It does not restart any container or timer; an operator must do that
separately.

Configure Cloudflare budget alerts in the Billing dashboard at $1
and $5. [Cloudflare documents][budget-alerts] that they are
notification-only and evaluated daily; they are not spending caps. The VPS
guard is therefore the enforcement control. At the current object count, its
periodic bucket listings are orders of magnitude below the Class A allowance.

Cloudflare Access is $0 for the first 50 users on the [Zero Trust Free
plan][zero-trust-pricing]. The IaC deliberately creates no pay-as-you-go Access
plan, Worker, Pages Function, Argo subscription, Load Balancer, Cache Reserve,
or Infrequent Access bucket.

## Deployment status (2026-09-05)

The app and apex DNS, Tunnel, Access policies and R2 resources are deployed.
The private production app is live, the database is at migration 065, the
off-host restore drill passed, and daily backups and the 15-minute storage
guard are active. The guard stops the VPS stack at 8,000,000,000 bytes; it
cannot stop charges from other clients or resources. Encrypted IaC credentials
and remote state are working. See the [production release record](../../docs/operations/production-launch-2026-09-05.md)
for exact deployed revisions, recovery receipts and remaining launch checks.

`check-cost-policy.sh` is enforced in CI. It rejects Terraform modules and any
resource class outside the explicit DNS, Tunnel, Access, and R2 allowlist, so a
future pull request cannot quietly add a Worker, Argo subscription, load
balancer, or another metered Cloudflare product.

[budget-alerts]: https://developers.cloudflare.com/billing/manage/budget-alerts/
[r2-pricing]: https://developers.cloudflare.com/r2/pricing/
[zero-trust-pricing]: https://www.cloudflare.com/plans/zero-trust-services/

## CountyIQ account integration

Both countyiq.net and app.countyiq.net use exact-email Access allowlists with
one-time PIN sign-in. Keep tester addresses in `production.auto.tfvars` and
apply through `tofu-sops.sh`; dashboard-only edits would drift from the managed
policy. A production health credential is restricted to `/api/ready` and cannot
authenticate a customer session. Live customer sign-in and workspace persistence
still need a completed browser check before publishing the marketing site.

See [account workspace configuration and guarded host rollout](../../docs/operations/account-workspaces.md) for the app host issuer/AUD settings and publication steps. The new app host has its own Access application. publish_marketing_site defaults to false so the existing apex gate remains until the split origin is verified. Access protects entry; CountyIQ stores stable account identity and saved-work ownership.
