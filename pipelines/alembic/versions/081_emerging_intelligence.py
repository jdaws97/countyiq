"""Versioned, source-current emerging hypotheses and private case workflow."""

from alembic import op

revision = "081"
down_revision = "080"
branch_labels = None
depends_on = None

CACHE_DEPENDENCIES = (
    "staging.zoning",
    "staging.future_landuse",
    "staging.soils",
    "staging.planning_subdivisions",
    "staging.conservation_easements",
    "staging.ag_security",
    "staging.flood_zones",
    "staging.environmental_diligence_sites",
    "meta.emerging_intelligence_publications",
)


def upgrade() -> None:
    op.execute("""
        ALTER TABLE meta.intelligence_inference_history
            DROP CONSTRAINT intelligence_inference_history_output_kind_check;
        ALTER TABLE meta.intelligence_inference_history
            ADD CONSTRAINT intelligence_inference_history_output_kind_check CHECK (
                output_kind IN ('proceeding_extraction', 'entity_verification',
                    'signal_validation', 'parcel_brief', 'owner_brief',
                    'municipal_evidence', 'record_explanation',
                    'emerging_analysis', 'emerging_replay'));
        CREATE TABLE meta.emerging_intelligence_publications (
            publication_id bigserial PRIMARY KEY,
            inference_id bigint NOT NULL
                REFERENCES meta.intelligence_inference_history(inference_id),
            action text NOT NULL CHECK (action IN ('publish', 'withdraw')),
            reviewer text NOT NULL CHECK (length(btrim(reviewer)) > 0),
            rationale text NOT NULL CHECK (length(btrim(rationale)) >= 12),
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX emerging_intelligence_publication_inference
            ON meta.emerging_intelligence_publications(inference_id, publication_id DESC);
        CREATE TRIGGER immutable_emerging_intelligence_publications
            BEFORE UPDATE OR DELETE ON meta.emerging_intelligence_publications
            FOR EACH ROW EXECUTE FUNCTION meta.reject_intelligence_audit_mutation();
        CREATE TRIGGER immutable_emerging_intelligence_publications_truncate
            BEFORE TRUNCATE ON meta.emerging_intelligence_publications
            FOR EACH STATEMENT EXECUTE FUNCTION meta.reject_intelligence_audit_mutation();

        ALTER TABLE public.watchspaces
            ADD COLUMN intelligence_profile jsonb NOT NULL DEFAULT '{}'::jsonb
                CHECK (jsonb_typeof(intelligence_profile) = 'object'),
            ADD COLUMN intelligence_work jsonb NOT NULL DEFAULT '[]'::jsonb
                CHECK (jsonb_typeof(intelligence_work) = 'array');
    """)
    _create_scope_source()
    _add_cache_dependencies()
    op.execute("""
        CREATE VIEW public.current_emerging_analyses AS
        WITH latest AS MATERIALIZED (
            SELECT DISTINCT ON (subject_key) history.*
            FROM meta.intelligence_inference_history history
            WHERE output_kind = 'emerging_analysis' AND disposition = 'accepted'
            ORDER BY subject_key, inference_id DESC
        )
        SELECT latest.inference_id, latest.subject_key, latest.created_at,
            latest.payload
        FROM latest
        JOIN LATERAL (
            SELECT action FROM meta.emerging_intelligence_publications publication
            WHERE publication.inference_id = latest.inference_id
            ORDER BY publication_id DESC LIMIT 1
        ) publication ON publication.action = 'publish'
        WHERE latest.payload->>'contract_version' = '1'
            AND latest.payload->'packet'->>'temporal_mode' = 'current'
            AND latest.payload->'packet'->'source' = public.emerging_scope_source(
                latest.payload->'packet'->'source'->>'seed_bundle',
                latest.payload->'packet'->'source'->'settings'->>'open_data_key',
                (latest.payload->'packet'->'source'->'settings'->>'planning_radius_m')::integer,
                (latest.payload->'packet'->'source'->'settings'->>'environmental_radius_m')::integer,
                (latest.payload->'packet'->'source'->'settings'->>'neighbor_limit')::integer
            );

        CREATE VIEW public.current_emerging_cases AS
        SELECT 'emerging-' || encode(sha256(convert_to(
                current.subject_key || '|' || (hypothesis->>'family'), 'UTF8'
            )), 'hex') AS case_key,
            current.inference_id, current.subject_key, current.created_at,
            current.payload->'packet' AS packet,
            current.payload->'analysis' AS analysis,
            hypothesis
        FROM public.current_emerging_analyses current
        CROSS JOIN LATERAL jsonb_array_elements(
            current.payload->'analysis'->'hypotheses'
        ) hypothesis;
    """)


