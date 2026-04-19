"""add development-radar staging + public tables

Revision ID: 010
Revises: 009
Create Date: 2026-03-30
"""
from alembic import op
import sqlalchemy as sa

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- staging.planning_subdivisions (YCPC subdivision/land dev plans, ~26K) ---
    op.execute("""
        CREATE TABLE IF NOT EXISTS staging.planning_subdivisions (
            objectid INTEGER,
            sequ_num VARCHAR(20) NOT NULL,
            mcd VARCHAR(10),
            date_rcvd TIMESTAMPTZ,
            plan_title TEXT,
            pt_prelim VARCHAR(5),
            pt_final VARCHAR(5),
            pt_land_dev VARCHAR(5),
            pt_subdiv VARCHAR(5),
            pt_bldg_add VARCHAR(5),
            cap VARCHAR(5),
            com VARCHAR(5),
            st_length INTEGER,
            water VARCHAR(10),
            sewer VARCHAR(10),
            ag_use VARCHAR(5),
            com_use VARCHAR(5),
            ind_use VARCHAR(5),
            mf_use VARCHAR(5),
            mhp_use VARCHAR(5),
            sr_use VARCHAR(5),
            sf_use VARCHAR(5),
            other_use VARCHAR(5),
            total_acres NUMERIC(12,2),
            exist_lots SMALLINT,
            prop_lots SMALLINT,
            bldg_lots SMALLINT,
            dev_lots SMALLINT,
            exist_du SMALLINT,
            prop_du SMALLINT,
            prop_bldg_add_sqft NUMERIC(12,2),
            prop_new_bldg_sqft NUMERIC(12,2),
            watershed SMALLINT,
            consistent VARCHAR(5),
            notes TEXT,
            engineer TEXT,
            valid_from TIMESTAMPTZ DEFAULT NOW(),
            valid_to TIMESTAMPTZ,
            geom geometry(Point, 4326)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_planning_subdiv_geom ON staging.planning_subdivisions USING GIST (geom)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_planning_subdiv_sequ ON staging.planning_subdivisions (sequ_num)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_planning_subdiv_date ON staging.planning_subdivisions (date_rcvd DESC)")

    # --- staging.ecodev_candidates (underutilized parcels, ~70, PIDN-linked) ---
    op.execute("""
        CREATE TABLE IF NOT EXISTS staging.ecodev_candidates (
            pidn VARCHAR(13) NOT NULL,
            percent_underutilized NUMERIC(5,2),
            buildable_acres NUMERIC(12,2),
            functional_class TEXT,
            interchange VARCHAR(50),
            railroad VARCHAR(50),
            primary_grwth_area VARCHAR(50),
            secondary_grwth_area VARCHAR(50),
            future_grwth_area VARCHAR(50),
            sewer_water_availability VARCHAR(50),
            broadband VARCHAR(50),
            transit_route VARCHAR(50),
            lev_suitability VARCHAR(50),
            ga_type VARCHAR(20),
            owner_full TEXT,
            propadr TEXT,
            class VARCHAR(5),
            acres NUMERIC(12,2),
            aprtotal TEXT,
            yrblt VARCHAR(10),
            comm_building_sq_ft NUMERIC(12,2),
            valid_from TIMESTAMPTZ DEFAULT NOW(),
            valid_to TIMESTAMPTZ,
            geom geometry(MultiPolygon, 4326)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_ecodev_pidn ON staging.ecodev_candidates (pidn)")

    # --- staging.growth_areas (growth zones, ~27) ---
    op.execute("""
        CREATE TABLE IF NOT EXISTS staging.growth_areas (
            globalid VARCHAR(40) NOT NULL,
            ga_type VARCHAR(20),
            district VARCHAR(10),
            ga_status VARCHAR(10),
            valid_from TIMESTAMPTZ DEFAULT NOW(),
            valid_to TIMESTAMPTZ,
            geom geometry(MultiPolygon, 4326)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_growth_areas_geom ON staging.growth_areas USING GIST (geom)")

    # --- staging.future_landuse (future land use zones, ~1.6K) ---
    op.execute("""
        CREATE TABLE IF NOT EXISTS staging.future_landuse (
            globalid VARCHAR(40) NOT NULL,
            district VARCHAR(10),
            future_lu TEXT,
            general_lu TEXT,
            adopt_date TIMESTAMPTZ,
            valid_from TIMESTAMPTZ DEFAULT NOW(),
            valid_to TIMESTAMPTZ,
            geom geometry(MultiPolygon, 4326)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_future_landuse_geom ON staging.future_landuse USING GIST (geom)")

    # --- staging.conservation_easements (easements, ~960, PIDN-linked) ---
    op.execute("""
        CREATE TABLE IF NOT EXISTS staging.conservation_easements (
            pidn VARCHAR(13) NOT NULL,
            ease_id VARCHAR(20),
            ease_code VARCHAR(5),
            exclusion VARCHAR(5),
            federal VARCHAR(5),
            ease_acres NUMERIC(12,2),
            grantor TEXT,
            curr_owner TEXT,
            pres_date TIMESTAMPTZ,
            district VARCHAR(10),
            valid_from TIMESTAMPTZ DEFAULT NOW(),
            valid_to TIMESTAMPTZ,
            geom geometry(MultiPolygon, 4326)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_conservation_pidn ON staging.conservation_easements (pidn)")

    # --- staging.ag_security (ag security areas, ~4.5K, PIDN-linked) ---
    op.execute("""
        CREATE TABLE IF NOT EXISTS staging.ag_security (
            pidn VARCHAR(13) NOT NULL,
            resolution VARCHAR(50),
            res_date TIMESTAMPTZ,
            res_acres NUMERIC(12,2),
            book VARCHAR(20),
            page VARCHAR(20),
            instrument VARCHAR(50),
            last_review TIMESTAMPTZ,
            flag VARCHAR(50),
            district VARCHAR(50),
            valid_from TIMESTAMPTZ DEFAULT NOW(),
            valid_to TIMESTAMPTZ,
            geom geometry(MultiPolygon, 4326)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_ag_security_pidn ON staging.ag_security (pidn)")

    # --- staging.cdbg_housing (CDBG housing projects, ~63) ---
    op.execute("""
        CREATE TABLE IF NOT EXISTS staging.cdbg_housing (
            housingdevid VARCHAR(20),
            prj_id VARCHAR(20),
            address TEXT,
            constructi TEXT,
            units INTEGER,
            date_of_oc TEXT,
            affordabil TEXT,
            name TEXT,
            valid_from TIMESTAMPTZ DEFAULT NOW(),
            valid_to TIMESTAMPTZ,
            geom geometry(Point, 4326)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_cdbg_housing_geom ON staging.cdbg_housing USING GIST (geom)")

    # --- public.development_signals (parcel-linked signal evidence) ---
    op.execute("""
        CREATE TABLE IF NOT EXISTS public.development_signals (
            id SERIAL PRIMARY KEY,
            pidn VARCHAR(13) NOT NULL,
            signal_key VARCHAR(50) NOT NULL,
            signal_weight NUMERIC(4,2) NOT NULL,
            source_table VARCHAR(60) NOT NULL,
            source_id TEXT,
            distance_m NUMERIC(10,1),
            evidence JSONB,
            observed_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_dev_signals_pidn ON public.development_signals (pidn)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_dev_signals_key ON public.development_signals (signal_key)")

    # --- public.development_momentum (scored parcel snapshot) ---
    op.execute("""
        CREATE TABLE IF NOT EXISTS public.development_momentum (
            pidn VARCHAR(13) PRIMARY KEY,
            score INTEGER NOT NULL DEFAULT 0,
            opportunity_score INTEGER NOT NULL DEFAULT 0,
            has_active_plan BOOLEAN NOT NULL DEFAULT FALSE,
            eligible BOOLEAN NOT NULL DEFAULT TRUE,
            exclusion_reasons JSONB,
            signals JSONB NOT NULL DEFAULT '{}',
            top_signal TEXT,
            signal_count INTEGER NOT NULL DEFAULT 0,
            score_version INTEGER NOT NULL DEFAULT 1,
            computed_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_dev_momentum_score ON public.development_momentum (score DESC) WHERE eligible = TRUE")
    op.execute("CREATE INDEX IF NOT EXISTS idx_dev_momentum_opportunity ON public.development_momentum (opportunity_score DESC) WHERE eligible = TRUE AND NOT has_active_plan")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.development_momentum")
    op.execute("DROP TABLE IF EXISTS public.development_signals")
    op.execute("DROP TABLE IF EXISTS staging.cdbg_housing")
    op.execute("DROP TABLE IF EXISTS staging.ag_security")
    op.execute("DROP TABLE IF EXISTS staging.conservation_easements")
    op.execute("DROP TABLE IF EXISTS staging.future_landuse")
    op.execute("DROP TABLE IF EXISTS staging.growth_areas")
    op.execute("DROP TABLE IF EXISTS staging.ecodev_candidates")
    op.execute("DROP TABLE IF EXISTS staging.planning_subdivisions")
