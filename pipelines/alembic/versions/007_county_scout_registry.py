"""County Scout source registry and observation history

Revision ID: 007
Revises: 006
Create Date: 2026-03-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_candidates",
        sa.Column("source_key", sa.Text, primary_key=True),
        sa.Column("county_key", sa.Text, nullable=False),
        sa.Column("seed_slug", sa.Text, nullable=False),
        sa.Column("source_name", sa.Text, nullable=False),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("normalized_url", sa.Text, nullable=False),
        sa.Column("parent_url", sa.Text),
        sa.Column(
            "discovery_method",
            sa.Text,
            nullable=False,
        ),
        sa.Column("source_type", sa.Text, nullable=False),
        sa.Column("platform", sa.Text, nullable=False),
        sa.Column(
            "extraction_method",
            sa.Text,
            nullable=False,
        ),
        sa.Column("categories", JSONB, nullable=False, server_default="[]"),
        sa.Column("audiences", JSONB, nullable=False, server_default="[]"),
        sa.Column("value_score", sa.Integer, nullable=False),
        sa.Column("risk_level", sa.Text, nullable=False),
        sa.Column("risk_memo", sa.Text, nullable=False),
        sa.Column("alert_examples", JSONB, nullable=False, server_default="[]"),
        sa.Column("product_examples", JSONB, nullable=False, server_default="[]"),
        sa.Column(
            "monitor_interval_hours", sa.Integer, nullable=False, server_default="24"
        ),
        sa.Column("classification_confidence", sa.Float, nullable=False),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "monitored", sa.Boolean, nullable=False, server_default=sa.text("FALSE")
        ),
        sa.Column(
            "first_discovered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
        sa.CheckConstraint(
            "value_score >= 0 AND value_score <= 100",
            name="ck_source_candidates_value_score",
        ),
        sa.CheckConstraint(
            "risk_level IN ('low', 'medium', 'high')",
            name="ck_source_candidates_risk_level",
        ),
        sa.CheckConstraint(
            "discovery_method IN ('seed', 'link_crawl', 'manual', 'monitor')",
            name="ck_source_candidates_discovery_method",
        ),
        sa.CheckConstraint(
            "extraction_method IN ('static_http_fetch', 'crawler_static_parser', 'browser_automation_fallback')",
            name="ck_source_candidates_extraction_method",
        ),
        schema="meta",
    )
    op.create_index(
        "idx_source_candidates_county_score",
        "source_candidates",
        ["county_key", "value_score"],
        schema="meta",
    )
    op.create_index(
        "idx_source_candidates_county_type",
        "source_candidates",
        ["county_key", "source_type"],
        schema="meta",
    )

    op.create_table(
        "source_observations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("source_key", sa.Text, nullable=False),
        sa.Column("county_key", sa.Text, nullable=False),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("probe_status", sa.Text, nullable=False),
        sa.Column("status_code", sa.Integer),
        sa.Column("final_url", sa.Text, nullable=False),
        sa.Column("content_type", sa.Text),
        sa.Column("extraction_method", sa.Text, nullable=False),
        sa.Column("response_ms", sa.Integer),
        sa.Column("content_hash", sa.Text),
        sa.Column("etag", sa.Text),
        sa.Column("last_modified", sa.Text),
        sa.Column("notes", sa.Text),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "checked_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
        sa.CheckConstraint(
            "probe_status IN ('ok', 'redirect', 'blocked', 'error')",
            name="ck_source_observations_probe_status",
        ),
        sa.CheckConstraint(
            "extraction_method IN ('static_http_fetch', 'crawler_static_parser', 'browser_automation_fallback')",
            name="ck_source_observations_extraction_method",
        ),
        schema="meta",
    )
    op.create_index(
        "idx_source_observations_source_checked",
        "source_observations",
        ["source_key", "checked_at"],
        schema="meta",
    )
    op.create_index(
        "idx_source_observations_county_checked",
        "source_observations",
        ["county_key", "checked_at"],
        schema="meta",
    )

    op.create_table(
        "source_registry",
        sa.Column("source_key", sa.Text, primary_key=True),
        sa.Column("county_key", sa.Text, nullable=False),
        sa.Column("source_name", sa.Text, nullable=False),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("source_type", sa.Text, nullable=False),
        sa.Column("platform", sa.Text, nullable=False),
        sa.Column("extraction_method", sa.Text, nullable=False),
        sa.Column("categories", JSONB, nullable=False, server_default="[]"),
        sa.Column("audiences", JSONB, nullable=False, server_default="[]"),
        sa.Column("value_score", sa.Integer, nullable=False),
        sa.Column("risk_level", sa.Text, nullable=False),
        sa.Column("risk_memo", sa.Text, nullable=False),
        sa.Column("alert_examples", JSONB, nullable=False, server_default="[]"),
        sa.Column("product_examples", JSONB, nullable=False, server_default="[]"),
        sa.Column("notes", sa.Text),
        sa.Column("health_status", sa.Text, nullable=False, server_default="healthy"),
        sa.Column("last_status_code", sa.Integer),
        sa.Column("last_probe_status", sa.Text),
        sa.Column("last_content_hash", sa.Text),
        sa.Column(
            "promoted_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        sa.Column("last_changed_at", sa.DateTime(timezone=True)),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("TRUE")),
        sa.Column(
            "monitor_interval_hours", sa.Integer, nullable=False, server_default="24"
        ),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.CheckConstraint(
            "value_score >= 0 AND value_score <= 100",
            name="ck_source_registry_value_score",
        ),
        sa.CheckConstraint(
            "risk_level IN ('low', 'medium', 'high')",
            name="ck_source_registry_risk_level",
        ),
        sa.CheckConstraint(
            "health_status IN ('healthy', 'changed', 'degraded', 'blocked', 'error')",
            name="ck_source_registry_health_status",
        ),
        sa.CheckConstraint(
            "extraction_method IN ('static_http_fetch', 'crawler_static_parser', 'browser_automation_fallback')",
            name="ck_source_registry_extraction_method",
        ),
        schema="meta",
    )
    op.create_index(
        "idx_source_registry_county_score",
        "source_registry",
        ["county_key", "value_score"],
        schema="meta",
    )
    op.create_index(
        "idx_source_registry_health",
        "source_registry",
        ["county_key", "health_status"],
        schema="meta",
    )


def downgrade() -> None:
    op.drop_table("source_registry", schema="meta")
    op.drop_table("source_observations", schema="meta")
    op.drop_table("source_candidates", schema="meta")
