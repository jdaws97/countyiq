"""Keep legacy explanations awaiting English presentation in research leads."""

from alembic import op

revision = "075"
down_revision = "074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE VIEW public.current_activity_events AS
        SELECT event.* FROM public.current_intelligence_events event
        WHERE activity_eligible
            AND (source_kind <> 'municipal_evidence' OR EXISTS (
                SELECT 1 FROM meta.intelligence_inference_history history
                WHERE history.inference_id =
                    (event.source_evidence->0->'details'->>'explanation_inference_id')::bigint
                    AND history.payload->'explanation'->>'presentation_language' = 'en'
            ));
    """)


def downgrade() -> None:
    op.execute("""
        CREATE OR REPLACE VIEW public.current_activity_events AS
        SELECT event.* FROM public.current_intelligence_events event
        WHERE activity_eligible;
    """)
