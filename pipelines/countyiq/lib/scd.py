"""SCD Type 2 upsert helper for staging tables.

Implements Slowly Changing Dimension Type 2:
  1. Expire changed/deleted records (SET valid_to = NOW())
  2. Insert new or changed records (valid_from = NOW(), valid_to = NULL)
  3. Skip unchanged records

Supports both list and iterable input for memory-efficient streaming.
"""

import json
from typing import Iterable

from dagster import get_dagster_logger
from psycopg2.extras import execute_batch


BATCH_SIZE = 1000


def scd2_upsert(
    cursor,
    schema: str,
    table: str,
    records: list[dict] | Iterable[dict],
    key_columns: list[str],
    value_columns: list[str],
    expire_missing: bool = True,
):
    """Perform an SCD Type 2 upsert inside an explicit transaction.

    Args:
        records: List or iterable of dicts. If iterable, records are streamed
                 into the temp table in chunks to minimize peak memory.
    """
    log = get_dagster_logger()
    fqn = f"{schema}.{table}"
    all_columns = key_columns + value_columns

    conn = cursor.connection
    was_autocommit = conn.autocommit
    if was_autocommit:
        conn.autocommit = False

    try:
        result = _scd2_upsert_inner(
            cursor, fqn, all_columns, key_columns, value_columns,
            records, log, expire_missing,
        )
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        if was_autocommit:
            conn.autocommit = True


def _scd2_upsert_inner(cursor, fqn, all_columns, key_columns, value_columns, records, log, expire_missing):
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

    log.info(f"Staged {total_staged} records into temp table")

    # Expire + insert (same as before)
    key_join = " AND ".join(f"c.{k} = t.{k}" for k in key_columns)
    value_diff = " OR ".join(
        f"c.{v}::text IS DISTINCT FROM t.{v}::text" for v in value_columns
    )

    if expire_missing:
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

    cursor.execute(f"DROP TABLE IF EXISTS {temp_table}")
    cursor.connection.commit()

    unchanged = total_staged - inserted
    log.info(
        f"SCD2 upsert {fqn}: {inserted} inserted, {expired} expired, "
        f"{unchanged} unchanged out of {total_staged} incoming"
    )
    return {"inserted": inserted, "expired": expired, "unchanged": unchanged}
