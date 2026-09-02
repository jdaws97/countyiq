"""Record refused automatic resolutions as their own queue reason.

Revision ID: 049
Revises: 048
Create Date: 2026-09-02

When the resolver refuses an automatic resolution (the live source hash moved
or the prior inference was superseded), the policy used to file it under
``queued_judge_unavailable``. That label was wrong and hid the real reason from
the review queue. Revision 047 is already applied in local databases, so the
constraint is widened here instead of edited in place.
"""

from alembic import op

revision = "049"
down_revision = "048"
branch_labels = None
depends_on = None

_OUTCOMES_WITH_REFUSED = (
    "'auto_resolved', 'queued_consequential', 'queued_disagreement', "
    "'queued_judge_unavailable', 'queued_resolution_refused'"
)
_OUTCOMES_ORIGINAL = (
    "'auto_resolved', 'queued_consequential', 'queued_disagreement', "
    "'queued_judge_unavailable'"
)


def upgrade() -> None:
    op.execute(
        f"""
        ALTER TABLE meta.intelligence_auto_resolutions
            DROP CONSTRAINT IF EXISTS intelligence_auto_resolutions_outcome_check;
        ALTER TABLE meta.intelligence_auto_resolutions
            ADD CONSTRAINT intelligence_auto_resolutions_outcome_check
            CHECK (outcome IN ({_OUTCOMES_WITH_REFUSED}));
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        UPDATE meta.intelligence_auto_resolutions
            SET outcome = 'queued_judge_unavailable'
            WHERE outcome = 'queued_resolution_refused';
        ALTER TABLE meta.intelligence_auto_resolutions
            DROP CONSTRAINT IF EXISTS intelligence_auto_resolutions_outcome_check;
        ALTER TABLE meta.intelligence_auto_resolutions
            ADD CONSTRAINT intelligence_auto_resolutions_outcome_check
            CHECK (outcome IN ({_OUTCOMES_ORIGINAL}));
        """
    )
