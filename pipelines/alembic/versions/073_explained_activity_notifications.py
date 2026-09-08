"""Use the same explained municipal activity boundary for discovery and alerts."""

from alembic import op

revision = "073"
down_revision = "072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE VIEW public.current_activity_events AS
        WITH covered AS MATERIALIZED (
            SELECT jsonb_array_elements_text(record_keys) AS event_key
            FROM public.current_municipal_matter_accounts
        )
        SELECT event.* FROM public.current_intelligence_events event
        WHERE (source_kind NOT IN ('municipal_evidence', 'municipal_matter') OR (
            source_evidence->0->'details'->>'discovery_eligible' = 'true'
            AND source_evidence->0->'details'->>'explanation_inference_id' IS NOT NULL
        ))
        AND (source_kind <> 'municipal_evidence' OR NOT EXISTS (
            SELECT 1 FROM covered WHERE covered.event_key = event.event_key
        ));

        DO $block$
        DECLARE definition text;
        BEGIN
            SELECT pg_get_functiondef('public.refresh_watch_notifications()'::regprocedure)
                INTO definition;
            EXECUTE replace(definition, 'public.current_intelligence_events',
                            'public.current_activity_events');
        END
        $block$;
    """)


def downgrade() -> None:
    op.execute("""
        DO $block$
        DECLARE definition text;
        BEGIN
            SELECT pg_get_functiondef('public.refresh_watch_notifications()'::regprocedure)
                INTO definition;
            EXECUTE replace(definition, 'public.current_activity_events',
                            'public.current_intelligence_events');
        END
        $block$;
        DROP VIEW public.current_activity_events;
    """)
