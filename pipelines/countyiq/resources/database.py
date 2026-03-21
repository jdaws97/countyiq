import os

import psycopg2
from dagster import ConfigurableResource, InitResourceContext


class DatabaseResource(ConfigurableResource):
    """PostgreSQL connection resource for the countyiq database.

    Reads connection parameters from environment variables (set by .env on EC2,
    or DATABASE_* vars for local dev). Reuses a single connection per resource
    instance to avoid connection churn.
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

    def execute_many(self, sql: str, params_list):
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.executemany(sql, params_list)

    def cursor(self):
        return self._get_conn().cursor()

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
