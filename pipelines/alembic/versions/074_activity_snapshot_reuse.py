"""Reuse accepted matter snapshots for discovery and normalize spaced case IDs."""

from alembic import op

revision = "074"
down_revision = "073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(r"""
        CREATE OR REPLACE FUNCTION public.municipal_case_reference(title text)
        RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $function$
            SELECT lower(regexp_replace(COALESCE(
                substring(title FROM '(?i)\m([0-9]{1,4}-20[0-9]{2}-Z-[A-Z-]+)\M'),
                regexp_replace(substring(title FROM '(?i)\m((?\:LD|SD|P|CUH|ZHB)[[:space:].-]*[0-9]{2,4}[-.][0-9]{1,4}(?\:[-.][0-9]{1,4})?)\M'),
                    '^([A-Za-z]+)[[:space:].-]*', '\1'),
                substring(title FROM '(?i)\m((?\:Ordinance|Resolution)[[:space:]]+(?\:No[.]?[[:space:]]*)?20[0-9]{2}-[0-9]+)\M')
            ), '[[:space:].]+', '-', 'g'))
        $function$;

        CREATE OR REPLACE VIEW public.current_intelligence_events AS
        WITH municipal AS MATERIALIZED (
            SELECT event_key, related_pidns, related_entities, explanation_inference_id
            FROM public.current_municipal_intelligence
            WHERE EXISTS (SELECT 1 FROM public.intelligence_events WHERE source_kind = 'municipal_evidence')
        ), matters AS MATERIALIZED (
            SELECT event_key, related_pidns, related_entities, explanation_inference_id, record_keys
            FROM public.current_municipal_matter_accounts
            WHERE EXISTS (SELECT 1 FROM public.intelligence_events WHERE source_kind = 'municipal_matter')
        )
        SELECT event.*,
            (event.source_kind NOT IN ('municipal_evidence', 'municipal_matter') OR (
                event.source_evidence->0->'details'->>'discovery_eligible' = 'true'
                AND event.source_evidence->0->'details'->>'explanation_inference_id' IS NOT NULL
                AND (event.source_kind <> 'municipal_evidence' OR NOT EXISTS (
                    SELECT 1 FROM matters covered WHERE covered.record_keys ? event.event_key
                ))
            )) AS activity_eligible
        FROM public.intelligence_events event
        LEFT JOIN municipal ON event.source_kind = 'municipal_evidence' AND municipal.event_key = event.event_key
        LEFT JOIN matters ON event.source_kind = 'municipal_matter' AND matters.event_key = event.event_key
        WHERE (event.source_kind <> 'municipal_evidence' OR (
            municipal.event_key IS NOT NULL
            AND municipal.related_pidns = event.related_pidns
            AND municipal.related_entities = event.related_entities
            AND municipal.explanation_inference_id::text IS NOT DISTINCT FROM
                event.source_evidence->0->'details'->>'explanation_inference_id'
        ))
        AND (event.source_kind <> 'municipal_matter' OR (
            matters.event_key IS NOT NULL
            AND matters.related_pidns = event.related_pidns
            AND matters.related_entities = event.related_entities
            AND matters.explanation_inference_id::text =
                event.source_evidence->0->'details'->>'explanation_inference_id'
        ))
        AND (event.source_kind <> 'proceeding_extraction' OR EXISTS (
            SELECT 1 FROM staging.proceeding_extractions extraction
            JOIN staging.public_proceedings proceeding ON proceeding.id = extraction.proceeding_id
            JOIN meta.municipality_source_rights policy ON policy.body_name = proceeding.body_name
            WHERE extraction.id::text = event.source_record_id
              AND LEFT(extraction.extraction_type, 1) <> '_'
              AND proceeding.valid_to IS NULL
              AND proceeding.metadata_quality->>'status' = 'ready'
              AND policy.rights_status <> 'paused' AND policy.derived_product_allowed
              AND policy.review_due_on >= CURRENT_DATE
              AND EXISTS (
                  SELECT 1 FROM meta.source_rights global_policy
                  WHERE global_policy.source_key = 'public_proceedings'
                    AND global_policy.rights_status <> 'paused'
                    AND global_policy.derived_product_allowed
                    AND global_policy.review_due_on >= CURRENT_DATE
              )
        ));

        CREATE OR REPLACE VIEW public.current_activity_events AS
        SELECT event.* FROM public.current_intelligence_events event
        WHERE activity_eligible;
    """)


def downgrade() -> None:
    raise RuntimeError(
        "Use a forward migration to preserve source freshness and followed matter identities."
    )
