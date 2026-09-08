"""Require source-bound subject references before municipal property linking.

Legacy cards remain readable as municipal evidence. Their rebuildable property
links are withdrawn until the source is reviewed under the subject contract.
"""

from alembic import op

revision = "070"
down_revision = "069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(r"""
        CREATE OR REPLACE FUNCTION public.municipal_reference_span_valid(span jsonb, source_hash text)
        RETURNS boolean LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $body$
        BEGIN
            IF jsonb_typeof(span) IS DISTINCT FROM 'object'
               OR jsonb_typeof(span->'text') IS DISTINCT FROM 'string'
               OR jsonb_typeof(span->'start') IS DISTINCT FROM 'number'
               OR jsonb_typeof(span->'end') IS DISTINCT FROM 'number'
               OR source_hash IS NULL OR source_hash !~ '^[a-f0-9]{64}$'
               OR span->>'source_text_sha256' IS DISTINCT FROM source_hash
            THEN RETURN FALSE; END IF;
            -- Bounds are checked before integer casts; malformed inference
            -- metadata must not raise an exception while serving evidence.
            IF span->>'start' !~ '^[0-9]{1,9}$'
               OR span->>'end' !~ '^[0-9]{1,9}$'
            THEN RETURN FALSE; END IF;
            RETURN (span->>'end')::integer > (span->>'start')::integer
                AND length(span->>'text') =
                    (span->>'end')::integer - (span->>'start')::integer;
        END
        $body$;

        CREATE OR REPLACE FUNCTION public.municipal_evidence_references(card jsonb)
        RETURNS jsonb LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $body$
        DECLARE
            ref jsonb;
            owned jsonb;
            surroundings jsonb;
            source_hash text;
            reference text;
            before_text text;
            after_text text;
            canonical_pidn text;
            identifier_text text;
            belongs_to_subject boolean;
            explicit_ids text[] := ARRAY[]::text[];
            addresses text[] := ARRAY[]::text[];
            candidates text[];
            result jsonb;
        BEGIN
            IF card->>'selection_contract' IS DISTINCT FROM 'subject-passages-v1'
               OR jsonb_typeof(card->'references') IS DISTINCT FROM 'array'
               OR jsonb_typeof(card->'subject_passages') IS DISTINCT FROM 'array'
            THEN RETURN '[]'::jsonb; END IF;
            source_hash := card->'subject'->>'source_text_sha256';
            FOR ref IN SELECT value FROM jsonb_array_elements(card->'references') LOOP
                IF ref->>'role' IS DISTINCT FROM 'subject_property'
                   OR NOT public.municipal_reference_span_valid(ref, source_hash)
                THEN CONTINUE; END IF;
                belongs_to_subject := FALSE;
                FOR owned IN SELECT value FROM jsonb_array_elements(card->'subject_passages') LOOP
                    IF public.municipal_reference_span_valid(owned, source_hash) THEN
                        IF (ref->>'start')::integer >= (owned->>'start')::integer
                           AND (ref->>'end')::integer <= (owned->>'end')::integer
                           AND substr(owned->>'text',
                               (ref->>'start')::integer - (owned->>'start')::integer + 1,
                               length(ref->>'text')) = ref->>'text'
                        THEN belongs_to_subject := TRUE; EXIT; END IF;
                    END IF;
                END LOOP;
                IF NOT belongs_to_subject THEN CONTINUE; END IF;
                surroundings := ref->'context';
                IF NOT public.municipal_reference_span_valid(surroundings, source_hash)
                THEN CONTINUE; END IF;
                IF (ref->>'start')::integer < (surroundings->>'start')::integer
                   OR (ref->>'end')::integer > (surroundings->>'end')::integer
                   OR substr(surroundings->>'text',
                       (ref->>'start')::integer - (surroundings->>'start')::integer + 1,
                       length(ref->>'text')) IS DISTINCT FROM ref->>'text'
                THEN CONTINUE; END IF;

                reference := btrim(regexp_replace(upper(ref->>'text'), '[[:space:]]+', ' ', 'g'));
                -- Only identifier-shaped text enters PIDN normalization. A
                -- five-digit street address must not become an alphanumeric ID.
                identifier_text := regexp_replace(reference, '-[[:space:]]+', '-', 'g');
                IF identifier_text ~ '^([0-9]{2}-[0-9]{3}-[A-Z0-9]{2}-[A-Z0-9]{4}[.][A-Z0-9]{2}[.-][0-9]{5}|[0-9]{5}[A-Z0-9]{7,8})$' THEN
                    canonical_pidn := public.normalize_parcel_reference(identifier_text);
                    explicit_ids := array_append(explicit_ids, canonical_pidn);
                    CONTINUE;
                END IF;
                reference := rtrim(reference, '.');
                reference := regexp_replace(reference,
                    '\m([0-9]{1,6})(NORTH|SOUTH|EAST|WEST)\M', '\1 \2', 'g');
                IF reference !~ '^([0-9]{1,6}[A-Z]?[[:space:]]+([A-Z][A-Z0-9.''-]*[[:space:]]+){1,7}(STREET|ST|ROAD|RD|AVENUE|AVE|AV|DRIVE|DR|LANE|LN|COURT|CT|BOULEVARD|BLVD|HIGHWAY|HWY|CIRCLE|CIR|PLACE|PL|TERRACE|TER|PARKWAY|PKWY|TRAIL|TRL|TURNPIKE|TPKE|PIKE|WAY)([[:space:]]+(NORTH|SOUTH|EAST|WEST|N|S|E|W))?)$'
                THEN CONTINUE; END IF;
                before_text := upper(regexp_replace(
                    left(surroundings->>'text',
                        (ref->>'start')::integer - (surroundings->>'start')::integer),
                    '[[:space:]]+', ' ', 'g'));
                after_text := upper(regexp_replace(
                    substr(surroundings->>'text',
                        (ref->>'end')::integer - (surroundings->>'start')::integer + 1),
                    '[[:space:]]+', ' ', 'g'));
                IF before_text ~ '\m[0-9]+[[:space:]]*[-/&][[:space:]]*$'
                   OR before_text ~ '\m[0-9]+[[:space:]]+(AND|TO)[[:space:]]+$'
                   OR before_text ~ '\m(INTERSECTION|CORNER)([[:space:]]+OF)?[[:space:]]+$'
                   OR reference ~ '\m(APT|APARTMENT|UNIT|SUITE|STE|BLDG|BUILDING|FL|FLOOR|REAR)\M'
                   OR after_text ~ '^[[:space:],.]*(APT|APARTMENT|UNIT|SUITE|STE|BLDG|BUILDING|FL|FLOOR|REAR)\M'
                   OR after_text ~ '^[[:space:],.]*LOT[[:space:]]+#?[[:space:]]*([0-9]+[A-Z]?|[A-Z])\M'
                   OR after_text ~ '^[[:space:],.]*#[[:space:]]*[A-Z0-9]'
                THEN CONTINUE; END IF;
                addresses := array_append(addresses, reference);
            END LOOP;
            candidates := CASE WHEN cardinality(explicit_ids) > 0 THEN explicit_ids ELSE addresses END;
            SELECT COALESCE(jsonb_agg(value ORDER BY value), '[]'::jsonb)
            INTO result FROM (SELECT DISTINCT unnest(candidates) AS value) unique_refs;
            RETURN result;
        END
        $body$;

        -- This index is derived. Keep all immutable source/inference history;
        -- never serve pre-contract associations while waiting for a rebuild.
        DELETE FROM public.municipal_evidence_links;
    """)


def downgrade() -> None:
    raise RuntimeError(
        "Restoring the unscoped municipal address extractor would reintroduce "
        "incorrect property links; use a reviewed forward migration."
    )
