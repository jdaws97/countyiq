"""Derive explicit parcel events from staging.parcels SCD2 version history.

Scans consecutive version pairs (old.valid_to = new.valid_from — both stamped
by the same NOW() inside the parcels_arcgis transaction) whose tracked fields
differ, classifies each diff with lib.parcel_events, and upserts into
public.parcel_events. The full history is rescanned every run and the unique
(pidn, event_type, new_version_from) constraint makes the insert idempotent,
so this asset doubles as its own backfill.

This is the recorder-portal replacement: transfer intelligence comes from
county-published parcel diffs only. Events say what the county's record
changed — never an inferred mortgage, lien, or title fact.
"""

import json

from dagster import (
    asset,
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
)
from psycopg2.extras import execute_batch

from countyiq.lib.parcel_events import TRACKED_FIELDS, classify_parcel_change
from countyiq.resources.database import DatabaseResource

_INSERT_SQL = """
    INSERT INTO public.parcel_events
        (pidn, event_type, confidence, event_date, detected_at,
         old_version_from, new_version_from, evidence)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT ON CONSTRAINT uq_parcel_events_version DO NOTHING
"""

_FETCH_BATCH = 5000


def _pairs_query() -> str:
    old_cols = ", ".join(f"o.{f} AS o_{f}" for f in TRACKED_FIELDS)
    new_cols = ", ".join(f"n.{f} AS n_{f}" for f in TRACKED_FIELDS)
    any_diff = " OR ".join(
        f"o.{f}::text IS DISTINCT FROM n.{f}::text" for f in TRACKED_FIELDS
    )
    return f"""
        SELECT n.pidn, o.valid_from AS old_version_from,
               n.valid_from AS new_version_from,
               {old_cols}, {new_cols}
        FROM staging.parcels n
        JOIN staging.parcels o
          ON o.pidn = n.pidn AND o.valid_to = n.valid_from
        WHERE {any_diff}
        ORDER BY n.pidn, n.valid_from
    """


@asset(
    group_name="enrichment",
    deps=["parcels_arcgis"],
    description="Transfer/value/structure events derived from parcel SCD2 diffs → public.parcel_events",
    kinds={"postgres"},
)
def parcel_events(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> MaterializeResult:
    cur = database.cursor()
    conn = cur.connection
    was_autocommit = conn.autocommit
    if was_autocommit:
        conn.autocommit = False

    pairs_seen = 0
    events_built = 0
    by_type: dict[str, int] = {}

    try:
        # Named cursor streams version pairs without materializing all of them.
        fetch_cur = conn.cursor(name="parcel_events_pairs")
        fetch_cur.itersize = _FETCH_BATCH
        fetch_cur.execute(_pairs_query())

        rows_to_insert = []
        for row in fetch_cur:
            pairs_seen += 1
            pidn, old_version_from, new_version_from = row[0], row[1], row[2]
            n = len(TRACKED_FIELDS)
            old = dict(zip(TRACKED_FIELDS, row[3:3 + n]))
            new = dict(zip(TRACKED_FIELDS, row[3 + n:3 + 2 * n]))

            for event in classify_parcel_change(old, new):
                events_built += 1
                by_type[event["event_type"]] = by_type.get(event["event_type"], 0) + 1
                rows_to_insert.append((
                    pidn,
                    event["event_type"],
                    event["confidence"],
                    event["event_date"],
                    new_version_from,  # detected_at
                    old_version_from,
                    new_version_from,
                    json.dumps(event["evidence"]),
                ))

            if len(rows_to_insert) >= _FETCH_BATCH:
                execute_batch(cur, _INSERT_SQL, rows_to_insert, page_size=1000)
                rows_to_insert = []

        if rows_to_insert:
            execute_batch(cur, _INSERT_SQL, rows_to_insert, page_size=1000)

        fetch_cur.close()
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        if was_autocommit:
            conn.autocommit = True
        cur.close()

    total_rows = database.execute("SELECT COUNT(*) FROM public.parcel_events")
    total = total_rows[0][0] if total_rows else 0
    context.log.info(
        f"Scanned {pairs_seen:,} changed version pairs → {events_built:,} events "
        f"({by_type}); table now holds {total:,} rows"
    )

    return MaterializeResult(
        metadata={
            "version_pairs_scanned": MetadataValue.int(pairs_seen),
            "events_classified": MetadataValue.int(events_built),
            "events_by_type": MetadataValue.json(by_type),
            "table_total": MetadataValue.int(total),
        }
    )
