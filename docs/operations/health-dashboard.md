# Operational Visibility & Health Dashboard

## Operational Visibility

### The Three Layers

| Layer | Tool | Purpose | When to Use |
|---|---|---|---|
| **Phone buzzes** | Slack push notifications | Something needs attention NOW | Automatic — `#alerts-critical` |
| **Scrollable history** | Slack channels | What happened today/this week | Open Slack, scroll `#pipeline-runs` |
| **Dashboard** | `/ops/health` page in your frontend | "Is everything healthy?" at a glance | Morning check-in, or whenever curious |
| **Deep-dive** | Dagster UI (via SSM port forward) | Investigate specific run failures, view logs, re-trigger runs | When debugging a specific issue |
| **Infra deep-dive** | CloudWatch console | EC2/RDS metrics, log streams | Rarely — only for infra-level investigation |

### Health Dashboard (`/ops/health`)

A page built into your React frontend that queries the Lambda API for system health. This is your "single pane of glass" — open it on your phone or laptop and see green/yellow/red for everything.

**API Endpoint:** `GET /api/ops/health` (CloudFront routes `/api/*` to API Gateway → Lambda)

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
    "ec2_cpu_pct": 12.3,
    "ec2_memory_used_pct": 62,
    "ec2_disk_used_pct": 38,
    "rds_free_storage_gb": 15.8,
    "rds_connections": 8
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

**Note:** These display statuses are **derived by the Lambda API handler**, not stored in the database. The `meta.pipeline_status` table stores raw pipeline outcomes (`SUCCESS`, `FAILURE`, `IN_PROGRESS`). The API computes the display status by comparing `last_run_at` and `schedule_type` against the current time:
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
│  │ EC2: Running    CPU 12%   Memory 58%   Disk 38%           │  │
│  │ RDS: Available  Storage 4.2 / 20 GB    Connections 3      │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌─── ENTITY RESOLUTION ──────────────────────────────────────┐  │
│  │ Last run: today 5:42 PM   Owners: 142,318   Matches: 8,921│  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### How the Health Page Gets Its Data

The health data comes from one place: **RDS**. Lambda is in a VPC with no internet access, so it cannot call AWS APIs (CloudWatch, etc.) directly. All data the health page needs is in the database.

1. **Dagster run history** — Dagster stores all run metadata (status, timestamps, record counts) in its own database on the same RDS instance. The Lambda API queries a `meta.pipeline_status` table (see below).

2. **Infrastructure metrics** — A Dagster sensor on EC2 polls CloudWatch every 5 minutes and writes EC2/RDS metrics to `meta.infra_metrics`. Lambda reads this table instead of calling CloudWatch directly. This avoids the need for a NAT Gateway or VPC Endpoints.

**Dagster infra metrics sensor (runs on EC2, which HAS internet access):**

```python
# pipelines/sensors/infra_metrics.py
import boto3
from dagster import sensor, RunRequest
from lib.database import get_connection

@sensor(minimum_interval_seconds=300)  # Every 5 minutes
def infra_metrics_sensor(context):
    """Poll CloudWatch and write EC2/RDS metrics to RDS for the health page."""
    cw = boto3.client("cloudwatch", region_name="us-east-1")
    conn = get_connection()

    # Fetch key metrics
    metrics = {
        "ec2_cpu_pct": get_metric(cw, "AWS/EC2", "CPUUtilization", "york-county-dagster"),
        "rds_free_storage_gb": get_metric(cw, "AWS/RDS", "FreeStorageSpace", "york-county-db") / 1e9,
        "rds_connections": get_metric(cw, "AWS/RDS", "DatabaseConnections", "york-county-db"),
    }

    conn.execute("""
        INSERT INTO meta.infra_metrics (checked_at, metrics)
        VALUES (NOW(), %s)
    """, [json.dumps(metrics)])

    # Keep only last 24 hours of metrics
    conn.execute("DELETE FROM meta.infra_metrics WHERE checked_at < NOW() - INTERVAL '24 hours'")
```

**Lambda API handler:**

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

    # Get infra metrics from RDS (written by Dagster sensor, NOT from CloudWatch API)
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

The `/ops/health` page is part of the public frontend (no auth for MVP). If you want to restrict it later, you can add a simple API key check or move it behind CloudFront's signed URLs.

**Quick access pattern:**
- Bookmark `https://your-cloudfront-url.cloudfront.net/ops/health` on your phone (this is the React frontend route; the page calls `/api/ops/health` internally)
- Morning routine: open bookmark, glance at colors, done
