"""Index immutable municipal evidence and reuse transactionally current feed pages."""

from alembic import op

revision = "078"
down_revision = "077"
branch_labels = None
depends_on = None


FEED_DEPENDENCIES = (
    "public.intelligence_events",
    "public.municipal_evidence_links",
    "public.municipal_read_index",
    "public.municipal_card_index",
    "public.owners",
    "staging.public_proceedings",
    "staging.proceeding_extractions",
    "staging.parcels",
    "meta.intelligence_inference_history",
    "meta.municipality_source_rights",
    "meta.source_rights",
)


def upgrade() -> None:
    # History is append-only. Compile its canonical card source once, in the
    # writer's transaction, while all rights and source-current checks stay live.
    _create_evidence_index()
    _create_indexed_input_views()
    _create_account_view()
    _create_serving_views()
    op.execute("""
        CREATE INDEX idx_intelligence_history_accepted_subject
        ON meta.intelligence_inference_history
            (subject_key, output_kind, inference_id DESC)
        WHERE disposition = 'accepted';

        CREATE TABLE meta.feed_cache_revision (
            singleton boolean PRIMARY KEY DEFAULT TRUE CHECK (singleton),
            generation uuid NOT NULL DEFAULT gen_random_uuid(),
            revision bigint NOT NULL DEFAULT 1
        );
        INSERT INTO meta.feed_cache_revision DEFAULT VALUES;

        CREATE FUNCTION meta.invalidate_feed_cache()
        RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog AS $function$
        BEGIN
            UPDATE meta.feed_cache_revision SET revision = revision + 1;
            RETURN NULL;
        END;
        $function$;
    """)
    for table in FEED_DEPENDENCIES:
        op.execute(f"""
            CREATE TRIGGER invalidate_feed_cache
            AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE ON {table}
            FOR EACH STATEMENT EXECUTE FUNCTION meta.invalidate_feed_cache();
        """)


