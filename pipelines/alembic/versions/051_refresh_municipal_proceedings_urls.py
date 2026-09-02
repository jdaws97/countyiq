"""Refresh reviewed municipal proceedings listing URLs.

Revision ID: 051
Revises: 050
Create Date: 2026-09-02

Four official York County municipality pages moved within their existing,
already-reviewed origins. Keep the fail-closed source policy synchronized with
the runtime county configuration so the scraper can use the replacement pages.
"""

from alembic import op

revision = "051"
down_revision = "050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE meta.municipality_source_rights
        SET listing_url = CASE source_key
                WHEN 'york_twp_board_of_commissioners'
                    THEN 'https://yorktownshippa.gov/boards-4/board-of-commissioners/'
                WHEN 'hellam_twp_board_of_supervisors'
                    THEN 'https://www.hellamtownship.gov/board-of-supervisors-meetings/'
                WHEN 'hellam_twp_planning_commission'
                    THEN 'https://www.hellamtownship.gov/planning-commission-meetings/'
                WHEN 'hellam_twp_zoning_hearing_board'
                    THEN 'https://www.hellamtownship.gov/zoning-hearing-board-meetings/'
            END,
            policy_version = policy_version + 1,
            evidence = COALESCE(evidence, '{}'::jsonb) || jsonb_build_object(
                'listing_url_reviewed_on', '2026-09-02',
                'listing_url_review_reason',
                'official page moved within the previously reviewed origin'
            ),
            updated_at = NOW()
        WHERE source_key IN (
            'york_twp_board_of_commissioners',
            'hellam_twp_board_of_supervisors',
            'hellam_twp_planning_commission',
            'hellam_twp_zoning_hearing_board'
        );
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE meta.municipality_source_rights
        SET listing_url = CASE source_key
                WHEN 'york_twp_board_of_commissioners'
                    THEN 'https://yorktownshippa.gov/boards/boc/'
                WHEN 'hellam_twp_board_of_supervisors'
                    THEN 'https://www.hellamtownship.gov/departments/public-meetings/'
                WHEN 'hellam_twp_planning_commission'
                    THEN 'https://www.hellamtownship.gov/planning-commission/'
                WHEN 'hellam_twp_zoning_hearing_board'
                    THEN 'https://www.hellamtownship.gov/government/zoning-hearing-board/'
            END,
            policy_version = GREATEST(policy_version - 1, 1),
            evidence = COALESCE(evidence, '{}'::jsonb)
                - 'listing_url_reviewed_on'
                - 'listing_url_review_reason',
            updated_at = NOW()
        WHERE source_key IN (
            'york_twp_board_of_commissioners',
            'hellam_twp_board_of_supervisors',
            'hellam_twp_planning_commission',
            'hellam_twp_zoning_hearing_board'
        );
        """
    )
