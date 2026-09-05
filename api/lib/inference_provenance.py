"""Serving checks for recorded proceeding dependencies in signal validation.

The fragment expects a public.evidence row aliased as supporting. It checks
recorded dependencies only; legacy history without references is not certified.
"""

SUPPORTING_PROCEEDINGS_CURRENT_SQL = """
    NOT EXISTS (
        SELECT 1
        FROM meta.intelligence_inference_history history
        WHERE history.inference_id = supporting.active_inference_id
          AND (
            history.disposition <> 'accepted'
            OR history.output_kind <> 'signal_validation'
            OR history.pass_number <> 2
            OR history.subject_key <> supporting.pidn
            OR EXISTS (
                SELECT 1
                FROM jsonb_array_elements_text(history.evidence_refs) dependency(ref)
                WHERE starts_with(dependency.ref, 'extraction:')
                  AND NOT EXISTS (
                    SELECT 1
                    FROM staging.proceeding_extractions extraction
                    JOIN staging.public_proceedings proceeding
                      ON proceeding.id = extraction.proceeding_id
                    WHERE extraction.id::text = split_part(dependency.ref, ':', 2)
                      AND proceeding.valid_to IS NULL
                      AND proceeding.metadata_quality->>'status' = 'ready'
                      AND LEFT(extraction.extraction_type, 1) <> '_'
                      AND history.evidence_refs ? ('proceeding:' || proceeding.id::text)
                      AND history.evidence_refs ? ('inference:' || extraction.active_inference_id::text)
                      AND EXISTS (
                        SELECT 1 FROM meta.intelligence_inference_history extraction_history
                        WHERE extraction_history.inference_id = extraction.active_inference_id
                          AND extraction_history.disposition = 'accepted'
                          AND extraction_history.output_kind = 'proceeding_extraction'
                          AND extraction_history.pass_number = 0
                          AND extraction_history.subject_key = 'proceeding:' || proceeding.id::text
                      )
                      AND EXISTS (
                        SELECT 1 FROM meta.source_rights source_policy
                        WHERE source_policy.source_key = 'public_proceedings'
                          AND source_policy.rights_status <> 'paused'
                          AND source_policy.derived_product_allowed
                          AND source_policy.review_due_on >= CURRENT_DATE
                      )
                      AND EXISTS (
                        SELECT 1 FROM meta.municipality_source_rights body_policy
                        WHERE body_policy.body_name = proceeding.body_name
                          AND body_policy.rights_status <> 'paused'
                          AND body_policy.derived_product_allowed
                          AND body_policy.review_due_on >= CURRENT_DATE
                      )
                  )
            )
          )
    )
"""


# Expects the cached brief aliased as brief. Check all supplied signal context,
# including signals the prose did not explicitly cite.
BRIEF_SIGNAL_VERSIONS_CURRENT_SQL = f"""
    EXISTS (
        SELECT 1 FROM meta.intelligence_inference_history brief_history
        WHERE brief_history.inference_id = brief.active_inference_id
          AND brief_history.disposition = 'accepted'
          AND brief_history.pass_number = 3
          AND brief_history.output_kind = %(brief_kind)s
          AND brief_history.subject_key = %(brief_subject)s
          AND brief_history.payload->>(CASE WHEN %(brief_kind)s = 'parcel_brief'
              THEN 'brief' ELSE 'brief_text' END) = brief.brief_text
          AND NOT EXISTS (
              SELECT 1 FROM jsonb_each(to_jsonb(brief)) projected(key, value)
              WHERE projected.key = ANY(CASE WHEN %(brief_kind)s = 'parcel_brief'
                  THEN ARRAY['assessment', 'assessment_reasoning', 'key_questions', 'citations']
                  ELSE ARRAY['portfolio_strategy', 'concentration_notes', 'key_pattern',
                      'recommendation', 'urgency', 'top_risk', 'evidence_strength',
                      'citations', 'parcel_citations'] END)
                AND brief_history.payload->projected.key IS DISTINCT FROM projected.value
          )
          AND EXISTS (
              SELECT 1 FROM jsonb_array_elements_text(brief_history.evidence_refs) version(ref)
              WHERE starts_with(version.ref, 'signal-version:')
          )
          AND NOT EXISTS (
              SELECT 1 FROM jsonb_array_elements_text(brief_history.evidence_refs) version(ref)
              WHERE starts_with(version.ref, 'signal-version:')
                AND NOT EXISTS (
                  SELECT 1 FROM public.evidence supporting
                  WHERE supporting.pidn = split_part(version.ref, ':', 2)
                    AND supporting.signal_key = split_part(version.ref, ':', 3)
                    AND supporting.active_inference_id::text = split_part(version.ref, ':', 4)
                    AND supporting.validation_status IN ('confirmed', 'upgraded', 'downgraded')
                    AND {SUPPORTING_PROCEEDINGS_CURRENT_SQL}
                )
          )
    )
"""


