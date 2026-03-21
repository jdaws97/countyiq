"""staging.address_points for GIS Portal address points

Revision ID: 005
Revises: 004
Create Date: 2026-03-21
"""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- staging.address_points (Source 1: GIS Portal — AddressPts layer, ~189,876 records) ---
    # Site_NGUID is the NENA Site Global Unique ID — guaranteed unique per address point
    op.create_table(
        "address_points",
        sa.Column("site_nguid", sa.String(254), nullable=False),
        sa.Column("add_number", sa.SmallInteger),
        sa.Column("addnum_suf", sa.String(15)),
        sa.Column("st_pre_dir", sa.String(9)),
        sa.Column("st_pre_typ", sa.String(50)),
        sa.Column("street_name", sa.String(60)),
        sa.Column("st_pos_typ", sa.String(50)),
        sa.Column("st_pos_dir", sa.String(30)),
        sa.Column("inc_muni", sa.String(100)),
        sa.Column("post_comm", sa.String(40)),
        sa.Column("post_code", sa.String(7)),
        sa.Column("post_code4", sa.String(4)),
        sa.Column("building", sa.String(75)),
        sa.Column("floor", sa.String(75)),
        sa.Column("unit", sa.String(75)),
        sa.Column("place_type", sa.String(50)),
        sa.Column("long", sa.Float),
        sa.Column("lat", sa.Float),
        sa.Column("valid_from", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("site_nguid", "valid_from"),
        schema="staging",
    )
    op.execute("SELECT AddGeometryColumn('staging', 'address_points', 'geom', 4326, 'POINT', 2)")
    op.create_index("idx_addr_pts_geom", "address_points", ["geom"], schema="staging", postgresql_using="gist")
    op.create_index("idx_addr_pts_street", "address_points", ["street_name"], schema="staging")
    op.create_index("idx_addr_pts_muni", "address_points", ["inc_muni"], schema="staging")
    op.create_index("idx_addr_pts_postcode", "address_points", ["post_code"], schema="staging")
    op.create_index("idx_addr_pts_current", "address_points", ["site_nguid"], schema="staging",
                     postgresql_where=sa.text("valid_to IS NULL"))


def downgrade() -> None:
    op.drop_table("address_points", schema="staging")
