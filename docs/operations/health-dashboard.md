# Source Availability Page

The React route `/ops/health` calls `GET /api/ops/health` and displays current
row counts for staging sources plus the municipal-source governance rollup.
The API returns entries shaped like:

```json
{
  "overall": "green",
  "sources": {
    "parcels": {"status": "green", "record_count": 176060},
    "municipal_proceedings": {
      "status": "red",
      "configured_count": 122,
      "active_count": 110,
      "healthy_count": 96,
      "blocked_count": 26,
      "unchecked_count": 0,
      "document_count": 7152
    }
  },
  "summary": "15/16 sources active"
}
```

A source is green when its table exists, the count query succeeds, and at
least one `valid_to IS NULL` row exists. A missing table, query failure, or
zero current rows is red. Overall status is green when all sources are green,
yellow when more than half are green, and red otherwise.

The municipal entry is computed from the 122 per-body policy rows and their
latest health records. Paused and blocked/failed/uncertain sources remain
visible, and document counts include active policies only so stale health from
a subsequently paused source cannot inflate coverage. The example reflects the
2026-08-27 retained audit; the API is authoritative at runtime. Health never
changes rights status or grants collection permission.

The result is cached for 60 seconds per Uvicorn worker because the navigation
bar and homepage also consume it. `COUNTYIQ_OPS_HEALTH_TTL` can change that
window.

This is an availability/count page, not a pipeline observability system. It
does not currently report last materialization, expected cadence, failed
Dagster runs, CPU, memory, disk, or container state; a stale populated table
will remain green. Dagster UI and container health checks remain the operator
tools until the freshness item in `docs/open-items.md` is implemented.

The Dagster UI is bound to host loopback. Reach it through an SSH tunnel:

```bash
ssh -L 3000:localhost:3000 countyiq
```

Then open `http://localhost:3000`.
