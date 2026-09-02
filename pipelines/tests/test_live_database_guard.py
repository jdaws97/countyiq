"""The session-wide guard refuses the live database before any socket opens."""

import psycopg2
import pytest

from countyiq.resources.database import DatabaseResource


def test_keyword_connection_to_live_database_is_refused(monkeypatch) -> None:
    monkeypatch.delenv("COUNTYIQ_ALLOW_LIVE_DB_TESTS", raising=False)
    with pytest.raises(RuntimeError, match="live 'countyiq' database"):
        psycopg2.connect(host="localhost", port=1, dbname="countyiq", user="x", password="y")


def test_dsn_connection_to_live_database_is_refused(monkeypatch) -> None:
    monkeypatch.delenv("COUNTYIQ_ALLOW_LIVE_DB_TESTS", raising=False)
    with pytest.raises(RuntimeError, match="live 'countyiq' database"):
        psycopg2.connect("postgresql://x:y@localhost:1/countyiq")


def test_database_resource_is_covered_by_the_guard(monkeypatch) -> None:
    monkeypatch.delenv("COUNTYIQ_ALLOW_LIVE_DB_TESTS", raising=False)
    resource = DatabaseResource(
        host="localhost", port=1, dbname="countyiq", user="x", password="y"
    )
    resource._conn = None  # what setup_for_execution does under Dagster
    with pytest.raises(RuntimeError, match="live 'countyiq' database"):
        resource.execute("SELECT 1")


def test_test_database_name_passes_through(monkeypatch) -> None:
    monkeypatch.delenv("COUNTYIQ_ALLOW_LIVE_DB_TESTS", raising=False)
    # Port 1 is closed, so the real driver fails with an OperationalError,
    # which proves the guard let the call through instead of refusing it.
    with pytest.raises(psycopg2.OperationalError):
        psycopg2.connect(
            host="127.0.0.1", port=1, dbname="countyiq_test", user="x", password="y",
            connect_timeout=1,
        )
