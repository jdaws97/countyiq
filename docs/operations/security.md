# Security and Production-Readiness Review

**Review date:** 2026-08-30

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
| Medium | Dynamic County Scout URLs and HTTP redirects could target loopback, private networks, or instance metadata. | Discovery and robots requests validate every hop as credential-free public HTTP(S), reject any hostname resolving to a non-global address, and strip sensitive headers across origins. Separate container egress networks reduce lateral reach. |
| Medium | API and pipeline processes ran as container root with the default capability set. | Both application images use UID/GID 10001. Compose drops all capabilities, sets `no-new-privileges`, adds PID ceilings, and makes both application filesystems read-only. Caddy retains only `NET_BIND_SERVICE`. |
| Medium | The VPS bootstrap executed mutable remote installer scripts as root and printed the generated database password. | Bootstrap uses signed Ubuntu packages, requires a reviewed 40-character commit SHA, generates separate hex credentials under `umask 077`, and never prints them. |
| Medium | Owner/entity portfolio routes lacked the privacy backlog's anti-scraping control. | Those routes now have a dedicated per-client token bucket behind the Cloudflare boundary. This is abuse resistance, not authorization. |
| Low | Public Swagger/OpenAPI routes and arbitrary Host headers were accepted by default. | Docs require explicit opt-in and `TrustedHostMiddleware` accepts only configured hosts. |
| Low | Backups were uploaded without a local archive-integrity check or checksum and overlapping cron runs were possible. | The backup job uses a lock, validates each custom-format dump with `pg_restore --list`, creates SHA-256 sidecars, and uses private file permissions. |

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
- Perform and record a full off-host backup restore. Dump validation proves the
  archive is readable; it does not prove the complete recovery procedure.
- Keep person-linked distress routes disabled until the documented privacy and
  access decision exists. Rate limiting is not a substitute for authorization.
- Protect Dagster's loopback-only UI with SSH access discipline. If it ever
  becomes remotely reachable, add authentication before exposure.
- The single VPS remains an accepted availability risk. External runtime
  images are digest-pinned and updated through Dependabot, but a registry or
  upstream compromise before review remains a supply-chain risk.

## Pre-Launch Security Gate

1. Set `DOMAIN`, `COUNTYIQ_TRUSTED_HOSTS`, all three database secrets, and separate
   pipeline/search provider credentials; leave public API docs off.
2. Apply migrations with the administrator credential, then run
   `/docker-entrypoint-initdb.d/02-runtime-role.sh` and
   `/docker-entrypoint-initdb.d/03-api-role.sh`. Confirm both roles are
   non-superusers and the API reports `transaction_read_only=on`.
3. Restrict the origin firewall to Cloudflare for HTTP(S), verify direct-IP
   requests fail, and verify real client addresses survive the proxy chain.
4. Confirm R2 credentials are least-privilege, archives are private, and one
   clean restore works on an isolated database.
5. Run the full verification ladder in `docs/operations/testing.md`, review
   CodeQL/dependency alerts, and run Gitleaks on the exact release revision.
6. Keep restricted distress disabled and record the privacy/access decision
   before any later enablement.
