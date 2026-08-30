"""Assemble the unified product-facing intelligence event ledger.

The asset combines rebuildable deterministic events with cached Pass 0
development interpretation. It never invokes an LLM itself.
"""

from dagster import AssetExecutionContext, MaterializeResult, MetadataValue, asset
from psycopg2.extras import Json, execute_batch

from countyiq.lib.intelligence_events import (
    build_delinquency_event,
    build_development_event,
    build_parcel_event,
)
from countyiq.resources.database import DatabaseResource


_INSERT_COLUMNS = (
    "event_key",
    "source_kind",
    "source_record_id",
    "category",
    "event_type",
    "event_tags",
    "title",
    "what_happened",
    "why_it_matters",
    "what_happens_next",
    "event_date",
    "detected_at",
    "confidence",
    "municipality",
    "project_key",
    "project_name",
    "related_entities",
    "related_pidns",
    "source_evidence",
    "interpretation_kind",
    "interpretation_model",
    "interpretation_generated_at",
)

_INSERT_SQL = f"""
    INSERT INTO public.intelligence_events ({', '.join(_INSERT_COLUMNS)})
    VALUES ({', '.join(['%s'] * len(_INSERT_COLUMNS))})
"""


_PARCEL_EVENTS_SQL = """
    SELECT
        ev.id,
        ev.pidn,
        ev.event_type,
        ev.confidence,
        ev.event_date,
        ev.detected_at,
        ev.evidence,
        COALESCE(versioned.owner_full, current_parcel.owner_full) AS owner_full,
        COALESCE(versioned.propadr, current_parcel.propadr) AS propadr,
        COALESCE(versioned.municipality, current_parcel.municipality) AS municipality,
        COALESCE(versioned.source_url, current_parcel.source_url) AS source_url
    FROM public.parcel_events ev
    LEFT JOIN staging.parcels versioned
      ON versioned.pidn = ev.pidn
     AND versioned.valid_from = ev.new_version_from
    LEFT JOIN staging.parcels current_parcel
      ON current_parcel.pidn = ev.pidn
     AND current_parcel.valid_to IS NULL
    ORDER BY ev.detected_at, ev.id
"""


_DELINQUENCY_EVENTS_SQL = """
    WITH inserted_or_changed AS (
        SELECT
            n.pidn,
            n.valid_from AS detected_at,
            MAX(n.report_date) AS event_date,
            SUM(COALESCE(o.total, 0)) AS old_total,
            SUM(COALESCE(n.total, 0)) AS new_total,
            COUNT(*) AS affected_claims,
            ARRAY_AGG(DISTINCT n.tax_year ORDER BY n.tax_year) AS tax_years,
            MAX(n.source_url) AS source_url
        FROM staging.tax_claims n
        LEFT JOIN staging.tax_claims o
          ON o.pidn = n.pidn
         AND o.unit_suffix = n.unit_suffix
         AND o.tax_year = n.tax_year
         AND o.authority_name = n.authority_name
         AND o.valid_to = n.valid_from
        WHERE o.pidn IS NULL OR o.total IS DISTINCT FROM n.total
        GROUP BY n.pidn, n.valid_from
    ),
    resolved AS (
        SELECT
            o.pidn,
            o.valid_to AS detected_at,
            MAX(o.report_date) AS event_date,
            SUM(COALESCE(o.total, 0)) AS old_total,
            0::numeric AS new_total,
            COUNT(*) AS affected_claims,
            ARRAY_AGG(DISTINCT o.tax_year ORDER BY o.tax_year) AS tax_years,
            MAX(o.source_url) AS source_url
        FROM staging.tax_claims o
        WHERE o.valid_to IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM staging.tax_claims n
              WHERE n.pidn = o.pidn
                AND n.unit_suffix = o.unit_suffix
                AND n.tax_year = o.tax_year
                AND n.authority_name = o.authority_name
                AND n.valid_from = o.valid_to
          )
        GROUP BY o.pidn, o.valid_to
    ),
    transitions AS (
        SELECT * FROM inserted_or_changed
        UNION ALL
        SELECT * FROM resolved
    )
    SELECT
        t.*,
        CASE
            WHEN t.old_total = 0 AND t.new_total > 0 THEN 'new'
            WHEN t.new_total = 0 AND t.old_total > 0 THEN 'resolved'
            WHEN t.new_total > t.old_total THEN 'increased'
            ELSE 'decreased'
        END AS change_kind,
        p.owner_full,
        p.propadr,
        p.municipality
    FROM transitions t
    LEFT JOIN staging.parcels p
      ON p.pidn = t.pidn
     AND p.valid_to IS NULL
    WHERE t.detected_at IS NOT NULL
      AND t.old_total IS DISTINCT FROM t.new_total
    ORDER BY t.detected_at, t.pidn
"""


