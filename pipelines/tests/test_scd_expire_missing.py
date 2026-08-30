"""Test SCD2 upsert with expire_missing=False for incremental loads."""

import psycopg2
import pytest

from countyiq.lib.scd import scd2_upsert

pytestmark = pytest.mark.integration


@pytest.fixture
def db_conn():
    """Connect to local Docker Postgres test database."""
    conn = psycopg2.connect(
        host="localhost",
        port=5433,
        dbname="countyiq",
        user="dagster_admin",
        password="localtest",
    )
    yield conn
    conn.close()


@pytest.fixture
def test_table(db_conn):
    """Create a temporary test table with SCD2 columns."""
    cur = db_conn.cursor()
    cur.execute("DROP TABLE IF EXISTS _test_scd2")
    cur.execute("""
        CREATE TABLE _test_scd2 (
            id TEXT NOT NULL,
            name TEXT,
            valid_from TIMESTAMPTZ DEFAULT NOW() NOT NULL,
            valid_to TIMESTAMPTZ,
            PRIMARY KEY (id, valid_from)
        )
    """)
    db_conn.commit()
    yield
    cur.execute("DROP TABLE IF EXISTS _test_scd2")
    db_conn.commit()
    cur.close()


@pytest.mark.usefixtures("test_table")
def test_expire_missing_false_preserves_absent_records(db_conn):
    """When expire_missing=False, records NOT in the incoming batch stay current."""
    cur = db_conn.cursor()

    # Seed two records
    scd2_upsert(
        cursor=cur,
        schema="public",
        table="_test_scd2",
        records=[
            {"id": "A", "name": "Alice"},
            {"id": "B", "name": "Bob"},
        ],
        key_columns=["id"],
        value_columns=["name"],
    )

    # Incremental upsert: only update A, don't mention B
    scd2_upsert(
        cursor=cur,
        schema="public",
        table="_test_scd2",
        records=[{"id": "A", "name": "Alice Updated"}],
        key_columns=["id"],
        value_columns=["name"],
        expire_missing=False,
    )

    # B should still be current (valid_to IS NULL)
    cur.execute(
        "SELECT id, name FROM _test_scd2 WHERE valid_to IS NULL ORDER BY id"
    )
    current = cur.fetchall()
    assert len(current) == 2
    assert current[0] == ("A", "Alice Updated")
    assert current[1] == ("B", "Bob")

    cur.close()
