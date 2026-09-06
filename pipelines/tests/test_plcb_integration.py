# pipelines/tests/test_plcb_integration.py
"""Integration test: materialize plcb_licenses against local Docker Postgres.

Requires: docker compose up -d postgres-test && alembic upgrade head
"""

import pytest
import psycopg2


# Skip if Docker Postgres is not running
def _pg_available():
    try:
        conn = psycopg2.connect(
            host="localhost",
            port=5433,
            dbname="countyiq_test",
            user="dagster_admin",
            password="localtest",
            connect_timeout=3,
        )
        conn.close()
        return True
    except Exception:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _pg_available(),
        reason="Local Docker Postgres not running on port 5433",
    ),
]


def test_plcb_parser_to_staging():
    """Parse real fixture CSV and SCD2 upsert to staging.plcb_licenses."""
    from pathlib import Path
    from countyiq.lib.parsers.plcb import parse_plcb_csv
    from countyiq.lib.scd import scd2_upsert

    fixture = (Path(__file__).parent / "fixtures" / "plcb_sample.csv").read_text()
    records = parse_plcb_csv(fixture, county_filter="York County")
    assert len(records) == 5

    conn = psycopg2.connect(
        host="localhost",
        port=5433,
        dbname="countyiq_test",
        user="dagster_admin",
        password="localtest",
    )
    conn.autocommit = True
    cur = conn.cursor()
    # Clean slate — remove any leftover data from previous runs
    cur.execute("DELETE FROM staging.plcb_licenses")
    conn.autocommit = False
    try:
        stats = scd2_upsert(
            cursor=cur,
            schema="staging",
            table="plcb_licenses",
            records=records,
            key_columns=["lid"],
            value_columns=[
                "license_number",
                "license_type",
                "status",
                "licensee",
                "premises_name",
                "premises_address",
                "premises_mailing_address",
                "premises_owner",
                "premises_manager",
                "municipality",
                "last_issue_date",
                "expiration_date",
            ],
        )
        conn.commit()

        assert stats["inserted"] == 5
        assert stats["expired"] == 0

        # Verify data landed
        cur.execute("SELECT COUNT(*) FROM staging.plcb_licenses WHERE valid_to IS NULL")
        count = cur.fetchone()[0]
        assert count >= 5

        # Verify a specific record
        cur.execute(
            "SELECT licensee, municipality FROM staging.plcb_licenses WHERE lid = '54316' AND valid_to IS NULL"
        )
        row = cur.fetchone()
        assert row[0] == "SUSQUEHANNA FISH AND GAME ASSOCIATION INC"
        assert row[1] == "Hellam Twp"

    finally:
        # Clean up test data (rollback clears failed transaction state if needed)
        conn.rollback()
        cur.execute("DELETE FROM staging.plcb_licenses")
        conn.commit()
        cur.close()
        conn.close()
