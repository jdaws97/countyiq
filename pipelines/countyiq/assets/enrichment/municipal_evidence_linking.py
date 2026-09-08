"""Index literal municipal property references without inferring project outcomes."""

from dagster import AssetExecutionContext, MaterializeResult, MetadataValue, asset

from countyiq.resources.database import DatabaseResource

LINK_EVIDENCE_QUERY = """
    SELECT DISTINCT read.inference_id, card->>'id' AS card_id,
           matched.pidn, matched.match_method,
           CASE WHEN matched.match_method = 'address'
                THEN public.normalize_street_address(p.propadr) END AS normalized_address,
           p.municipality
    FROM public.current_municipal_reads read
    CROSS JOIN LATERAL jsonb_array_elements(read.payload->'cards') card
    CROSS JOIN LATERAL public.proceeding_parcel_matches(
        public.municipal_evidence_references(card), read.body_name) matched
    JOIN staging.parcels p ON p.pidn = matched.pidn AND p.valid_to IS NULL
"""


def refresh_evidence_links(database: DatabaseResource) -> int:
    """Atomically replace a derived index; retained source history is untouched."""
    with database.transaction() as cur:
        cur.execute(
            "SELECT pg_advisory_xact_lock(hashtext('countyiq:municipal_evidence_links'))"
        )
        cur.execute(
            "CREATE TEMP TABLE countyiq_new_evidence_links ON COMMIT DROP AS "
            + LINK_EVIDENCE_QUERY
        )
        cur.execute("DELETE FROM public.municipal_evidence_links")
        cur.execute("""
            INSERT INTO public.municipal_evidence_links (
                inference_id, card_id, pidn, match_method, normalized_address, municipality
            )
            SELECT inference_id, card_id, pidn, match_method, normalized_address, municipality
            FROM pg_temp.countyiq_new_evidence_links
        """)
        return cur.rowcount


@asset(
    group_name="enrichment",
    deps=["proceeding_extraction", "municipality_join"],
    description="Match literal municipal PIDNs and unique addresses to current properties, without inference",
    kinds={"postgres"},
)
def municipal_evidence_linking(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> MaterializeResult:
    count = refresh_evidence_links(database)
    context.log.info("Indexed %d current municipal property references", count)
    return MaterializeResult(metadata={"property_references": MetadataValue.int(count)})
