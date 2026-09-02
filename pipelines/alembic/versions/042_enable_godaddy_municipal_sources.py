"""enable explicitly accepted GoDaddy municipal document sources

Revision ID: 042
Revises: 041
Create Date: 2026-08-31
"""

from alembic import op


revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE meta.municipality_source_rights
            DROP CONSTRAINT municipality_source_rights_terms_review_status_check;
        ALTER TABLE meta.municipality_source_rights
            ADD CONSTRAINT municipality_source_rights_terms_review_status_check
            CHECK (terms_review_status IN (
                'reviewed', 'reviewed_risk_accepted', 'not_found',
                'restricted', 'no_web_presence'
            ));

        UPDATE meta.municipality_source_rights
        SET
            rights_status = 'conditional',
            acquisition_allowed = TRUE,
            raw_retention_allowed = TRUE,
            derived_product_allowed = TRUE,
            person_level_display_allowed = FALSE,
            raw_export_allowed = FALSE,
            allowed_methods = ARRAY['official_document_direct']::TEXT[],
            terms_review_status = 'reviewed_risk_accepted',
            terms_url = 'https://www.godaddy.com/legal/agreements/website-services-agreement',
            reviewed_on = DATE '2026-08-31',
            review_due_on = DATE '2026-11-30',
            allowed_origins = CASE
                WHEN 'https://img1.wsimg.com' = ANY(allowed_origins)
                    THEN allowed_origins
                ELSE array_append(allowed_origins, 'https://img1.wsimg.com')
            END,
            evidence = (
                evidence - 'pause_reviewed_on' - 'pause_basis'
            ) || jsonb_build_object(
                'terms_review', 'reviewed_risk_accepted',
                'terms_url', 'https://www.godaddy.com/legal/agreements/website-services-agreement',
                'product_owner_decision',
                    'accept automated collection risk for official municipal PDFs delivered by GoDaddy',
                'product_owner_decision_on', '2026-08-31',
                'delivery_boundary',
                    'official listing and direct PDF retrieval; private raw archive; no raw export',
                'live_verified_on', '2026-08-31',
                'live_document_origin', 'https://img1.wsimg.com',
                'live_discovered_document_links', CASE source_key
                    WHEN 'franklintown_borough_council' THEN 62
                    WHEN 'newberry_twp_board_of_supervisors' THEN 76
                    WHEN 'washington_twp_board_of_supervisors' THEN 30
                END
            ),
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


def downgrade() -> None:
    op.execute(
        """
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
            terms_url = NULL,
            reviewed_on = DATE '2026-08-27',
            review_due_on = DATE '2026-11-27',
            allowed_origins = array_remove(
                allowed_origins, 'https://img1.wsimg.com'
            ),
            evidence = (
                evidence
                - 'product_owner_decision'
                - 'product_owner_decision_on'
                - 'delivery_boundary'
                - 'live_verified_on'
                - 'live_document_origin'
                - 'live_discovered_document_links'
            ) || jsonb_build_object(
                'terms_review', 'not_found',
                'terms_url', 'https://www.godaddy.com/en/legal/agreements/website-services-agreement',
                'pause_reviewed_on', '2026-08-27',
                'pause_basis',
                    'GoDaddy Website Services terms prohibit automated downloading with robots or crawlers'
            ),
            notes = (
                'Paused: useful documents are delivered only from the GoDaddy '
                'img1.wsimg.com CDN, while the current Website Services terms '
                'prohibit automated content downloads by robots/crawlers. Resume '
                'only with written permission or municipality-hosted originals.'
            )
        WHERE source_key IN (
            'franklintown_borough_council',
            'newberry_twp_board_of_supervisors',
            'washington_twp_board_of_supervisors'
        );

        ALTER TABLE meta.municipality_source_rights
            DROP CONSTRAINT municipality_source_rights_terms_review_status_check;
        ALTER TABLE meta.municipality_source_rights
            ADD CONSTRAINT municipality_source_rights_terms_review_status_check
            CHECK (terms_review_status IN (
                'reviewed', 'not_found', 'restricted', 'no_web_presence'
            ));
        """
    )
