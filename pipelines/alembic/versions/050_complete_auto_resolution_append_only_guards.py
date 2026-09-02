"""Complete auto-resolution audit guards and repair the 049 downgrade path.

Revision ID: 050
Revises: 049
Create Date: 2026-09-02

Revision 047 protected its two audit tables from row updates and deletes but
did not close PostgreSQL's statement-level TRUNCATE path. Revision 049 also
normalizes its new outcome during downgrade, which conflicts with that row
trigger. Because both revisions may already be applied, this forward repair
adds the missing guards and performs the normalization in 050's downgrade;
049's subsequent downgrade UPDATE then affects zero rows.
"""

from alembic import op

revision = "050"
down_revision = "049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TRIGGER trg_intelligence_auto_resolutions_no_truncate
            BEFORE TRUNCATE ON meta.intelligence_auto_resolutions
            FOR EACH STATEMENT
            EXECUTE FUNCTION meta.reject_intelligence_audit_mutation();
        CREATE TRIGGER trg_intelligence_audit_reviews_no_truncate
            BEFORE TRUNCATE ON meta.intelligence_audit_reviews
            FOR EACH STATEMENT
            EXECUTE FUNCTION meta.reject_intelligence_audit_mutation();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_intelligence_audit_reviews_no_truncate
            ON meta.intelligence_audit_reviews;
        DROP TRIGGER IF EXISTS trg_intelligence_auto_resolutions_no_truncate
            ON meta.intelligence_auto_resolutions;

        -- Pre-normalize the only 049-only value while preserving the table's
        -- row-level append-only contract before this revision finishes. When
        -- Alembic continues into revision 049, its UPDATE matches no rows and
        -- therefore does not fire the row trigger.
        DROP TRIGGER IF EXISTS trg_intelligence_auto_resolutions_append_only
            ON meta.intelligence_auto_resolutions;
        UPDATE meta.intelligence_auto_resolutions
            SET outcome = 'queued_judge_unavailable'
            WHERE outcome = 'queued_resolution_refused';
        CREATE TRIGGER trg_intelligence_auto_resolutions_append_only
            BEFORE UPDATE OR DELETE ON meta.intelligence_auto_resolutions
            FOR EACH ROW
            EXECUTE FUNCTION meta.reject_intelligence_audit_mutation();
        """
    )
