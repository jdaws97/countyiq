"""Test-session safety net: no test may open the live ``countyiq`` database.

On 2026-09-02 an integration test whose connection defaulted to ``countyiq``
deleted all 175,935 rows of ``staging.parcels`` in the local backfill store.
Every integration test now targets ``countyiq_test``, but a default in one
module is easy to regress. This guard wraps ``psycopg2.connect`` for the whole
session and refuses the protected database names no matter which module asks,
including ``DatabaseResource`` and DSN-style connections.

Set ``COUNTYIQ_ALLOW_LIVE_DB_TESTS=1`` to bypass deliberately (for example, a
read-only smoke check against a disposable restore).
"""

from __future__ import annotations

import os

import psycopg2
import psycopg2.extensions
import pytest

PROTECTED_DATABASES = frozenset({"countyiq"})
BYPASS_ENV = "COUNTYIQ_ALLOW_LIVE_DB_TESTS"
_REAL_CONNECT = psycopg2.connect


def _requested_database(args: tuple, kwargs: dict) -> str | None:
    name = kwargs.get("dbname") or kwargs.get("database")
    if name:
        return str(name)
    dsn = kwargs.get("dsn")
    if dsn is None and args and isinstance(args[0], str):
        dsn = args[0]
    if not dsn:
        return None
    try:
        return psycopg2.extensions.parse_dsn(dsn).get("dbname")
    except Exception:  # pragma: no cover - malformed DSN fails later anyway
        return None


def guarded_connect(*args, **kwargs):
    if os.environ.get(BYPASS_ENV, "").strip() != "1":
        name = _requested_database(args, kwargs)
        if name in PROTECTED_DATABASES:
            raise RuntimeError(
                f"Tests may not connect to the live {name!r} database; use "
                f"countyiq_test (set {BYPASS_ENV}=1 to override deliberately)"
            )
    return _REAL_CONNECT(*args, **kwargs)


@pytest.fixture(autouse=True, scope="session")
def _protect_live_database():
    psycopg2.connect = guarded_connect
    try:
        yield
    finally:
        psycopg2.connect = _REAL_CONNECT