def _create_evidence_index() -> None:
    op.execute(r"""
        CREATE TABLE public.municipal_read_index (
            inference_id bigint PRIMARY KEY REFERENCES meta.intelligence_inference_history,
            record_snapshot jsonb,
            source_text_sha256 text,
            document_kind text NOT NULL,
            cards_present boolean NOT NULL
        );

        CREATE TABLE public.municipal_card_index (
            inference_id bigint NOT NULL REFERENCES public.municipal_read_index,
            card_position bigint NOT NULL,
            card_id text,
            event_key text,
            title text,
            passage_count integer NOT NULL,
            explanation_source jsonb NOT NULL,
            source_fingerprint text NOT NULL,
            PRIMARY KEY (inference_id, card_position)
        );
        CREATE INDEX idx_municipal_card_index_event
            ON public.municipal_card_index(event_key, inference_id);

        CREATE FUNCTION public.compile_municipal_card_index(subject_key text, payload jsonb)
        RETURNS TABLE (
            card_position bigint,
            card_id text,
            event_key text,
            title text,
            passage_count integer,
            explanation_source jsonb,
            source_fingerprint text
        )
        LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $function$
            WITH document AS MATERIALIZED (
                SELECT payload->'record_snapshot' AS snapshot,
                    payload->>'source_text_sha256' AS source_text_sha256,
                    COALESCE(payload->>'document_kind', 'record') AS document_kind,
                    'municipal:' || split_part(subject_key, ':', 2) || ':' ||
                        left(encode(sha256(convert_to(
                            (payload->'record_snapshot')::text ||
                            COALESCE(payload->>'source_text_sha256', ''), 'UTF8'
                        )), 'hex'), 20) AS event_prefix
            ), cards AS (
                SELECT document.*, selected.card, selected.position,
                    document.event_prefix || ':' || (selected.card->>'id') AS event_key,
                    CASE WHEN jsonb_typeof(selected.card->'passages') = 'array'
                        THEN selected.card->'passages' ELSE '[]'::jsonb END AS passages
                FROM document
                CROSS JOIN LATERAL jsonb_array_elements(
                    CASE WHEN jsonb_typeof(payload->'cards') = 'array'
                        THEN payload->'cards' ELSE '[]'::jsonb END
                ) WITH ORDINALITY selected(card, position)
            ), sources AS MATERIALIZED (
                SELECT cards.position, cards.card->>'id' AS card_id, cards.event_key,
                    cards.card->>'title' AS title,
                    jsonb_array_length(cards.passages) AS passage_count,
                    jsonb_build_object(
                        'kind', 'municipal', 'subject_key', cards.event_key,
                        'title', cards.card->>'title',
                        'meeting_date', cards.snapshot->>'meeting_date',
                        'document_kind', cards.document_kind,
                        'body_name', cards.snapshot->>'body_name',
                        'sources', (
                            SELECT jsonb_agg(jsonb_build_object(
                                'id', 'P' || passage_position::text,
                                'label', (cards.snapshot->>'body_name') || ' · ' ||
                                    (cards.snapshot->>'meeting_date'),
                                'text', passage->>'text',
                                'url', cards.snapshot->>'document_url',
                                'start', passage->'start', 'end', passage->'end',
                                'source_text_sha256', cards.source_text_sha256
                            ) ORDER BY passage_position)
                            FROM jsonb_array_elements(cards.passages)
                                WITH ORDINALITY spans(passage, passage_position)
                        )
                    ) AS explanation_source
                FROM cards
            )
            SELECT sources.position, sources.card_id, sources.event_key, sources.title,
                sources.passage_count, sources.explanation_source,
                encode(sha256(convert_to(sources.explanation_source::text, 'UTF8')), 'hex')
            FROM sources;
        $function$;

        INSERT INTO public.municipal_read_index
        SELECT inference_id, payload->'record_snapshot', payload->>'source_text_sha256',
            COALESCE(payload->>'document_kind', 'record'),
            COALESCE(jsonb_typeof(payload->'cards') = 'array', FALSE)
        FROM meta.intelligence_inference_history
        WHERE output_kind = 'municipal_evidence' AND disposition = 'accepted';

        INSERT INTO public.municipal_card_index
        SELECT history.inference_id, compiled.*
        FROM meta.intelligence_inference_history history
        CROSS JOIN LATERAL public.compile_municipal_card_index(
            history.subject_key, history.payload
        ) compiled
        WHERE history.output_kind = 'municipal_evidence' AND history.disposition = 'accepted';

        CREATE FUNCTION public.index_accepted_municipal_read()
        RETURNS trigger LANGUAGE plpgsql AS $function$
        BEGIN
            INSERT INTO public.municipal_read_index
            VALUES (
                NEW.inference_id, NEW.payload->'record_snapshot',
                NEW.payload->>'source_text_sha256',
                COALESCE(NEW.payload->>'document_kind', 'record'),
                COALESCE(jsonb_typeof(NEW.payload->'cards') = 'array', FALSE)
            );
            INSERT INTO public.municipal_card_index
            SELECT NEW.inference_id, compiled.*
            FROM public.compile_municipal_card_index(NEW.subject_key, NEW.payload) compiled;
            RETURN NULL;
        END;
        $function$;

        CREATE TRIGGER index_accepted_municipal_read
        AFTER INSERT ON meta.intelligence_inference_history
        FOR EACH ROW
        WHEN (NEW.output_kind = 'municipal_evidence' AND NEW.disposition = 'accepted')
        EXECUTE FUNCTION public.index_accepted_municipal_read();

        ANALYZE public.municipal_read_index;
        ANALYZE public.municipal_card_index;
    """)


