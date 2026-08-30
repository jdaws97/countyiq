"""Indexes for the search/browse hot paths.

The 2026-08 review traced every /api/search and /api/delinquent query to a
sequential scan:

- ``parcels.propadr %% q``          — no trgm index (only owner_full had one, 015)
- ``tax_claims.owner_name %% q``    — plain btree, unusable for ``%``
- ``plcb premises_name/licensee %% q`` — unindexed / btree-only
- ``UPPER(tax_district_name) LIKE`` — needs a text_pattern_ops expression index
- ``pidn = ANY(affected_pidns)``    — needs GIN on the array
- feed ``ORDER BY generated_at``    — small today, indexed while we're here

pg_trgm is already installed (015 depends on it).

Revision ID: 023
Revises: 022
Create Date: 2026-08-02
"""

from alembic import op


revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None

INDEXES = [
    (
        "idx_parcels_propadr_trgm",
        "CREATE INDEX idx_parcels_propadr_trgm ON staging.parcels "
        "USING gin (propadr gin_trgm_ops)",
    ),
    (
        "idx_tax_claims_owner_name_trgm",
        "CREATE INDEX idx_tax_claims_owner_name_trgm ON staging.tax_claims "
        "USING gin (owner_name gin_trgm_ops)",
    ),
    (
        "idx_plcb_premises_name_trgm",
        "CREATE INDEX idx_plcb_premises_name_trgm ON staging.plcb_licenses "
        "USING gin (premises_name gin_trgm_ops)",
    ),
    (
        "idx_plcb_licensee_trgm",
        "CREATE INDEX idx_plcb_licensee_trgm ON staging.plcb_licenses "
        "USING gin (licensee gin_trgm_ops)",
    ),
    (
        "idx_tax_claims_district_upper",
        "CREATE INDEX idx_tax_claims_district_upper ON staging.tax_claims "
        "(upper(tax_district_name) text_pattern_ops)",
    ),
    (
        "idx_county_narratives_pidns",
        "CREATE INDEX idx_county_narratives_pidns ON public.county_narratives "
        "USING gin (affected_pidns)",
    ),
    (
        "idx_county_narratives_generated_at",
        "CREATE INDEX idx_county_narratives_generated_at ON public.county_narratives "
        "(generated_at DESC)",
    ),
]


def upgrade() -> None:
    for _name, ddl in INDEXES:
        op.execute(ddl)


def downgrade() -> None:
    for name, ddl in reversed(INDEXES):
        schema = "public" if "public." in ddl else "staging"
        op.execute(f"DROP INDEX IF EXISTS {schema}.{name}")
