"""PostgreSQL client for the Auto Reranker plugin.

Owns the connection pool, health check, and the `PGUnavailable` sentinel
exception used by the degradation paths in `config_loader`.
"""

import logging
import os
from typing import Any, Optional

logger = logging.getLogger("searx.plugins.auto_reranker.pg_client")


class PGUnavailable(RuntimeError):
    """Raised when PostgreSQL is unreachable / query fails."""


class PGClient:
    """Thin wrapper around a psycopg2 connection pool.

    Connection parameters are resolved (in order) from:
      1. explicit kwargs (used in tests)
      2. the ``auto_reranker`` settings dict passed by SearXNG
      3. environment variables (DATABASE_URL / PGHOST / ...)
    """

    def __init__(
        self,
        dsn: Optional[str] = None,
        *,
        host: Optional[str] = None,
        port: Optional[int] = None,
        dbname: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        min_conn: int = 1,
        max_conn: int = 4,
    ) -> None:
        self._dsn = dsn or os.getenv("DATABASE_URL") or os.getenv("AUTORERANKER_DATABASE_URL")
        self._host = host or os.getenv("PGHOST", "localhost")
        self._port = int(port or os.getenv("PGPORT", "5432"))
        self._dbname = dbname or os.getenv("PGDATABASE", "auto_reranker")
        self._user = user or os.getenv("PGUSER", "auto_reranker")
        self._password = password or os.getenv("PGPASSWORD", "")
        self._min_conn = min_conn
        self._max_conn = max_conn
        self._pool: Any = None  # psycopg2.pool.SimpleConnectionPool

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #
    def _ensure_pool(self) -> Any:
        if self._pool is not None:
            return self._pool
        try:
            import psycopg2.pool  # type: ignore
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise PGUnavailable("psycopg2 is not installed") from exc
        try:
            kwargs = dict(
                minconn=self._min_conn,
                maxconn=self._max_conn,
                host=self._host,
                port=self._port,
                dbname=self._dbname,
                user=self._user,
                password=self._password,
            )
            if self._dsn:
                # Prefer DSN if supplied: it can encode all params.
                self._pool = psycopg2.pool.SimpleConnectionPool(self._min_conn, self._max_conn, self._dsn)
            else:
                self._pool = psycopg2.pool.SimpleConnectionPool(self._min_conn, self._max_conn, **kwargs)
        except Exception as exc:  # noqa: BLE001 - any connect error -> unavailable
            raise PGUnavailable(f"cannot connect to PostgreSQL: {exc}") from exc
        return self._pool

    def close(self) -> None:
        if self._pool is not None:
            try:
                self._pool.closeall()
            finally:
                self._pool = None

    # ------------------------------------------------------------------ #
    # query helpers
    # ------------------------------------------------------------------ #
    def health(self) -> bool:
        """Return True if a round-trip `SELECT 1` succeeds."""
        try:
            self.fetchone("SELECT 1")
            return True
        except PGUnavailable:
            return False

    def fetchall(self, sql: str, params: Optional[tuple] = None) -> list[dict]:
        return self._run(sql, params or (), many=True)

    def fetchone(self, sql: str, params: Optional[tuple] = None) -> Optional[dict]:
        rows = self._run(sql, params or (), many=False)
        return rows[0] if rows else None

    def execute(self, sql: str, params: Optional[tuple] = None) -> None:
        self._run(sql, params or (), many=False, write=True)

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #
    def _run(self, sql: str, params: tuple, *, many: bool, write: bool = False) -> list[dict]:
        pool = self._ensure_pool()
        conn = None
        try:
            conn = pool.getconn()
            with conn.cursor() as cur:
                cur.execute(sql, params)
                if write:
                    conn.commit()
                    return []
                if cur.description is None:
                    return []
                cols = [c[0] for c in cur.description]
                rows = cur.fetchall()
                out = [dict(zip(cols, row)) for row in rows]
                return out if many else out[:1]
        except PGUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:  # noqa: BLE001
                    pass
            logger.warning("PG query failed: %s", exc)
            raise PGUnavailable(str(exc)) from exc
        finally:
            if conn is not None:
                pool.putconn(conn)