def _add_cache_dependencies() -> None:
    # The ordinary feed revision already tracks parcels, municipal sources,
    # candidate reviews, inference history and rights. Include every additional
    # property-context layer and publication action before reusing case snapshots.
    for table in CACHE_DEPENDENCIES:
        op.execute(f"""
            CREATE TRIGGER invalidate_emerging_cache
            AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE ON {table}
            FOR EACH STATEMENT EXECUTE FUNCTION meta.invalidate_feed_cache();
        """)


def _create_scope_source() -> None:
    op.execute("""
        CREATE FUNCTION public.emerging_scope_source(
            requested_bundle text, open_data_key text,
            planning_radius_m integer, environmental_radius_m integer,
            neighbor_limit integer
        ) RETURNS jsonb LANGUAGE sql STABLE AS $function$
        WITH seed AS MATERIALIZED (
            SELECT source FROM public.municipal_matter_source(requested_bundle)
            WHERE neighbor_limit BETWEEN 0 AND 12
                AND planning_radius_m BETWEEN 1 AND 2000
                AND environmental_radius_m BETWEEN 1 AND 2000
        ), permitted AS (
            SELECT EXISTS (
                SELECT 1 FROM meta.source_rights policy
                WHERE policy.source_key = open_data_key
                    AND policy.rights_status <> 'paused'
                    AND policy.derived_product_allowed
                    AND policy.review_due_on >= CURRENT_DATE
            ) AS available
        ), anchor_keys AS (
            SELECT DISTINCT pidn FROM seed,
                LATERAL jsonb_array_elements(seed.source->'records') record,
                LATERAL jsonb_array_elements_text(record->'related_pidns') pidn
        ), anchors AS MATERIALIZED (
            SELECT parcel.* FROM staging.parcels parcel
            JOIN anchor_keys USING (pidn)
            WHERE parcel.valid_to IS NULL AND (SELECT available FROM permitted)
        ), neighbors AS MATERIALIZED (
            SELECT DISTINCT ON (other.pidn, anchor.pidn)
                other.pidn, other.propadr AS address, other.owner_full AS owner,
                anchor.pidn AS anchor_pidn,
                (other.owner_full = anchor.owner_full
                    AND btrim(COALESCE(anchor.owner_full, '')) <> '') AS same_recorded_name
            FROM anchors anchor
            JOIN staging.parcels other ON other.valid_to IS NULL
                AND other.pidn <> anchor.pidn
                AND other.geom && anchor.geom
                AND ST_Intersects(other.geom, anchor.geom)
            WHERE NOT EXISTS (SELECT 1 FROM anchors WHERE pidn = other.pidn)
            ORDER BY other.pidn, anchor.pidn
        ), neighbor_keys AS (
            SELECT pidn FROM neighbors GROUP BY pidn
            ORDER BY bool_or(same_recorded_name) DESC, pidn LIMIT neighbor_limit
        ), selected_keys AS (
            SELECT pidn FROM anchors UNION SELECT pidn FROM neighbor_keys
        ), selected_bundles AS MATERIALIZED (
            SELECT DISTINCT input.bundle_key
            FROM public.current_municipal_matter_scoped_inputs input
            WHERE input.bundle_key = requested_bundle
                OR input.related_pidns && ARRAY(SELECT pidn FROM selected_keys)
        ), bundles AS MATERIALIZED (
            SELECT current.source
            FROM selected_bundles selected
            CROSS JOIN LATERAL public.municipal_matter_source(selected.bundle_key) current
        ), properties AS MATERIALIZED (
            SELECT selected.pidn,
                CASE WHEN EXISTS (SELECT 1 FROM anchors WHERE pidn = selected.pidn)
                    THEN 'subject' ELSE 'adjoining' END AS relationship,
                public.property_explanation_source(
                    selected.pidn, open_data_key,
                    planning_radius_m, environmental_radius_m
                ) AS source
            FROM selected_keys selected
        ), availability AS (
            SELECT input.event_key, proceeding.valid_from AS source_observed_at
            FROM public.current_municipal_matter_scoped_inputs input
            JOIN selected_bundles USING (bundle_key)
            JOIN staging.public_proceedings proceeding ON proceeding.id = input.proceeding_id
        )
        SELECT jsonb_build_object(
            'seed_bundle', requested_bundle,
            'seed_scope', seed.source->'candidate_scope',
            'municipality', seed.source->'municipality',
            'settings', jsonb_build_object(
                'open_data_key', open_data_key,
                'planning_radius_m', planning_radius_m,
                'environmental_radius_m', environmental_radius_m,
                'neighbor_limit', neighbor_limit
            ),
            'municipal_bundles', COALESCE((SELECT jsonb_agg(source ORDER BY source->>'subject_key')
                FROM bundles), '[]'::jsonb),
            'property_bundles', COALESCE((SELECT jsonb_agg(jsonb_build_object(
                'pidn', pidn, 'relationship', relationship, 'source', source,
                'available_at', (SELECT valid_from FROM staging.parcels parcel
                    WHERE parcel.pidn = properties.pidn AND parcel.valid_to IS NULL)
                ) ORDER BY pidn) FROM properties), '[]'::jsonb),
            'relationships', COALESCE((SELECT jsonb_agg(jsonb_build_object(
                'pidn', neighbors.pidn, 'anchor_pidn', anchor_pidn,
                'relationship', 'adjoining', 'same_recorded_name', same_recorded_name
                ) ORDER BY neighbors.pidn, anchor_pidn)
                FROM neighbors JOIN neighbor_keys USING (pidn)), '[]'::jsonb),
            'record_availability', COALESCE((SELECT jsonb_object_agg(
                event_key, source_observed_at ORDER BY event_key
                ) FROM availability), '{}'::jsonb),
            'scope_limits', jsonb_build_object(
                'adjoining_parcels_found', (SELECT count(DISTINCT pidn) FROM neighbors),
                'adjoining_parcels_included', (SELECT count(*) FROM neighbor_keys),
                'parcel_context_available', (SELECT available FROM permitted)
            )
        ) FROM seed;
        $function$;
    """)


