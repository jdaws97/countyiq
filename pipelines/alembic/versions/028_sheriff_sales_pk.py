"""sheriff_sales: PK must match the SCD2 key

The asset keys SCD2 on (case_no, property_address) — one foreclosure case can
cover several properties — but the table PK was (case_no, valid_from), so any
multi-property case violated the PK and the whole scrape failed (first seen on
the 2026-08-06 local run; production had the same latent bug).

property_address becomes NOT NULL DEFAULT '' so it can join the PK.

Revision ID: 028
Revises: 027
Create Date: 2026-08-06
"""

from alembic import op

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE staging.sheriff_sales SET property_address = '' WHERE property_address IS NULL"
    )
    op.execute(
        "ALTER TABLE staging.sheriff_sales ALTER COLUMN property_address SET DEFAULT ''"
    )
    op.execute(
        "ALTER TABLE staging.sheriff_sales ALTER COLUMN property_address SET NOT NULL"
    )
    op.execute("ALTER TABLE staging.sheriff_sales DROP CONSTRAINT sheriff_sales_pkey")
    op.execute(
        "ALTER TABLE staging.sheriff_sales ADD CONSTRAINT sheriff_sales_pkey "
        "PRIMARY KEY (case_no, property_address, valid_from)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE staging.sheriff_sales DROP CONSTRAINT sheriff_sales_pkey")
    op.execute(
        "ALTER TABLE staging.sheriff_sales ADD CONSTRAINT sheriff_sales_pkey "
        "PRIMARY KEY (case_no, valid_from)"
    )
    op.execute(
        "ALTER TABLE staging.sheriff_sales ALTER COLUMN property_address DROP NOT NULL"
    )
    op.execute(
        "ALTER TABLE staging.sheriff_sales ALTER COLUMN property_address DROP DEFAULT"
    )