def _create_indexed_input_views() -> None:
    op.execute(r"""
        CREATE OR REPLACE VIEW public.current_municipal_reads AS
        SELECT pp.id AS proceeding_id, pp.body_name, pp.meeting_date,
               pp.proceeding_type, pp.document_url, pp.content_hash,
               pp.valid_from AS source_observed_at,
               policy.municipality_name AS municipality,
               selected.inference_id, selected.created_at AS reviewed_at,
               selected.payload
        FROM staging.public_proceedings pp
        JOIN meta.municipality_source_rights policy ON policy.body_name = pp.body_name
        CROSS JOIN LATERAL (
            SELECT inference_id, created_at, payload
            FROM meta.intelligence_inference_history history
            WHERE history.subject_key = 'proceeding:' || pp.id::text
              AND history.pass_number = 0
              AND history.output_kind = 'municipal_evidence'
              AND history.disposition = 'accepted'
            ORDER BY history.inference_id DESC
            LIMIT 1
        ) selected
        JOIN public.municipal_read_index indexed ON indexed.inference_id = selected.inference_id
        WHERE pp.valid_to IS NULL
          AND pp.metadata_quality->>'status' = 'ready'
          AND pp.meeting_date <= CURRENT_DATE
          AND policy.rights_status <> 'paused'
          AND policy.derived_product_allowed
          AND policy.review_due_on >= CURRENT_DATE
          AND EXISTS (
              SELECT 1 FROM meta.source_rights global_policy
              WHERE global_policy.source_key = 'public_proceedings'
                AND global_policy.rights_status <> 'paused'
                AND global_policy.derived_product_allowed
                AND global_policy.review_due_on >= CURRENT_DATE
          )
          AND indexed.record_snapshot->>'content_hash'
              IS NOT DISTINCT FROM pp.content_hash
          AND indexed.record_snapshot->>'raw_text_sha256'
              = encode(sha256(convert_to(COALESCE(pp.raw_text, ''), 'UTF8')), 'hex')
          AND indexed.record_snapshot->>'body_name' = pp.body_name
          AND indexed.record_snapshot->>'meeting_date' = pp.meeting_date::text
          AND indexed.record_snapshot->>'proceeding_type' = pp.proceeding_type
          AND indexed.record_snapshot->>'document_url' = pp.document_url
          AND indexed.cards_present;


        CREATE VIEW public.current_municipal_matter_inputs AS
        SELECT read.proceeding_id, read.body_name, read.meeting_date,
            read.document_url, read.municipality, read.inference_id,
            indexed.card_position, indexed.card_id, indexed.event_key,
            indexed.title, indexed.passage_count, indexed.source_fingerprint,
            source.document_kind,
            COALESCE(properties.matches, '[]'::jsonb) AS matched_properties,
            COALESCE(properties.pidns, ARRAY[]::text[]) AS related_pidns,
            COALESCE(properties.owners, ARRAY[]::text[]) AS related_entities
        FROM public.current_municipal_reads read
        JOIN public.municipal_read_index source USING (inference_id)
        JOIN public.municipal_card_index indexed USING (inference_id)
        LEFT JOIN LATERAL (
            SELECT jsonb_agg(jsonb_build_object(
                       'pidn', p.pidn, 'address', p.propadr,
                       'match_method', link.match_method) ORDER BY p.pidn) AS matches,
                   array_agg(DISTINCT p.pidn ORDER BY p.pidn)::text[] AS pidns,
                   array_agg(DISTINCT p.owner_full ORDER BY p.owner_full)
                       FILTER (WHERE p.owner_full IS NOT NULL)::text[] AS owners
            FROM public.municipal_evidence_links link
            JOIN staging.parcels p ON p.pidn = link.pidn AND p.valid_to IS NULL
            WHERE link.inference_id = read.inference_id
              AND link.card_id = indexed.card_id
              AND p.municipality = read.municipality
              AND link.municipality = p.municipality
              AND (link.match_method = 'pidn' OR (
                  p.propadr !~* '\m(APT|APARTMENT|UNIT|SUITE|STE|BLDG|BUILDING|FL|FLOOR|REAR)\M|#[[:space:]]*[A-Z0-9]'
                  AND
                  public.normalize_street_address(p.propadr) = link.normalized_address
                  AND NOT EXISTS (
                      SELECT 1 FROM staging.parcels competing
                      WHERE competing.valid_to IS NULL
                        AND competing.municipality = p.municipality
                        AND competing.pidn <> p.pidn
                        AND public.normalize_street_address(competing.propadr)
                            = link.normalized_address
                  )
              ))
        ) properties ON TRUE;

        CREATE OR REPLACE VIEW public.current_municipal_matter_scopes AS
        WITH evidence AS MATERIALIZED (
            SELECT current.event_key, current.proceeding_id, current.card_position,
                current.meeting_date, current.municipality, current.related_pidns,
                current.matched_properties,
                public.municipal_case_reference(current.title) AS case_reference,
                CASE WHEN current.title ~*
                    '^[0-9]+[[:space:]]+.+[[:space:]](st|street|rd|road|dr|drive|ave|avenue|ln|lane)[.]?$'
                    THEN public.normalize_street_address(current.title)
                END AS title_address
            FROM public.current_municipal_matter_inputs current
        ), known_cases AS (
            SELECT municipality, case_reference, min(related_pidns[1]) AS pidn
            FROM evidence
            WHERE case_reference IS NOT NULL AND cardinality(related_pidns) = 1
            GROUP BY municipality, case_reference
            HAVING count(DISTINCT related_pidns[1]) = 1
        ), known_addresses AS (
            SELECT municipality,
                public.normalize_street_address(matched->>'address') AS address,
                min(matched->>'pidn') AS pidn
            FROM evidence, LATERAL jsonb_array_elements(matched_properties) matched
            GROUP BY municipality, public.normalize_street_address(matched->>'address')
            HAVING count(DISTINCT matched->>'pidn') = 1
        ), scoped AS (
            SELECT evidence.*,
                CASE
                    WHEN cardinality(related_pidns) = 1 THEN 'property:' || related_pidns[1]
                    WHEN known_cases.pidn IS NOT NULL THEN 'property:' || known_cases.pidn
                    WHEN known_addresses.pidn IS NOT NULL THEN 'property:' || known_addresses.pidn
                    WHEN evidence.case_reference IS NOT NULL THEN 'case:' || evidence.case_reference
                    WHEN title_address IS NOT NULL THEN 'address:' || title_address
                    ELSE 'selection:' || event_key
                END AS candidate_scope
            FROM evidence
            LEFT JOIN known_cases USING (municipality, case_reference)
            LEFT JOIN known_addresses ON known_addresses.municipality = evidence.municipality
                AND known_addresses.address = evidence.title_address
        )
        SELECT scoped.event_key, scoped.proceeding_id, scoped.card_position,
            scoped.candidate_scope,
            'municipal-bundle:' || encode(sha256(convert_to(
                municipality || '|' || candidate_scope, 'UTF8')), 'hex') AS bundle_key,
            row_number() OVER (PARTITION BY municipality, candidate_scope
                ORDER BY meeting_date, proceeding_id, card_position) AS record_position
        FROM scoped;

        CREATE VIEW public.current_municipal_record_versions AS
        SELECT current.event_key, current.related_pidns, current.related_entities,
            explanation.inference_id AS explanation_inference_id
        FROM public.current_municipal_matter_inputs current
        JOIN public.municipal_card_index indexed
            USING (inference_id, card_position)
        LEFT JOIN LATERAL (
            SELECT history.inference_id
            FROM meta.intelligence_inference_history history
            WHERE history.subject_key = current.event_key
                AND history.output_kind = 'record_explanation'
                AND history.disposition = 'accepted'
                AND history.payload->'source' = indexed.explanation_source
            ORDER BY history.inference_id DESC LIMIT 1
        ) explanation ON TRUE;
    """)


