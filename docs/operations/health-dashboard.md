# Source Availability Page

The page summarizes healthy sources, sources needing attention, stale refreshes,
and distinct jobs whose latest observed run failed. Source cards put unhealthy
entries first and can be filtered to **Needs attention**. Manual refresh and a
one-minute refresh while the tab is visible reload the cached API response.
Source cards remain visible without animation. Municipal counts distinguish
active bodies needing attention from the broader paused-or-blocked count.

Access requires a verified human identity whose email appears in the
comma-separated `COUNTYIQ_OPERATOR_EMAILS` allowlist. The API checks this on
every request, including cache hits. An empty allowlist denies everyone, and
disabling authentication locally does not bypass operator authorization.
The session exposes an `operator` flag; the page and navigation use it to show
the dashboard only to operators. The server remains the authorization boundary.

The React route `/ops/health` calls `GET /api/ops/health` and displays current
row counts, source-refresh freshness, the latest job outcome, source-policy
review state, and municipal-source health. The API returns entries shaped like:

```json
{
  "overall": "green",
  "sources": {
    "parcels": {
      "status": "green",
      "status_reason": "healthy",
      "record_count": 176060,
      "refresh_job": "arcgis_refresh",
      "expected_refresh_hours": 192,
      "last_run_status": "success",
      "last_run_at": "2026-08-30T06:00:00Z",
      "last_success_at": "2026-08-30T06:00:00Z",
      "freshness_due_at": "2026-09-07T06:00:00Z",
      "stale": false
    },
    "municipal_proceedings": {
      "status": "red",
      "status_reason": "source_unhealthy",
      "configured_count": 122,
      "active_count": 110,
      "healthy_count": 96,
      "blocked_count": 26,
      "unchecked_count": 0,
      "stale_count": 0,
      "record_count": 7152,
      "refresh_job": "scraper_refresh",
      "last_run_status": "success"
    }
  },
  "intelligence_integrity": {
    "status": "yellow",
    "status_reason": "unresolved_contradictions",
    "accepted_count": 124,
    "quarantined_count": 2,
    "unresolved_contradiction_count": 1,
    "resolved_contradiction_count": 1,
    "oldest_unresolved_at": "2026-08-31T12:00:00Z",
    "unlinked_projection_count": 0,
    "projection_mismatch_count": 0,
    "validation_rejection_count": 3,
    "validation_rejections_last_24h": 1,
    "latest_validation_rejection_at": "2026-08-31T12:05:00Z"
  },
  "summary": "26/27 sources healthy; intelligence integrity yellow"
}
```

Sources with a weekly freshness target are healthy for eight days after their
latest verified refresh; monthly bulk sources are healthy for 35 days. These
are freshness limits, not automatic schedules: operators run local commands.
A source is red
when its table is missing, its count query fails, it has no current rows, no job
outcome has been observed, its latest owning job failed, or its latest success
is older than the configured window. An observed success does not make an
empty source green. Migration 037 starts the job projection empty, so existing
data correctly remains `run_not_observed` until the corresponding job next
completes.

Mapped source cards use `meta.asset_refresh_status`, so a successful asset does
not inherit a sibling's failure in the same job. Only verified nonempty
materializations advance successful freshness; failed or missing asset checks
leave the result unverified. The local runner publishes both asset and job
receipts before exiting. The job projection remains relevant to municipal
proceedings and to older databases without the asset ledger. A newer targeted
`proceedings_refresh` run can update the municipal card after focused recovery.
Full execution history stays in the PC's persistent Dagster state.

The municipal entry also checks every active body's `checked_at` timestamp.
Paused and blocked/failed/uncertain sources remain visible, and document counts
include active policies only so stale health from a subsequently paused source
cannot inflate coverage. Health never changes rights status or grants
collection permission.

The manual `staging.pa_open_data` compatibility table has no alpha consumer and
does not affect product health. The bounded PA DOS `staging.corporate_entities`
input and every configured Radar source family do. The compatibility table
remains a manual retire candidate until external operator compatibility is
confirmed.

Overall status is green when all sources are green, yellow when more than half
are green, and red otherwise, then worsened by intelligence-integrity status.
A new unresolved contradiction is yellow so the prior accepted projection can
remain available during review. It becomes red after
`COUNTYIQ_CONTRADICTION_MAX_AGE_HOURS` (72 by default). Any model-backed row
without accepted provenance or pointing to the wrong pass/output kind is red
immediately. A deterministic evidence, identity-membership, or citation gate
rejection in the last 24 hours is yellow and remains a failed canary condition.
The aggregate exposes no inference payloads or identities.

The result is cached for 60 seconds per Uvicorn worker because navigation also
consumes it; `COUNTYIQ_OPS_HEALTH_TTL` can change that window.

This remains application health, not infrastructure telemetry. It does not
report CPU, memory, disk, container state, or step-level Dagster history.
Use [infrastructure monitoring](monitoring.md) for host telemetry and
[local pipeline commands](local-pipelines.md) for execution logs and receipt
replay. There is no VPS Dagster UI.
