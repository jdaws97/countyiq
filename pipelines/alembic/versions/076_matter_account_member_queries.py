"""Join accepted matter members once instead of rescanning county evidence."""

from alembic import op

revision = "076"
down_revision = "075"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE INDEX idx_parcels_current_municipality_address
        ON staging.parcels (municipality, public.normalize_street_address(propadr))
        WHERE valid_to IS NULL;
    """)
    # Gather first-observation dates once per proceeding, before expanding cards.
    op.execute(r"""
        CREATE OR REPLACE VIEW public.current_municipal_evidence AS
        SELECT read.proceeding_id, read.body_name, read.meeting_date,
               read.proceeding_type, read.document_url, read.content_hash,
               read.source_observed_at, read.municipality,
               read.inference_id, read.reviewed_at, read.payload - 'cards' AS payload,
               selected.card, selected.position AS card_position,
               'municipal:' || read.proceeding_id::text || ':' ||
                   left(encode(sha256(convert_to(
                       (read.payload->'record_snapshot')::text ||
                       COALESCE(read.payload->>'source_text_sha256', ''), 'UTF8'
                   )), 'hex'), 20) || ':' || (selected.card->>'id') AS event_key,
               COALESCE((first_seen.by_card->>(selected.card->>'id'))::timestamptz, read.reviewed_at) AS observed_at,
               COALESCE(properties.matches, '[]'::jsonb) AS matched_properties,
               COALESCE(properties.pidns, ARRAY[]::text[]) AS related_pidns,
               COALESCE(properties.owners, ARRAY[]::text[]) AS related_entities
        FROM public.current_municipal_reads read
        LEFT JOIN LATERAL (
            SELECT jsonb_object_agg(card_id, observed_at) AS by_card
            FROM (
                SELECT prior.card->>'id' AS card_id, min(history.created_at) AS observed_at
                FROM meta.intelligence_inference_history history
                CROSS JOIN LATERAL jsonb_array_elements(history.payload->'cards') prior(card)
                WHERE history.subject_key = 'proceeding:' || read.proceeding_id::text
                  AND history.output_kind = 'municipal_evidence'
                  AND history.disposition = 'accepted'
                  AND prior.card->>'id' IS NOT NULL
                  AND history.payload->'record_snapshot' = read.payload->'record_snapshot'
                  AND history.payload->>'source_text_sha256' = read.payload->>'source_text_sha256'
                GROUP BY prior.card->>'id'
            ) observations
        ) first_seen ON TRUE
        CROSS JOIN LATERAL jsonb_array_elements(read.payload->'cards')
            WITH ORDINALITY selected(card, position)
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
              AND link.card_id = selected.card->>'id'
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
    """)
    op.execute(r"""
        CREATE VIEW public.current_municipal_matter_scopes AS
        WITH evidence AS MATERIALIZED (
            SELECT current.event_key, current.proceeding_id, current.card_position,
                current.meeting_date, current.municipality, current.related_pidns,
                current.matched_properties,
                public.municipal_case_reference(current.card->>'title') AS case_reference,
                CASE WHEN current.card->>'title' ~*
                    '^[0-9]+[[:space:]]+.+[[:space:]](st|street|rd|road|dr|drive|ave|avenue|ln|lane)[.]?$'
                    THEN public.normalize_street_address(current.card->>'title')
                END AS title_address
            FROM public.current_municipal_evidence current
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
    op.execute("""
        CREATE OR REPLACE VIEW public.current_municipal_matter_accounts AS
        WITH all_scopes AS MATERIALIZED (
            SELECT * FROM public.current_municipal_matter_scopes
        ), scopes AS MATERIALIZED (
            SELECT * FROM all_scopes
            WHERE bundle_key IN (
                SELECT subject_key FROM meta.intelligence_inference_history
                WHERE output_kind = 'record_explanation'
                    AND disposition = 'accepted'
                    AND jsonb_typeof(payload->'matters') = 'array'
            )
        ), evidence AS MATERIALIZED (
            SELECT current.* FROM public.current_municipal_evidence current
            WHERE proceeding_id IN (SELECT proceeding_id FROM scopes)
        ), candidates AS MATERIALIZED (
            SELECT evidence.*, scopes.bundle_key, scopes.record_position,
                jsonb_build_object(
                    'key', evidence.event_key, 'title', evidence.card->>'title',
                    'body_name', evidence.body_name,
                    'meeting_date', evidence.meeting_date::text,
                    'document_kind', COALESCE(evidence.payload->>'document_kind', 'record'),
                    'related_pidns', to_jsonb(evidence.related_pidns),
                    'source_fingerprint', encode(sha256(convert_to(
                        public.municipal_explanation_source(
                            ROW(evidence.*)::public.current_municipal_evidence
                        )::text, 'UTF8')), 'hex'),
                    'source_ids', (
                        SELECT jsonb_agg(
                            'R' || scopes.record_position::text || 'P' || position::text
                            ORDER BY position
                        )
                        FROM jsonb_array_elements(evidence.card->'passages')
                            WITH ORDINALITY spans(passage, position)
                    )
                ) AS source_record
            FROM scopes JOIN evidence USING (event_key, proceeding_id, card_position)
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
                max(evidence.meeting_date) AS meeting_date,
                max(evidence.observed_at) AS observed_at,
                min(evidence.municipality) AS municipality,
                jsonb_agg(to_jsonb(evidence.related_pidns)) AS pidn_groups,
                jsonb_agg(to_jsonb(evidence.related_entities)) AS entity_groups,
                jsonb_agg(jsonb_build_object(
                    'event_key', evidence.event_key, 'body_name', evidence.body_name,
                    'meeting_date', evidence.meeting_date::text, 'card', evidence.card,
                    'payload', evidence.payload, 'document_url', evidence.document_url
                ) ORDER BY evidence.meeting_date, evidence.proceeding_id,
                    evidence.card_position) AS records
            FROM matters matter
            CROSS JOIN LATERAL jsonb_array_elements_text(matter.matter->'record_keys')
                member(record_key)
            JOIN candidates evidence ON evidence.event_key = member.record_key
                AND evidence.bundle_key = matter.bundle_key
            GROUP BY matter.inference_id, matter.matter_position
        )
        SELECT matter.matter->>'key' AS event_key, matter.bundle_key,
            matter.source, matter.matter->'account' AS explanation,
            matter.matter->'record_keys' AS record_keys,
            matter.inference_id AS explanation_inference_id,
            matter.created_at AS explanation_generated_at,
            matter.requested_model AS explanation_model,
            members.meeting_date, members.observed_at, members.municipality,
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
            members.records
        FROM matters matter
        JOIN members USING (inference_id, matter_position);
    """)
    op.execute("""
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
            FROM public.current_municipal_intelligence
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
    """)


def downgrade() -> None:
    raise RuntimeError(
        "Use a forward migration to preserve current matter-source checks."
    )
