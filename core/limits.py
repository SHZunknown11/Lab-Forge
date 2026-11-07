"""Rate limits that survive restarts and are shared by every instance (Postgres), with an
in-memory fallback for a single machine.

Limits are kept per browser (an anonymous id the page makes up and keeps) and, with a larger
allowance, per IP address. A whole college behind one Wi-Fi address shares the IP allowance,
not one student's.
"""
from __future__ import annotations

import os
import random
import threading
import time
from collections import defaultdict, deque


class RateLimited(Exception):
    def __init__(self, bucket: str, wait: int):
        super().__init__(bucket)
        self.bucket, self.wait = bucket, wait


class MemoryLimiter:
    def __init__(self):
        self._hits: dict[tuple[str, str], deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, subject: str, bucket: str, limit: int, window: int, consume: bool = True) -> int:
        now = time.time()
        with self._lock:
            q = self._hits[(subject, bucket)]
            while q and q[0] < now - window:
                q.popleft()
            if len(q) >= limit:
                raise RateLimited(bucket, int(q[0] + window - now) + 1)
            if consume:
                q.append(now)
            return limit - len(q)

    def remaining(self, subject: str, bucket: str, limit: int, window: int) -> int:
        now = time.time()
        with self._lock:
            q = self._hits[(subject, bucket)]
            return max(0, limit - sum(1 for t in q if t >= now - window))

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()


class PostgresLimiter:
    def __init__(self, url: str):
        self.url = url
        self.fallback = MemoryLimiter()  # used while the database is unreachable

    def hit(self, subject: str, bucket: str, limit: int, window: int, consume: bool = True) -> int:
        from core.db import connect

        try:
            with connect(self.url) as conn:
                if random.random() < 0.01:  # keep the table small
                    conn.execute("DELETE FROM labforge_hits WHERE ts < now() - interval '2 days'")
                row = conn.execute(
                    "SELECT count(*), extract(epoch FROM min(ts)) FROM labforge_hits "
                    "WHERE subject = %s AND bucket = %s AND ts > now() - make_interval(secs => %s)",
                    (subject, bucket, window)).fetchone()
                used, oldest = int(row[0]), row[1]
                if used >= limit:
                    wait = int(float(oldest) + window - time.time()) + 1 if oldest else window
                    raise RateLimited(bucket, max(1, wait))
                if consume:
                    conn.execute("INSERT INTO labforge_hits (subject, bucket) VALUES (%s, %s)", (subject, bucket))
                    used += 1
                return limit - used
        except RateLimited:
            raise
        except Exception as exc:  # noqa: BLE001 - an outage must not block every student
            print(f"[limits] database unavailable, using memory: {type(exc).__name__}: {exc}")
            return self.fallback.hit(subject, bucket, limit, window, consume)

    def remaining(self, subject: str, bucket: str, limit: int, window: int) -> int:
        from core.db import connect

        try:
            with connect(self.url) as conn:
                row = conn.execute(
                    "SELECT count(*) FROM labforge_hits WHERE subject = %s AND bucket = %s "
                    "AND ts > now() - make_interval(secs => %s)", (subject, bucket, window)).fetchone()
            return max(0, limit - int(row[0]))
        except Exception:  # noqa: BLE001
            return self.fallback.remaining(subject, bucket, limit, window)

    def clear(self) -> None:
        self.fallback.clear()


def make_limiter():
    from core.db import database_url

    url = database_url()
    return PostgresLimiter(url) if url else MemoryLimiter()


# ── the limits themselves ─────────────────────────────────────────
# (bucket, per browser per window, per IP per window, window seconds). Env overrides where useful.

def _env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def limits() -> dict[str, tuple[int, int, int]]:
    ai = _env("LABFORGE_AI_DAILY_LIMIT", 10)
    return {
        "ai": (ai, _env("LABFORGE_AI_DAILY_PER_IP", ai * 6), 86400),
        "drafts": (30, 120, 3600),
        "runs": (_env("LABFORGE_RUNS_PER_HOUR", 30), 150, 3600),
        "edited_runs": (_env("LABFORGE_EDITED_RUNS_PER_HOUR", 10), 40, 3600),
        "renders": (40, 200, 3600),
        "uploads": (60, 240, 3600),
        "feedback": (20, 80, 3600),
        "explain": (_env("LABFORGE_EXPLAIN_DAILY_LIMIT", 20), 120, 86400),
        "deletes": (30, 120, 3600),
    }
