"""Project bounded source-refresh evidence from Dagster into application health.

Only full source snapshots with a positive, explicit record count establish a
successful refresh. Incremental entity enrichment and municipal listing health
retain their separate contracts. No exception text or source payload is copied.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from dagster import DagsterEventType, DagsterInstance, DagsterRun

from countyiq.resources.database import DatabaseResource

ASSET_COUNT_FIELDS: dict[str, tuple[str, ...]] = {
    "parcels_arcgis": ("record_count",),
    "municipalities_arcgis": ("record_count",),
    "address_points_arcgis": ("record_count",),
    "structures_arcgis": ("record_count",),
    "roads_arcgis": ("record_count",),
    "zoning_arcgis": ("record_count",),
    "fema_flood_zones": ("record_count",),
    "plcb_licenses": ("record_count",),
    "penndot_roads_arcgis": ("record_count",),
    "penndot_projects_arcgis": ("record_count",),
    "tax_claims": ("record_count",),
    "sheriff_sales_scrape": ("record_count",),
    "traffic_counts_arcgis": ("record_count",),
    "zipcodes_arcgis": ("record_count",),
    "zoning_overlays_arcgis": ("record_count",),
    "planning_subdivisions_arcgis": ("record_count",),
    "growth_areas_arcgis": ("record_count",),
    "future_landuse_arcgis": ("record_count",),
    "conservation_easements_arcgis": ("record_count",),
    "ag_security_arcgis": ("record_count",),
    "business_parks_arcgis": ("record_count",),
    "industrial_parks_arcgis": ("record_count",),
    "soils_arcgis": ("record_count",),
    "local_traffic_counts_arcgis": ("record_count",),
    "pa_dep_environmental_diligence": ("storage_tank_count", "cleanup_site_count"),
}


@dataclass(frozen=True)
class AssetRefreshOutcome:
    asset_key: str
    finished_at: datetime
    status: Literal["success", "failure"]
    record_count: int | None = None
    failure_reason: str | None = None


def collect_asset_refresh_outcomes(
    instance: DagsterInstance,
    run: DagsterRun,
) -> list[AssetRefreshOutcome]:
    """Read materialization/failure events, including successes in failed runs."""
    outcomes = []
    cursor = None
    for _ in range(20):
        page = instance.get_records_for_run(
            run.run_id,
            cursor=cursor,
            of_type={
                DagsterEventType.ASSET_MATERIALIZATION,
                DagsterEventType.STEP_FAILURE,
            },
            limit=500,
            ascending=True,
        )
        for record in page.records:
            entry = record.event_log_entry
            event = entry.dagster_event
            if event is None:
                continue
            finished_at = datetime.fromtimestamp(entry.timestamp, tz=UTC)
            if event.event_type == DagsterEventType.STEP_FAILURE:
                # These source assets have one ordinary, identically named op.
                # Do not guess the asset identity of arbitrary dynamic steps.
                if event.step_key in ASSET_COUNT_FIELDS:
                    outcomes.append(
                        AssetRefreshOutcome(
                            asset_key=event.step_key,
                            finished_at=finished_at,
                            status="failure",
                            failure_reason="step_failed",
                        )
                    )
                continue
            materialization = event.step_materialization_data.materialization
            asset_key = materialization.asset_key.to_user_string()
            fields = ASSET_COUNT_FIELDS.get(asset_key)
            if fields is None:
                continue
            counts = [
                getattr(materialization.metadata.get(field), "value", None)
                for field in fields
            ]
            count = (
                sum(counts)
                if all(type(value) is int and value >= 0 for value in counts)
                else None
            )
            reason = None
            if count is None:
                reason = "unverified_result"
            elif count == 0:
                reason = "empty_result"
            outcomes.append(
                AssetRefreshOutcome(
                    asset_key=asset_key,
                    finished_at=finished_at,
                    status="failure" if reason else "success",
                    record_count=count,
                    failure_reason=reason,
                )
            )
        if not page.has_more:
            return outcomes
        if page.cursor == cursor:
            raise RuntimeError("Dagster event pagination did not advance")
        cursor = page.cursor
    raise RuntimeError("Source-refresh event scan exceeded its bounded page limit")


def record_asset_refresh_outcome(
    database: DatabaseResource,
    *,
    run: DagsterRun,
    outcome: AssetRefreshOutcome,
) -> None:
    """Preserve both the latest attempt and successes replayed out of order."""
    database.execute(
        """
        INSERT INTO meta.asset_refresh_status (
            asset_key, job_name, run_id, status, finished_at,
            last_success_at, record_count, failure_reason
        ) VALUES (
            %(asset_key)s, %(job_name)s, %(run_id)s, %(status)s, %(finished_at)s,
            CASE WHEN %(status)s = 'success' THEN %(finished_at)s END,
            %(record_count)s, %(failure_reason)s
        )
        ON CONFLICT (asset_key) DO UPDATE SET
            job_name = CASE
                WHEN EXCLUDED.finished_at >= meta.asset_refresh_status.finished_at
                    THEN EXCLUDED.job_name ELSE meta.asset_refresh_status.job_name
            END,
            run_id = CASE
                WHEN EXCLUDED.finished_at >= meta.asset_refresh_status.finished_at
                    THEN EXCLUDED.run_id ELSE meta.asset_refresh_status.run_id
            END,
            status = CASE
                WHEN EXCLUDED.finished_at >= meta.asset_refresh_status.finished_at
                    THEN EXCLUDED.status ELSE meta.asset_refresh_status.status
            END,
            finished_at = GREATEST(
                meta.asset_refresh_status.finished_at, EXCLUDED.finished_at
            ),
            last_success_at = GREATEST(
                meta.asset_refresh_status.last_success_at, EXCLUDED.last_success_at
            ),
            record_count = CASE
                WHEN EXCLUDED.finished_at >= meta.asset_refresh_status.finished_at
                    THEN EXCLUDED.record_count ELSE meta.asset_refresh_status.record_count
            END,
            failure_reason = CASE
                WHEN EXCLUDED.finished_at >= meta.asset_refresh_status.finished_at
                    THEN EXCLUDED.failure_reason ELSE meta.asset_refresh_status.failure_reason
            END,
            updated_at = NOW()
        """,
        {
            "asset_key": outcome.asset_key,
            "job_name": run.job_name,
            "run_id": run.run_id,
            "status": outcome.status,
            "finished_at": outcome.finished_at,
            "record_count": outcome.record_count,
            "failure_reason": outcome.failure_reason,
        },
    )
