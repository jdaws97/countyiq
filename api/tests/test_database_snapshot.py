"""Profile reads use one snapshot while pooled write cursors remain usable."""
import psycopg2
import pytest

from api.lib.database import get_cursor
from api.tests.conftest import DB_ENV, TEST_PIDN


def test_profile_snapshot_does_not_mix_refresh_versions(client):
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as writer:
        with writer.cursor() as cursor:
            cursor.execute("SELECT aprtotal FROM staging.parcels WHERE pidn=%s AND valid_to IS NULL", (TEST_PIDN,))
            original = cursor.fetchone()[0]
    try:
        with get_cursor(snapshot=True) as cursor:
            cursor.execute("SELECT aprtotal FROM staging.parcels WHERE pidn=%s AND valid_to IS NULL", (TEST_PIDN,))
            assert cursor.fetchone()["aprtotal"] == original
            with psycopg2.connect(DB_ENV["DATABASE_URL"]) as writer:
                with writer.cursor() as concurrent:
                    concurrent.execute("UPDATE staging.parcels SET aprtotal=%s WHERE pidn=%s AND valid_to IS NULL", (original+1,TEST_PIDN))
            cursor.execute("SELECT aprtotal FROM staging.parcels WHERE pidn=%s AND valid_to IS NULL", (TEST_PIDN,))
            assert cursor.fetchone()["aprtotal"] == original
            cursor.execute("SHOW transaction_read_only")
            assert next(iter(cursor.fetchone().values())) == "on"
        with get_cursor(snapshot=True) as cursor:
            cursor.execute("SELECT aprtotal FROM staging.parcels WHERE pidn=%s AND valid_to IS NULL", (TEST_PIDN,))
            assert cursor.fetchone()["aprtotal"] == original+1
        with pytest.raises(psycopg2.errors.ReadOnlySqlTransaction):
            with get_cursor(snapshot=True) as cursor:
                cursor.execute("CREATE TABLE public.review_forbidden_snapshot_write (id integer)")
        # Transaction-local options must not leak into another pool checkout.
        with get_cursor(write=True) as cursor:
            cursor.execute("SHOW transaction_read_only")
            assert next(iter(cursor.fetchone().values())) == "off"
            cursor.execute("SHOW transaction_isolation")
            assert next(iter(cursor.fetchone().values())) == "read committed"
    finally:
        with psycopg2.connect(DB_ENV["DATABASE_URL"]) as writer:
            with writer.cursor() as cursor:
                cursor.execute("UPDATE staging.parcels SET aprtotal=%s WHERE pidn=%s AND valid_to IS NULL", (original,TEST_PIDN))


def test_snapshot_rejects_write_mode_before_database_checkout():
    with pytest.raises(ValueError, match="read-only"):
        with get_cursor(snapshot=True, write=True):
            pass
