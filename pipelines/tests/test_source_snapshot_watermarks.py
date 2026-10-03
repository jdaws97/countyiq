"""Committed source data cannot regress when Dagster has no completion receipt."""

import json
import os
from datetime import UTC, datetime, timedelta

import psycopg2
import pytest
from countyiq.lib.scd import scd2_upsert, scd2_upsert_geom


@pytest.fixture
def snapshot_table():
    connection = psycopg2.connect(
        os.environ.get(
            "TEST_DATABASE_URL",
            "postgresql://dagster_admin:localtest@localhost:5433/countyiq_test",
        )
    )
    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute("""
            CREATE TABLE staging._test_source_snapshots (
                id TEXT NOT NULL,
                name TEXT NOT NULL CHECK (name <> 'reject'),
                geom geometry(Point, 4326),
                valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                valid_to TIMESTAMPTZ,
                PRIMARY KEY (id, valid_from)
            )
        """)
    yield connection
    with connection.cursor() as cursor:
        cursor.execute("DROP TABLE staging._test_source_snapshots")
        cursor.execute(
            "DELETE FROM meta.source_snapshot_watermarks WHERE dataset_key = 'staging._test_source_snapshots'"
        )
    connection.close()


def apply_snapshot(connection, acquired_at, records, with_geometry, snapshot_id=None):
    arguments = {
        "schema": "staging",
        "table": "_test_source_snapshots",
        "records": records,
        "key_columns": ["id"],
        "value_columns": ["name"],
        "snapshot_started_at": acquired_at,
        "snapshot_id": snapshot_id or acquired_at.isoformat(),
    }
    with connection.cursor() as cursor:
        if with_geometry:
            return scd2_upsert_geom(
                cursor=cursor,
                **arguments,
                geom_kind="point",
                geom_lookup={
                    record["id"]: json.dumps(
                        {"type": "Point", "coordinates": [-76.7, 39.9]}
                    )
                    for record in records
                },
            )
        return scd2_upsert(cursor=cursor, **arguments)


def stored_watermark(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT acquired_at FROM meta.source_snapshot_watermarks WHERE dataset_key = 'staging._test_source_snapshots'"
        )
        return cursor.fetchone()[0]


@pytest.mark.integration
@pytest.mark.parametrize("with_geometry", [False, True])
def test_snapshot_watermark_survives_missing_completion_and_rolls_back_failed_write(
    snapshot_table, with_geometry
):
    connection = snapshot_table
    acquired_at = datetime.now(UTC) - timedelta(minutes=5)
    initial = [{"id": "1", "name": "new"}]
    apply_snapshot(connection, acquired_at, initial, with_geometry)

    # No Dagster completion event was recorded. The database is still protected.
    with pytest.raises(RuntimeError, match="newer source snapshot"):
        apply_snapshot(
            connection,
            acquired_at - timedelta(minutes=1),
            [{"id": "1", "name": "old"}],
            with_geometry,
        )
    assert stored_watermark(connection) == acquired_at

    # The target table rejects this value after the watermark has been claimed.
    with pytest.raises(psycopg2.errors.CheckViolation):
        apply_snapshot(
            connection,
            datetime.now(UTC),
            [{"id": "1", "name": "reject"}],
            with_geometry,
        )
    assert stored_watermark(connection) == acquired_at
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT name FROM staging._test_source_snapshots WHERE valid_to IS NULL"
        )
        assert cursor.fetchall() == [("new",)]

    # A byte-equivalent retry keeps the original SCD2 history intact.
    stats = apply_snapshot(connection, acquired_at, initial, with_geometry)
    assert stats == {"inserted": 0, "expired": 0, "unchanged": 1}
    later = datetime.now(UTC)
    apply_snapshot(
        connection,
        later,
        [{"id": "1", "name": "later"}],
        with_geometry,
    )
    assert stored_watermark(connection) == later


@pytest.mark.integration
@pytest.mark.parametrize("with_geometry", [False, True])
def test_truncation_guard_does_not_commit_a_rejected_watermark(
    snapshot_table, with_geometry
):
    acquired_at = datetime.now(UTC) - timedelta(minutes=5)
    records = [{"id": str(index), "name": "retained"} for index in range(150)]
    apply_snapshot(snapshot_table, acquired_at, records, with_geometry)
    with pytest.raises(RuntimeError, match="DATA LOSS GUARD"):
        apply_snapshot(
            snapshot_table,
            datetime.now(UTC),
            records[:1],
            with_geometry,
        )
    assert stored_watermark(snapshot_table) == acquired_at


@pytest.mark.integration
@pytest.mark.parametrize("with_geometry", [False, True])
@pytest.mark.parametrize("overlap", [timedelta(), timedelta(minutes=2)])
def test_different_snapshot_captured_before_committed_write_is_rejected(
    snapshot_table, with_geometry, overlap
):
    acquired_at = datetime.now(UTC) - timedelta(minutes=5)
    apply_snapshot(
        snapshot_table, acquired_at, [{"id": "1", "name": "latest"}], with_geometry
    )
    with pytest.raises(RuntimeError, match="newer source snapshot"):
        apply_snapshot(
            snapshot_table,
            acquired_at + overlap,
            [{"id": "1", "name": "overlapping acquisition"}],
            with_geometry,
            snapshot_id="different-bundle",
        )
    assert stored_watermark(snapshot_table) == acquired_at
