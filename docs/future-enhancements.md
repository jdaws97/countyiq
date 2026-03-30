# Future Enhancements

## Future Enhancements (Not Implemented)

These are documented for future reference. None are needed for the MVP.

### 1. VPS Resize

**Trigger:** Sustained memory usage > 80% (check via `docker stats` or monitoring cron).

**Action:** Hetzner console -> resize CX23 to CX33 (4 vCPU, 8GB RAM). Cost: EUR6/mo. Downtime: ~2 minutes. No architecture changes — same Docker Compose, same containers, just more headroom.

### 2. NAIP Imagery Pipeline (Phase 2)

**Concept:** Download USDA NAIP orthophotos for York County, store in R2, and serve as a tile layer for change detection analysis. Dagster asset processes raw imagery and generates difference tiles.

**Estimated storage:** 10-20 GB per year of coverage stored in R2. Multi-year comparison: 30-60 GB.

### 3. Dagster Cloud Hybrid

**Trigger:** Need for multi-user Dagster UI access without SSH tunnels.

**Concept:** Dagster Cloud free tier handles orchestration UI (hosted by Dagster). The VPS runs the actual compute via a Dagster agent container. Eliminates the need for `ssh -L 3000:localhost:3000 countyiq` to access Dagster.

**Cost:** Free tier available (limited concurrent runs).

### 4. Cloudflare Workers

**Trigger:** Need for edge compute beyond what Cloudflare's free WAF provides.

**Use cases:**
- API response caching — cache GET `/api/parcels/bbox` responses for 5 minutes at the edge
- Geo-blocking — restrict to US IPs if needed
- Custom rate limiting rules beyond free WAF tier
- Request transformation or header injection

**Cost:** Workers free tier includes 100K requests/day. Paid plan ($5/mo) for higher limits.

### 5. Automated Cost Monitoring

**Concept:** Simple Python script run via cron that polls Hetzner API for usage/billing and Cloudflare API for R2 storage usage. Posts to Slack if costs exceed a threshold.

**Implementation outline:**
- Hetzner API: check current invoice amount
- Cloudflare API: check R2 storage and operations usage
- Compare against thresholds (e.g., Hetzner > 10 EUR, R2 > 5GB)
- Post to `#alerts-warning` Slack channel on threshold breach

**Why deferred:** Hetzner is fixed monthly pricing and Cloudflare is free tier. Costs are predictable. Revisit when R2 usage grows beyond free tier.

### 6. Multi-VPS Split

**Trigger:** API and pipeline workloads conflict on the same VPS (e.g., Dagster Playwright jobs starving API of memory during peak hours).

**Concept:** Separate VPS for Dagster (pipeline-heavy) and VPS for API + Postgres (latency-sensitive). Postgres stays on the API VPS. Dagster connects over private network (Hetzner vSwitch).

**Cost:** Second CX23 adds EUR3.49/mo.

**Why deferred:** Unlikely needed at county scale. 4GB RAM with staggered schedules should be sufficient. The monitoring cron will surface memory pressure before it becomes a problem.

### 7. Automated Backup Verification

**Concept:** Monthly cron job that restores the latest pg_dump to a temporary Docker Postgres container, runs schema validation queries, and posts results to Slack. Ensures backups are actually restorable without manual testing.

**Implementation outline:**
- Pull latest backup from R2
- Start temporary Postgres container with the backup
- Run `SELECT count(*) FROM public.properties` and other validation queries
- Compare row counts against expected ranges
- Post pass/fail results to `#alerts-warning` Slack channel
- Remove temporary container

**Why deferred:** Manual monthly restore test is sufficient for MVP. Automate when backup volume or complexity increases.
