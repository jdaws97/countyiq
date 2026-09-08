"""Bind named resolutions to their own subject lines when titles omit the ID."""

from alembic import op

revision = "079"
down_revision = "078"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(r"""
        CREATE FUNCTION public.municipal_card_case_reference(card jsonb)
        RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $function$
            WITH subject_lines AS (
                SELECT line
                FROM jsonb_array_elements(
                    CASE WHEN jsonb_typeof(card->'subject_passages') = 'array'
                        THEN card->'subject_passages' ELSE '[]'::jsonb END
                ) passage
                CROSS JOIN LATERAL regexp_split_to_table(passage->>'text', E'\n') line
            ), named_references AS (
                SELECT public.municipal_case_reference(line) AS reference
                FROM subject_lines
                WHERE line ~* '^[[:space:]]*([a-z0-9]+[.)][[:space:]]*)?(Resolution|Ordinance)[[:space:]]+(No[.]?[[:space:]]*)?20[0-9]{2}-[0-9]+[[:space:]]*:'
                    AND lower(regexp_replace(btrim(substring(line FROM ':(.*)$')),
                        '[[:space:]]+', ' ', 'g'))
                        = lower(regexp_replace(btrim(card->>'title'),
                            '[[:space:]]+', ' ', 'g'))
                    AND length(btrim(card->>'title')) >= 12
            )
            SELECT COALESCE(public.municipal_case_reference(card->>'title'),
                (SELECT min(reference) FROM named_references
                    HAVING count(DISTINCT reference) = 1))
        $function$;

        ALTER TABLE public.municipal_card_index ADD COLUMN case_reference text;
        UPDATE public.municipal_card_index indexed
        SET case_reference = public.municipal_card_case_reference(
            history.payload->'cards'->((indexed.card_position - 1)::integer)
        )
        FROM meta.intelligence_inference_history history
        WHERE history.inference_id = indexed.inference_id;

        CREATE OR REPLACE FUNCTION public.index_accepted_municipal_read()
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
            SELECT NEW.inference_id, compiled.*,
                public.municipal_card_case_reference(
                    NEW.payload->'cards'->((compiled.card_position - 1)::integer)
                )
            FROM public.compile_municipal_card_index(NEW.subject_key, NEW.payload) compiled;
            RETURN NULL;
        END;
        $function$;
    """)
    _create_scope_view()
    _create_candidate_view()


def _create_scope_view() -> None:
    op.execute(r"""
        CREATE OR REPLACE VIEW public.current_municipal_matter_scopes AS
        WITH evidence AS MATERIALIZED (
            SELECT current.event_key, current.proceeding_id, current.card_position,
                current.meeting_date, current.municipality, current.related_pidns,
                current.matched_properties,
                indexed.case_reference,
                CASE WHEN current.title ~*
                    '^[0-9]+[[:space:]]+.+[[:space:]](st|street|rd|road|dr|drive|ave|avenue|ln|lane)[.]?$'
                    THEN public.normalize_street_address(current.title)
                END AS title_address
            FROM public.current_municipal_matter_inputs current
            JOIN public.municipal_card_index indexed USING (inference_id, card_position)
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

    """)


def _create_candidate_view() -> None:
    op.execute(r"""
        CREATE OR REPLACE VIEW public.current_municipal_matter_candidates AS
        SELECT evidence.*, indexed.case_reference,
            CASE WHEN evidence.card->>'title' ~*
                '^[0-9]+[[:space:]]+.+[[:space:]](st|street|rd|road|dr|drive|ave|avenue|ln|lane)[.]?$'
                THEN public.normalize_street_address(evidence.card->>'title')
            END AS title_address,
            indexed.source_fingerprint, scopes.candidate_scope,
            scopes.bundle_key, scopes.record_position,
            jsonb_build_object(
                'key', evidence.event_key, 'title', indexed.title,
                'body_name', evidence.body_name,
                'meeting_date', evidence.meeting_date::text,
                'document_kind', COALESCE(evidence.payload->>'document_kind', 'record'),
                'related_pidns', to_jsonb(evidence.related_pidns),
                'source_fingerprint', indexed.source_fingerprint,
                'source_ids', (SELECT jsonb_agg(
                    'R' || scopes.record_position::text || 'P' || position::text
                    ORDER BY position)
                    FROM generate_series(1, indexed.passage_count) position)
            ) AS source_record
        FROM public.current_municipal_evidence evidence
        JOIN public.current_municipal_matter_scopes scopes USING (event_key)
        JOIN public.municipal_card_index indexed
            ON indexed.inference_id = evidence.inference_id
                AND indexed.card_position = evidence.card_position;
    """)


def downgrade() -> None:
    raise NotImplementedError(
        "Restore a reviewed database backup to reverse case grouping."
    )
