"""add source_url provenance column to existing staging tables

Revision ID: 013
Revises: 012
Create Date: 2026-04-03
"""

from alembic import op
import sqlalchemy as sa

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None

# Tables that already have source_url (created in migration 012 with it):
#   corporate_entities, public_proceedings, recorded_documents
# Tables skipped because they are not source-data tables or have no natural source URL:
#   (none — all tables below receive the column)

TABLES = [
    "address_points",
    "ag_security",
    "assessment_properties",
    "cdbg_housing",
    "conservation_easements",
    "ecodev_candidates",
    "flood_zones",
    "future_landuse",
    "growth_areas",
    "municipalities",
    "pa_open_data",
    "parcels",
    "penndot_projects",
    "penndot_roads",
    "planning_subdivisions",
    "plcb_licenses",
    "proceeding_extractions",
    "recorded_document_parcels",
    "roads",
    "school_districts",
    "sheriff_sales",
    "structures",
    "tax_claims",
    "traffic_counts",
    "zipcodes",
    "zoning",
    "zoning_districts",
]


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table,
            sa.Column("source_url", sa.Text),
            schema="staging",
        )


def downgrade() -> None:
    for table in TABLES:
        op.drop_column(table, "source_url", schema="staging")