def owner_context_is_current(cur, canonical_name: str, references: list[str]) -> bool:
    """Match the owner/portfolio context originally supplied to brief generation."""
    import hashlib
    import json

    cur.execute("""
        SELECT o.owner_id, o.canonical_name, o.entity_type,
               array_agg(DISTINCT osl.source_id ORDER BY osl.source_id) AS pidns,
               COUNT(DISTINCT osl.source_id) AS n_parcels
        FROM public.owners o
        JOIN public.owner_source_links osl
          ON osl.owner_id = o.owner_id AND osl.source_type = 'parcel'
        WHERE o.canonical_name = %(name)s
        GROUP BY o.owner_id, o.canonical_name, o.entity_type
    """, {"name": canonical_name})
    owner = cur.fetchone()
    if not owner:
        return False
    context = dict(owner)
    signal_pidns = sorted({
        ref.split(":")[1] for ref in references
        if ref.startswith("signal-version:") and len(ref.split(":")) == 4
    })
    cur.execute("""
        SELECT requested.pidn, parcel.municipality
        FROM unnest(%(pidns)s::text[]) AS requested(pidn)
        LEFT JOIN staging.parcels parcel
          ON parcel.pidn=requested.pidn AND parcel.valid_to IS NULL
        ORDER BY requested.pidn
    """, {"pidns": signal_pidns})
    context["signal_municipalities"] = {
        row["pidn"]: row["municipality"] or None for row in cur.fetchall()
    }
    # Same canonical JSON contract as the pipeline intelligence content hash.
    serialized = json.dumps(context, sort_keys=True, separators=(",", ":"), default=str)
    expected = "owner-context:v2:" + hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return expected in references


# Expects the pass-status row aliased as pass_record. Pass 2 publishes its
# validations under one inference ID; summaries must follow that entire set.
CROSS_SIGNAL_SUMMARY_CURRENT_SQL = f"""
    EXISTS (
        SELECT 1 FROM meta.intelligence_inference_history summary_history
        WHERE summary_history.subject_key = pass_record.pidn
          AND summary_history.pass_number = 2
          AND summary_history.output_kind = 'signal_validation'
          AND summary_history.disposition = 'accepted'
          AND summary_history.input_hash = pass_record.input_hash
          AND summary_history.payload->>'cross_signal_insight' = pass_record.cross_signal_insight
          AND jsonb_typeof(summary_history.payload->'validations') = 'array'
          AND jsonb_array_length(CASE WHEN jsonb_typeof(summary_history.payload->'validations') = 'array' THEN summary_history.payload->'validations' ELSE '[]'::jsonb END) > 0
          AND NOT EXISTS (
              SELECT 1 FROM jsonb_array_elements(CASE WHEN jsonb_typeof(summary_history.payload->'validations') = 'array' THEN summary_history.payload->'validations' ELSE '[]'::jsonb END) validation
              WHERE NOT EXISTS (
                  SELECT 1 FROM public.evidence supporting
                  WHERE supporting.pidn = pass_record.pidn
                    AND supporting.signal_key = validation->>'signal_key'
                    AND supporting.active_inference_id = summary_history.inference_id
                    AND supporting.validation_status = validation->>'validation_status'
                    AND supporting.adjusted_significance = validation->>'adjusted_significance'
                    AND {SUPPORTING_PROCEEDINGS_CURRENT_SQL}
              )
          )
          AND NOT EXISTS (
              SELECT 1 FROM public.evidence extra
              WHERE extra.pidn = pass_record.pidn
                AND extra.active_inference_id IS DISTINCT FROM summary_history.inference_id
          )
    )
"""
