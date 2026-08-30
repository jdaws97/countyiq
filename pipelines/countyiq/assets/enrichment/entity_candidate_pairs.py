"""Maintain the deterministic Pass 1 candidate-pair materialized view."""

from dagster import AssetExecutionContext, MaterializeResult, MetadataValue, asset

from countyiq.lib.pass1_entity_verification import REFRESH_CANDIDATE_PAIRS
from countyiq.resources.database import DatabaseResource


@asset(
    group_name="enrichment",
    deps=["municipality_join"],
    description=(
        "Refresh the trigram candidate-pair materialized view used by Pass 1; "
        "deterministic and makes no model calls"
    ),
    kinds={"postgres"},
)
def entity_candidate_pairs_refresh(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> MaterializeResult:
    context.log.info("Refreshing public.entity_candidate_pairs")
    database.execute(REFRESH_CANDIDATE_PAIRS)
    rows = database.execute("SELECT COUNT(*) FROM public.entity_candidate_pairs") or []
    pair_count = int(rows[0][0]) if rows else 0
    context.log.info("Refreshed %d candidate entity pairs", pair_count)
    return MaterializeResult(
        metadata={"candidate_pairs": MetadataValue.int(pair_count)}
    )
