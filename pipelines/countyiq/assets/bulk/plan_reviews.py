"""Manual, private conservation-district review snapshots."""

from dagster import AssetExecutionContext, MaterializeResult, asset

from countyiq.lib.county_config import get_county_config
from countyiq.lib.plan_review_snapshots import collect_snapshot
from countyiq.lib.source_rights import authorize_source, require_source_use
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource


@asset(group_name="source_pilots", kinds={"pdf"})
def plan_review_snapshot(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    county = get_county_config()
    if not county.plan_review_listing_url or not county.plan_review_source_key:
        return MaterializeResult(metadata={"status": "not configured"})
    if not s3.strict:
        raise ValueError("Review snapshots require strict archive persistence")
    authorization = authorize_source(
        database,
        source_key=county.plan_review_source_key,
        acquisition_method="official_pdf",
        asset_key="plan_review_snapshot",
        dagster_run_id=context.run_id,
    )
    require_source_use(authorization, "raw_retention")
    content, snapshot = collect_snapshot(
        county.plan_review_listing_url,
        delay_seconds=county.plan_review_crawl_delay_seconds,
    )
    if snapshot["source_key"] != authorization.source_key:
        raise ValueError("Parsed review source does not match its authorization")
    snapshot["dagster_run_id"] = context.run_id
    prefix = f"{county.s3_prefix}/source_pilots/plan_reviews".strip("/")
    stem = snapshot["source_sha256"]
    s3.archive(prefix, content, filename=f"{stem}.pdf")
    s3.archive(prefix, snapshot, filename=f"{stem}-{context.run_id}.json")
    return MaterializeResult(
        metadata={
            "source_date": snapshot["document_date"],
            "source_url": snapshot["document_url"],
            "source_sha256": stem,
            "rows": len(snapshot["rows"]),
            "archive_prefix": prefix,
            "publication": "Private review snapshot; no project links or customer publication",
        }
    )
