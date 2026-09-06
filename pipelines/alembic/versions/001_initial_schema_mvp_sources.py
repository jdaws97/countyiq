"""initial_schema_mvp_sources

Revision ID: 001
Revises:
Create Date: 2026-03-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Extensions (idempotent) ---
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis_topology")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # --- Schemas ---
    op.execute("CREATE SCHEMA IF NOT EXISTS staging")
    op.execute("CREATE SCHEMA IF NOT EXISTS meta")

    # =====================================================================
    # STAGING SCHEMA — Cleaned, normalized, SCD Type 2
    # =====================================================================

    # --- staging.parcels (Source 1: York County GIS Portal) ---
    op.create_table(
        "parcels",
        sa.Column("pidn", sa.Text, nullable=False),
        sa.Column("district", sa.String(2)),
        sa.Column("block", sa.String(3)),
        sa.Column("map", sa.String(2)),
        sa.Column("parcel", sa.String(6)),
        sa.Column("deed_bk", sa.String(8)),
        sa.Column("deed_pg", sa.String(8)),
        sa.Column("propadr", sa.String(54)),
        sa.Column("owner_full", sa.String(81)),
        sa.Column("own_name1", sa.String(40)),
        sa.Column("own_name2", sa.String(40)),
        sa.Column("mail_addr_full", sa.String(124)),
        sa.Column("prev_owner", sa.String(40)),
        sa.Column("class", sa.String(1)),
        sa.Column("luc", sa.String(4)),
        sa.Column("acres", sa.Float),
        sa.Column("style", sa.String(2)),
        sa.Column("num_stories", sa.Float),
        sa.Column("res_living_area", sa.Integer),
        sa.Column("yrblt", sa.SmallInteger),
        sa.Column("clean_green", sa.String(3)),
        sa.Column("heatsys", sa.SmallInteger),
        sa.Column("fuel", sa.SmallInteger),
        sa.Column("aprland", sa.Float),
        sa.Column("aprbldg", sa.Float),
        sa.Column("aprtotal", sa.Float),
        sa.Column("saledt", sa.String(11)),
        sa.Column("price", sa.Float),
        sa.Column("prev_price", sa.Float),
        sa.Column("municipality", sa.Text),
        sa.Column("school_dis", sa.String(5)),
        sa.Column("comm_struc", sa.String(3)),
        sa.Column("comm_year_built", sa.Integer),
        sa.Column("comm_building_sq_ft", sa.Integer),
        sa.Column("grade", sa.String(2)),
        sa.Column("cdu", sa.String(2)),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("pidn", "valid_from"),
        schema="staging",
    )
    # PostGIS geometry column added separately (Alembic doesn't natively handle geometry)
    op.execute(
        "SELECT AddGeometryColumn('staging', 'parcels', 'geom', 4326, 'MULTIPOLYGON', 2)"
    )
    op.create_index(
        "idx_parcels_geom",
        "parcels",
        ["geom"],
        schema="staging",
        postgresql_using="gist",
    )
    op.create_index("idx_parcels_owner", "parcels", ["owner_full"], schema="staging")
    op.create_index(
        "idx_parcels_municipality", "parcels", ["municipality"], schema="staging"
    )
    op.create_index(
        "idx_parcels_current",
        "parcels",
        ["pidn"],
        schema="staging",
        postgresql_where=sa.text("valid_to IS NULL"),
    )

    # --- staging.assessment_properties (Source 2: Assessment Database) ---
    op.create_table(
        "assessment_properties",
        sa.Column("pidn", sa.Text, nullable=False),
        sa.Column("parid", sa.String(18)),
        sa.Column("owner_name", sa.Text),
        sa.Column("address", sa.Text),
        sa.Column("municipality", sa.Text),
        sa.Column("school_district", sa.Text),
        sa.Column("property_class", sa.Text),
        sa.Column("land_use_code", sa.String(4)),
        sa.Column("assessed_land", sa.Numeric),
        sa.Column("assessed_building", sa.Numeric),
        sa.Column("assessed_total", sa.Numeric),
        sa.Column("sale_date", sa.Text),
        sa.Column("sale_price", sa.Numeric),
        sa.Column("permits", JSONB),
        sa.Column("delinquent_taxes", JSONB),
        sa.Column("value_history", JSONB),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("pidn", "valid_from"),
        schema="staging",
    )
    op.create_index(
        "idx_assessment_owner",
        "assessment_properties",
        ["owner_name"],
        schema="staging",
    )
    op.create_index(
        "idx_assessment_current",
        "assessment_properties",
        ["pidn"],
        schema="staging",
        postgresql_where=sa.text("valid_to IS NULL"),
    )

    # --- staging.flood_zones (Source 3: FEMA NFHL) ---
    op.create_table(
        "flood_zones",
        sa.Column("fld_zone", sa.Text, nullable=False),
        sa.Column("zone_subty", sa.Text),
        sa.Column("sfha_tf", sa.String(1)),
        sa.Column("fld_ar_id", sa.Text, nullable=False),
        sa.Column("study_typ", sa.Text),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("fld_ar_id", "valid_from"),
        schema="staging",
    )
    op.execute(
        "SELECT AddGeometryColumn('staging', 'flood_zones', 'geom', 4326, 'MULTIPOLYGON', 2)"
    )
    op.create_index(
        "idx_flood_geom",
        "flood_zones",
        ["geom"],
        schema="staging",
        postgresql_using="gist",
    )

    # --- staging.municipalities (Source 1: GIS Portal) ---
    op.create_table(
        "municipalities",
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("muni_type", sa.Text),
        sa.Column("county", sa.Text),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("name", "valid_from"),
        schema="staging",
    )
    op.execute(
        "SELECT AddGeometryColumn('staging', 'municipalities', 'geom', 4326, 'MULTIPOLYGON', 2)"
    )
    op.create_index(
        "idx_muni_geom",
        "municipalities",
        ["geom"],
        schema="staging",
        postgresql_using="gist",
    )

    # --- staging.school_districts (Source 1: GIS Portal) ---
    op.create_table(
        "school_districts",
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("district_code", sa.String(5)),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("name", "valid_from"),
        schema="staging",
    )
    op.execute(
        "SELECT AddGeometryColumn('staging', 'school_districts', 'geom', 4326, 'MULTIPOLYGON', 2)"
    )
    op.create_index(
        "idx_school_geom",
        "school_districts",
        ["geom"],
        schema="staging",
        postgresql_using="gist",
    )

    # --- staging.zoning_districts (Source 1: GIS Portal) ---
    op.create_table(
        "zoning_districts",
        sa.Column("zone_id", sa.Text, nullable=False),
        sa.Column("zone_type", sa.Text),
        sa.Column("zone_desc", sa.Text),
        sa.Column("municipality", sa.Text),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("zone_id", "valid_from"),
        schema="staging",
    )
    op.execute(
        "SELECT AddGeometryColumn('staging', 'zoning_districts', 'geom', 4326, 'MULTIPOLYGON', 2)"
    )
    op.create_index(
        "idx_zoning_geom",
        "zoning_districts",
        ["geom"],
        schema="staging",
        postgresql_using="gist",
    )
    op.create_index(
        "idx_zoning_municipality",
        "zoning_districts",
        ["municipality"],
        schema="staging",
    )

    # --- staging.pa_open_data (Source 4: PA Open Data / SODA API) ---
    op.create_table(
        "pa_open_data",
        sa.Column("dataset_id", sa.Text, nullable=False),
        sa.Column("record_id", sa.Text, nullable=False),
        sa.Column("data", JSONB, nullable=False),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("dataset_id", "record_id", "valid_from"),
        schema="staging",
    )

    # --- staging.penndot_roads (Source 5: PennDOT Open Data) ---
    op.create_table(
        "penndot_roads",
        sa.Column("road_id", sa.Text, nullable=False),
        sa.Column("route_number", sa.Text),
        sa.Column("road_name", sa.Text),
        sa.Column("road_class", sa.Text),
        sa.Column("municipality", sa.Text),
        sa.Column("speed_limit", sa.Integer),
        sa.Column("surface_type", sa.Text),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("road_id", "valid_from"),
        schema="staging",
    )
    op.execute(
        "SELECT AddGeometryColumn('staging', 'penndot_roads', 'geom', 4326, 'MULTILINESTRING', 2)"
    )
    op.create_index(
        "idx_roads_geom",
        "penndot_roads",
        ["geom"],
        schema="staging",
        postgresql_using="gist",
    )

    # --- staging.penndot_projects (Source 13: PennDOT Projects MapServer) ---
    op.create_table(
        "penndot_projects",
        sa.Column("project_id", sa.Text, nullable=False),
        sa.Column("project_name", sa.Text),
        sa.Column("description", sa.Text),
        sa.Column("status", sa.Text),
        sa.Column("project_type", sa.Text),
        sa.Column("start_date", sa.Date),
        sa.Column("end_date", sa.Date),
        sa.Column("cost", sa.Numeric),
        sa.Column("municipality", sa.Text),
        sa.Column("county", sa.Text),
        sa.Column("data", JSONB),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("project_id", "valid_from"),
        schema="staging",
    )
    op.execute(
        "SELECT AddGeometryColumn('staging', 'penndot_projects', 'geom', 4326, 'GEOMETRY', 2)"
    )
    op.create_index(
        "idx_projects_geom",
        "penndot_projects",
        ["geom"],
        schema="staging",
        postgresql_using="gist",
    )

    # =====================================================================
    # PUBLIC SCHEMA — Entity-resolved, query-ready
    # =====================================================================

    # --- public.owners ---
    op.create_table(
        "owners",
        sa.Column("owner_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("canonical_name", sa.Text, nullable=False),
        sa.Column("canonical_addr", sa.Text),
        sa.Column("entity_type", sa.Text),
        sa.Column("municipality", sa.Text),
        sa.Column("parcel_count", sa.Integer, server_default="0"),
        sa.Column("first_seen", sa.Date),
        sa.Column("last_seen", sa.Date),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
        schema="public",
    )
    op.create_index(
        "idx_owners_name",
        "owners",
        ["canonical_name"],
        schema="public",
        postgresql_using="gin",
        postgresql_ops={"canonical_name": "gin_trgm_ops"},
    )
    op.create_index(
        "idx_owners_municipality", "owners", ["municipality"], schema="public"
    )

    # --- public.owner_source_links ---
    op.create_table(
        "owner_source_links",
        sa.Column("link_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "owner_id",
            sa.Integer,
            sa.ForeignKey("public.owners.owner_id"),
            nullable=False,
        ),
        sa.Column("source_type", sa.Text, nullable=False),
        sa.Column("source_id", sa.Text, nullable=False),
        sa.Column("source_name", sa.Text),
        sa.Column("source_address", sa.Text),
        sa.Column("match_tier", sa.Text),
        sa.Column("confidence", sa.Numeric(3, 2)),
        sa.Column(
            "matched_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
        sa.UniqueConstraint("source_type", "source_id"),
        schema="public",
    )
    op.create_index(
        "idx_owner_links_owner", "owner_source_links", ["owner_id"], schema="public"
    )
    op.create_index(
        "idx_owner_links_source",
        "owner_source_links",
        ["source_type", "source_id"],
        schema="public",
    )

    # --- public.properties VIEW ---
    op.execute("""
        CREATE VIEW public.properties AS
        SELECT
            p.pidn,
            p.geom,
            p.owner_full,
            p.propadr,
            p.aprtotal,
            p.saledt,
            p.price,
            p.municipality,
            p.school_dis,
            p.acres,
            p."class",
            a.permits,
            a.delinquent_taxes,
            a.value_history,
            p.valid_from,
            p.valid_to
        FROM staging.parcels p
        LEFT JOIN staging.assessment_properties a
            ON p.pidn = a.pidn
            AND a.valid_to IS NULL
        WHERE p.valid_to IS NULL
    """)

    # =====================================================================
    # META SCHEMA — Application metadata
    # =====================================================================

    op.create_table(
        "pipeline_status",
        sa.Column("source_name", sa.Text, primary_key=True),
        sa.Column("schedule_type", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("duration_seconds", sa.Integer),
        sa.Column("record_count", sa.Integer),
        sa.Column("prev_record_count", sa.Integer),
        sa.Column("error_message", sa.Text),
        sa.Column("next_scheduled_run", sa.DateTime(timezone=True)),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
        schema="meta",
    )
    op.execute(
        "ALTER TABLE meta.pipeline_status ADD CONSTRAINT chk_schedule_type CHECK (schedule_type IN ('daily', 'weekly', 'monthly', 'on_demand'))"
    )
    op.execute(
        "ALTER TABLE meta.pipeline_status ADD CONSTRAINT chk_status CHECK (status IN ('SUCCESS', 'FAILURE', 'IN_PROGRESS'))"
    )
    op.execute(
        "ALTER TABLE meta.pipeline_status ADD CONSTRAINT chk_duration CHECK (duration_seconds >= 0)"
    )
    op.execute(
        "ALTER TABLE meta.pipeline_status ADD CONSTRAINT chk_record_count CHECK (record_count >= 0)"
    )
    op.execute(
        "ALTER TABLE meta.pipeline_status ADD CONSTRAINT chk_prev_count CHECK (prev_record_count >= 0)"
    )

    op.create_table(
        "infra_metrics",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "checked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("metrics", JSONB, nullable=False),
        schema="meta",
    )
    op.create_index(
        "idx_infra_metrics_checked", "infra_metrics", ["checked_at"], schema="meta"
    )

    op.create_table(
        "data_quality_checks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("source_name", sa.Text, nullable=False),
        sa.Column("check_name", sa.Text, nullable=False),
        sa.Column("passed", sa.Boolean, nullable=False),
        sa.Column("details", sa.Text),
        sa.Column(
            "checked_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
        schema="meta",
    )
    op.execute(
        "ALTER TABLE meta.data_quality_checks ADD CONSTRAINT chk_check_name CHECK (check_name IN ('record_count_nonzero', 'schema_valid', 'freshness_ok', 'row_count_delta'))"
    )
    op.create_index(
        "idx_dq_checks_source",
        "data_quality_checks",
        [sa.text("source_name"), sa.text("checked_at DESC")],
        schema="meta",
    )

    # =====================================================================
    # FUNCTIONS — Normalization + PARID crosswalk
    # =====================================================================

    op.execute("""
        CREATE OR REPLACE FUNCTION staging.parid_to_pidn(parid TEXT) RETURNS TEXT AS $$
            SELECT CONCAT(
                SUBSTRING(parid FROM 1 FOR 2),
                SUBSTRING(parid FROM 4 FOR 3),
                SUBSTRING(parid FROM 8 FOR 2),
                SUBSTRING(parid FROM 11 FOR 6)
            );
        $$ LANGUAGE sql IMMUTABLE
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION public.normalize_name(raw_name TEXT) RETURNS TEXT AS $$
            SELECT UPPER(
                REGEXP_REPLACE(
                    REGEXP_REPLACE(
                        TRIM(raw_name),
                        '\\s+(JR|SR|II|III|IV|LLC|INC|CORP|LP|LTD|CO|TRUST|ESTATE)\\.?$',
                        '', 'gi'
                    ),
                    '[^A-Za-z0-9\\s]', '', 'g'
                )
            );
        $$ LANGUAGE sql IMMUTABLE
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION public.normalize_address(raw_address TEXT) RETURNS TEXT AS $$
            SELECT UPPER(
                REGEXP_REPLACE(
                    REGEXP_REPLACE(
                        REGEXP_REPLACE(
                            REGEXP_REPLACE(
                                TRIM(raw_address),
                                '\\s+(APT|UNIT|STE|SUITE|#)\\s*\\S*$', '', 'gi'
                            ),
                            '\\bSTREET\\b', 'ST', 'gi'
                        ),
                        '\\bAVENUE\\b', 'AVE', 'gi'
                    ),
                    '\\bROAD\\b', 'RD', 'gi'
                )
            );
        $$ LANGUAGE sql IMMUTABLE
    """)


def downgrade() -> None:
    # Functions
    op.execute("DROP FUNCTION IF EXISTS public.normalize_address(TEXT)")
    op.execute("DROP FUNCTION IF EXISTS public.normalize_name(TEXT)")
    op.execute("DROP FUNCTION IF EXISTS staging.parid_to_pidn(TEXT)")

    # Meta schema tables
    op.drop_table("data_quality_checks", schema="meta")
    op.drop_table("infra_metrics", schema="meta")
    op.drop_table("pipeline_status", schema="meta")

    # Public schema
    op.execute("DROP VIEW IF EXISTS public.properties")
    op.drop_table("owner_source_links", schema="public")
    op.drop_table("owners", schema="public")

    # Staging schema tables (reverse order)
    op.drop_table("penndot_projects", schema="staging")
    op.drop_table("penndot_roads", schema="staging")
    op.drop_table("pa_open_data", schema="staging")
    op.drop_table("zoning_districts", schema="staging")
    op.drop_table("school_districts", schema="staging")
    op.drop_table("municipalities", schema="staging")
    op.drop_table("flood_zones", schema="staging")
    op.drop_table("assessment_properties", schema="staging")
    op.drop_table("parcels", schema="staging")

    # Schemas (only drop if empty — leave extensions)
    op.execute("DROP SCHEMA IF EXISTS meta")
    op.execute("DROP SCHEMA IF EXISTS staging")
