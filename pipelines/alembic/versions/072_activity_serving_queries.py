"""Validate municipal source sets once per activity query, with compact signatures."""

from alembic import op

revision = "072"
down_revision = "071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(r"""
        CREATE VIEW public.current_municipal_matter_candidates AS
        WITH evidence AS MATERIALIZED (
            SELECT current.*,
                public.municipal_case_reference(current.card->>'title') AS case_reference,
                CASE WHEN current.card->>'title' ~* '^[0-9]+[[:space:]]+.+[[:space:]](st|street|rd|road|dr|drive|ave|avenue|ln|lane)[.]?$'
                    THEN public.normalize_street_address(current.card->>'title') END AS title_address,
                encode(sha256(convert_to(public.municipal_explanation_source(current)::text, 'UTF8')), 'hex') AS source_fingerprint
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
        )
        SELECT numbered.*,
            jsonb_build_object(
                'key', event_key, 'title', card->>'title', 'body_name', body_name,
                'meeting_date', meeting_date::text,
                'document_kind', COALESCE(payload->>'document_kind', 'record'),
                'related_pidns', to_jsonb(related_pidns),
                'source_fingerprint', source_fingerprint,
                'source_ids', (SELECT jsonb_agg('R' || record_position::text || 'P' || position::text ORDER BY position)
                    FROM jsonb_array_elements(card->'passages') WITH ORDINALITY spans(passage, position))
            ) AS source_record
        FROM numbered;

        CREATE OR REPLACE VIEW public.current_municipal_matter_sources AS
        WITH candidates AS MATERIALIZED (SELECT * FROM public.current_municipal_matter_candidates),
        records AS (
            SELECT bundle_key, max(meeting_date) AS latest_meeting_date,
                min(municipality) AS municipality, min(candidate_scope) AS candidate_scope,
                jsonb_agg(source_record ORDER BY record_position) AS records
            FROM candidates GROUP BY bundle_key
        ), sources AS (
            SELECT bundle_key,
                jsonb_agg(jsonb_build_object(
                    'id', 'R' || record_position::text || 'P' || position::text,
                    'record_key', event_key,
                    'label', body_name || ' · ' || meeting_date::text,
                    'body_name', body_name, 'meeting_date', meeting_date::text,
                    'document_kind', COALESCE(payload->>'document_kind', 'record'),
                    'text', passage->>'text', 'url', document_url,
                    'start', passage->'start', 'end', passage->'end',
                    'source_text_sha256', payload->>'source_text_sha256'
                ) ORDER BY record_position, position) AS sources
            FROM candidates,
                LATERAL jsonb_array_elements(card->'passages') WITH ORDINALITY spans(passage, position)
            GROUP BY bundle_key
        )
        SELECT bundle_key, latest_meeting_date,
            jsonb_build_object(
                'kind', 'municipal_matters', 'subject_key', bundle_key,
                'municipality', municipality, 'candidate_scope', candidate_scope,
                'records', records.records, 'sources', sources.sources
            ) AS source
        FROM records JOIN sources USING (bundle_key);

        CREATE OR REPLACE VIEW public.current_municipal_matter_accounts AS
        WITH candidates AS MATERIALIZED (SELECT * FROM public.current_municipal_matter_candidates),
        snapshots AS (
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
        )
        SELECT matter->>'key' AS event_key, history.bundle_key,
            history.payload->'source' AS source,
            matter->'account' AS explanation, matter->'record_keys' AS record_keys,
            history.inference_id AS explanation_inference_id,
            history.created_at AS explanation_generated_at,
            history.requested_model AS explanation_model,
            members.meeting_date, members.observed_at, members.municipality,
            members.related_pidns, members.related_entities, members.records
        FROM accepted history
        CROSS JOIN LATERAL jsonb_array_elements(history.payload->'matters') matter
        CROSS JOIN LATERAL (
            SELECT max(evidence.meeting_date) AS meeting_date,
                max(evidence.observed_at) AS observed_at,
                min(evidence.municipality) AS municipality,
                ARRAY(SELECT DISTINCT pidn FROM candidates related,
                    LATERAL unnest(related.related_pidns) pidn
                    WHERE matter->'record_keys' ? related.event_key ORDER BY pidn) AS related_pidns,
                ARRAY(SELECT DISTINCT owner FROM candidates related,
                    LATERAL unnest(related.related_entities) owner
                    WHERE matter->'record_keys' ? related.event_key ORDER BY owner) AS related_entities,
                jsonb_agg(jsonb_build_object(
                    'event_key', evidence.event_key, 'body_name', evidence.body_name,
                    'meeting_date', evidence.meeting_date::text, 'card', evidence.card,
                    'payload', evidence.payload, 'document_url', evidence.document_url
                ) ORDER BY evidence.meeting_date, evidence.proceeding_id, evidence.card_position) AS records
            FROM candidates evidence WHERE matter->'record_keys' ? evidence.event_key
        ) members;

        -- The previous correlated EXISTS rebuilt the same governed source view
        -- for every event before sorting. Materialize compact live keys once.
        CREATE OR REPLACE VIEW public.current_intelligence_events AS
        WITH municipal AS MATERIALIZED (
            SELECT event_key, related_pidns, related_entities, explanation_inference_id
            FROM public.current_municipal_intelligence
            WHERE EXISTS (SELECT 1 FROM public.intelligence_events WHERE source_kind = 'municipal_evidence')
        ), matters AS MATERIALIZED (
            SELECT event_key, related_pidns, related_entities, explanation_inference_id
            FROM public.current_municipal_matter_accounts
            WHERE EXISTS (SELECT 1 FROM public.intelligence_events WHERE source_kind = 'municipal_matter')
        )
        SELECT event.* FROM public.intelligence_events event
        LEFT JOIN municipal ON event.source_kind = 'municipal_evidence' AND municipal.event_key = event.event_key
        LEFT JOIN matters ON event.source_kind = 'municipal_matter' AND matters.event_key = event.event_key
        WHERE (event.source_kind <> 'municipal_evidence' OR (
            municipal.event_key IS NOT NULL
            AND municipal.related_pidns = event.related_pidns
            AND municipal.related_entities = event.related_entities
            AND municipal.explanation_inference_id::text IS NOT DISTINCT FROM
                event.source_evidence->0->'details'->>'explanation_inference_id'
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
    """)


def downgrade() -> None:
    raise RuntimeError(
        "Use a forward migration to preserve current-source and matter-identity checks."
    )
