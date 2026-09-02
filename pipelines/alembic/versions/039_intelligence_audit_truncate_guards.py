"""block truncate on append-only intelligence audit tables

Revision ID: 039
Revises: 038
Create Date: 2026-08-31
"""

from alembic import op

revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TRIGGER trg_intelligence_history_no_truncate
            BEFORE TRUNCATE ON meta.intelligence_inference_history
            FOR EACH STATEMENT EXECUTE FUNCTION meta.reject_intelligence_audit_mutation();
        CREATE TRIGGER trg_intelligence_contradictions_no_truncate
            BEFORE TRUNCATE ON meta.intelligence_contradictions
            FOR EACH STATEMENT EXECUTE FUNCTION meta.reject_intelligence_audit_mutation();
        CREATE TRIGGER trg_intelligence_resolutions_no_truncate
            BEFORE TRUNCATE ON meta.intelligence_contradiction_resolutions
            FOR EACH STATEMENT EXECUTE FUNCTION meta.reject_intelligence_audit_mutation();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_intelligence_resolutions_no_truncate
            ON meta.intelligence_contradiction_resolutions;
        DROP TRIGGER IF EXISTS trg_intelligence_contradictions_no_truncate
            ON meta.intelligence_contradictions;
        DROP TRIGGER IF EXISTS trg_intelligence_history_no_truncate
            ON meta.intelligence_inference_history;
        """
    )
