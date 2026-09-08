"""Retrieve explicitly reviewed cross-document subjects as one candidate bundle."""

from alembic import op

revision = "080"
down_revision = "079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE meta.municipal_candidate_reviews (
            review_id bigserial PRIMARY KEY,
            candidate_key text NOT NULL,
            action text NOT NULL CHECK (action IN ('group', 'release')),
            members jsonb NOT NULL CHECK (
                jsonb_typeof(members) = 'object' AND members <> '{}'::jsonb
            ),
            reviewer text NOT NULL CHECK (length(btrim(reviewer)) > 0),
            rationale text NOT NULL CHECK (length(btrim(rationale)) >= 12),
            decision_origin text NOT NULL CHECK (
                decision_origin IN ('human_resolution', 'auto_resolution')
            ),
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE TRIGGER immutable_municipal_candidate_reviews
            BEFORE UPDATE OR DELETE ON meta.municipal_candidate_reviews
            FOR EACH ROW EXECUTE FUNCTION meta.reject_intelligence_audit_mutation();
        CREATE INDEX idx_municipal_candidate_reviews_members
            ON meta.municipal_candidate_reviews USING gin (members);
        CREATE TRIGGER invalidate_feed_cache
            AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE
            ON meta.municipal_candidate_reviews
            FOR EACH STATEMENT EXECUTE FUNCTION meta.invalidate_feed_cache();
    """)
    _create_scope_view()
    _create_source_views()


def _create_scope_view() -> None:
    op.execute(r"""
        CREATE VIEW public.current_municipal_matter_scoped_inputs AS
        WITH evidence AS MATERIALIZED (
            SELECT current.*, indexed.case_reference,
                CASE WHEN current.title ~*
                    '^[0-9]+[[:space:]]+.+[[:space:]](st|street|rd|road|dr|drive|ave|avenue|ln|lane)[.]?$'
                    THEN public.normalize_street_address(current.title)
                END AS title_address
            FROM public.current_municipal_matter_inputs current
            JOIN public.municipal_card_index indexed USING (inference_id, card_position)
        ), latest_reviews AS MATERIALIZED (
            SELECT DISTINCT ON (member.key)
                member.key AS event_key, member.value AS source_fingerprint,
                review.review_id, review.candidate_key, review.action,
                member_counts.members_count
            FROM meta.municipal_candidate_reviews review
            CROSS JOIN LATERAL jsonb_each_text(review.members) member
            CROSS JOIN LATERAL (
                SELECT count(*) AS members_count FROM jsonb_object_keys(review.members)
            ) member_counts
            ORDER BY member.key, review.review_id DESC
        ), complete_reviews AS (
            SELECT latest.review_id
            FROM latest_reviews latest
            JOIN evidence ON evidence.event_key = latest.event_key
                AND evidence.source_fingerprint = latest.source_fingerprint
            WHERE latest.action = 'group'
            GROUP BY latest.review_id
            HAVING count(*) = max(latest.members_count)
        ), reviewed_members AS (
            SELECT latest.event_key, latest.candidate_key
            FROM latest_reviews latest JOIN complete_reviews USING (review_id)
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
                    WHEN reviewed_members.candidate_key IS NOT NULL THEN reviewed_members.candidate_key
                    ELSE 'selection:' || evidence.event_key
                END AS candidate_scope
            FROM evidence
            LEFT JOIN reviewed_members USING (event_key)
            LEFT JOIN known_cases USING (municipality, case_reference)
            LEFT JOIN known_addresses ON known_addresses.municipality = evidence.municipality
                AND known_addresses.address = evidence.title_address
        )
        SELECT scoped.*,
            'municipal-bundle:' || encode(sha256(convert_to(
                municipality || '|' || candidate_scope, 'UTF8')), 'hex') AS bundle_key,
            row_number() OVER (PARTITION BY municipality, candidate_scope
                ORDER BY meeting_date, proceeding_id, card_position) AS record_position
        FROM scoped;

        CREATE OR REPLACE VIEW public.current_municipal_matter_scopes AS
        SELECT event_key, proceeding_id, card_position, candidate_scope,
            bundle_key, record_position
        FROM public.current_municipal_matter_scoped_inputs;
    """)


def _source_query(scope_filter: str = "") -> str:
    return f"""
        WITH candidates AS MATERIALIZED (
            SELECT current.*, indexed.explanation_source,
                jsonb_build_object(
                    'key', current.event_key, 'title', current.title,
                    'body_name', current.body_name,
                    'meeting_date', current.meeting_date::text,
                    'document_kind', current.document_kind,
                    'related_pidns', to_jsonb(current.related_pidns),
                    'source_fingerprint', current.source_fingerprint,
                    'source_ids', (SELECT jsonb_agg(
                        'R' || current.record_position::text || 'P' || position::text
                        ORDER BY position)
                        FROM generate_series(1, current.passage_count) position)
                ) AS source_record
            FROM public.current_municipal_matter_scoped_inputs current
            JOIN public.municipal_card_index indexed
                USING (inference_id, card_position)
            {scope_filter}
        ), grouped AS (
            SELECT bundle_key, max(meeting_date) AS latest_meeting_date,
                min(municipality) AS municipality, min(candidate_scope) AS candidate_scope,
                jsonb_agg(source_record ORDER BY record_position)
                    FILTER (WHERE position = 1 OR position IS NULL) AS records,
                jsonb_agg(
                    passage || jsonb_build_object(
                        'id', 'R' || record_position::text || (passage->>'id'),
                        'record_key', event_key, 'body_name', body_name,
                        'meeting_date', meeting_date::text, 'document_kind', document_kind
                    ) ORDER BY record_position, position
                ) FILTER (WHERE passage IS NOT NULL) AS sources
            FROM candidates
            LEFT JOIN LATERAL jsonb_array_elements(explanation_source->'sources')
                WITH ORDINALITY spans(passage, position) ON TRUE
            GROUP BY bundle_key
            HAVING count(passage) > 0
        )
        SELECT grouped.bundle_key, grouped.latest_meeting_date,
            jsonb_build_object(
                'kind', 'municipal_matters', 'subject_key', grouped.bundle_key,
                'municipality', grouped.municipality,
                'candidate_scope', grouped.candidate_scope,
                'records', grouped.records, 'sources', grouped.sources
            ) AS source
        FROM grouped
    """


def _create_source_views() -> None:
    op.execute(
        "CREATE OR REPLACE VIEW public.current_municipal_matter_sources AS "
        + _source_query()
    )
    op.execute(
        "CREATE OR REPLACE FUNCTION public.municipal_matter_source(requested_bundle text) "
        "RETURNS TABLE (bundle_key text, latest_meeting_date date, source jsonb) "
        "LANGUAGE sql STABLE AS $function$ "
        + _source_query("WHERE bundle_key = requested_bundle")
        + " $function$;"
    )


def downgrade() -> None:
    raise NotImplementedError("Restore a reviewed backup to reverse candidate reviews.")