_DEVELOPMENT_EVENTS_SQL = """
    SELECT
        pe.id,
        pe.proceeding_id,
        pe.extraction_type,
        pe.applicant_name,
        pe.parcel_reference,
        pe.current_zoning,
        pe.proposed_zoning,
        pe.decision,
        pe.conditions,
        pe.supporting_text,
        pe.extraction_confidence,
        pe.model_used,
        pe.extracted_at,
        pe.event_tags,
        pe.project_name,
        pe.related_entities,
        pe.what_happened,
        pe.why_it_matters,
        pe.what_happens_next,
        pe.upcoming_date,
        pe.interpretation_generated_at,
        pp.body_name,
        pp.meeting_date,
        pp.proceeding_type,
        pp.source_url,
        pp.document_url,
        pp.valid_from AS proceeding_valid_from,
        COALESCE(matches.related_pidns, ARRAY[]::text[]) AS related_pidns,
        COALESCE(matches.matched_owners, ARRAY[]::text[]) AS matched_owners
    FROM staging.proceeding_extractions pe
    JOIN staging.public_proceedings pp
      ON pp.id = pe.proceeding_id
     AND pp.valid_to IS NULL
    LEFT JOIN LATERAL (
        SELECT
            ARRAY_AGG(m.pidn ORDER BY m.pidn) AS related_pidns,
            ARRAY_AGG(DISTINCT m.owner_full) FILTER (WHERE m.owner_full IS NOT NULL) AS matched_owners
        FROM (
            SELECT p.pidn, p.owner_full
            FROM staging.parcels p
            WHERE p.valid_to IS NULL
              AND pe.parcel_reference IS NOT NULL
              AND (
                  p.pidn = REGEXP_REPLACE(pe.parcel_reference, '[^0-9]', '', 'g')
                  OR (
                      LENGTH(REGEXP_REPLACE(pe.parcel_reference, '[^A-Za-z0-9]', '', 'g')) >= 6
                      AND REGEXP_REPLACE(UPPER(p.propadr), '[^A-Z0-9]', '', 'g') =
                          REGEXP_REPLACE(UPPER(pe.parcel_reference), '[^A-Z0-9]', '', 'g')
                  )
              )
            ORDER BY p.pidn
            LIMIT 20
        ) m
    ) matches ON TRUE
    WHERE pe.extraction_type NOT IN ('_complete', '_no_extractions')
    ORDER BY pe.extracted_at, pe.id
"""


def _fetch_dicts(database: DatabaseResource, sql: str) -> list[dict]:
    with database.dict_cursor() as cur:
        cur.execute(sql)
        return [dict(row) for row in cur.fetchall()]


def _insert_tuple(event: dict) -> tuple:
    values = []
    for column in _INSERT_COLUMNS:
        value = event.get(column)
        if column == "source_evidence":
            value = Json(value or [])
        values.append(value)
    return tuple(values)


@asset(
    group_name="enrichment",
    deps=["parcel_events", "tax_claims", "proceeding_extraction"],
    description=(
        "Unified evidence-backed parcel and development intelligence events; "
        "uses cached Pass 0 interpretation and makes no LLM calls"
    ),
    kinds={"postgres"},
)
def intelligence_events(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> MaterializeResult:
    parcel_rows = _fetch_dicts(database, _PARCEL_EVENTS_SQL)
    delinquency_rows = _fetch_dicts(database, _DELINQUENCY_EVENTS_SQL)
    development_rows = _fetch_dicts(database, _DEVELOPMENT_EVENTS_SQL)

    events = [build_parcel_event(row) for row in parcel_rows]
    events.extend(build_delinquency_event(row) for row in delinquency_rows)
    events.extend(build_development_event(row) for row in development_rows)

    if not events:
        context.log.warning(
            "No source events were available; preserving the current intelligence ledger"
        )
        return MaterializeResult(
            metadata={
                "status": MetadataValue.text("preserved_empty_source"),
                "events": MetadataValue.int(0),
            }
        )

    with database.transaction() as cur:
        cur.execute("DELETE FROM public.intelligence_events")
        execute_batch(cur, _INSERT_SQL, [_insert_tuple(event) for event in events], page_size=500)

    by_category = {
        "parcel": sum(event["category"] == "parcel" for event in events),
        "development": sum(event["category"] == "development" for event in events),
    }
    llm_interpretations = sum(
        event["interpretation_kind"] == "llm" for event in events
    )
    context.log.info(
        "Rebuilt intelligence ledger: %d parcel, %d development, %d cached LLM interpretations",
        by_category["parcel"],
        by_category["development"],
        llm_interpretations,
    )
    return MaterializeResult(
        metadata={
            "status": MetadataValue.text("complete"),
            "events": MetadataValue.int(len(events)),
            "parcel_events": MetadataValue.int(by_category["parcel"]),
            "development_events": MetadataValue.int(by_category["development"]),
            "cached_llm_interpretations": MetadataValue.int(llm_interpretations),
        }
    )
