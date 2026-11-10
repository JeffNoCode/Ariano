from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://ariano:ariano@localhost:5432/ariano"
)
POOL_MIN = int(os.environ.get("ARIANO_POOL_MIN", "1"))
POOL_MAX = int(os.environ.get("ARIANO_POOL_MAX", "10"))

_pool: ConnectionPool | None = None


def open_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            DATABASE_URL,
            min_size=POOL_MIN,
            max_size=POOL_MAX,
            kwargs={"row_factory": dict_row},
            # Bancos gerenciados (Neon) derrubam conexões ociosas: testa cada
            # conexão antes de entregá-la e descarta as que ficaram paradas.
            check=ConnectionPool.check_connection,
            max_idle=float(os.environ.get("ARIANO_POOL_MAX_IDLE", "120")),
            open=True,
        )
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def connection() -> Iterator:
    pool = open_pool()
    with pool.connection() as conn:
        yield conn
