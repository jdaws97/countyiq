"""review municipal redirects and pause restricted CDN delivery

Revision ID: 034
Revises: 033
Create Date: 2026-08-27
"""

from alembic import op


revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE meta.municipality_source_rights
        SET allowed_origins = array_append(
                allowed_origins, 'https://heidelbergtwpmunicipal.com'
            ),
            evidence = evidence || '{"origin_alias_reviewed_on":"2026-08-27"}'::jsonb,
            updated_at = NOW()
        WHERE source_key IN (
            'heidelberg_twp_board_of_supervisors',
            'heidelberg_twp_planning_commission',
            'heidelberg_twp_zoning_hearing_board'
        );

        UPDATE meta.municipality_source_rights
        SET allowed_origins = array_append(
                allowed_origins, 'https://lowerwindsor.com'
            ),
            evidence = evidence || '{"origin_alias_reviewed_on":"2026-08-27"}'::jsonb,
            updated_at = NOW()
        WHERE source_key IN (
            'lower_windsor_twp_board_of_supervisors',
            'lower_windsor_twp_planning_commission',
            'lower_windsor_twp_zoning_hearing_board'
        );

        UPDATE meta.municipality_source_rights
        SET allowed_origins = array_append(
                allowed_origins, 'https://westmanchestertownship.com'
            ),
            evidence = evidence || '{"origin_alias_reviewed_on":"2026-08-27"}'::jsonb,
            updated_at = NOW()
        WHERE source_key IN (
            'west_manchester_twp_board_of_supervisors',
            'west_manchester_twp_planning_commission',
            'west_manchester_twp_zoning_hearing_board'
        );

        UPDATE meta.municipality_source_rights
        SET allowed_origins = array_append(allowed_origins, alias.origin),
            evidence = evidence || '{"document_origin_reviewed_on":"2026-08-27"}'::jsonb,
            updated_at = NOW()
        FROM (
            VALUES
                ('spring_grove_borough_council', 'https://springgrovepa.gov'),
                ('windsor_twp_board_of_supervisors', 'https://www.windsortownship.com'),
                ('windsor_twp_planning_commission', 'https://www.windsortownship.com'),
                ('york_city_council', 'https://yorkcity.org'),
                ('york_city_planning_commission', 'https://yorkcity.org'),
                ('york_city_zoning_hearing_board', 'https://yorkcity.org'),
                ('peach_bottom_twp_board_of_supervisors', 'https://peachbottomtownship.org'),
                ('peach_bottom_twp_zoning_hearing_board', 'https://peachbottomtownship.org'),
                ('spring_garden_twp_board_of_supervisors', 'https://springgardentwp.org'),
                ('spring_garden_twp_planning_commission', 'https://springgardentwp.org'),
                ('spring_garden_twp_zoning_hearing_board', 'https://springgardentwp.org')
        ) AS alias(source_key, origin)
        WHERE meta.municipality_source_rights.source_key = alias.source_key;

        UPDATE meta.municipality_source_rights
        SET
            rights_status = 'paused',
            acquisition_allowed = FALSE,
            raw_retention_allowed = FALSE,
            derived_product_allowed = FALSE,
            person_level_display_allowed = FALSE,
            raw_export_allowed = FALSE,
            allowed_methods = ARRAY[]::TEXT[],
            terms_review_status = 'restricted',
            evidence = evidence || jsonb_build_object(
                'pause_reviewed_on', '2026-08-27',
                'pause_basis', 'GoDaddy Website Services terms prohibit automated downloading with robots or crawlers',
                'terms_url', 'https://www.godaddy.com/en/legal/agreements/website-services-agreement'
            ),
            notes = 'Paused: useful documents are delivered only from the GoDaddy img1.wsimg.com CDN, while the current Website Services terms prohibit automated content downloads by robots/crawlers. Resume only with written permission or municipality-hosted originals.',
            updated_at = NOW()
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
            rights_status = 'conditional',
            acquisition_allowed = TRUE,
            raw_retention_allowed = TRUE,
            derived_product_allowed = TRUE,
            allowed_methods = ARRAY['official_document_direct']::TEXT[],
            terms_review_status = 'not_found',
            evidence = evidence - 'pause_reviewed_on' - 'pause_basis' - 'terms_url',
            updated_at = NOW()
        WHERE source_key IN (
            'franklintown_borough_council',
            'newberry_twp_board_of_supervisors',
            'washington_twp_board_of_supervisors'
        );

        UPDATE meta.municipality_source_rights
        SET allowed_origins = ARRAY[allowed_origins[1]],
            evidence = evidence - 'origin_alias_reviewed_on'
                                - 'document_origin_reviewed_on',
            updated_at = NOW()
        WHERE evidence ? 'origin_alias_reviewed_on'
           OR evidence ? 'document_origin_reviewed_on';
        """
    )