def downgrade() -> None:
    for table in CACHE_DEPENDENCIES:
        op.execute(f"DROP TRIGGER invalidate_emerging_cache ON {table}")
    op.execute("""
        DROP VIEW public.current_emerging_cases;
        DROP VIEW public.current_emerging_analyses;
        DROP FUNCTION public.emerging_scope_source(text, text, integer, integer, integer);
    """)
    # Preserve authored reviews and customer work on a downgrade. Removing these
    # populated tables/columns would turn a code rollback into a data deletion.
    op.execute("""
        DO $block$
        BEGIN
            IF EXISTS (SELECT 1 FROM meta.emerging_intelligence_publications)
                OR EXISTS (SELECT 1 FROM meta.intelligence_inference_history
                    WHERE output_kind IN ('emerging_analysis', 'emerging_replay'))
                OR EXISTS (SELECT 1 FROM public.watchspaces
                    WHERE intelligence_profile <> '{}'::jsonb
                        OR intelligence_work <> '[]'::jsonb)
            THEN
                RAISE EXCEPTION 'Emerging intelligence has retained reviews or workspace data; use a reviewed rollback';
            END IF;
        END;
        $block$;
        DROP TABLE meta.emerging_intelligence_publications;
        ALTER TABLE public.watchspaces
            DROP COLUMN intelligence_profile, DROP COLUMN intelligence_work;
        ALTER TABLE meta.intelligence_inference_history
            DROP CONSTRAINT intelligence_inference_history_output_kind_check;
        ALTER TABLE meta.intelligence_inference_history
            ADD CONSTRAINT intelligence_inference_history_output_kind_check CHECK (
                output_kind IN ('proceeding_extraction', 'entity_verification',
                    'signal_validation', 'parcel_brief', 'owner_brief',
                    'municipal_evidence', 'record_explanation'));
    """)
