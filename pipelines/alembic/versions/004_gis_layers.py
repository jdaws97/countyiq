"""staging tables for GIS layers: zoning, roads, structures

Revision ID: 004
Revises: 003
Create Date: 2026-03-21
"""
from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- staging.zoning (Source 1: GIS Portal — Zoning layer, ~1,694 records) ---
    op.create_table(
        "zoning",
        sa.Column("zrecid", sa.Integer, nullable=False),
        sa.Column("muni_name", sa.String(50)),
        sa.Column("district", sa.String(2)),
        sa.Column("zcode", sa.String(5)),
        sa.Column("zname", sa.String(50)),
        sa.Column("ztype", sa.String(1)),
        sa.Column("gen_zcode", sa.String(5)),
        sa.Column("gen_zname", sa.String(50)),
        sa.Column("changetype", sa.String(255)),
        sa.Column("prj_num", sa.String(7)),
        sa.Column("muni_ord", sa.String(12)),
        sa.Column("adpt_date", sa.DateTime(timezone=True)),
        sa.Column("prev_zcode", sa.String(8)),
        sa.Column("prev_zname", sa.String(50)),
        sa.Column("valid_from", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("zrecid", "valid_from"),
        schema="staging",
    )
    op.execute("SELECT AddGeometryColumn('staging', 'zoning', 'geom', 4326, 'MULTIPOLYGON', 2)")
    op.create_index("idx_zoning_layer_geom", "zoning", ["geom"], schema="staging", postgresql_using="gist")
    op.create_index("idx_zoning_muni", "zoning", ["muni_name"], schema="staging")
    op.create_index("idx_zoning_current", "zoning", ["zrecid"], schema="staging",
                     postgresql_where=sa.text("valid_to IS NULL"))

    # --- staging.roads (Source 1: GIS Portal — Roads layer, ~33,748 records) ---
    op.create_table(
        "roads",
        sa.Column("rcl_nguid", sa.String(254), nullable=False),
        sa.Column("street_name", sa.String(60)),
        sa.Column("st_pre_dir", sa.String(9)),
        sa.Column("st_pre_typ", sa.String(50)),
        sa.Column("st_pos_typ", sa.String(50)),
        sa.Column("st_pos_dir", sa.String(20)),
        sa.Column("road_class", sa.String(15)),
        sa.Column("speed_limit", sa.SmallInteger),
        sa.Column("one_way", sa.String(2)),
        sa.Column("rte_num", sa.String(5)),
        sa.Column("from_addr_l", sa.SmallInteger),
        sa.Column("to_addr_l", sa.SmallInteger),
        sa.Column("from_addr_r", sa.SmallInteger),
        sa.Column("to_addr_r", sa.SmallInteger),
        sa.Column("inc_muni_l", sa.String(100)),
        sa.Column("inc_muni_r", sa.String(100)),
        sa.Column("post_code_l", sa.String(7)),
        sa.Column("post_code_r", sa.String(7)),
        sa.Column("valid_from", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("rcl_nguid", "valid_from"),
        schema="staging",
    )
    op.execute("SELECT AddGeometryColumn('staging', 'roads', 'geom', 4326, 'MULTILINESTRING', 2)")
    op.create_index("idx_roads_cl_geom", "roads", ["geom"], schema="staging", postgresql_using="gist")
    op.create_index("idx_roads_street", "roads", ["street_name"], schema="staging")
    op.create_index("idx_roads_current", "roads", ["rcl_nguid"], schema="staging",
                     postgresql_where=sa.text("valid_to IS NULL"))

    # --- staging.structures (Source 1: GIS Portal — BLDG_Footprint layer, ~213,041 records) ---
    # INDEX_ is NOT unique (multiple buildings per parcel). Use OBJECTID as PK.
    op.create_table(
        "structures",
        sa.Column("objectid", sa.Integer, nullable=False),
        sa.Column("index_id", sa.String(20)),
        sa.Column("building_type", sa.String(512)),
        sa.Column("valid_from", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("objectid", "valid_from"),
        schema="staging",
    )
    op.execute("SELECT AddGeometryColumn('staging', 'structures', 'geom', 4326, 'MULTIPOLYGON', 2)")
    op.create_index("idx_structures_geom", "structures", ["geom"], schema="staging", postgresql_using="gist")
    op.create_index("idx_structures_type", "structures", ["building_type"], schema="staging")
    op.create_index("idx_structures_index", "structures", ["index_id"], schema="staging")
    op.create_index("idx_structures_current", "structures", ["objectid"], schema="staging",
                     postgresql_where=sa.text("valid_to IS NULL"))


def downgrade() -> None:
    op.drop_table("structures", schema="staging")
    op.drop_table("roads", schema="staging")
    op.drop_table("zoning", schema="staging")
