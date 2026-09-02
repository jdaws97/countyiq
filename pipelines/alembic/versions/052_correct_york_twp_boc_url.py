"""Correct York Township Board of Commissioners listing URL.

Revision ID: 052
Revises: 051
Create Date: 2026-09-02

The township's current Board of Commissioners route is ``/boards-4/boc/``.
The longer route recorded in revision 051 redirects to an unrelated event.
"""

from alembic import op

revision = "052"
down_revision = "051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE meta.municipality_source_rights
        SET listing_url = 'https://yorktownshippa.gov/boards-4/boc/',
            policy_version = policy_version + 1,
            evidence = COALESCE(evidence, '{}'::jsonb) || jsonb_build_object(
                'listing_url_reviewed_on', '2026-09-02',
                'listing_url_review_reason',
                'official Board of Commissioners page with agenda and minute PDFs'
            ),
            updated_at = NOW()
        WHERE source_key = 'york_twp_board_of_commissioners';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE meta.municipality_source_rights
        SET listing_url = 'https://yorktownshippa.gov/boards-4/board-of-commissioners/',
            policy_version = GREATEST(policy_version - 1, 1),
            evidence = COALESCE(evidence, '{}'::jsonb) || jsonb_build_object(
                'listing_url_reviewed_on', '2026-09-02',
                'listing_url_review_reason',
                'official page moved within the previously reviewed origin'
            ),
            updated_at = NOW()
        WHERE source_key = 'york_twp_board_of_commissioners';
        """
    )
