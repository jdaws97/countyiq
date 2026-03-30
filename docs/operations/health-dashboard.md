# Operational Visibility & Health Dashboard

## Operational Visibility

### The Three Layers

| Layer | Tool | Purpose | When to Use |
|---|---|---|---|
| **Phone buzzes** | Slack push notifications | Something needs attention NOW | Automatic — `#alerts-critical` |
| **Scrollable history** | Slack channels | What happened today/this week | Open Slack, scroll `#pipeline-runs` |
| **Dashboard** | `/ops/health` page in your frontend | "Is everything healthy?" at a glance | Morning check-in, or whenever curious |
| **Deep-dive** | Dagster UI (via SSH tunnel) | Investigate specific run failures, view logs, re-trigger runs | When debugging a specific issue |

### Health Dashboard (`/ops/health`)

A page built into your React frontend that queries the API for system health. This is your "single pane of glass" — open it on your phone or laptop and see green/yellow/red for everything.

**API Endpoint:** `GET /api/ops/health` (Caddy reverse-proxies `/api/*` to the API container)

**Frontend route:** `/ops/health` (React client-side route — the React page fetches `/api/ops/health` and renders the dashboard)

**Response structure:**

```json
{
  "overall_status": "healthy",
  "checked_at": "2026-03-20T18:00:00Z",
  "sources": [
    {
      "name": "parcels_arcgis",
      "schedule": "weekly",
      "last_success": "2026-03-16T02:14:22Z",
      "last_record_count": 176060,
      "prev_record_count": 175982,
      "status": "healthy",
      "next_run": "2026-03-23T02:00:00Z"
    },
    {
      "name": "flood_zones",
      "schedule": "weekly",
      "last_success": "2026-03-16T04:03:11Z",
      "last_record_count": 48200,
      "prev_record_count": 48200,
      "status": "healthy",
      "next_run": "2026-03-23T04:00:00Z"
    },
    {
      "name": "pa_open_data",
      "schedule": "weekly",
      "last_success": "2026-03-17T02:22:45Z",
      "last_record_count": 12400,
      "prev_record_count": 12380,
      "status": "healthy",
      "next_run": "2026-03-24T02:00:00Z"
    },
    {
      "name": "penndot_open_data",
      "schedule": "weekly",
      "last_success": "2026-03-17T03:08:33Z",
      "last_record_count": 3200,
      "prev_record_count": 3180,
      "status": "healthy",
      "next_run": "2026-03-24T03:00:00Z"
    },
    {
      "name": "penndot_projects",
      "schedule": "weekly",
      "last_success": "2026-03-17T02:45:00Z",
      "last_record_count": 78,
      "prev_record_count": 76,
      "status": "healthy",
      "next_run": "2026-03-24T02:00:00Z"
    }
  ],
  "infrastructure": {
    "cpu_pct": 12.3,
    "memory_used_pct": 62,
    "disk_used_pct": 38,
    "postgres_size_gb": 4.2,
    "postgres_connections": 8
  }
}
```

**Status logic:**

| Status | Color | Rule |
|---|---|---|
| `healthy` | 🟢 Green | Last run succeeded within expected schedule window |
| `late` | 🟡 Yellow | Last run succeeded, but it's overdue for the next run (missed schedule) |
| `error` | 🔴 Red | Last run failed after all retries |
| `unknown` | ⚪ Gray | Never run (new source, or on-demand only) |

**Note:** These display statuses are **derived by the API handler**, not stored in the database. The `meta.pipeline_status` table stores raw pipeline outcomes (`SUCCESS`, `FAILURE`, `IN_PROGRESS`). The API computes the display status by comparing `last_run_at` and `schedule_type` against the current time:
- `healthy` = status is SUCCESS and last_run_at is within the expected schedule window
- `late` = status is SUCCESS but next_scheduled_run has passed without a new run
- `error` = status is FAILURE (after all retries exhausted)
- `unknown` = no row exists in meta.pipeline_status for this source (never run or new)

**UI mockup:**

