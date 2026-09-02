"""SCD Type 2 upsert helper for staging tables.

Implements Slowly Changing Dimension Type 2:
  1. Expire changed/deleted records (SET valid_to = NOW())
  2. Insert new or changed records (valid_from = NOW(), valid_to = NULL)
  3. Skip unchanged records

Supports both list and iterable input for memory-efficient streaming.
The :func:`scd2_upsert_geom` variant adds a PostGIS geometry column for the
ArcGIS-style ``staging.*`` tables.
"""

import json
from typing import Iterable, Literal

from dagster import get_dagster_logger
from psycopg2.extras import execute_batch


BATCH_SIZE = 1000


# Geometry kinds supported by scd2_upsert_geom.
# - "multipolygon": wrap GeoJSON in ST_Multi() to coerce Polygon→MultiPolygon
#   if needed (and pass MultiPolygon through unchanged). Use for polygon rings.
# - "multilinestring": same idea but for paths.
# - "point": no ST_Multi wrapping (column is POINT, not MULTIPOINT).
GeomKind = Literal["multipolygon", "multilinestring", "point"]


def scd2_upsert(
    cursor,
    schema: str,
    table: str,
    records: list[dict] | Iterable[dict],
    key_columns: list[str],
    value_columns: list[str],
    expire_missing: bool = True,
    carry_columns: list[str] | None = None,
):
    """Perform an SCD Type 2 upsert inside an explicit transaction.

    Args:
        records: List or iterable of dicts. If iterable, records are streamed
                 into the temp table in chunks to minimize peak memory.
        carry_columns: Columns that are written with every row but never
                 count as a change. They are refreshed in place on the
                 current version instead of expiring it. Use them for
                 "observed on" style bookkeeping (a listing's report date,
                 a last-checked timestamp) so a weekly refresh of identical
                 facts does not rewrite the whole table.
    """
    log = get_dagster_logger()
    fqn = f"{schema}.{table}"
    carry_columns = list(carry_columns or [])
    overlap = set(carry_columns) & (set(key_columns) | set(value_columns))
    if overlap:
        raise ValueError(f"carry_columns overlap key/value columns: {sorted(overlap)}")
    all_columns = key_columns + value_columns + carry_columns

    conn = cursor.connection
    was_autocommit = conn.autocommit
    if was_autocommit:
        conn.autocommit = False

    try:
        result = _scd2_upsert_inner(
            cursor, fqn, all_columns, key_columns, value_columns,
            records, log, expire_missing, carry_columns,
        )
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        if was_autocommit:
            conn.autocommit = True


