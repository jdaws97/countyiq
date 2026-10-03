"""Index reviewed case candidates so reads validate only a bounded page."""

from alembic import op

revision = "086"
down_revision = "085"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE public.emerging_case_index (
            case_key text PRIMARY KEY,
            subject_key text NOT NULL,
            inference_id bigint NOT NULL
                REFERENCES meta.intelligence_inference_history(inference_id),
            created_at timestamptz NOT NULL,
            published boolean NOT NULL,
            family text NOT NULL,
            municipalities text[] NOT NULL,
            project_types text[] NOT NULL,
            pidns text[] NOT NULL,
            audiences text[] NOT NULL,
            services text[] NOT NULL,
            readiness text[] NOT NULL,
            search_text text NOT NULL,
            has_opportunities boolean NOT NULL,
            summary jsonb NOT NULL
        );
        COMMENT ON TABLE public.emerging_case_index IS
            'Rebuildable reviewed candidates, not a source-current evidence view. '
            'Serving must validate each selected inference against canonical sources.';
        CREATE INDEX emerging_case_index_subject
            ON public.emerging_case_index(subject_key);
        CREATE INDEX emerging_case_index_page
            ON public.emerging_case_index(created_at DESC, case_key)
            WHERE published;
        CREATE INDEX emerging_case_index_family_page
            ON public.emerging_case_index(family, created_at DESC, case_key)
            WHERE published;
        CREATE INDEX emerging_case_index_municipalities
            ON public.emerging_case_index USING gin(municipalities) WHERE published;
        CREATE INDEX emerging_case_index_project_types
            ON public.emerging_case_index USING gin(project_types) WHERE published;
        CREATE INDEX emerging_case_index_pidns
            ON public.emerging_case_index USING gin(pidns) WHERE published;
        CREATE INDEX emerging_case_index_commercial_filters
            ON public.emerging_case_index USING gin(audiences, services, readiness)
            WHERE published;
        CREATE INDEX emerging_case_index_search
            ON public.emerging_case_index USING gin(search_text gin_trgm_ops)
            WHERE published;

        CREATE FUNCTION public.emerging_opportunity_is_qualified(item jsonb)
        RETURNS boolean LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $function$
            SELECT COALESCE(
                item->>'readiness' IN ('qualify', 'act')
                AND jsonb_typeof(item->'commercial_basis') = 'object'
                AND NOT EXISTS (
                    SELECT 1 FROM unnest(ARRAY['need', 'timing', 'qualification_route']) key
                    WHERE jsonb_typeof(item->'commercial_basis'->key)
                            IS DISTINCT FROM 'object'
                        OR COALESCE(item->'commercial_basis'->key->>'source_id', '') = ''
                ), FALSE
            );
        $function$;

        CREATE FUNCTION public.emerging_opportunity_summary(item jsonb)
        RETURNS jsonb LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $function$
            SELECT jsonb_build_object(
                'audience', item->'audience', 'services', item->'services',
                'title', item->'title', 'rationale', item->'rationale',
                'readiness', item->'readiness',
                'commercial_basis', CASE
                    WHEN public.emerging_opportunity_is_qualified(item)
                    THEN jsonb_build_object(
                        'timing', item->'commercial_basis'->'timing'->>'statement'
                    ) ELSE NULL END
            );
        $function$;

        CREATE FUNCTION public.rebuild_emerging_case_index(requested_subject text)
        RETURNS void LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog AS $function$
        DECLARE
            retained record;
            is_published boolean;
        BEGIN
            -- Serialize projections of concurrent decisions for the same scope.
            PERFORM pg_advisory_xact_lock(hashtextextended(
                'emerging-case-index:' || requested_subject, 0
            ));
            SELECT history.* INTO retained
            FROM meta.intelligence_inference_history history
            WHERE history.subject_key = requested_subject
                AND history.output_kind = 'emerging_analysis'
                AND history.disposition = 'accepted'
            ORDER BY history.inference_id DESC LIMIT 1;

            DELETE FROM public.emerging_case_index WHERE subject_key = requested_subject;
            IF retained.inference_id IS NULL
                OR retained.payload->>'contract_version' IS DISTINCT FROM '1'
                OR retained.payload->'packet'->>'temporal_mode' IS DISTINCT FROM 'current'
            THEN
                RETURN;
            END IF;
            SELECT COALESCE((
                SELECT publication.action = 'publish'
                FROM meta.emerging_intelligence_publications publication
                WHERE publication.inference_id = retained.inference_id
                ORDER BY publication.publication_id DESC LIMIT 1
            ), FALSE) INTO is_published;

            INSERT INTO public.emerging_case_index
            SELECT
                'emerging-' || encode(sha256(convert_to(
                    requested_subject || '|' || (hypothesis->>'family'), 'UTF8'
                )), 'hex'),
                requested_subject, retained.inference_id, retained.created_at,
                is_published, hypothesis->>'family',
                ARRAY(SELECT lower(value) FROM jsonb_array_elements_text(
                    retained.payload->'packet'->'municipalities'
                )),
                ARRAY(SELECT value FROM jsonb_array_elements_text(
                    COALESCE(hypothesis->'project_types', '[]'::jsonb)
                )),
                ARRAY(SELECT property->>'pidn' FROM jsonb_array_elements(
                    retained.payload->'packet'->'properties'
                ) property),
                ARRAY(SELECT DISTINCT item->>'audience'
                    FROM jsonb_array_elements(hypothesis->'opportunities') item),
                ARRAY(SELECT DISTINCT service
                    FROM jsonb_array_elements(hypothesis->'opportunities') item
                    CROSS JOIN LATERAL jsonb_array_elements_text(item->'services') service),
                ARRAY(SELECT DISTINCT item->>'readiness'
                    FROM jsonb_array_elements(hypothesis->'opportunities') item),
                lower((hypothesis->>'title') || ' ' || (hypothesis->>'hypothesis')),
                EXISTS (
                    SELECT 1 FROM jsonb_array_elements(hypothesis->'opportunities') item
                    WHERE public.emerging_opportunity_is_qualified(item)
                ),
                jsonb_build_object(
                    'family', hypothesis->'family', 'title', hypothesis->'title',
                    'hypothesis', hypothesis->'hypothesis', 'status', hypothesis->'status',
                    'evidence_strength', hypothesis->'evidence_strength',
                    'stage', hypothesis->'stage',
                    'supporting_facts', CASE
                        WHEN jsonb_array_length(hypothesis->'supporting_facts') > 0
                        THEN jsonb_build_array(hypothesis->'supporting_facts'->0->>'statement')
                        ELSE '[]'::jsonb END,
                    'opportunities', COALESCE((
                        SELECT jsonb_agg(public.emerging_opportunity_summary(item) ORDER BY position)
                        FROM jsonb_array_elements(hypothesis->'opportunities')
                            WITH ORDINALITY possibility(item, position)
                        WHERE public.emerging_opportunity_is_qualified(item)
                    ), '[]'::jsonb),
                    'implications', COALESCE((
                        SELECT jsonb_agg(public.emerging_opportunity_summary(item) ORDER BY position)
                        FROM jsonb_array_elements(hypothesis->'opportunities')
                            WITH ORDINALITY possibility(item, position)
                        WHERE NOT public.emerging_opportunity_is_qualified(item)
                    ), '[]'::jsonb),
                    'project_types', COALESCE(hypothesis->'project_types', '[]'::jsonb),
                    'municipalities', retained.payload->'packet'->'municipalities',
                    'as_of', retained.payload->'packet'->'as_of'
                )
            FROM jsonb_array_elements(retained.payload->'analysis'->'hypotheses') hypothesis;
        END;
        $function$;
        REVOKE ALL ON FUNCTION public.rebuild_emerging_case_index(text) FROM PUBLIC;

        CREATE FUNCTION public.index_emerging_analysis()
        RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog AS $function$
        BEGIN
            PERFORM public.rebuild_emerging_case_index(NEW.subject_key);
            RETURN NULL;
        END;
        $function$;
        CREATE TRIGGER index_emerging_analysis
            AFTER INSERT ON meta.intelligence_inference_history
            FOR EACH ROW
            WHEN (NEW.output_kind = 'emerging_analysis' AND NEW.disposition = 'accepted')
            EXECUTE FUNCTION public.index_emerging_analysis();

        CREATE FUNCTION public.index_emerging_publication()
        RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog AS $function$
        BEGIN
            PERFORM public.rebuild_emerging_case_index(history.subject_key)
            FROM meta.intelligence_inference_history history
            WHERE history.inference_id = NEW.inference_id;
            RETURN NULL;
        END;
        $function$;
        CREATE TRIGGER index_emerging_publication
            AFTER INSERT ON meta.emerging_intelligence_publications
            FOR EACH ROW EXECUTE FUNCTION public.index_emerging_publication();

        SELECT public.rebuild_emerging_case_index(subject_key)
        FROM (
            SELECT DISTINCT subject_key FROM meta.intelligence_inference_history
            WHERE output_kind = 'emerging_analysis' AND disposition = 'accepted'
        ) subjects;
    """)


def downgrade() -> None:
    op.execute("""
        DROP TRIGGER index_emerging_publication ON meta.emerging_intelligence_publications;
        DROP TRIGGER index_emerging_analysis ON meta.intelligence_inference_history;
        DROP FUNCTION public.index_emerging_publication();
        DROP FUNCTION public.index_emerging_analysis();
        DROP FUNCTION public.rebuild_emerging_case_index(text);
        DROP FUNCTION public.emerging_opportunity_summary(jsonb);
        DROP FUNCTION public.emerging_opportunity_is_qualified(jsonb);
        DROP TABLE public.emerging_case_index;
    """)
