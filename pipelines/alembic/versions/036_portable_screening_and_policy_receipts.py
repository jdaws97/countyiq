"""add portable environmental screening and immutable policy receipts

Revision ID: 036
Revises: 035
Create Date: 2026-08-28
"""

from alembic import op


revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE meta.source_rights
            ADD COLUMN county_key TEXT;
        ALTER TABLE meta.source_rights
            ADD COLUMN policy_version INTEGER NOT NULL DEFAULT 1;
        ALTER TABLE meta.municipality_source_rights
            ADD COLUMN county_key TEXT NOT NULL DEFAULT 'york';
        ALTER TABLE meta.municipality_source_rights
            ADD COLUMN policy_version INTEGER NOT NULL DEFAULT 1;

        UPDATE meta.source_rights
        SET county_key = 'york'
        WHERE source_key IN (
            'york_open_data', 'tax_claims', 'sheriff_sales',
            'public_proceedings', 'ecodev_candidates', 'cdbg_housing',
            'county_scout'
        );
        CREATE INDEX idx_source_rights_county_key
            ON meta.source_rights (county_key);
        CREATE INDEX idx_municipality_source_rights_county_key
            ON meta.municipality_source_rights (county_key);

        ALTER TABLE meta.source_rights_audit
            ADD COLUMN policy_version INTEGER,
            ADD COLUMN policy_fingerprint TEXT,
            ADD COLUMN policy_snapshot JSONB NOT NULL DEFAULT '{}'::JSONB;
        ALTER TABLE meta.municipality_source_audit
            ADD COLUMN policy_version INTEGER,
            ADD COLUMN policy_fingerprint TEXT,
            ADD COLUMN policy_snapshot JSONB NOT NULL DEFAULT '{}'::JSONB;

        CREATE OR REPLACE FUNCTION meta.bump_source_policy_version()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $function$
        BEGIN
            NEW.policy_version = OLD.policy_version + 1;
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $function$;

        CREATE TRIGGER source_rights_policy_version
        BEFORE UPDATE ON meta.source_rights
        FOR EACH ROW EXECUTE FUNCTION meta.bump_source_policy_version();

        CREATE TRIGGER municipality_source_rights_policy_version
        BEFORE UPDATE ON meta.municipality_source_rights
        FOR EACH ROW EXECUTE FUNCTION meta.bump_source_policy_version();

        INSERT INTO meta.source_rights (
            source_key, publisher, source_url, rights_status,
            acquisition_allowed, raw_retention_allowed,
            derived_product_allowed, person_level_display_allowed,
            raw_export_allowed, allowed_methods, terms_url,
            reviewed_on, review_due_on, evidence, notes
        ) VALUES (
            'pa_dep_open_data',
            'Pennsylvania Department of Environmental Protection',
            'https://gis.dep.pa.gov/depgisprd/rest/services',
            'green', TRUE, TRUE, TRUE, FALSE, FALSE,
            ARRAY['arcgis_rest'],
            'https://www.pa.gov/agencies/dep/data-and-tools/gis',
            DATE '2026-08-28', DATE '2027-02-28',
            '{"basis":"DEP describes the portal as its publicly published, non-sensitive GIS data and expressly supports connecting, downloading, embedding, and sharing","delivery_boundary":"derived parcel screening with direct attribution; no source-equivalent export"}'::JSONB,
            'Screening evidence only. A nearby record is not a contamination finding, regulatory determination, or substitute for environmental due diligence.'
        );

        CREATE TABLE staging.environmental_diligence_sites (
            source_layer TEXT NOT NULL,
            source_id TEXT NOT NULL,
            site_name TEXT,
            facility_type TEXT,
            facility_status TEXT,
            address TEXT,
            municipality TEXT,
            county_name TEXT,
            detail_url TEXT,
            source_url TEXT NOT NULL,
            valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            valid_to TIMESTAMPTZ,
            geom geometry(Point, 4326)
        );
        CREATE UNIQUE INDEX idx_environmental_diligence_sites_current_key
            ON staging.environmental_diligence_sites (source_layer, source_id)
            WHERE valid_to IS NULL;
        CREATE INDEX idx_environmental_diligence_sites_geom
            ON staging.environmental_diligence_sites USING GIST (geom);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS staging.environmental_diligence_sites;
        DROP TRIGGER IF EXISTS source_rights_audit_append_only
            ON meta.source_rights_audit;
        DELETE FROM meta.source_rights_audit WHERE source_key = 'pa_dep_open_data';
        DELETE FROM meta.source_rights WHERE source_key = 'pa_dep_open_data';
        CREATE TRIGGER source_rights_audit_append_only
        BEFORE UPDATE OR DELETE ON meta.source_rights_audit
        FOR EACH ROW EXECUTE FUNCTION meta.prevent_source_audit_mutation();

        DROP TRIGGER IF EXISTS municipality_source_rights_policy_version
            ON meta.municipality_source_rights;
        DROP TRIGGER IF EXISTS source_rights_policy_version
            ON meta.source_rights;
        DROP FUNCTION IF EXISTS meta.bump_source_policy_version();

        ALTER TABLE meta.municipality_source_audit
            DROP COLUMN IF EXISTS policy_snapshot,
            DROP COLUMN IF EXISTS policy_fingerprint,
            DROP COLUMN IF EXISTS policy_version;
        ALTER TABLE meta.source_rights_audit
            DROP COLUMN IF EXISTS policy_snapshot,
            DROP COLUMN IF EXISTS policy_fingerprint,
            DROP COLUMN IF EXISTS policy_version;
        ALTER TABLE meta.municipality_source_rights
            DROP COLUMN IF EXISTS policy_version,
            DROP COLUMN IF EXISTS county_key;
        ALTER TABLE meta.source_rights
            DROP COLUMN IF EXISTS policy_version,
            DROP COLUMN IF EXISTS county_key;
        """
    )
