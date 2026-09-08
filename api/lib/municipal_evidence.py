"""Current source excerpts, literal property associations and reading coverage."""

from __future__ import annotations

from api.lib.source_explanations import explanation_payload
from api.lib.source_locations import page_passages

EVIDENCE_QUERY = """
    SELECT * FROM public.current_municipal_intelligence
    WHERE UPPER(municipality) = UPPER(%(municipality)s)
      AND (%(pidn)s::text IS NULL OR %(pidn)s = ANY(related_pidns))
    ORDER BY meeting_date DESC, proceeding_id DESC, card_position
    LIMIT %(limit)s
"""

COVERAGE_QUERY = """
    WITH records AS (
        SELECT pp.id, pp.meeting_date, pp.valid_from,
               CASE
                   WHEN (policy.rights_status <> 'paused'
                     AND policy.derived_product_allowed
                     AND policy.review_due_on >= CURRENT_DATE) IS NOT TRUE
                     OR NOT EXISTS (
                         SELECT 1 FROM meta.source_rights global_policy
                         WHERE global_policy.source_key = 'public_proceedings'
                           AND global_policy.rights_status <> 'paused'
                           AND global_policy.derived_product_allowed
                           AND global_policy.review_due_on >= CURRENT_DATE
                     ) THEN 'blocked'
                   WHEN pp.meeting_date > CURRENT_DATE THEN 'future'
                   WHEN pp.metadata_quality->>'status' IS DISTINCT FROM 'ready'
                     OR pp.meeting_date IS NULL THEN 'review_required'
                   ELSE 'eligible'
               END AS eligibility
        FROM staging.public_proceedings pp
        JOIN meta.municipality_source_rights policy ON policy.body_name = pp.body_name
        WHERE pp.valid_to IS NULL
          AND UPPER(policy.municipality_name) = UPPER(%(municipality)s)
    )
    SELECT COUNT(*) AS total_documents,
           COUNT(*) FILTER (WHERE r.eligibility = 'eligible') AS eligible_documents,
           COUNT(*) FILTER (WHERE read.inference_id IS NOT NULL) AS reviewed_documents,
           COUNT(*) FILTER (WHERE r.eligibility = 'eligible'
                             AND read.inference_id IS NULL) AS awaiting_read_documents,
           COUNT(*) FILTER (WHERE r.eligibility = 'review_required') AS review_required_documents,
           COUNT(*) FILTER (WHERE r.eligibility = 'blocked') AS blocked_documents,
           COUNT(*) FILTER (WHERE r.eligibility = 'future') AS future_documents,
           COUNT(*) FILTER (WHERE r.eligibility = 'eligible'
                             AND read.inference_id IS NULL AND attempt.status = 'error') AS failed_documents,
           COUNT(*) FILTER (WHERE jsonb_array_length(read.payload->'cards') > 0) AS documents_with_passages,
           MAX(r.meeting_date) FILTER (WHERE r.meeting_date <= CURRENT_DATE) AS latest_meeting_date,
           MAX(read.meeting_date) AS latest_reviewed_meeting_date,
           MAX(r.valid_from) AS last_source_observed_at,
           MAX(read.reviewed_at) AS last_reviewed_at
    FROM records r
    LEFT JOIN public.current_municipal_reads read ON read.proceeding_id = r.id
    LEFT JOIN meta.intelligence_passes attempt
        ON attempt.pidn = 'proceeding:' || r.id::text AND attempt.pass_number = 0
"""


def _temporal(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def evidence_cards(rows: list[dict], *, limit: int) -> dict:
    """Split retained spans at physical pages without rewriting their text."""
    cards = []
    for row in rows[:limit]:
        payload = row["payload"]
        card = row["card"]
        passages = page_passages(card["passages"], payload.get("pages", []))
        cards.append(
            {
                "id": f"{row['inference_id']}:{card['id']}",
                "event_key": row["event_key"],
                "title": card["title"],
                "body_name": row["body_name"],
                "meeting_date": _temporal(row["meeting_date"]),
                "proceeding_type": payload.get("document_kind", "record"),
                "document_url": row["document_url"],
                "passages": passages,
                "source_text_sha256": payload["source_text_sha256"],
                "matched_properties": row["matched_properties"],
                "observed_at": _temporal(row["observed_at"]),
                "explanation": explanation_payload(row),
            }
        )
    return {"cards": cards, "more": len(rows) > limit}


def fetch_municipal_evidence(
    cur, *, municipality: str, pidn: str | None = None, limit: int = 12
) -> dict:
    """Property coverage describes its municipality, never presumed parcel silence."""
    cur.execute(
        EVIDENCE_QUERY,
        {"municipality": municipality, "pidn": pidn, "limit": limit + 1},
    )
    result = evidence_cards([dict(row) for row in cur.fetchall()], limit=limit)
    cur.execute(COVERAGE_QUERY, {"municipality": municipality})
    result["coverage"] = {
        key: _temporal(value) for key, value in dict(cur.fetchone()).items()
    }
    return result
