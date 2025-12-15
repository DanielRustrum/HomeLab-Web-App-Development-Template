from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Any
from psycopg_pool import ConnectionPool
from backend.config import Settings

class Database:
    """Small psycopg pool wrapper.

    - Use `db.conn()` as a context manager to get a connection.
    - Keep SQL in Python for small apps; graduate to migrations/ORM later if needed.
    """

    def __init__(self, settings: Settings) -> None:
        self._pool = ConnectionPool(conninfo=settings.resolved_dsn, min_size=1, max_size=10, open=True)

    @contextmanager
    def conn(self) -> Iterator[Any]:
        with self._pool.connection() as conn:
            yield conn

    def close(self) -> None:
        self._pool.close()