def _scd2_upsert_inner(
    cursor, fqn, all_columns, key_columns, value_columns, records, log,
    expire_missing, carry_columns=(),
):
    """Inner implementation — streams records into temp table in batches."""

    table_name = fqn.split(".")[-1]
    temp_table = f"_tmp_{table_name}"
    cursor.execute(f"DROP TABLE IF EXISTS {temp_table}")
    cursor.execute(f"CREATE TEMP TABLE {temp_table} (LIKE {fqn} INCLUDING DEFAULTS)")

    # Stream records into temp table in chunks
    placeholders = ", ".join(["%s"] * len(all_columns))
    insert_sql = f"INSERT INTO {temp_table} ({', '.join(all_columns)}) VALUES ({placeholders})"

    total_staged = 0
    batch = []

    for rec in records:
        row = []
        for col in all_columns:
            val = rec.get(col)
            if isinstance(val, (dict, list)):
                val = json.dumps(val)
            row.append(val)
        batch.append(row)

        if len(batch) >= BATCH_SIZE:
            execute_batch(cursor, insert_sql, batch, page_size=BATCH_SIZE)
            total_staged += len(batch)
            batch = []

    # Flush remaining
    if batch:
        execute_batch(cursor, insert_sql, batch, page_size=BATCH_SIZE)
        total_staged += len(batch)
        batch = []

    if total_staged == 0:
        log.warning(f"No records to upsert into {fqn}")
        cursor.execute(f"DROP TABLE IF EXISTS {temp_table}")
        cursor.connection.commit()
        return {"inserted": 0, "expired": 0, "unchanged": 0}

    # Index temp table on key columns for fast expire query
    key_idx_cols = ", ".join(key_columns)
    cursor.execute(f"CREATE INDEX ON {temp_table} ({key_idx_cols})")
    log.info(f"Staged {total_staged} records into temp table (indexed)")

    key_join = " AND ".join(f"c.{k} = t.{k}" for k in key_columns)
    value_diff = " OR ".join(
        f"c.{v}::text IS DISTINCT FROM t.{v}::text" for v in value_columns
    )

    if expire_missing:
        # ── DATA LOSS GUARD ──────────────────────────────────────
        # If we're about to expire-missing and the new dataset is
        # suspiciously small compared to what exists, ABORT.
        # This prevents partial fetches (network errors, rate limits)
        # from wiping existing records.
        cursor.execute(f"SELECT COUNT(*) FROM {fqn} WHERE valid_to IS NULL")
        existing_count = cursor.fetchone()[0]

        if existing_count > 100 and total_staged < existing_count * 0.5:
            cursor.execute(f"DROP TABLE IF EXISTS {temp_table}")
            cursor.connection.commit()
            msg = (
                f"DATA LOSS GUARD on {fqn}: incoming {total_staged:,} records "
                f"vs {existing_count:,} existing ({total_staged / existing_count * 100:.0f}%). "
                f"Refusing to expire — likely a partial fetch. "
                f"Set expire_missing=False to bypass."
            )
            log.error(msg)
            raise RuntimeError(msg)

        expire_sql = f"""
            UPDATE {fqn} c SET valid_to = NOW()
            WHERE c.valid_to IS NULL
            AND (
                EXISTS (SELECT 1 FROM {temp_table} t WHERE {key_join} AND ({value_diff}))
                OR NOT EXISTS (SELECT 1 FROM {temp_table} t WHERE {key_join})
            )
        """
    else:
        expire_sql = f"""
            UPDATE {fqn} c SET valid_to = NOW()
            WHERE c.valid_to IS NULL
            AND EXISTS (SELECT 1 FROM {temp_table} t WHERE {key_join} AND ({value_diff}))
        """
    cursor.execute(expire_sql)
    expired = cursor.rowcount

    col_list = ", ".join(all_columns)
    insert_new_sql = f"""
        INSERT INTO {fqn} ({col_list}, valid_from)
        SELECT {', '.join(f't.{c}' for c in all_columns)}, NOW()
        FROM {temp_table} t
        WHERE NOT EXISTS (
            SELECT 1 FROM {fqn} c WHERE c.valid_to IS NULL AND {key_join}
        )
    """
    cursor.execute(insert_new_sql)
    inserted = cursor.rowcount

    # Carry columns are bookkeeping, not facts: refresh them on the surviving
    # current version so "last seen" advances without a new SCD2 version.
    carried = 0
    if carry_columns:
        carry_set = ", ".join(f"{c} = t.{c}" for c in carry_columns)
        carry_diff = " OR ".join(
            f"c.{c}::text IS DISTINCT FROM t.{c}::text" for c in carry_columns
        )
        cursor.execute(f"""
            UPDATE {fqn} c SET {carry_set}
            FROM {temp_table} t
            WHERE c.valid_to IS NULL AND {key_join} AND ({carry_diff})
        """)
        carried = cursor.rowcount

    cursor.execute(f"DROP TABLE IF EXISTS {temp_table}")
    cursor.connection.commit()

    unchanged = total_staged - inserted
    log.info(
        f"SCD2 upsert {fqn}: {inserted} inserted, {expired} expired, "
        f"{unchanged} unchanged out of {total_staged} incoming"
        + (f", {carried} carry-column refreshes" if carry_columns else "")
    )
    return {"inserted": inserted, "expired": expired, "unchanged": unchanged}


