"""make entity_graph.canonical_name unique for ON CONFLICT upsert

Revision ID: 016
Revises: 015
Create Date: 2026-04-08

The entity_verification asset upserts to public.entity_graph using
ON CONFLICT (canonical_name), which requires a unique constraint.
Migration 012 created a non-unique btree index. This replaces it.
"""

from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index(
        "idx_entity_graph_canonical_name", table_name="entity_graph", schema="public"
    )
    op.create_unique_constraint(
        "uq_entity_graph_canonical_name",
        "entity_graph",
        ["canonical_name"],
        schema="public",
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_entity_graph_canonical_name", "entity_graph", schema="public"
    )
    op.create_index(
        "idx_entity_graph_canonical_name",
        "entity_graph",
        ["canonical_name"],
        schema="public",
    )