def _create_account_view() -> None:
    op.execute(r"""
        CREATE OR REPLACE VIEW public.current_municipal_matter_accounts AS
        WITH all_scopes AS MATERIALIZED (
            SELECT * FROM public.current_municipal_matter_scopes
        ), scopes AS MATERIALIZED (
            SELECT * FROM all_scopes
            WHERE bundle_key IN (
                SELECT DISTINCT subject_key FROM meta.intelligence_inference_history
                WHERE output_kind = 'record_explanation'
                    AND disposition = 'accepted'
                    AND jsonb_typeof(payload->'matters') = 'array'
            )
        ), candidates AS MATERIALIZED (
            SELECT current.*, scopes.bundle_key, scopes.record_position,
                jsonb_build_object(
                    'key', current.event_key, 'title', current.title,
                    'body_name', current.body_name,
                    'meeting_date', current.meeting_date::text,
                    'document_kind', current.document_kind,
                    'related_pidns', to_jsonb(current.related_pidns),
                    'source_fingerprint', current.source_fingerprint,
                    'source_ids', (
                        SELECT jsonb_agg(
                            'R' || scopes.record_position::text || 'P' || position::text
                            ORDER BY position
                        )
                        FROM generate_series(1, current.passage_count) position
                    )
                ) AS source_record
            FROM scopes
            JOIN public.current_municipal_matter_inputs current
                USING (event_key, proceeding_id, card_position)
        ), snapshots AS (
            SELECT bundle_key, jsonb_agg(source_record ORDER BY record_position) AS records
            FROM candidates GROUP BY bundle_key
        ), accepted AS MATERIALIZED (
            SELECT current.bundle_key, history.*
            FROM snapshots current
            CROSS JOIN LATERAL (
                SELECT accepted.* FROM meta.intelligence_inference_history accepted
                WHERE accepted.subject_key = current.bundle_key
                    AND accepted.output_kind = 'record_explanation'
                    AND accepted.disposition = 'accepted'
                    AND accepted.payload->'source'->'records' = current.records
                    AND jsonb_typeof(accepted.payload->'matters') = 'array'
                ORDER BY accepted.inference_id DESC LIMIT 1
            ) history
        ), matters AS MATERIALIZED (
            SELECT history.bundle_key, history.inference_id, history.created_at,
                history.requested_model, history.payload->'source' AS source,
                item.matter, item.position AS matter_position
            FROM accepted history
            CROSS JOIN LATERAL jsonb_array_elements(history.payload->'matters')
                WITH ORDINALITY item(matter, position)
        ), members AS (
            SELECT matter.inference_id, matter.matter_position,
                max(current.meeting_date) AS meeting_date,
                min(current.municipality) AS municipality,
                jsonb_agg(to_jsonb(current.related_pidns)) AS pidn_groups,
                jsonb_agg(to_jsonb(current.related_entities)) AS entity_groups
            FROM matters matter
            CROSS JOIN LATERAL jsonb_array_elements_text(matter.matter->'record_keys')
                member(record_key)
            JOIN candidates current ON current.event_key = member.record_key
                AND current.bundle_key = matter.bundle_key
            GROUP BY matter.inference_id, matter.matter_position
        ), evidence AS MATERIALIZED (
            SELECT current.* FROM public.current_municipal_evidence current
            WHERE proceeding_id IN (SELECT proceeding_id FROM candidates)
        ), details AS (
            SELECT matter.inference_id, matter.matter_position,
                max(evidence.observed_at) AS observed_at,
                jsonb_agg(jsonb_build_object(
                    'event_key', evidence.event_key, 'body_name', evidence.body_name,
                    'meeting_date', evidence.meeting_date::text, 'card', evidence.card,
                    'payload', evidence.payload, 'document_url', evidence.document_url
                ) ORDER BY evidence.meeting_date, evidence.proceeding_id,
                    evidence.card_position) AS records
            FROM matters matter
            CROSS JOIN LATERAL jsonb_array_elements_text(matter.matter->'record_keys')
                member(record_key)
            JOIN candidates current ON current.event_key = member.record_key
                AND current.bundle_key = matter.bundle_key
            JOIN evidence ON evidence.event_key = current.event_key
                AND evidence.proceeding_id = current.proceeding_id
                AND evidence.card_position = current.card_position
            GROUP BY matter.inference_id, matter.matter_position
        )
        SELECT matter.matter->>'key' AS event_key, matter.bundle_key,
            matter.source, matter.matter->'account' AS explanation,
            matter.matter->'record_keys' AS record_keys,
            matter.inference_id AS explanation_inference_id,
            matter.created_at AS explanation_generated_at,
            matter.requested_model AS explanation_model,
            members.meeting_date, details.observed_at, members.municipality,
            ARRAY(
                SELECT DISTINCT pidn
                FROM jsonb_array_elements(members.pidn_groups) grouped(values),
                    LATERAL jsonb_array_elements_text(grouped.values) linked(pidn)
                ORDER BY pidn
            ) AS related_pidns,
            ARRAY(
                SELECT DISTINCT owner
                FROM jsonb_array_elements(members.entity_groups) grouped(values),
                    LATERAL jsonb_array_elements_text(grouped.values) linked(owner)
                ORDER BY owner
            ) AS related_entities,
            details.records
        FROM matters matter
        JOIN members USING (inference_id, matter_position)
        LEFT JOIN details USING (inference_id, matter_position);
    """)