def scd2_upsert_geom(
    cursor,
    schema: str,
    table: str,
    records: list[dict],
    key_columns: list[str],
    value_columns: list[str],
    geom_lookup: dict[str, str | None],
    geom_kind: GeomKind = "multipolygon",
    geom_key: str | None = None,
    scope_column: str | None = None,
    scope_value: object = None,
    expire_missing: bool = True,
):
    """SCD Type 2 upsert with a PostGIS geometry column.

    Mirrors :func:`scd2_upsert` but also writes the ``geom`` column from a
    pre-built ``geom_lookup``. Supports MultiPolygon, MultiLineString and
    Point geometry columns and an optional scope filter (e.g. FEMA's
    ``dfirm_id`` per-county scoping) so that running for one county does
    not expire another county's records that share the same staging table.

    Args:
        cursor: Open psycopg2 cursor.
        schema: Schema name (e.g. ``"staging"``).
        table: Table name without schema (e.g. ``"zoning"``).
        records: List of dicts containing key + value columns.
        key_columns: Primary-key columns inside ``records`` (e.g. ``["pidn"]``).
            For composite keys (e.g. ``["route", "seg"]``), the lookup key
            in ``geom_lookup`` must match what the caller chose — see
            ``geom_key``.
        value_columns: Non-key columns to compare for change detection.
        geom_lookup: Maps a per-record key (string) to a JSON-encoded GeoJSON
            geometry string, or ``None`` if no geometry exists. The lookup
            key is the value of ``record[geom_key]`` if ``geom_key`` is set,
            otherwise it is ``record[key_columns[0]]``. For composite keys,
            pass ``geom_key`` and put the same composite string in both the
            record and the lookup. Use ``json.dumps`` on the GeoJSON dict
            before inserting into the lookup.
        geom_kind: ``"multipolygon"`` (rings → MULTIPOLYGON column),
            ``"multilinestring"`` (paths → MULTILINESTRING column), or
            ``"point"`` (x/y → POINT column).
        geom_key: Record column whose value is the lookup key. Defaults to
            ``key_columns[0]`` (correct for single-column keys).
        scope_column: Optional column name to scope expire/insert queries by.
            When set, only rows where ``column = scope_value`` are considered
            "current" for the purposes of the SCD2 expire/dedup checks.
            Used by FEMA flood (multiple counties share one table, scoped
            by ``dfirm_id``).
        scope_value: The value bound for ``scope_column``. Required if
            ``scope_column`` is set.
        expire_missing: If True (default), records present in the staging
            table but missing from the incoming batch are expired. If False,
            absent records are left alone (incremental loads).

    Returns:
        ``{"inserted": int, "expired": int, "unchanged": int}``
    """
    log = get_dagster_logger()
    fqn = f"{schema}.{table}"
    all_columns = key_columns + value_columns
    table_name = table
    temp_table = f"_tmp_{table_name}"
    lookup_key = geom_key or key_columns[0]

    if scope_column is not None and scope_value is None:
        raise ValueError(
            f"scope_column={scope_column!r} requires a non-None scope_value"
        )

    if geom_kind == "point":
        geom_expr = "ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)"
    else:
        # MultiPolygon / MultiLineString — ST_Multi coerces Polygon→MultiPolygon
        # and LineString→MultiLineString, and is a no-op on already-multi types.
        geom_expr = "ST_SetSRID(ST_Multi(ST_GeomFromGeoJSON(%s)), 4326)"

    insert_sql = (
        f"INSERT INTO {temp_table} ({', '.join(all_columns)}, geom)\n"
        f"VALUES ({', '.join(['%s'] * len(all_columns))},\n"
        f"        CASE WHEN %s IS NOT NULL THEN {geom_expr} ELSE NULL END)"
    )

    conn = cursor.connection
    was_autocommit = conn.autocommit
    if was_autocommit:
        conn.autocommit = False

    try:
        cursor.execute(f"DROP TABLE IF EXISTS {temp_table}")
        cursor.execute(
            f"CREATE TEMP TABLE {temp_table} (LIKE {fqn} INCLUDING DEFAULTS)"
        )

        # Build rows for batch insert. The geom value is passed twice —
        # once for the NULL guard, once for ST_GeomFromGeoJSON.
        rows = []
        for rec in records:
            row = []
            for col in all_columns:
                val = rec.get(col)
                if isinstance(val, (dict, list)):
                    val = json.dumps(val)
                row.append(val)
            geom_json = geom_lookup.get(rec.get(lookup_key)) if rec.get(lookup_key) is not None else None
            row.extend([geom_json, geom_json])
            rows.append(row)

        total_staged = len(rows)
        if total_staged == 0:
            log.warning(f"No records to upsert into {fqn}")
            cursor.execute(f"DROP TABLE IF EXISTS {temp_table}")
            conn.commit()
            return {"inserted": 0, "expired": 0, "unchanged": 0}

        execute_batch(cursor, insert_sql, rows, page_size=500)

        # Index temp table on key columns for fast expire query
        key_idx_cols = ", ".join(key_columns)
        cursor.execute(f"CREATE INDEX ON {temp_table} ({key_idx_cols})")
        log.info(f"Staged {total_staged} records into temp table (indexed)")

        # Build join + diff predicates
        key_join = " AND ".join(f"c.{k} = t.{k}" for k in key_columns)
        value_diff = " OR ".join(
            f"c.{v}::text IS DISTINCT FROM t.{v}::text" for v in value_columns
        )

        # Scope clause used inside the expire/insert queries (table aliased "c")
        scope_clause = f" AND c.{scope_column} = %s" if scope_column else ""
        scope_params = (scope_value,) if scope_column else ()
        # Same idea but unaliased for the data-loss guard COUNT(*) below.
        guard_scope_clause = f" AND {scope_column} = %s" if scope_column else ""

        if expire_missing:
            # ── DATA LOSS GUARD ──────────────────────────────────────
            # If we're about to expire-missing and the new dataset is
            # suspiciously small compared to what exists, ABORT. This
            # prevents partial fetches (network errors, rate limits)
            # from wiping existing records. Mirror the guard in
            # scd2_upsert(). Scoped by scope_column if applicable.
            cursor.execute(
                f"SELECT COUNT(*) FROM {fqn} WHERE valid_to IS NULL{guard_scope_clause}",
                scope_params,
            )
            existing_count = cursor.fetchone()[0]

            if existing_count > 100 and total_staged < existing_count * 0.5:
                cursor.execute(f"DROP TABLE IF EXISTS {temp_table}")
                conn.commit()
                msg = (
                    f"DATA LOSS GUARD on {fqn}: incoming {total_staged:,} records "
                    f"vs {existing_count:,} existing ({total_staged / existing_count * 100:.0f}%). "
                    f"Refusing to expire — likely a partial fetch. "
                    f"Set expire_missing=False to bypass."
                )
                log.error(msg)
                raise RuntimeError(msg)

            expire_sql = f"""
                UPDATE {fqn} c SET valid_to = NOW()
                WHERE c.valid_to IS NULL{scope_clause}
                AND (
                    EXISTS (SELECT 1 FROM {temp_table} t WHERE {key_join} AND ({value_diff}))
                    OR NOT EXISTS (SELECT 1 FROM {temp_table} t WHERE {key_join})
                )
            """
        else:
            expire_sql = f"""
                UPDATE {fqn} c SET valid_to = NOW()
                WHERE c.valid_to IS NULL{scope_clause}
                AND EXISTS (SELECT 1 FROM {temp_table} t WHERE {key_join} AND ({value_diff}))
            """

        cursor.execute(expire_sql, scope_params)
        expired = cursor.rowcount

        col_list = ", ".join(all_columns)
        insert_new_sql = f"""
            INSERT INTO {fqn} ({col_list}, geom, valid_from)
            SELECT {', '.join(f't.{c}' for c in all_columns)}, t.geom, NOW()
            FROM {temp_table} t
            WHERE NOT EXISTS (
                SELECT 1 FROM {fqn} c
                WHERE c.valid_to IS NULL{scope_clause} AND {key_join}
            )
        """
        cursor.execute(insert_new_sql, scope_params)
        inserted = cursor.rowcount

        cursor.execute(f"DROP TABLE IF EXISTS {temp_table}")
        conn.commit()

        unchanged = total_staged - inserted
        log.info(
            f"SCD2 upsert (geom) {fqn}: {inserted} inserted, {expired} expired, "
            f"{unchanged} unchanged out of {total_staged} incoming"
        )
        return {"inserted": inserted, "expired": expired, "unchanged": unchanged}
    except Exception:
        conn.rollback()
        raise
    finally:
        if was_autocommit:
            conn.autocommit = True
