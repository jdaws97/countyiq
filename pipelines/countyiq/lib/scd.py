"""SCD Type 2 upsert helper for staging tables.

Implements Slowly Changing Dimension Type 2:
  1. Expire changed/deleted records (SET valid_to = NOW())
  2. Insert new or changed records (valid_from = NOW(), valid_to = NULL)
  3. Skip unchanged records
"""

import json

from dagster import get_dagster_logger


def scd2_upsert(
    cursor,
    schema: str,
    table: str,
    records: list[dict],
    key_columns: list[str],
    value_columns: list[str],
):
    """Perform an SCD Type 2 upsert inside an explicit transaction.

    The expire + insert steps run atomically — if the process crashes between
    them, the transaction rolls back and no data is lost. The caller should NOT
    have autocommit=True on the connection; this function manages its own
    BEGIN/COMMIT/ROLLBACK.

    Args:
        cursor: psycopg2 cursor (connection should have autocommit=False, or
                this function will temporarily disable it)
        schema: Schema name (e.g. "staging")
        table: Table name (e.g. "parcels")
        records: List of dicts with column values
        key_columns: Columns that identify a unique record (e.g. ["pidn"])
        value_columns: Columns to compare for changes (non-key, non-SCD columns)
    """
    log = get_dagster_logger()
    if not records:
        log.warning(f"No records to upsert into {schema}.{table}")
        return {"inserted": 0, "expired": 0, "unchanged": 0}

    fqn = f"{schema}.{table}"
    all_columns = key_columns + value_columns

    # Ensure we're in a transaction (disable autocommit if it was on)
    conn = cursor.connection
    was_autocommit = conn.autocommit
    if was_autocommit:
        conn.autocommit = False

    try:
        return _scd2_upsert_inner(cursor, fqn, all_columns, key_columns, value_columns, records, log)
    except Exception:
        conn.rollback()
        raise
    finally:
        if was_autocommit:
            conn.autocommit = True


def _scd2_upsert_inner(cursor, fqn, all_columns, key_columns, value_columns, records, log):
    """Inner implementation — runs inside a transaction managed by scd2_upsert."""

    # Build a temp table cloned from the target (inherits column types)
    table_name = fqn.split(".")[-1]
    temp_table = f"_tmp_{table_name}"
    cursor.execute(f"DROP TABLE IF EXISTS {temp_table}")
    cursor.execute(f"CREATE TEMP TABLE {temp_table} (LIKE {fqn} INCLUDING DEFAULTS)")

    # Bulk insert into temp table
    placeholders = ", ".join(["%s"] * len(all_columns))
    insert_sql = f"INSERT INTO {temp_table} ({', '.join(all_columns)}) VALUES ({placeholders})"
    rows = []
    for rec in records:
        row = []
        for col in all_columns:
            val = rec.get(col)
            if isinstance(val, (dict, list)):
                val = json.dumps(val)
            row.append(val)
        rows.append(row)
    cursor.executemany(insert_sql, rows)

    key_join = " AND ".join(f"c.{k} = t.{k}" for k in key_columns)
    value_diff = " OR ".join(
        f"c.{v}::text IS DISTINCT FROM t.{v}::text" for v in value_columns
    )

    # Step 1: Expire current records that have changed or been deleted
    expire_sql = f"""
        UPDATE {fqn} c SET valid_to = NOW()
        WHERE c.valid_to IS NULL
        AND (
            -- Changed: key exists in incoming but values differ
            EXISTS (
                SELECT 1 FROM {temp_table} t
                WHERE {key_join} AND ({value_diff})
            )
            OR
            -- Deleted: key not in incoming data
            NOT EXISTS (
                SELECT 1 FROM {temp_table} t WHERE {key_join}
            )
        )
    """
    cursor.execute(expire_sql)
    expired = cursor.rowcount

    # Step 2: Insert new or changed records (not already current)
    col_list = ", ".join(all_columns)
    insert_new_sql = f"""
        INSERT INTO {fqn} ({col_list}, valid_from)
        SELECT {', '.join(f't.{c}' for c in all_columns)}, NOW()
        FROM {temp_table} t
        WHERE NOT EXISTS (
            SELECT 1 FROM {fqn} c
            WHERE c.valid_to IS NULL AND {key_join}
        )
    """
    cursor.execute(insert_new_sql)
    inserted = cursor.rowcount

    cursor.execute(f"DROP TABLE IF EXISTS {temp_table}")

    # Commit the transaction — expire + insert are now atomic
    cursor.connection.commit()

    unchanged = len(records) - inserted
    log.info(
        f"SCD2 upsert {fqn}: {inserted} inserted, {expired} expired, "
        f"{unchanged} unchanged out of {len(records)} incoming"
    )
    return {"inserted": inserted, "expired": expired, "unchanged": unchanged}
