"""reconcile the County Scout policy on already-migrated databases

Revision ID: 035
Revises: 034
Create Date: 2026-08-27
"""

from alembic import op


revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Make the paused Scout policy explicit on both old and fresh databases."""

    op.execute(
        """
        INSERT INTO meta.source_rights (
            source_key, publisher, source_url, rights_status,
            acquisition_allowed, raw_retention_allowed,
            derived_product_allowed, person_level_display_allowed,
            raw_export_allowed, allowed_methods, terms_url,
            reviewed_on, review_due_on, evidence, notes
        ) VALUES (
            'county_scout', 'Multiple publishers',
            'https://yorkcountypa.gov/', 'paused',
            FALSE, FALSE, FALSE, FALSE, FALSE, ARRAY[]::TEXT[], NULL,
            DATE '2026-08-27', DATE '2026-11-27',
            '{"basis":"dynamic crawler can follow and auto-promote unreviewed sources"}'::JSONB,
            'Paused until every seed and discovered-link class has robots, terms, retention, and promotion gates.'
        )
        ON CONFLICT (source_key) DO UPDATE SET
            publisher = EXCLUDED.publisher,
            source_url = EXCLUDED.source_url,
            rights_status = EXCLUDED.rights_status,
            acquisition_allowed = EXCLUDED.acquisition_allowed,
            raw_retention_allowed = EXCLUDED.raw_retention_allowed,
            derived_product_allowed = EXCLUDED.derived_product_allowed,
            person_level_display_allowed = EXCLUDED.person_level_display_allowed,
            raw_export_allowed = EXCLUDED.raw_export_allowed,
            allowed_methods = EXCLUDED.allowed_methods,
            terms_url = EXCLUDED.terms_url,
            reviewed_on = EXCLUDED.reviewed_on,
            review_due_on = EXCLUDED.review_due_on,
            evidence = EXCLUDED.evidence,
            notes = EXCLUDED.notes,
            updated_at = NOW();
        """
    )


def downgrade() -> None:
    # Revision 032 defines this policy for a fresh database. Removing it while
    # downgrading only the reconciliation revision would make identical schema
    # histories diverge again, so the historical policy intentionally remains.
    pass