def _create_serving_views() -> None:
    op.execute(r"""
        CREATE OR REPLACE VIEW public.current_intelligence_events AS
        WITH municipal AS MATERIALIZED (
            SELECT event_key, related_pidns, related_entities, explanation_inference_id
            FROM public.current_municipal_record_versions
            WHERE EXISTS (
                SELECT 1 FROM public.intelligence_events WHERE source_kind = 'municipal_evidence'
            )
        ), matters AS MATERIALIZED (
            SELECT event_key, related_pidns, related_entities, explanation_inference_id,
                record_keys
            FROM public.current_municipal_matter_accounts
            WHERE EXISTS (
                SELECT 1 FROM public.intelligence_events WHERE source_kind = 'municipal_matter'
            )
        )
        SELECT event.*,
            (event.source_evidence->0->'details'->>'discovery_eligible' = 'true'
                AND event.source_evidence->0->'details'->>'explanation_inference_id' IS NOT NULL
                AND NOT EXISTS (
                    SELECT 1 FROM matters covered WHERE covered.record_keys ? event.event_key
                )
            ) AS activity_eligible
        FROM municipal
        JOIN public.intelligence_events event ON event.event_key = municipal.event_key
        WHERE event.source_kind = 'municipal_evidence'
            AND municipal.related_pidns = event.related_pidns
            AND municipal.related_entities = event.related_entities
            AND municipal.explanation_inference_id::text IS NOT DISTINCT FROM
                event.source_evidence->0->'details'->>'explanation_inference_id'
        UNION ALL
        SELECT event.*,
            (event.source_evidence->0->'details'->>'discovery_eligible' = 'true'
                AND event.source_evidence->0->'details'->>'explanation_inference_id' IS NOT NULL
            ) AS activity_eligible
        FROM matters
        JOIN public.intelligence_events event ON event.event_key = matters.event_key
        WHERE event.source_kind = 'municipal_matter'
            AND matters.related_pidns = event.related_pidns
            AND matters.related_entities = event.related_entities
            AND matters.explanation_inference_id::text =
                event.source_evidence->0->'details'->>'explanation_inference_id'
        UNION ALL
        SELECT event.*, TRUE AS activity_eligible
        FROM public.intelligence_events event
        WHERE event.source_kind NOT IN ('municipal_evidence', 'municipal_matter')
            AND (event.source_kind <> 'proceeding_extraction' OR EXISTS (
                SELECT 1 FROM staging.proceeding_extractions extraction
                JOIN staging.public_proceedings proceeding ON proceeding.id = extraction.proceeding_id
                JOIN meta.municipality_source_rights policy ON policy.body_name = proceeding.body_name
                WHERE extraction.id::text = event.source_record_id
                    AND LEFT(extraction.extraction_type, 1) <> '_'
                    AND proceeding.valid_to IS NULL
                    AND proceeding.metadata_quality->>'status' = 'ready'
                    AND policy.rights_status <> 'paused' AND policy.derived_product_allowed
                    AND policy.review_due_on >= CURRENT_DATE
                    AND EXISTS (
                        SELECT 1 FROM meta.source_rights global_policy
                        WHERE global_policy.source_key = 'public_proceedings'
                            AND global_policy.rights_status <> 'paused'
                            AND global_policy.derived_product_allowed
                            AND global_policy.review_due_on >= CURRENT_DATE
                    )
            ));
                CREATE OR REPLACE VIEW public.current_activity_events AS
                WITH eligible_events AS MATERIALIZED (
                    SELECT event.* FROM public.intelligence_events event
                    WHERE event.source_kind NOT IN ('municipal_evidence', 'municipal_matter')
                        OR (
                            event.source_evidence->0->'details'->>'discovery_eligible' = 'true'
                            AND event.source_evidence->0->'details'->>'explanation_inference_id'
                                IS NOT NULL
                        )
                ), municipal AS MATERIALIZED (
                    SELECT event_key, related_pidns, related_entities, explanation_inference_id
                    FROM public.current_municipal_record_versions
                    WHERE EXISTS (
                        SELECT 1 FROM eligible_events WHERE source_kind = 'municipal_evidence'
                    )
                ), matters AS MATERIALIZED (
                    SELECT event_key, related_pidns, related_entities,
                        explanation_inference_id, record_keys
                    FROM public.current_municipal_matter_accounts
                    WHERE EXISTS (
                        SELECT 1 FROM public.intelligence_events WHERE source_kind = 'municipal_matter'
                    )
                )
                SELECT event.*, TRUE AS activity_eligible
                FROM eligible_events event
                LEFT JOIN municipal ON event.source_kind = 'municipal_evidence'
                    AND municipal.event_key = event.event_key
                LEFT JOIN matters ON event.source_kind = 'municipal_matter'
                    AND matters.event_key = event.event_key
                WHERE (event.source_kind <> 'municipal_evidence' OR (
                    municipal.event_key IS NOT NULL
                    AND municipal.related_pidns = event.related_pidns
                    AND municipal.related_entities = event.related_entities
                    AND municipal.explanation_inference_id::text IS NOT DISTINCT FROM
                        event.source_evidence->0->'details'->>'explanation_inference_id'
                    AND NOT EXISTS (
                        SELECT 1 FROM matters covered WHERE covered.record_keys ? event.event_key
                    )
                    AND EXISTS (
                        SELECT 1 FROM meta.intelligence_inference_history history
                        WHERE history.inference_id =
                            (event.source_evidence->0->'details'->>'explanation_inference_id')::bigint
                            AND history.payload->'explanation'->>'presentation_language' = 'en'
                    )
                ))
                AND (event.source_kind <> 'municipal_matter' OR (
                    matters.event_key IS NOT NULL
                    AND matters.related_pidns = event.related_pidns
                    AND matters.related_entities = event.related_entities
                    AND matters.explanation_inference_id::text =
                        event.source_evidence->0->'details'->>'explanation_inference_id'
                ))
                AND (event.source_kind <> 'proceeding_extraction' OR EXISTS (
                    SELECT 1 FROM staging.proceeding_extractions extraction
                    JOIN staging.public_proceedings proceeding ON proceeding.id = extraction.proceeding_id
                    JOIN meta.municipality_source_rights policy ON policy.body_name = proceeding.body_name
                    WHERE extraction.id::text = event.source_record_id
                        AND LEFT(extraction.extraction_type, 1) <> '_'
                        AND proceeding.valid_to IS NULL
                        AND proceeding.metadata_quality->>'status' = 'ready'
                        AND policy.rights_status <> 'paused' AND policy.derived_product_allowed
                        AND policy.review_due_on >= CURRENT_DATE
                        AND EXISTS (
                            SELECT 1 FROM meta.source_rights global_policy
                            WHERE global_policy.source_key = 'public_proceedings'
                                AND global_policy.rights_status <> 'paused'
                                AND global_policy.derived_product_allowed
                                AND global_policy.review_due_on >= CURRENT_DATE
                        )
                ));

        CREATE OR REPLACE VIEW public.current_research_events AS
        WITH municipal AS MATERIALIZED (
            SELECT event_key, related_pidns, related_entities, explanation_inference_id
            FROM public.current_municipal_record_versions
        ), matters AS MATERIALIZED (
            SELECT event_key, related_pidns, related_entities, explanation_inference_id,
                record_keys
            FROM public.current_municipal_matter_accounts
        )
        SELECT event.*,
            (
                event.source_evidence->0->'details'->>'discovery_eligible' = 'true'
                AND event.source_evidence->0->'details'->>'explanation_inference_id' IS NOT NULL
                AND NOT EXISTS (
                    SELECT 1 FROM matters covered WHERE covered.record_keys ? event.event_key
                )
            ) AS activity_eligible
        FROM municipal
        JOIN public.intelligence_events event ON event.event_key = municipal.event_key
        WHERE event.source_kind = 'municipal_evidence'
            AND municipal.related_pidns = event.related_pidns
            AND municipal.related_entities = event.related_entities
            AND municipal.explanation_inference_id::text IS NOT DISTINCT FROM
                event.source_evidence->0->'details'->>'explanation_inference_id'
            AND event.event_key NOT IN (
                SELECT jsonb_array_elements_text(covered.record_keys)
                FROM matters covered
            )
        UNION ALL
        SELECT event.*,
            (event.source_evidence->0->'details'->>'discovery_eligible' = 'true'
                AND event.source_evidence->0->'details'->>'explanation_inference_id' IS NOT NULL
            ) AS activity_eligible
        FROM matters
        JOIN public.intelligence_events event ON event.event_key = matters.event_key
        WHERE event.source_kind = 'municipal_matter'
            AND event.source_evidence->0->'details'->>'discovery_eligible' = 'false'
            AND matters.related_pidns = event.related_pidns
            AND matters.related_entities = event.related_entities
            AND matters.explanation_inference_id::text =
                event.source_evidence->0->'details'->>'explanation_inference_id';
    """)


def downgrade() -> None:
    raise RuntimeError("Use a forward migration to preserve feed freshness checks.")