```
┌──────────────────────────────────────────────────────────────────┐
│  YORK COUNTY PLATFORM — OPERATIONS HEALTH          March 20 6PM │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Overall: 🟢 HEALTHY (5/5 sources OK)                         │
│                                                                  │
│  ┌─── WEEKLY SOURCES (MVP) ─────────────────────────────────────┐  │
│  │ 🟢 Parcels (ArcGIS)      176,060 parcels   Mon 2:14 AM    │  │
│  │ 🟢 FEMA Flood Zones      48,200 zones      Mon 4:03 AM    │  │
│  │ 🟢 PA Open Data          12,400 records    Tue 2:22 AM    │  │
│  │ 🟢 PennDOT Open Data     3,200 records     Tue 3:08 AM    │  │
│  │ 🟢 PennDOT Projects      78 projects       Tue 2:45 AM    │  │
│  │    (Assessment: one-time bulk import at launch)            │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌─── INFRASTRUCTURE ─────────────────────────────────────────┐  │
│  │ VPS: Running   CPU 12%   Memory 58%   Disk 38%            │  │
│  │ Postgres: 4.2 GB                      Connections 3       │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌─── ENTITY RESOLUTION ──────────────────────────────────────┐  │
│  │ Last run: today 5:42 PM   Owners: 142,318   Matches: 8,921│  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### How the Health Page Gets Its Data

The health data comes from one place: **Postgres**. The API container queries the database directly for both pipeline status and infrastructure metrics.

1. **Dagster run history** — Dagster stores all run metadata (status, timestamps, record counts) in its own database on the same Postgres instance. The API queries a `meta.pipeline_status` table (see below).

2. **Infrastructure metrics** — A Dagster sensor running inside the Dagster container collects VPS metrics directly using `psutil` and the Docker SDK, then writes them to `meta.infra_metrics`. The API reads this table.

**Dagster infra metrics sensor (collects from VPS directly):**

```python
# pipelines/sensors/infra_metrics.py
import json
import psutil
import docker
from dagster import sensor, RunRequest
from lib.database import get_connection

@sensor(minimum_interval_seconds=300)  # Every 5 minutes
def infra_metrics_sensor(context):
    """Collect VPS metrics and write to Postgres for the health page."""
    conn = get_connection()
    client = docker.from_env()

    # Collect system metrics via psutil
    cpu_pct = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/opt/countyiq")

    # Check container status
    containers = client.containers.list(all=True)
    container_status = {
        c.name: c.status for c in containers
        if c.name.startswith("countyiq-")
    }

    # Check Postgres connections
    pg_connections = conn.execute(
        "SELECT count(*) FROM pg_stat_activity WHERE datname = 'countyiq';"
    ).scalar()

    # Check Postgres database size
    pg_size_bytes = conn.execute(
        "SELECT pg_database_size('countyiq');"
    ).scalar()

    metrics = {
        "cpu_pct": cpu_pct,
        "memory_used_pct": mem.percent,
        "disk_used_pct": disk.percent,
        "postgres_size_gb": round(pg_size_bytes / 1e9, 2),
        "postgres_connections": pg_connections,
        "container_status": container_status,
    }

    conn.execute("""
        INSERT INTO meta.infra_metrics (checked_at, metrics)
        VALUES (NOW(), %s)
    """, [json.dumps(metrics)])

    # Keep only last 24 hours of metrics
    conn.execute("DELETE FROM meta.infra_metrics WHERE checked_at < NOW() - INTERVAL '24 hours'")
```

**API handler:**

```python
# api/routes/ops.py
from fastapi import APIRouter
from lib.database import get_connection

router = APIRouter()

@router.get("/health")  # Mounted at /api/ops by main.py → full path: /api/ops/health
def health_check():
    conn = get_connection()

    # Query pipeline status (written by Dagster sensor, decoupled from Dagster internals)
    sources = conn.execute("""
        SELECT
            source_name,
            status,
            last_run_at,
            duration_seconds,
            record_count,
            prev_record_count,
            error_message
        FROM meta.pipeline_status
        ORDER BY source_name
    """).fetchall()

    # Get infra metrics from Postgres (written by Dagster sensor)
    infra = conn.execute("""
        SELECT metrics FROM meta.infra_metrics
        ORDER BY checked_at DESC LIMIT 1
    """).scalar()

    return {
        "overall_status": "healthy" if all(s.status == "SUCCESS" for s in sources) else "degraded",
        "sources": [format_source(s) for s in sources],
        "infrastructure": json.loads(infra) if infra else {}
    }
```

### Access

The `/ops/health` page is part of the public frontend (no auth for MVP). If you want to restrict it later, you can add a simple API key check or Cloudflare Access.

**Quick access pattern:**
- Bookmark `https://countyiq.dev/ops/health` on your phone (this is the React frontend route; the page calls `/api/ops/health` internally)
- Morning routine: open bookmark, glance at colors, done

**Dagster UI access (for deep investigation):**
```bash
# SSH tunnel to the Dagster webserver container
ssh -L 3000:localhost:3000 countyiq

# Then open http://localhost:3000 in your browser
```
