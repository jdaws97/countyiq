"""govern source use and add site-readiness data

Revision ID: 031
Revises: 030
Create Date: 2026-08-27
"""

from alembic import op


revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE meta.source_rights (
            source_key TEXT PRIMARY KEY,
            publisher TEXT NOT NULL,
            source_url TEXT NOT NULL,
            rights_status TEXT NOT NULL
                CHECK (rights_status IN ('green', 'conditional', 'paused')),
            acquisition_allowed BOOLEAN NOT NULL DEFAULT FALSE,
            raw_retention_allowed BOOLEAN NOT NULL DEFAULT FALSE,
            derived_product_allowed BOOLEAN NOT NULL DEFAULT FALSE,
            person_level_display_allowed BOOLEAN NOT NULL DEFAULT FALSE,
            raw_export_allowed BOOLEAN NOT NULL DEFAULT FALSE,
            allowed_methods TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
            terms_url TEXT,
            reviewed_on DATE NOT NULL,
            review_due_on DATE NOT NULL,
            evidence JSONB NOT NULL DEFAULT '{}'::JSONB,
            notes TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE TABLE meta.source_rights_audit (
            id BIGSERIAL PRIMARY KEY,
            source_key TEXT NOT NULL REFERENCES meta.source_rights(source_key),
            asset_key TEXT NOT NULL,
            dagster_run_id TEXT,
            acquisition_method TEXT NOT NULL,
            allowed BOOLEAN NOT NULL,
            reason TEXT NOT NULL,
            checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX idx_source_rights_audit_source_checked
            ON meta.source_rights_audit (source_key, checked_at DESC);

        INSERT INTO meta.source_rights (
            source_key, publisher, source_url, rights_status,
            acquisition_allowed, raw_retention_allowed,
            derived_product_allowed, person_level_display_allowed,
            raw_export_allowed, allowed_methods, terms_url,
            reviewed_on, review_due_on, evidence, notes
        ) VALUES
            (
                'york_open_data', 'York County Planning Commission',
                'https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA', 'green',
                TRUE, TRUE, TRUE, FALSE, FALSE, ARRAY['arcgis_rest'],
                'https://yorkcountypa.gov/1042/GISMaps',
                DATE '2026-08-27', DATE '2027-02-27',
                '{"basis":"official OPEN_DATA folder; public query APIs; current metadata reports no access/use constraints","delivery_boundary":"derived analytics only"}'::JSONB,
                'Do not source from the separate Property Tax Viewer or offer source-equivalent bulk export.'
            ),
            (
                'penndot_open_data', 'Pennsylvania Department of Transportation',
                'https://gis.penndot.pa.gov/gis/rest/services/opendata', 'green',
                TRUE, TRUE, TRUE, FALSE, FALSE, ARRAY['arcgis_rest'],
                'https://www.pa.gov/agencies/penndot/programs-and-doing-business/digital-delivery/glossary-of-terms',
                DATE '2026-08-27', DATE '2027-02-27',
                '{"basis":"PennDOT defines published open data as free to use or reuse without restriction"}'::JSONB,
                'Attribute the data source; do not treat separately controlled PennDOT maps or logos as open GIS data.'
            ),
            (
                'fema_nfhl', 'Federal Emergency Management Agency',
                'https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer', 'green',
                TRUE, TRUE, TRUE, FALSE, FALSE, ARRAY['arcgis_rest'],
                'https://www.fema.gov/about/openfema/terms-conditions',
                DATE '2026-08-27', DATE '2027-02-27',
                '{"basis":"federal public hazard data"}'::JSONB,
                'Never represent NFHL output as an official flood determination.'
            ),
            (
                'data_pa_businesses', 'Commonwealth of Pennsylvania',
                'https://data.pa.gov/resource/xvd7-5r2c.json', 'green',
                TRUE, TRUE, TRUE, FALSE, FALSE, ARRAY['soda_api'],
                'https://data.pa.gov/data-policy',
                DATE '2026-08-27', DATE '2027-02-27',
                '{"basis":"data.pa.gov datasets are offered free and without restriction"}'::JSONB,
                'Attribution requested by the Commonwealth.'
            ),
            (
                'plcb_licenses', 'Pennsylvania Liquor Control Board',
                'https://plcbplus.pa.gov/pub/LicenseExport.aspx', 'conditional',
                TRUE, TRUE, TRUE, FALSE, FALSE, ARRAY['official_bulk_export'],
                'https://plcbplus.pa.gov/pub/LicenseExport.aspx',
                DATE '2026-08-27', DATE '2027-02-27',
                '{"basis":"intentionally published official statewide bulk export","open_license":"not expressly posted"}'::JSONB,
                'Keep raw files private; expose license facts and derived analysis, not a source-replacement export.'
            ),
            (
                'tax_claims', 'York County Tax Claim Bureau',
                'https://yorkcountypa.gov/DocumentCenter/View/1911/Delinquent-Tax-Claim-Listing-PDF', 'conditional',
                TRUE, TRUE, TRUE, FALSE, FALSE, ARRAY['official_pdf'],
                'https://yorkcountypa.gov/523/Delinquent-Tax-Information-Payment',
                DATE '2026-08-27', DATE '2026-11-27',
                '{"basis":"county states listing is for public access and informational only","privacy":"high"}'::JSONB,
                'No people rankings, claimant-name search, broad export, eligibility decisions, or solicitation list.'
            ),
            (
                'sheriff_sales', 'York County Sheriff',
                'https://attorneyportal.yorkcountypa.gov/sheriff.salelisting/', 'conditional',
                TRUE, TRUE, TRUE, FALSE, FALSE, ARRAY['official_html_direct'],
                'https://yorkcountypa.gov/468/Real-Estate-Sheriff-Sales',
                DATE '2026-08-27', DATE '2026-11-27',
                '{"basis":"official public listing; no affirmative open-data license located","privacy":"high"}'::JSONB,
                'Use honest direct HTTP access. Product output must be property-level and derived; no defendant lists or eligibility use.'
            ),
            (
                'public_proceedings', 'York County municipalities',
                'https://yorkcountypa.gov/1019/Municipalities', 'conditional',
                TRUE, TRUE, TRUE, FALSE, FALSE, ARRAY['official_document_direct'],
                NULL,
                DATE '2026-08-27', DATE '2026-11-27',
                '{"basis":"official public proceedings; source terms and delivery vary by municipality","copyright":"facts may be derived; packets are not republished"}'::JSONB,
                'Fail closed on robots/access uncertainty; no bot-wall bypass; archive privately and expose facts or short evidence excerpts.'
            ),
            (
                'ecodev_candidates', 'York County Planning Commission',
                'https://arcweb1.ycpc.org/server/rest/services/Projects/EcoDev_Candidates_Parcels/FeatureServer/0', 'paused',
                FALSE, FALSE, FALSE, FALSE, FALSE, ARRAY[]::TEXT[],
                'https://yorkcountypa.gov/1042/GISMaps',
                DATE '2026-08-27', DATE '2026-11-27',
                '{"basis":"publicly reachable project service outside OPEN_DATA; no reuse grant located"}'::JSONB,
                'Written YCPC publication/reuse confirmation is required before reactivation.'
            ),
            (
                'cdbg_housing', 'York County',
                'https://arcweb1.ycpc.org/server/rest/services/CDBG/CDBG_Housing_Locations/FeatureServer/0', 'paused',
                FALSE, FALSE, FALSE, FALSE, FALSE, ARRAY[]::TEXT[],
                'https://yorkcountypa.gov/1042/GISMaps',
                DATE '2026-08-27', DATE '2026-11-27',
                '{"basis":"service is outside OPEN_DATA and describes itself as a testing feature service","privacy":"potential housing-recipient sensitivity"}'::JSONB,
                'Written publication intent, field review, and reuse approval are required before reactivation.'
            );

        CREATE TABLE staging.zoning_overlays (
            globalid TEXT NOT NULL,
            objectid INTEGER,
            municipality TEXT,
            overlay_type TEXT,
            overlay_name TEXT,
            description TEXT,
            project_number TEXT,
            create_date TIMESTAMPTZ,
            modify_date TIMESTAMPTZ,
            source_url TEXT NOT NULL,
            valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            valid_to TIMESTAMPTZ,
            geom geometry(MultiPolygon, 4326)
        );
        CREATE INDEX idx_zoning_overlays_current_key
            ON staging.zoning_overlays (globalid) WHERE valid_to IS NULL;
        CREATE INDEX idx_zoning_overlays_geom
            ON staging.zoning_overlays USING GIST (geom);

        CREATE TABLE staging.economic_development_parks (
            park_type TEXT NOT NULL CHECK (park_type IN ('business', 'industrial')),
            pidn TEXT NOT NULL,
            source_objectid INTEGER NOT NULL,
            name TEXT,
            website_url TEXT,
            create_date TIMESTAMPTZ,
            modify_date TIMESTAMPTZ,
            source_url TEXT NOT NULL,
            valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            valid_to TIMESTAMPTZ,
            geom geometry(MultiPolygon, 4326)
        );
        CREATE INDEX idx_economic_parks_current_key
            ON staging.economic_development_parks (park_type, source_objectid) WHERE valid_to IS NULL;
        CREATE INDEX idx_economic_parks_pidn
            ON staging.economic_development_parks (pidn) WHERE valid_to IS NULL;
        CREATE INDEX idx_economic_parks_geom
            ON staging.economic_development_parks USING GIST (geom);

        CREATE TABLE staging.soils (
            objectid INTEGER NOT NULL,
            map_unit_symbol TEXT,
            map_unit_name TEXT,
            map_unit_key TEXT,
            calculated_acres NUMERIC,
            drainage TEXT,
            capability_class NUMERIC,
            permeability NUMERIC,
            septic_rating TEXT,
            slope_low INTEGER,
            slope_high INTEGER,
            representative_slope NUMERIC,
            hydric_rating TEXT,
            hydrologic_group TEXT,
            relative_value TEXT,
            source_url TEXT NOT NULL,
            valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            valid_to TIMESTAMPTZ,
            geom geometry(MultiPolygon, 4326)
        );
        CREATE INDEX idx_soils_current_key
            ON staging.soils (objectid) WHERE valid_to IS NULL;
        CREATE INDEX idx_soils_geom ON staging.soils USING GIST (geom);

        CREATE TABLE staging.local_traffic_counts (
            globalid TEXT NOT NULL,
            objectid INTEGER,
            counter_id TEXT,
            count_type TEXT,
            bridge_id TEXT,
            bridge_key TEXT,
            purpose TEXT,
            volume INTEGER,
            am_volume INTEGER,
            am_percent NUMERIC,
            am_peak INTEGER,
            pm_volume INTEGER,
            pm_percent NUMERIC,
            pm_peak INTEGER,
            planning_region TEXT,
            count_year INTEGER,
            other_mode TEXT,
            comment TEXT,
            create_date TIMESTAMPTZ,
            modify_date TIMESTAMPTZ,
            source_url TEXT NOT NULL,
            valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            valid_to TIMESTAMPTZ,
            geom geometry(Point, 4326)
        );
        CREATE INDEX idx_local_traffic_counts_current_key
            ON staging.local_traffic_counts (globalid) WHERE valid_to IS NULL;
        CREATE INDEX idx_local_traffic_counts_year
            ON staging.local_traffic_counts (count_year DESC) WHERE valid_to IS NULL;
        CREATE INDEX idx_local_traffic_counts_geom
            ON staging.local_traffic_counts USING GIST (geom);

        ALTER TABLE public.development_momentum
            ADD COLUMN site_readiness_score INTEGER NOT NULL DEFAULT 0;
        CREATE INDEX idx_dev_momentum_site_readiness
            ON public.development_momentum (site_readiness_score DESC)
            WHERE eligible = TRUE;

        UPDATE staging.ecodev_candidates
        SET valid_to = NOW()
        WHERE valid_to IS NULL;

        UPDATE staging.cdbg_housing
        SET valid_to = NOW()
        WHERE valid_to IS NULL;

        DELETE FROM public.evidence
        WHERE signal_key IN ('ecodev_candidate', 'cdbg_investment');

        DELETE FROM public.development_signals
        WHERE signal_key IN ('ecodev_candidate', 'cdbg_investment');

        DELETE FROM public.development_momentum;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS public.idx_dev_momentum_site_readiness;
        ALTER TABLE public.development_momentum
            DROP COLUMN IF EXISTS site_readiness_score;

        DROP TABLE IF EXISTS staging.local_traffic_counts;
        DROP TABLE IF EXISTS staging.soils;
        DROP TABLE IF EXISTS staging.economic_development_parks;
        DROP TABLE IF EXISTS staging.zoning_overlays;
        DROP TABLE IF EXISTS meta.source_rights_audit;
        DROP TABLE IF EXISTS meta.source_rights;
        """
    )
