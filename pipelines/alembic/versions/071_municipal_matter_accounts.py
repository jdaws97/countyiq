"""Assemble current municipal evidence for case accounts, with stable history links.

Candidate bundles are retrieval scopes, never assertions that their records are
one case. An accepted, source-bound account explicitly partitions those records.
"""

from alembic import op

revision = "071"
down_revision = "070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(r"""
        CREATE TABLE meta.municipal_matter_aliases (
            record_key text PRIMARY KEY,
            matter_key text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX municipal_matter_aliases_matter
            ON meta.municipal_matter_aliases(matter_key);

        CREATE FUNCTION public.municipal_case_reference(title text)
        RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $function$
            -- Retrieval only. These literal identifiers do not establish an
            -- outcome, property association, or cross-board case relationship.
            SELECT lower(regexp_replace(COALESCE(
                substring(title FROM '(?i)\m([0-9]{1,4}-20[0-9]{2}-Z-[A-Z-]+)\M'),
                substring(title FROM '(?i)\m((?\:LD|SD|P|CUH|ZHB)[-.]?[0-9]{2,4}[-.][0-9]{1,4}(?\:[-.][0-9]{1,4})?)\M'),
                substring(title FROM '(?i)\m((?\:Ordinance|Resolution)[[:space:]]+(?\:No[.]?[[:space:]]*)?20[0-9]{2}-[0-9]+)\M')
            ), '[[:space:].]+', '-', 'g'))
        $function$;

        CREATE VIEW public.current_municipal_matter_sources AS
        WITH evidence AS MATERIALIZED (
            SELECT current.*,
                public.municipal_case_reference(current.card->>'title') AS case_reference,
                CASE WHEN current.card->>'title' ~* '^[0-9]+[[:space:]]+.+[[:space:]](st|street|rd|road|dr|drive|ave|avenue|ln|lane)[.]?$'
                    THEN public.normalize_street_address(current.card->>'title') END AS title_address
            FROM public.current_municipal_evidence current
        ), known_cases AS (
            SELECT municipality, case_reference, min(related_pidns[1]) AS pidn
            FROM evidence
            WHERE case_reference IS NOT NULL AND cardinality(related_pidns) = 1
            GROUP BY municipality, case_reference
            HAVING count(DISTINCT related_pidns[1]) = 1
        ), known_addresses AS (
            SELECT municipality, public.normalize_street_address(matched->>'address') AS address,
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
        ), numbered AS (
            SELECT scoped.*,
                'municipal-bundle:' || encode(sha256(convert_to(
                    municipality || '|' || candidate_scope, 'UTF8')), 'hex') AS bundle_key,
                row_number() OVER (PARTITION BY municipality, candidate_scope
                    ORDER BY meeting_date, proceeding_id, card_position) AS record_position
            FROM scoped
        ), records AS (
            SELECT numbered.*,
                jsonb_build_object(
                    'key', event_key, 'title', card->>'title', 'body_name', body_name,
                    'meeting_date', meeting_date::text,
                    'document_kind', COALESCE(payload->>'document_kind', 'record'),
                    'related_pidns', to_jsonb(related_pidns),
                    'source_ids', (SELECT jsonb_agg('R' || record_position::text || 'P' || position::text ORDER BY position)
                        FROM jsonb_array_elements(card->'passages') WITH ORDINALITY spans(passage, position))
                ) AS source_record,
                (SELECT jsonb_agg(jsonb_build_object(
                    'id', 'R' || record_position::text || 'P' || position::text,
                    'record_key', event_key,
                    'label', body_name || ' · ' || meeting_date::text,
                    'body_name', body_name, 'meeting_date', meeting_date::text,
                    'document_kind', COALESCE(payload->>'document_kind', 'record'),
                    'text', passage->>'text', 'url', document_url,
                    'start', passage->'start', 'end', passage->'end',
                    'source_text_sha256', payload->>'source_text_sha256'
                ) ORDER BY position)
                FROM jsonb_array_elements(card->'passages') WITH ORDINALITY spans(passage, position)) AS sources
            FROM numbered
        )
        SELECT bundle_key, max(meeting_date) AS latest_meeting_date,
            jsonb_build_object(
                'kind', 'municipal_matters', 'subject_key', bundle_key,
                'municipality', municipality, 'candidate_scope', candidate_scope,
                'records', jsonb_agg(source_record ORDER BY record_position),
                'sources', (SELECT jsonb_agg(source ORDER BY member.record_position, position)
                    FROM records member,
                        LATERAL jsonb_array_elements(member.sources) WITH ORDINALITY span(source, position)
                    WHERE member.bundle_key = records.bundle_key)
            ) AS source
        FROM records GROUP BY bundle_key, municipality, candidate_scope;

        CREATE VIEW public.current_municipal_matter_accounts AS
        SELECT matter->>'key' AS event_key, current.bundle_key, current.source,
            matter->'account' AS explanation, matter->'record_keys' AS record_keys,
            history.inference_id AS explanation_inference_id,
            history.created_at AS explanation_generated_at,
            history.requested_model AS explanation_model,
            members.meeting_date, members.observed_at, members.municipality,
            members.related_pidns, members.related_entities, members.records
        FROM public.current_municipal_matter_sources current
        CROSS JOIN LATERAL (
            SELECT accepted.* FROM meta.intelligence_inference_history accepted
            WHERE accepted.subject_key = current.bundle_key
                AND accepted.output_kind = 'record_explanation'
                AND accepted.disposition = 'accepted'
                AND accepted.payload->'source' = current.source
                AND jsonb_typeof(accepted.payload->'matters') = 'array'
            ORDER BY accepted.inference_id DESC LIMIT 1
        ) history
        CROSS JOIN LATERAL jsonb_array_elements(history.payload->'matters') matter
        CROSS JOIN LATERAL (
            SELECT max(evidence.meeting_date) AS meeting_date,
                max(evidence.observed_at) AS observed_at,
                min(evidence.municipality) AS municipality,
                ARRAY(SELECT DISTINCT pidn FROM public.current_municipal_evidence related,
                    LATERAL unnest(related.related_pidns) pidn
                    WHERE matter->'record_keys' ? related.event_key ORDER BY pidn) AS related_pidns,
                ARRAY(SELECT DISTINCT owner FROM public.current_municipal_evidence related,
                    LATERAL unnest(related.related_entities) owner
                    WHERE matter->'record_keys' ? related.event_key ORDER BY owner) AS related_entities,
                jsonb_agg(jsonb_build_object(
                    'event_key', evidence.event_key, 'body_name', evidence.body_name,
                    'meeting_date', evidence.meeting_date::text, 'card', evidence.card,
                    'payload', evidence.payload, 'document_url', evidence.document_url
                ) ORDER BY evidence.meeting_date, evidence.proceeding_id, evidence.card_position) AS records
            FROM public.current_municipal_evidence evidence
            WHERE matter->'record_keys' ? evidence.event_key
        ) members;

        ALTER TABLE public.intelligence_events DROP CONSTRAINT chk_intelligence_events_source_kind;
        ALTER TABLE public.intelligence_events ADD CONSTRAINT chk_intelligence_events_source_kind
            CHECK (source_kind IN ('parcel_event', 'delinquency_event', 'proceeding_extraction',
                'municipal_evidence', 'municipal_matter'));

        DO $block$
        DECLARE definition text;
        BEGIN
            SELECT pg_get_viewdef('public.current_intelligence_events'::regclass, true) INTO definition;
            definition := regexp_replace(definition, ';[[:space:]]*$', '');
            EXECUTE 'CREATE OR REPLACE VIEW public.current_intelligence_events AS ' || definition ||
                ' AND (event.source_kind <> ''municipal_matter'' OR EXISTS (' ||
                'SELECT 1 FROM public.current_municipal_matter_accounts account ' ||
                'WHERE account.event_key = event.event_key ' ||
                'AND account.related_pidns = event.related_pidns ' ||
                'AND account.related_entities = event.related_entities ' ||
                'AND account.explanation_inference_id::text = ' ||
                '(event.source_evidence->0->''details''->>''explanation_inference_id'')))';
        END
        $block$;
    """)


def downgrade() -> None:
    raise RuntimeError(
        "Matter identities may be followed by customers; review their retention before reverting."
    )
