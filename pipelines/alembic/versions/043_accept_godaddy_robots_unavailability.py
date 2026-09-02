"""record exact GoDaddy listing robots unavailability acceptance

Revision ID: 043
Revises: 042
Create Date: 2026-08-31
"""

from alembic import op


revision = "043"
down_revision = "042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE meta.municipality_source_rights
        SET
            evidence = evidence || jsonb_build_object(
                'robots_unavailable_risk_accepted', TRUE,
                'robots_unavailable_decision_on', '2026-08-31',
                'robots_unavailable_scope',
                    'exact official listing origin only; document origin remains live robots-gated',
                'robots_unavailable_observation',
                    'direct client returned TLS EOF or timeout and Chromium robots navigation timed out; official listing remained reachable'
            ),
            notes = notes || (
                ' The exact official listing origin may use the browser transport '
                'when robots.txt is unavailable; the img1.wsimg.com document '
                'origin remains subject to its live robots policy.'
            )
        WHERE source_key IN (
            'franklintown_borough_council',
            'newberry_twp_board_of_supervisors',
            'washington_twp_board_of_supervisors'
        );
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE meta.municipality_source_rights
        SET
            evidence = evidence
                - 'robots_unavailable_risk_accepted'
                - 'robots_unavailable_decision_on'
                - 'robots_unavailable_scope'
                - 'robots_unavailable_observation',
            notes = (
                'GoDaddy terms reviewed; automated collection enabled by explicit '
                'product-owner risk acceptance. Restrict collection to the official '
                'listing and img1.wsimg.com PDF origin. Raw archives remain private; '
                'person-level display and raw export remain disabled.'
            )
        WHERE source_key IN (
            'franklintown_borough_council',
            'newberry_twp_board_of_supervisors',
            'washington_twp_board_of_supervisors'
        );
        """
    )
