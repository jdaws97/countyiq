"""Connect current source selections to properties, events and private watches.

The link table is a rebuildable association index. Original passages remain in
immutable inference history; live views retract stale sources and associations.
"""

from alembic import op

revision = "068"
down_revision = "067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(r"""
        CREATE FUNCTION public.municipal_evidence_references(card jsonb)
        RETURNS jsonb LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $body$
        WITH lines AS (
            -- Repair only a missing separator before a spelled-out direction.
            -- The retained passage remains unchanged (e.g. "2861east Prospect").
            SELECT regexp_replace(upper(line),
                '\m([0-9]{1,6})(NORTH|SOUTH|EAST|WEST)\M', '\1 \2', 'g') AS line
            FROM jsonb_array_elements(COALESCE(card->'passages', '[]'::jsonb)) passage,
                 LATERAL (SELECT regexp_replace(passage->>'text', '[[:space:]]+', ' ', 'g') AS line) normalized
        ), explicit_ids AS (
            SELECT match[1] AS reference
            FROM lines, LATERAL regexp_matches(line,
                '\m([0-9]{2}-[0-9]{3}-[A-Z0-9]{2}-[A-Z0-9]{4}[.][A-Z0-9]{2}[.-][0-9]{5}|[0-9]{5}[A-Z0-9]{7,8})\M', 'g') match
        ), address_candidates AS (
            SELECT match[1] AS reference,
                   left(line, strpos(line, match[1]) - 1) AS before_text,
                   substr(line, strpos(line, match[1]) + length(match[1])) AS after_text
            FROM lines, LATERAL regexp_matches(line,
                '\m([0-9]{1,6}[A-Z]?[[:space:]]+([A-Z][A-Z0-9.''-]*[[:space:]]+){1,7}(STREET|ST|ROAD|RD|AVENUE|AVE|AV|DRIVE|DR|LANE|LN|COURT|CT|BOULEVARD|BLVD|HIGHWAY|HWY|CIRCLE|CIR|PLACE|PL|TERRACE|TER|PARKWAY|PKWY|TRAIL|TRL|TURNPIKE|TPKE|PIKE|WAY)([[:space:]]+(NORTH|SOUTH|EAST|WEST|N|S|E|W)\M)?)\M', 'g') match
            WHERE NOT EXISTS (SELECT 1 FROM explicit_ids)
        ), addresses AS (
            -- Check the address's own range/unit context, not unrelated plan
            -- dates elsewhere in the paragraph. Do not silently strip units.
            SELECT reference FROM address_candidates
            WHERE before_text !~ '\m[0-9]+[[:space:]]*[-/&][[:space:]]*$'
              AND before_text !~ '\m[0-9]+[[:space:]]+(AND|TO)[[:space:]]+$'
              AND before_text !~ '\m(INTERSECTION|CORNER)([[:space:]]+OF)?[[:space:]]+$'
              AND reference !~ '\m(APT|APARTMENT|UNIT|SUITE|STE|BLDG|BUILDING|FL|FLOOR|REAR)\M'
              AND after_text !~ '^[[:space:],.]*(APT|APARTMENT|UNIT|SUITE|STE|BLDG|BUILDING|FL|FLOOR|REAR)\M'
              AND after_text !~ '^[[:space:],.]*LOT[[:space:]]+#?[[:space:]]*([0-9]+[A-Z]?|[A-Z])\M'
              AND after_text !~ '^[[:space:],.]*#[[:space:]]*[A-Z0-9]'
        ), refs AS (
            SELECT reference FROM explicit_ids
            UNION
            SELECT reference FROM addresses
        )
        SELECT COALESCE(jsonb_agg(reference ORDER BY reference), '[]'::jsonb)
        FROM refs
        $body$;

        CREATE TABLE public.municipal_evidence_links (
            inference_id bigint NOT NULL REFERENCES meta.intelligence_inference_history,
            card_id text NOT NULL,
            pidn text NOT NULL,
            match_method text NOT NULL CHECK (match_method IN ('pidn', 'address')),
            normalized_address text,
            municipality text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT NOW(),
            PRIMARY KEY (inference_id, card_id, pidn)
        );
        CREATE INDEX municipal_evidence_links_pidn
            ON public.municipal_evidence_links(pidn, inference_id);

        CREATE VIEW public.current_municipal_reads AS
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
          AND selected.payload->'record_snapshot'->>'content_hash'
              IS NOT DISTINCT FROM pp.content_hash
          AND selected.payload->'record_snapshot'->>'raw_text_sha256'
              = encode(sha256(convert_to(COALESCE(pp.raw_text, ''), 'UTF8')), 'hex')
          AND selected.payload->'record_snapshot'->>'body_name' = pp.body_name
          AND selected.payload->'record_snapshot'->>'meeting_date' = pp.meeting_date::text
          AND selected.payload->'record_snapshot'->>'proceeding_type' = pp.proceeding_type
          AND selected.payload->'record_snapshot'->>'document_url' = pp.document_url
          AND jsonb_typeof(selected.payload->'cards') = 'array';

        CREATE VIEW public.current_municipal_evidence AS
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
               COALESCE(first_seen.observed_at, read.reviewed_at) AS observed_at,
               COALESCE(properties.matches, '[]'::jsonb) AS matched_properties,
               COALESCE(properties.pidns, ARRAY[]::text[]) AS related_pidns,
               COALESCE(properties.owners, ARRAY[]::text[]) AS related_entities
        FROM public.current_municipal_reads read
        CROSS JOIN LATERAL jsonb_array_elements(read.payload->'cards')
            WITH ORDINALITY selected(card, position)
        LEFT JOIN LATERAL (
            SELECT min(history.created_at) AS observed_at
            FROM meta.intelligence_inference_history history
            WHERE history.subject_key = 'proceeding:' || read.proceeding_id::text
              AND history.output_kind = 'municipal_evidence'
              AND history.disposition = 'accepted'
              AND history.payload->'record_snapshot' = read.payload->'record_snapshot'
              AND history.payload->>'source_text_sha256' = read.payload->>'source_text_sha256'
              AND history.payload->'cards' @> jsonb_build_array(
                  jsonb_build_object('id', selected.card->>'id'))
        ) first_seen ON TRUE
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

        ALTER TABLE public.intelligence_events
            DROP CONSTRAINT chk_intelligence_events_source_kind;
        ALTER TABLE public.intelligence_events
            ADD CONSTRAINT chk_intelligence_events_source_kind CHECK (
                source_kind IN ('parcel_event', 'delinquency_event',
                                'proceeding_extraction', 'municipal_evidence'));
        ALTER TABLE public.intelligence_events
            DROP CONSTRAINT chk_intelligence_events_type;
        ALTER TABLE public.intelligence_events
            ADD CONSTRAINT chk_intelligence_events_type CHECK (event_type IN (
                'transfer', 'value_change', 'structure_change', 'delinquency_change',
                'application', 'hearing', 'revision', 'continuance', 'approval',
                'denial', 'condition', 'upcoming_decision', 'policy_action',
                'recommendation', 'update', 'withdrawn', 'removed', 'scoped_decision',
                'municipal_record'));

        CREATE VIEW public.current_intelligence_events AS
        SELECT event.* FROM public.intelligence_events event
        WHERE (event.source_kind <> 'municipal_evidence' OR EXISTS (
            SELECT 1 FROM public.current_municipal_evidence current
            WHERE current.event_key = event.event_key
              AND current.related_pidns = event.related_pidns
              AND current.related_entities = event.related_entities
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

        CREATE VIEW public.current_development_momentum AS
        SELECT dm.pidn, dm.score, dm.opportunity_score, dm.has_active_plan,
               dm.eligible, dm.exclusion_reasons,
               CASE WHEN stale.mention THEN dm.signals - 'municipal_record'
                    ELSE dm.signals END AS signals,
               CASE WHEN stale.mention AND dm.top_signal LIKE 'Municipal record:%'
                    THEN NULL ELSE dm.top_signal END AS top_signal,
               CASE WHEN stale.mention THEN GREATEST(dm.signal_count - 1, 0)
                    ELSE dm.signal_count END AS signal_count,
               dm.score_version, dm.computed_at, dm.site_readiness_score,
               dm.previous_score, dm.previous_opportunity_score,
               dm.previous_site_readiness_score, dm.previous_computed_at,
               dm.score_delta, dm.opportunity_delta, dm.first_seen_at, dm.is_new
        FROM public.development_momentum dm
        CROSS JOIN LATERAL (
            SELECT COALESCE(dm.signals ? 'municipal_record', FALSE) AND NOT EXISTS (
                SELECT 1 FROM public.current_municipal_evidence source
                WHERE source.event_key = dm.signals->'municipal_record'->'evidence'->>'event_key'
                  AND dm.pidn = ANY(source.related_pidns)
                  AND source.meeting_date >= CURRENT_DATE - INTERVAL '24 months'
            ) AS mention
        ) stale;
    """)
    # Keep the existing watch noise/identity policy byte-for-byte, changing only
    # its source to the live guarded view. Later migrations may have tightened it.
    op.execute("""
        DO $block$
        DECLARE definition text;
        BEGIN
            SELECT pg_get_functiondef('public.refresh_watch_notifications()'::regprocedure)
                INTO definition;
            EXECUTE replace(definition, 'public.intelligence_events',
                            'public.current_intelligence_events');
        END
        $block$;
    """)


def downgrade() -> None:
    # Refuse to drop a populated projection; reversion needs an explicit decision
    # about published evidence events and their retained notification identities.
    op.execute("""
        DO $block$
        BEGIN
            IF EXISTS (SELECT 1 FROM public.intelligence_events
                       WHERE source_kind = 'municipal_evidence') THEN
                RAISE EXCEPTION 'Municipal evidence events remain; review before downgrade';
            END IF;
        END
        $block$;
        DO $block$
        DECLARE definition text;
        BEGIN
            SELECT pg_get_functiondef('public.refresh_watch_notifications()'::regprocedure)
                INTO definition;
            EXECUTE replace(definition, 'public.current_intelligence_events',
                            'public.intelligence_events');
        END
        $block$;
        DROP VIEW IF EXISTS public.current_development_momentum;
        DROP VIEW public.current_intelligence_events;
        DROP VIEW public.current_municipal_evidence;
        DROP VIEW public.current_municipal_reads;
        DROP TABLE public.municipal_evidence_links;
        DROP FUNCTION public.municipal_evidence_references(jsonb);
        ALTER TABLE public.intelligence_events DROP CONSTRAINT chk_intelligence_events_source_kind;
        ALTER TABLE public.intelligence_events ADD CONSTRAINT chk_intelligence_events_source_kind
            CHECK (source_kind IN ('parcel_event', 'delinquency_event', 'proceeding_extraction'));
        ALTER TABLE public.intelligence_events DROP CONSTRAINT chk_intelligence_events_type;
        ALTER TABLE public.intelligence_events ADD CONSTRAINT chk_intelligence_events_type
            CHECK (event_type IN ('transfer', 'value_change', 'structure_change',
                'delinquency_change', 'application', 'hearing', 'revision', 'continuance',
                'approval', 'denial', 'condition', 'upcoming_decision', 'policy_action',
                'recommendation', 'update', 'withdrawn', 'removed', 'scoped_decision'));
    """)
