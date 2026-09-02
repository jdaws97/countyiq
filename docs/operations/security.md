# Security and Production-Readiness Review

**Review date:** 2026-08-31

## Scope and Deployment Reality

This review covers the repository's public FastAPI surface, database access,
pipeline egress, dependency locks, Docker images and Compose topology, Caddy
proxy boundary, CI, bootstrap, and backups. CountyIQ is not deployed, so this
is a code/configuration audit rather than a live penetration test. Cloudflare,
Hetzner firewall rules, SSH configuration, R2 permissions, TLS, and recovery
behavior must still be verified on the actual host.

## Remediated Findings

| Severity | Finding | Control now in the repository |
|---|---|---|
| High | The public API container inherited the database administrator, pipeline OpenRouter, R2, and Slack secrets. | Compose now gives the API only an independently generated read-only PostgreSQL login plus an optional search-only provider key. PostgreSQL grants are refreshed by `03-api-role.sh` after migrations. |
| High | Scheduled Dagster work inherited every deployment secret and used the PostgreSQL bootstrap superuser. | Dagster now receives an explicit environment allowlist and a dedicated non-superuser DML role. Administrator access is confined to a short-lived migration service and host backups. |
| High | The installed pipeline environment reported 56 known advisories in 13 packages, including Dagster and request/parsing dependencies. | Dagster and the complete lock were upgraded; `pip-audit` reports no known vulnerabilities and now runs in CI for both Python environments. |
| Medium | Client throttles trusted caller-supplied `CF-Connecting-IP` and `X-Forwarded-For`, allowing origin requests to forge limiter identities. | Caddy trusts only Cloudflare's published ranges and collapses the validated chain. Uvicorn accepts forwarding headers only from the dedicated Caddy subnet, the API port is not host-published, and application code no longer reads forwarding headers directly. |
| Medium | API and pipeline processes ran as container root with the default capability set. | Both application images use UID/GID 10001. Compose drops all capabilities, sets `no-new-privileges`, adds PID ceilings, and makes both application filesystems read-only. Caddy retains only `NET_BIND_SERVICE`. |
| Medium | The VPS bootstrap executed mutable remote installer scripts as root and printed the generated database password. | Bootstrap uses signed Ubuntu packages, requires a reviewed 40-character commit SHA and pre-verified GitHub SSH host key, generates separate hex credentials under `umask 077`, and never prints them. |
| Medium | Owner/entity portfolio routes lacked the privacy backlog's anti-scraping control. | Those routes now have a dedicated per-client token bucket behind the Cloudflare boundary. This is abuse resistance, not authorization. |
| Low | Public Swagger/OpenAPI routes and arbitrary Host headers were accepted by default. | Docs require explicit opt-in and `TrustedHostMiddleware` accepts only configured hosts. |
| High | The manual release sequence could migrate while old API/Dagster processes were active and had no durable release identity. | `deploy.sh` requires an exact clean SHA, versioned images, a recent restore receipt, quiesced runtime roles, a remotely verified pre-deploy backup, readiness checks, and an immutable release receipt. Any migration-started failure leaves writers stopped. |
| Medium | Same-day backup names could overwrite one another, R2 depended on hidden host config, partial uploads were not distinguishable, the pipeline shared backup authority, and the host pruned recovery objects. | Backup IDs are unique, rclone uses a distinct host-only credential, uploads are immutable and download-checked, a manifest is published last, and no remote delete operation exists on the host. R2 bucket lock and lifecycle are explicit launch gates. |

CI actions are pinned to immutable commit SHAs. Dependency review, CodeQL,
secret scanning, npm audit, pip-audit, Compose validation, and Caddy validation
form the automated security baseline.

The release images were also scanned after removing runtime package installers
and unused native development headers. Trivy reported zero fixable high or
critical vulnerabilities in the API and Dagster images on the review date.

## Residual Risks and Launch Blockers

- Restrict origin ports 80 and 443 to Cloudflare's current published IP ranges.
  Caddy rejects spoofed proxy headers, but a public origin still bypasses WAF
  and edge rate rules.
- Verify SSH key-only access, disable password/root SSH login after provisioning,
  and test the provider recovery console before making that change.
- Run a live external scan and abuse/load test against the actual Cloudflare and
  Caddy path. In-process rate limits are per Uvicorn worker and intentionally
  approximate.
- Block instance-metadata, link-local, host, and private-network destinations
  from the pipeline bridge in the host firewall. Application URL checks reduce
  SSRF risk but cannot eliminate DNS rebinding between resolution and connect.
- Perform and record the first live `restore-drill.sh` run, then monitor both
  the persistent systemd timer and R2 completion manifests. Repository tests
  cannot prove host scheduling, credential scope, or object retention.
- Keep person-linked distress routes disabled until the documented privacy and
  access decision exists. Rate limiting is not a substitute for authorization.
- Protect Dagster's loopback-only UI with SSH access discipline. If it ever
  becomes remotely reachable, add authentication before exposure.
- The single VPS remains an accepted availability risk. External runtime
  images are digest-pinned and updated through Dependabot, but a registry or
  upstream compromise before review remains a supply-chain risk.
- Enable Hetzner server deletion/rebuild protection and provider backups as a
  second recovery layer. They are not substitutes for R2 logical backups:
  provider backups follow the server lifecycle and live-disk consistency is
  not guaranteed.

## Pre-Launch Security Gate

1. Set `DOMAIN`, `COUNTYIQ_TRUSTED_HOSTS`, all three database secrets, and separate
   pipeline/search provider credentials; leave public API docs off.
2. Use `docker/deploy.sh --initial`; do not manually interleave migration and
   service replacement. Confirm both runtime roles are non-superusers and the
   API reports `transaction_read_only=on`.
3. Restrict the origin firewall to Cloudflare for HTTP(S), verify direct-IP
   requests fail, and verify real client addresses survive the proxy chain.
4. Confirm the private R2 bucket has a reviewed bucket lock and lifecycle rule,
   the host credential cannot configure the bucket, and one exact completed
   backup restores through `restore-drill.sh`.
5. Run the full verification ladder in `docs/operations/testing.md`, review
   CodeQL/dependency alerts, and run Gitleaks on the exact release revision.
6. Keep restricted distress disabled and record the privacy/access decision
   before any later enablement.
7. Enable Hetzner deletion/rebuild protection and server backups; record a
   protected post-provisioning snapshot without treating it as a live database
   consistency guarantee.
