"""Permit bounded YCCD review acquisition and private snapshot retention."""

from alembic import op

revision = "082"
down_revision = "081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO meta.source_rights (
            source_key, publisher, source_url, rights_status,
            acquisition_allowed, raw_retention_allowed,
            derived_product_allowed, raw_export_allowed, allowed_methods,
            terms_url, reviewed_on, review_due_on, evidence, notes
        ) VALUES (
            'yccd_plan_reviews', 'York County Conservation District',
            'https://www.yorkccd.org/erosion-and-sediment-control/pending-plan-review-list',
            'conditional', TRUE, TRUE, FALSE, FALSE,
            ARRAY['official_pdf'], NULL,
            DATE '2026-09-08', DATE '2026-12-08',
            '{"basis":"Official public weekly review list; product owner authorized a bounded source pilot on 2026-09-08.",
              "robots_review":"2026-09-08: general public paths allowed, wp-admin disallowed, crawl-delay 5 seconds.",
              "delivery_boundary":"Private original and normalized review snapshots only; no customer publication or source-equivalent export.",
              "terms_limit":"No affirmative bulk reuse license established. Manual low-volume pilot only."}'::jsonb,
            'One listing and its newest linked PDF per manual run. Recheck robots; fail on changed origin, layout, or expired policy. No scheduled collection, PIDN join, approval inference, or customer delivery.'
        );
    """)


def downgrade() -> None:
    # A code-only rollback retains schema and immutable acquisition receipts.
    op.execute("""
        DO $block$
        BEGIN
            IF EXISTS (SELECT 1 FROM meta.source_rights_audit
                       WHERE source_key = 'yccd_plan_reviews') THEN
                RAISE EXCEPTION 'YCCD pilot has retained acquisition receipts; use a reviewed code-only rollback';
            END IF;
            DELETE FROM meta.source_rights WHERE source_key = 'yccd_plan_reviews';
        END;
        $block$;
    """)
