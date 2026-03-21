"""Integration test: parcels parser + SCD2 upsert against local Docker Postgres.

Requires: docker compose up -d postgres-test (with init.sql + alembic applied)
"""

import json
import os
from pathlib import Path

import psycopg2
import pytest

from countyiq.lib.parsers.parcels import parse_parcels_features
from countyiq.lib.scd import scd2_upsert

FIXTURES_DIR = Path(__file__).parent / "fixtures"

DB_PARAMS = {
    "host": os.environ.get("DATABASE_HOST", "localhost"),
    "port": int(os.environ.get("DATABASE_PORT", "5433")),
    "dbname": os.environ.get("DATABASE_NAME", "countyiq"),
    "user": os.environ.get("DATABASE_USER", "dagster_admin"),
    "password": os.environ.get("DATABASE_PASSWORD", "localtest"),
}


@pytest.fixture
def db_conn():
    conn = psycopg2.connect(**DB_PARAMS)
    conn.autocommit = True
    yield conn
    # Clean up test data
    with conn.cursor() as cur:
        cur.execute("DELETE FROM staging.parcels")
    conn.close()


def test_scd2_upsert_inserts_new_records(db_conn):
    raw = json.loads((FIXTURES_DIR / "parcels_sample.json").read_text())
    records = parse_parcels_features(raw)

    key_columns = ["pidn"]
    value_columns = ["owner_full", "propadr", "aprtotal", "municipality"]

    cur = db_conn.cursor()
    stats = scd2_upsert(cur, "staging", "parcels", records, key_columns, value_columns)
    cur.close()

    assert stats["inserted"] == 2
    assert stats["expired"] == 0

    cur = db_conn.cursor()
    cur.execute("SELECT COUNT(*) FROM staging.parcels WHERE valid_to IS NULL")
    assert cur.fetchone()[0] == 2
    cur.close()


def test_scd2_upsert_detects_changes(db_conn):
    raw = json.loads((FIXTURES_DIR / "parcels_sample.json").read_text())
    records = parse_parcels_features(raw)

    key_columns = ["pidn"]
    value_columns = ["owner_full", "propadr", "aprtotal", "municipality"]

    # Initial insert
    cur = db_conn.cursor()
    scd2_upsert(cur, "staging", "parcels", records, key_columns, value_columns)
    cur.close()

    # Modify one record's owner
    records[0]["owner_full"] = "JONES ROBERT"

    # Second upsert — should expire old, insert new
    cur = db_conn.cursor()
    stats = scd2_upsert(cur, "staging", "parcels", records, key_columns, value_columns)
    cur.close()

    assert stats["inserted"] == 1  # Changed record re-inserted
    assert stats["expired"] == 1   # Old version expired

    # Should have 3 total rows (2 current + 1 expired)
    cur = db_conn.cursor()
    cur.execute("SELECT COUNT(*) FROM staging.parcels")
    assert cur.fetchone()[0] == 3

    cur.execute("SELECT COUNT(*) FROM staging.parcels WHERE valid_to IS NULL")
    assert cur.fetchone()[0] == 2

    # Current owner for first parcel should be JONES ROBERT
    cur.execute(
        "SELECT owner_full FROM staging.parcels WHERE pidn = %s AND valid_to IS NULL",
        ("4300006006500",),
    )
    assert cur.fetchone()[0] == "JONES ROBERT"
    cur.close()


def test_scd2_upsert_no_change_is_noop(db_conn):
    raw = json.loads((FIXTURES_DIR / "parcels_sample.json").read_text())
    records = parse_parcels_features(raw)

    key_columns = ["pidn"]
    value_columns = ["owner_full", "propadr", "aprtotal", "municipality"]

    cur = db_conn.cursor()
    scd2_upsert(cur, "staging", "parcels", records, key_columns, value_columns)
    cur.close()

    # Same data again — nothing should change
    cur = db_conn.cursor()
    stats = scd2_upsert(cur, "staging", "parcels", records, key_columns, value_columns)
    cur.close()

    assert stats["inserted"] == 0
    assert stats["expired"] == 0

    cur = db_conn.cursor()
    cur.execute("SELECT COUNT(*) FROM staging.parcels")
    assert cur.fetchone()[0] == 2  # No new rows
    cur.close()
