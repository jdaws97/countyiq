import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from dagster import ConfigurableResource, InitResourceContext


class DatabaseResource(ConfigurableResource):
    """PostgreSQL connection resource for the countyiq database.

    Reads connection parameters from environment variables (set by Compose in
    production or DATABASE_* vars for local dev). Reuses a single connection
    per resource instance to avoid connection churn.
    """

    host: str = ""
    port: int = 5432
    dbname: str = ""
    user: str = ""
    password: str = ""

    def setup_for_execution(self, context: InitResourceContext) -> None:
        self._conn = None

    def _get_conn(self):
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                dbname=self.dbname,
                user=self.user,
                password=self.password,
                connect_timeout=10,
            )
            self._conn.autocommit = True
        return self._conn

    def execute(self, sql: str, params=None):
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if cur.description:
                return cur.fetchall()
            return None

    def cursor(self):
        return self._get_conn().cursor()

    @contextmanager
    def dict_cursor(self):
        """Yield a RealDictCursor bound to the shared connection.

        Use when callers need dict-row access (e.g., gather_parcel_batch_context
        passing rows to formatter functions that look up columns by name).
        The connection runs in autocommit mode, so each statement commits
        independently — this context manager does not provide transaction
        semantics, only cursor lifecycle and dict-row access.
        """
        conn = self._get_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            yield cur
        finally:
            cur.close()

    @contextmanager
    def transaction(self, *, dict_rows: bool = False):
        """Yield a cursor inside an explicit transaction.

        ``dict_rows`` is reserved for transactional workflows that must gather
        and validate named source fields before writing. Ordinary asset writes
        retain the lighter tuple cursor.
        """
        conn = self._get_conn()
        prior_autocommit = conn.autocommit
        conn.autocommit = False
        cursor_factory = psycopg2.extras.RealDictCursor if dict_rows else None
        cur = conn.cursor(cursor_factory=cursor_factory)
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.autocommit = prior_autocommit

    def teardown_after_execution(self, context: InitResourceContext) -> None:
        if self._conn and not self._conn.closed:
            self._conn.close()


def make_database_resource() -> DatabaseResource:
    """Create a DatabaseResource from environment variables."""
    return DatabaseResource(
        host=os.environ.get("DATABASE_HOST", "localhost"),
        port=int(os.environ.get("DATABASE_PORT", "5432")),
        dbname=os.environ.get("DATABASE_NAME", "countyiq"),
        user=os.environ.get("DATABASE_USER", "dagster_admin"),
        password=os.environ.get("DATABASE_PASSWORD", "localtest"),
    )
