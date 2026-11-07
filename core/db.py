"""Shared Postgres access for state that must survive restarts and work across instances.

LABFORGE_DATABASE_URL (or, for older setups, LABFORGE_LOG_DB_URL) turns on Postgres for the
draft cache, rate limits and the activity log. Without it everything falls back to files and
process memory, which is fine on one machine and lost on hosts whose disk is wiped.
"""
from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from typing import Iterator

_pools: dict[str, object] = {}
_lock = threading.Lock()
_ready: set[str] = set()

SCHEMA = """
CREATE TABLE IF NOT EXISTS labforge_cache (
    kind TEXT NOT NULL,
    key TEXT NOT NULL,
    value JSONB NOT NULL,
    created TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (kind, key)
);
CREATE TABLE IF NOT EXISTS labforge_hits (
    id BIGSERIAL PRIMARY KEY,
    subject TEXT NOT NULL,
    bucket TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS labforge_hits_lookup ON labforge_hits (subject, bucket, ts);
"""


def database_url() -> str:
    return (os.environ.get("LABFORGE_DATABASE_URL") or os.environ.get("LABFORGE_LOG_DB_URL") or "").strip()


def _pool(url: str):
    with _lock:
        pool = _pools.get(url)
        if pool is None:
            from psycopg_pool import ConnectionPool

            size = max(1, int(os.environ.get("LABFORGE_DB_POOL_SIZE", "4") or 4))
            pool = ConnectionPool(url, min_size=0, max_size=size, open=True, timeout=10,
                                  kwargs={"autocommit": True, "connect_timeout": 10})
            _pools[url] = pool
        return pool


@contextmanager
def connect(url: str | None = None) -> Iterator:
    """A pooled autocommit connection; the tables exist by the time it's handed out."""
    url = url or database_url()
    if not url:
        raise RuntimeError("No database configured (LABFORGE_DATABASE_URL).")
    with _pool(url).connection() as conn:
        if url not in _ready:
            conn.execute(SCHEMA)
            _ready.add(url)
        yield conn


def close_all() -> None:
    with _lock:
        for pool in _pools.values():
            try:
                pool.close()  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass
        _pools.clear()
        _ready.clear()
