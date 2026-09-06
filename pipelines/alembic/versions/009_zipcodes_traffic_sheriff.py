"""add staging.zipcodes, staging.traffic_counts, staging.sheriff_sales

Revision ID: 009
Revises: 008
Create Date: 2026-03-30
"""

from alembic import op
import sqlalchemy as sa

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Zip codes (GIS layer)
    op.execute("""
        CREATE TABLE IF NOT EXISTS staging.zipcodes (
            zipcode VARCHAR(10) NOT NULL,
            po_name VARCHAR(100),
            valid_from TIMESTAMPTZ DEFAULT NOW(),
            valid_to TIMESTAMPTZ,
            geom geometry(MultiPolygon, 4326)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_zipcodes_geom ON staging.zipcodes USING GIST (geom)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_zipcodes_code ON staging.zipcodes (zipcode)"
    )

    # Traffic counts (PennDOT ArcGIS)
    op.execute("""
        CREATE TABLE IF NOT EXISTS staging.traffic_counts (
            objectid INTEGER,
            route_number VARCHAR(10),
            aadt INTEGER,
            truck_aadt INTEGER,
            segment_length NUMERIC,
            valid_from TIMESTAMPTZ DEFAULT NOW(),
            valid_to TIMESTAMPTZ,
            geom geometry(MultiLineString, 4326)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_traffic_geom ON staging.traffic_counts USING GIST (geom)"
    )

    # Sheriff sales (Playwright scraper)
    op.create_table(
        "sheriff_sales",
        sa.Column("case_no", sa.String(30), nullable=False),
        sa.Column("plaintiff", sa.Text),
        sa.Column("defendant", sa.Text),
        sa.Column("property_address", sa.Text),
        sa.Column("zip_code", sa.String(10)),
        sa.Column("municipality", sa.Text),
        sa.Column("judgment_amount", sa.Numeric(14, 2)),
        sa.Column("status", sa.String(30)),
        sa.Column("status_date", sa.Date),
        sa.Column("sale_date", sa.Date),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("case_no", "valid_from"),
        schema="staging",
    )
    op.create_index("idx_sheriff_status", "sheriff_sales", ["status"], schema="staging")
    op.create_index(
        "idx_sheriff_address", "sheriff_sales", ["property_address"], schema="staging"
    )


def downgrade() -> None:
    op.drop_table("sheriff_sales", schema="staging")
    op.execute("DROP TABLE IF EXISTS staging.traffic_counts")
    op.execute("DROP TABLE IF EXISTS staging.zipcodes")
