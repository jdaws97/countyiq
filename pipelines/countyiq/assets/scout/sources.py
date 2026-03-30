"""County Scout discovery and monitoring assets."""

from __future__ import annotations

import os

from dagster import (
    AssetCheckResult,
    AssetCheckSeverity,
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
    asset_check,
)

from countyiq.lib.county_config import get_county_config
from countyiq.lib.scout.discovery import (
    PROMOTION_THRESHOLD,
    discover_county_sources,
    monitor_registry_sources,
    select_promoted_candidates,
)
from countyiq.lib.scout.persistence import (
    apply_registry_monitor_updates,
    candidate_count_summary,
    fetch_registry_sources,
    insert_source_observations,
    promote_source_registry,
    upsert_source_candidates,
)
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource


@asset(
    group_name="scout",
    description="Discover, classify, score, and promote York County public-intelligence sources.",
    kinds={"postgres", "requests"},
)
def county_scout_discovery(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Discover York County source candidates and promote the strongest ones."""
    county_key = os.environ.get("COUNTY", "york")
    county = get_county_config(county_key)

    candidates, observations = discover_county_sources(county_key=county_key)
    promoted = select_promoted_candidates(candidates)

    upsert_source_candidates(database, candidates)
    insert_source_observations(database, observations)
    promote_source_registry(database, promoted)

    snapshot = {
        "county": county_key,
        "candidate_count": len(candidates),
        "promoted_count": len(promoted),
        "promotion_threshold": PROMOTION_THRESHOLD,
        "sources": [
            {
                "source_key": candidate.source_key,
                "source_name": candidate.source_name,
                "source_url": candidate.source_url,
                "source_type": candidate.source_type,
                "platform": candidate.platform,
                "extraction_method": candidate.extraction_method,
                "value_score": candidate.value_score,
                "risk_level": candidate.risk_level,
                "categories": candidate.categories,
            }
            for candidate in candidates
        ],
    }
    s3.archive(f"{county.s3_prefix}/scout/discovery", snapshot, filename="snapshot.json")

    high_value = sum(1 for candidate in candidates if candidate.value_score >= PROMOTION_THRESHOLD)
    return MaterializeResult(
        metadata={
            "county": MetadataValue.text(county_key),
            "candidate_count": MetadataValue.int(len(candidates)),
            "observation_count": MetadataValue.int(len(observations)),
            "high_value_candidates": MetadataValue.int(high_value),
            "promoted_count": MetadataValue.int(len(promoted)),
        }
    )


@asset(
    group_name="scout",
    description="Re-check promoted County Scout sources for changes, outages, and access degradation.",
    kinds={"postgres", "requests"},
)
def county_scout_monitor(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Monitor already-promoted source registry entries."""
    county_key = os.environ.get("COUNTY", "york")
    county = get_county_config(county_key)

    registry_rows = fetch_registry_sources(database, county_key)
    if not registry_rows:
        context.log.warning("County Scout registry is empty; skipping monitor run")
        return MaterializeResult(
            metadata={
                "county": MetadataValue.text(county_key),
                "monitored_sources": MetadataValue.int(0),
            }
        )

    updates, observations = monitor_registry_sources(registry_rows)
    apply_registry_monitor_updates(database, updates)
    insert_source_observations(database, observations)

    changed = sum(1 for update in updates if update.last_changed)
    blocked = sum(1 for update in updates if update.health_status == "blocked")
    errors = sum(1 for update in updates if update.health_status == "error")
    s3.archive(
        f"{county.s3_prefix}/scout/monitor",
        {
            "county": county_key,
            "updates": [
                {
                    "source_key": update.source_key,
                    "source_url": update.source_url,
                    "health_status": update.health_status,
                    "last_changed": update.last_changed,
                    "status_code": update.status_code,
                }
                for update in updates
            ],
        },
        filename="status.json",
    )

    return MaterializeResult(
        metadata={
            "county": MetadataValue.text(county_key),
            "monitored_sources": MetadataValue.int(len(registry_rows)),
            "changed_sources": MetadataValue.int(changed),
            "blocked_sources": MetadataValue.int(blocked),
            "error_sources": MetadataValue.int(errors),
        }
    )


@asset_check(asset=county_scout_discovery)
def county_scout_registry_depth(database: DatabaseResource) -> AssetCheckResult:
    """Sanity check that discovery is populating more than a trivial registry."""
    county_key = os.environ.get("COUNTY", "york")
    candidate_count, registry_count = candidate_count_summary(database, county_key)
    passed = candidate_count >= 10 and registry_count >= 5
    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.WARN,
        metadata={
            "county": MetadataValue.text(county_key),
            "candidate_count": MetadataValue.int(candidate_count),
            "registry_count": MetadataValue.int(registry_count),
        },
    )
