# Dagster Runtime

## Production Processes

The Compose stack runs `dagster-webserver` and `dagster-daemon` as separately
supervised containers from the same CountyIQ pipeline image. If schedule or
sensor evaluation dies, the daemon container fails independently instead of
being hidden behind a healthy webserver process.

Both processes load `countyiq.definitions` directly. This is intentionally a
single-code-location deployment for one VPS; a separate gRPC code-server tier
would add operational surface without isolating another team or machine.

## Durable State

- Dagster run, event, and schedule storage uses the `dagster` database in the
  production PostgreSQL/PostGIS container.
- Local artifacts and compute logs use the shared `dagster-storage` volume at
  `/opt/dagster/storage`.
- Source and model archives use the host-backed `/opt/countyiq/archives` mount
  and are copied off-host by `docker/backup.sh`.
- Both the `countyiq` and `dagster` databases are included in daily backups.

SQLite is not part of the production path. Local test-created Dagster homes
are generated artifacts and are ignored by git.

## Registered Schedules

All schedules use `America/New_York` explicitly. The source jobs are staggered
before the Sunday deterministic enrichment run; manual pass-specific jobs
remain available in the Dagster UI but have no schedules.

| Schedule | Cadence |
|---|---|
| `weekly_arcgis` | Sunday 02:00 |
| `weekly_radar` | Sunday 02:30 |
| `weekly_scrapers` | Sunday 03:00 |
| `weekly_pa_dos` | Sunday 03:30 |
| `weekly_fema` | Sunday 04:00 |
| `weekly_deterministic_enrichment` | Sunday 08:00 |
| `monthly_bulk` | First day of month 05:00 |

The schedule list in `countyiq/schedules/__init__.py` is authoritative. A new
source asset joins an existing job only when that job selects its group. Paid
LLM assets must remain outside every schedule. A new group or cadence requires
a registered job, schedule, wiring test, and this table to be updated together.
