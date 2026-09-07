"""Serve concise explanations only while their complete source bundle is current."""

from alembic import op

revision = "069"
down_revision = "068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE meta.intelligence_inference_history
            DROP CONSTRAINT intelligence_inference_history_output_kind_check;
        ALTER TABLE meta.intelligence_inference_history
            ADD CONSTRAINT intelligence_inference_history_output_kind_check CHECK (
                output_kind IN ('proceeding_extraction', 'entity_verification',
                    'signal_validation', 'parcel_brief', 'owner_brief',
                    'municipal_evidence', 'record_explanation'));

        CREATE FUNCTION public.municipal_explanation_source(
            evidence public.current_municipal_evidence
        ) RETURNS jsonb LANGUAGE sql STABLE STRICT AS $function$
            SELECT jsonb_build_object(
                'kind', 'municipal', 'subject_key', evidence.event_key,
                'title', evidence.card->>'title',
                'meeting_date', evidence.meeting_date::text,
                'document_kind', COALESCE(evidence.payload->>'document_kind', 'record'),
                'body_name', evidence.body_name,
                'sources', (
                    SELECT jsonb_agg(jsonb_build_object(
                        'id', 'P' || position::text,
                        'label', evidence.body_name || ' · ' || evidence.meeting_date::text,
                        'text', passage->>'text', 'url', evidence.document_url,
                        'start', passage->'start', 'end', passage->'end',
                        'source_text_sha256', evidence.payload->>'source_text_sha256'
                    ) ORDER BY position)
                    FROM jsonb_array_elements(evidence.card->'passages')
                        WITH ORDINALITY spans(passage, position)
                )
            )
        $function$;

        CREATE VIEW public.current_municipal_intelligence AS
        SELECT evidence.*, source.bundle AS explanation_source,
            explanation.inference_id AS explanation_inference_id,
            explanation.payload->'explanation' AS explanation,
            explanation.created_at AS explanation_generated_at,
            explanation.requested_model AS explanation_model
        FROM public.current_municipal_evidence evidence
        CROSS JOIN LATERAL (
            SELECT public.municipal_explanation_source(evidence) AS bundle
        ) source
        LEFT JOIN LATERAL (
            SELECT history.* FROM meta.intelligence_inference_history history
            WHERE history.subject_key = evidence.event_key
              AND history.output_kind = 'record_explanation'
              AND history.disposition = 'accepted'
              AND history.payload->'source' = source.bundle
            ORDER BY history.inference_id DESC LIMIT 1
        ) explanation ON TRUE;

        CREATE FUNCTION public.property_explanation_source(
            parcel_id text, open_data_key text, planning_radius_m integer,
            environmental_radius_m integer
        ) RETURNS jsonb LANGUAGE sql STABLE AS $function$
        WITH parcel AS MATERIALIZED (
            SELECT p.* FROM staging.parcels p
            WHERE p.pidn = parcel_id AND p.valid_to IS NULL
              AND planning_radius_m BETWEEN 1 AND 2000
              AND environmental_radius_m BETWEEN 1 AND 2000
              AND EXISTS (
                  SELECT 1 FROM meta.source_rights policy
                  WHERE policy.source_key = open_data_key
                    AND policy.rights_status <> 'paused'
                    AND policy.derived_product_allowed
                    AND policy.review_due_on >= CURRENT_DATE
              )
        ), facts AS (
            SELECT 'parcel' AS id, 'Current county parcel record' AS label,
                p.source_url AS url, jsonb_build_object(
                    'pidn', p.pidn, 'address', p.propadr, 'recorded_owner', p.owner_full,
                    'previous_owner', p.prev_owner, 'acres', p.acres, 'class', p.class,
                    'assessment', p.aprtotal, 'last_recorded_sale_date', p.saledt,
                    'last_recorded_sale_price', p.price
                ) AS facts FROM parcel p
            UNION ALL
            SELECT 'zoning', 'Current mapped zoning', z.source_url,
                to_jsonb(z) - ARRAY['geom', 'valid_to', 'valid_from']
            FROM parcel p CROSS JOIN LATERAL public.parcel_center_zoning(p.geom) z
            UNION ALL
            SELECT 'future_landuse', 'Future land-use policy', future.source_url,
                to_jsonb(future) - ARRAY['geom', 'valid_to', 'valid_from']
            FROM parcel p CROSS JOIN LATERAL (
                SELECT f.* FROM staging.future_landuse f
                WHERE f.valid_to IS NULL AND ST_Intersects(f.geom, ST_Centroid(p.geom))
                ORDER BY f.adopt_date DESC NULLS LAST, f.globalid LIMIT 1
            ) future
            UNION ALL
            SELECT 'soils', 'Mapped soils screening', min(s.source_url),
                jsonb_build_object(
                    'mapped_coverage_pct', round(max(s.mapped_coverage_pct), 1),
                    'very_limited_septic_coverage_pct', round(max(s.very_limited_coverage_pct), 1),
                    'units', jsonb_agg(jsonb_build_object(
                        'name', s.map_unit_name, 'coverage_pct', round(s.coverage_pct, 1),
                        'slope_low_pct', s.slope_low, 'slope_high_pct', s.slope_high,
                        'septic_rating', s.septic_rating,
                        'source_record_ids', s.source_record_ids
                    ) ORDER BY s.coverage_pct DESC, s.map_unit_key)
                )
            FROM parcel p CROSS JOIN LATERAL public.parcel_soil_units(p.geom) s
            HAVING COUNT(*) > 0
            UNION ALL
            SELECT 'adjacent_' || adjacent.pidn, 'Touching parcel with the same recorded owner',
                adjacent.source_url, jsonb_build_object(
                    'pidn', adjacent.pidn, 'address', adjacent.propadr,
                    'recorded_owner', adjacent.owner_full, 'acres', adjacent.acres,
                    'last_recorded_sale_date', adjacent.saledt,
                    'last_recorded_sale_price', adjacent.price,
                    'association', 'Exact recorded owner name and touching mapped boundary'
                )
            FROM parcel p CROSS JOIN LATERAL (
                SELECT other.* FROM staging.parcels other
                WHERE other.valid_to IS NULL AND other.pidn <> p.pidn
                  AND other.owner_full = p.owner_full AND btrim(p.owner_full) <> ''
                  AND other.geom && p.geom AND ST_Touches(other.geom, p.geom)
                ORDER BY other.pidn LIMIT 8
            ) adjacent
            UNION ALL
            SELECT 'plan_' || plan.sequ_num, 'Nearby planning inventory point', plan.source_url,
                jsonb_build_object(
                    'sequence_number', plan.sequ_num, 'plan_title', plan.plan_title,
                    'received_date', plan.date_rcvd, 'distance_m', plan.distance_m,
                    'plan_types', jsonb_build_object(
                        'final_plan', plan.pt_final, 'preliminary_plan', plan.pt_prelim,
                        'subdivision', plan.pt_subdiv, 'land_development', plan.pt_land_dev),
                    'total_acres', plan.total_acres, 'proposed_lots', plan.prop_lots,
                    'proposed_dwelling_units', plan.prop_du,
                    'proposed_new_building_sqft', plan.prop_new_bldg_sqft,
                    'engineer', plan.engineer,
                    'meaning', 'Plan types classify submitted documents; final_plan does not establish approval or completion. Proximity does not establish project boundaries.'
                )
            FROM parcel p CROSS JOIN LATERAL (
                SELECT subdivision.*,
                    round(ST_Distance(subdivision.geom::geography, p.geom::geography)) AS distance_m
                FROM staging.planning_subdivisions subdivision
                WHERE subdivision.valid_to IS NULL
                  AND ST_DWithin(subdivision.geom::geography, p.geom::geography, planning_radius_m)
                ORDER BY subdivision.date_rcvd DESC NULLS LAST,
                    ST_Distance(subdivision.geom::geography, p.geom::geography), subdivision.sequ_num
                LIMIT 3
            ) plan
            UNION ALL
            SELECT 'easement_' || e.ease_id, 'Recorded conservation easement inventory', e.source_url,
                to_jsonb(e) - ARRAY['geom', 'valid_to', 'valid_from']
            FROM parcel p JOIN staging.conservation_easements e ON e.pidn = p.pidn
            WHERE e.valid_to IS NULL
            UNION ALL
            SELECT 'ag_security_' || a.resolution, 'Agricultural security area inventory', a.source_url,
                to_jsonb(a) - ARRAY['geom', 'valid_to', 'valid_from']
            FROM parcel p JOIN staging.ag_security a ON a.pidn = p.pidn
            WHERE a.valid_to IS NULL
            UNION ALL
            SELECT 'flood', 'Mapped special flood hazard overlap', min(f.source_url),
                jsonb_build_object(
                    'zones', jsonb_agg(DISTINCT f.fld_zone),
                    'source_record_ids', jsonb_agg(DISTINCT f.fld_ar_id),
                    'coverage_pct', round((100 * ST_Area(ST_Transform(
                        ST_UnaryUnion(ST_Collect(ST_Intersection(ST_MakeValid(f.geom), ST_MakeValid(p.geom)))), 32617))
                        / NULLIF(ST_Area(ST_Transform(ST_MakeValid(p.geom), 32617)), 0))::numeric, 1),
                    'meaning', 'Mapped screening overlap, not a site-specific flood determination'
                )
            FROM parcel p JOIN staging.flood_zones f
                ON f.valid_to IS NULL AND f.sfha_tf = 'T'
                AND f.geom && p.geom AND ST_Intersects(f.geom, p.geom)
            WHERE EXISTS (
                SELECT 1 FROM meta.source_rights policy
                WHERE policy.source_key = 'fema_nfhl' AND policy.rights_status <> 'paused'
                  AND policy.derived_product_allowed AND policy.review_due_on >= CURRENT_DATE
            )
            GROUP BY p.geom
            UNION ALL
            SELECT 'dep_' || md5(site.source_layer || ':' || site.source_id),
                'Nearby PA DEP inventory record', COALESCE(site.detail_url, site.source_url),
                jsonb_build_object(
                    'source_layer', site.source_layer, 'source_id', site.source_id,
                    'site_name', site.site_name, 'facility_type', site.facility_type,
                    'facility_status', site.facility_status, 'address', site.address,
                    'distance_m', site.distance_m,
                    'meaning', 'Proximity only; this does not establish contamination or impact on the subject parcel'
                )
            FROM parcel p CROSS JOIN LATERAL (
                SELECT d.*, round(ST_Distance(d.geom::geography, p.geom::geography)) AS distance_m
                FROM staging.environmental_diligence_sites d
                WHERE d.valid_to IS NULL
                  AND ST_DWithin(d.geom::geography, p.geom::geography, environmental_radius_m)
                  AND EXISTS (
                      SELECT 1 FROM meta.source_rights policy
                      WHERE policy.source_key = 'pa_dep_open_data' AND policy.rights_status <> 'paused'
                        AND policy.derived_product_allowed AND policy.review_due_on >= CURRENT_DATE
                  )
                ORDER BY ST_Distance(d.geom::geography, p.geom::geography), d.source_layer, d.source_id
                LIMIT 2
            ) site
        ), sources AS (
            SELECT jsonb_build_object('id', id, 'label', label, 'url', url, 'facts', facts) AS source
            FROM facts
            UNION ALL
            SELECT jsonb_build_object(
                'id', 'M' || record.source_position::text,
                'label', record.body_name || ' · ' || record.meeting_date::text,
                'url', record.document_url, 'document_kind', record.payload->>'document_kind',
                'meeting_date', record.meeting_date::text,
                'text', (SELECT string_agg(span->>'text', E'\n[…]\n' ORDER BY position)
                    FROM jsonb_array_elements(record.card->'passages') WITH ORDINALITY passage(span, position)),
                'source_text_sha256', record.payload->>'source_text_sha256'
            )
            FROM (
                SELECT evidence.*, row_number() OVER (
                    ORDER BY evidence.meeting_date DESC, evidence.proceeding_id DESC, evidence.card_position
                ) AS source_position
                FROM public.current_municipal_evidence evidence
                WHERE parcel_id = ANY(evidence.related_pidns) AND EXISTS (SELECT 1 FROM parcel)
                ORDER BY evidence.meeting_date DESC, evidence.proceeding_id DESC, evidence.card_position
                LIMIT 6
            ) record
        )
        SELECT jsonb_build_object(
            'kind', 'property', 'subject_key', 'parcel:' || parcel_id,
            'open_data_key', open_data_key, 'planning_radius_m', planning_radius_m,
            'environmental_radius_m', environmental_radius_m,
            'sources', (SELECT jsonb_agg(source ORDER BY source->>'id') FROM sources)
        ) FROM parcel
        $function$;
    """)
    # Keep other live-source and watch guards unchanged. A projection with an
    # older summary must retract before the event producer runs again.
    op.execute("""
        DO $block$
        DECLARE definition text;
        BEGIN
            SELECT pg_get_viewdef('public.current_intelligence_events'::regclass, true)
                INTO definition;
            definition := replace(definition, 'current_municipal_evidence current',
                'current_municipal_intelligence current');
            definition := replace(definition,
                'current.related_entities = event.related_entities',
                'current.related_entities = event.related_entities AND '
                || '(event.source_evidence->0->''details''->>''explanation_inference_id'') '
                || 'IS NOT DISTINCT FROM current.explanation_inference_id::text');
            EXECUTE 'CREATE OR REPLACE VIEW public.current_intelligence_events AS ' || definition;
        END
        $block$;
    """)


def downgrade() -> None:
    raise RuntimeError(
        "Review retained explanations and event projections before reverting"
    )
