"""Consolidate owner identity onto public.owners.

owner_resolution now upserts by canonical_name instead of delete-all +
sequence restart, so owner_id is stable across runs and the API can serve
a single ID space (the entity-graph offset encoding is removed).

Adds the columns that used to live only on public.entity_graph so the
resolved owner row carries its own aliases, relationships, and Pass 1
verification metadata. entity_graph remains as Pass 1's output table;
owner_resolution folds it in.

Revision ID: 025
Revises: 024
Create Date: 2026-08-02
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB


revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("owners", sa.Column("aliases", ARRAY(sa.Text())), schema="public")
    op.add_column("owners", sa.Column("relationships", JSONB), schema="public")
    op.add_column("owners", sa.Column("verification_status", sa.Text()), schema="public")
    op.add_column("owners", sa.Column("verification_reasoning", sa.Text()), schema="public")
    op.add_column("owners", sa.Column("verified_at", sa.DateTime(timezone=True)), schema="public")

    # Upsert key for stable owner IDs. The table is rebuilt from a
    # dict keyed by canonical_name, so duplicates cannot exist; wipe any
    # legacy duplicates before constraining (dev environments only).
    op.execute(
        """
        DELETE FROM public.owner_source_links osl
        USING public.owners o
        WHERE osl.owner_id = o.owner_id
          AND o.owner_id NOT IN (
              SELECT MIN(owner_id) FROM public.owners GROUP BY canonical_name
          )
        """
    )
    op.execute(
        """
        DELETE FROM public.owners
        WHERE owner_id NOT IN (
            SELECT MIN(owner_id) FROM public.owners GROUP BY canonical_name
        )
        """
    )
    op.create_unique_constraint(
        "uq_owners_canonical_name", "owners", ["canonical_name"], schema="public"
    )


def downgrade() -> None:
    op.drop_constraint("uq_owners_canonical_name", "owners", schema="public")
    op.drop_column("owners", "verified_at", schema="public")
    op.drop_column("owners", "verification_reasoning", schema="public")
    op.drop_column("owners", "verification_status", schema="public")
    op.drop_column("owners", "relationships", schema="public")
    op.drop_column("owners", "aliases", schema="public")
