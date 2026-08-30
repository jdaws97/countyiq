"""bound municipal origins and pause restricted vendor delivery paths

Revision ID: 033
Revises: 032
Create Date: 2026-08-27
"""

from alembic import op


revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


_PAUSED_SOURCE_KEYS = (
    "dover_twp_board_of_supervisors",
    "dover_twp_zoning_hearing_board",
    "west_york_borough_council",
    "west_manheim_twp_board_of_supervisors",
    "west_manheim_twp_planning_commission",
    "west_manheim_twp_zoning_hearing_board",
)


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE meta.municipality_source_rights
            ADD COLUMN allowed_origins TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[];

        UPDATE meta.municipality_source_rights
        SET allowed_origins = CASE
            WHEN listing_url IS NULL THEN ARRAY[]::TEXT[]
            ELSE ARRAY[
                lower(regexp_replace(listing_url, '^(https?://[^/]+).*$', '\\1'))
            ]::TEXT[]
        END;

        UPDATE meta.municipality_source_rights
        SET
            rights_status = 'paused',
            acquisition_allowed = FALSE,
            raw_retention_allowed = FALSE,
            derived_product_allowed = FALSE,
            person_level_display_allowed = FALSE,
            raw_export_allowed = FALSE,
            allowed_methods = ARRAY[]::TEXT[],
            terms_review_status = CASE
                WHEN source_key IN (
                    'dover_twp_board_of_supervisors',
                    'dover_twp_zoning_hearing_board',
                    'west_york_borough_council'
                ) THEN 'restricted'
                ELSE terms_review_status
            END,
            evidence = evidence || jsonb_build_object(
                'pause_reviewed_on', '2026-08-27',
                'pause_basis', CASE
                    WHEN source_key IN (
                        'dover_twp_board_of_supervisors',
                        'dover_twp_zoning_hearing_board'
                    ) THEN 'Repd document widget terms restrict use to personal, non-commercial use'
                    WHEN source_key = 'west_york_borough_council'
                    THEN 'Google Drive delivery origin not separately approved for commercial collection'
                    ELSE 'official robots.txt explicitly disallows the reviewed path'
                END
            ),
            notes = CASE
                WHEN source_key IN (
                    'dover_twp_board_of_supervisors',
                    'dover_twp_zoning_hearing_board'
                ) THEN 'Paused: the current official page delegates document delivery to Repd; its published Terms of Use restrict website contents to personal, non-commercial use. Resume only with written permission or township-hosted originals.'
                WHEN source_key = 'west_york_borough_council'
                THEN 'Paused: public documents are delivered through an unreviewed Google Drive origin. Resume only after written permission or a township-hosted direct source is approved.'
                ELSE 'Paused: the live 2026-08-27 audit found an explicit robots.txt disallow for this reviewed path. Resume only after the policy changes or written authorization is recorded.'
            END,
            updated_at = NOW()
        WHERE source_key = ANY(
            ARRAY[
                'dover_twp_board_of_supervisors',
                'dover_twp_zoning_hearing_board',
                'west_york_borough_council',
                'west_manheim_twp_board_of_supervisors',
                'west_manheim_twp_planning_commission',
                'west_manheim_twp_zoning_hearing_board'
            ]::TEXT[]
        );
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE meta.municipality_source_rights
        SET
            rights_status = 'conditional',
            acquisition_allowed = TRUE,
            raw_retention_allowed = TRUE,
            derived_product_allowed = TRUE,
            allowed_methods = ARRAY['official_document_direct']::TEXT[],
            terms_review_status = 'not_found',
            evidence = evidence - 'pause_reviewed_on' - 'pause_basis',
            updated_at = NOW()
        WHERE source_key = ANY(
            ARRAY[
                'dover_twp_board_of_supervisors',
                'dover_twp_zoning_hearing_board',
                'west_york_borough_council',
                'west_manheim_twp_board_of_supervisors',
                'west_manheim_twp_planning_commission',
                'west_manheim_twp_zoning_hearing_board'
            ]::TEXT[]
        );

        ALTER TABLE meta.municipality_source_rights
            DROP COLUMN allowed_origins;
        """
    )
