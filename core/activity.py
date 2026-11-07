"""Which reports were made and how their programs did: a private log for the site owner.

Rows go to Postgres when LABFORGE_DATABASE_URL (or LABFORGE_LOG_DB_URL) is set, otherwise to
artifacts/activity.jsonl. Writes happen on a background thread so a slow database never holds
up a student. Rows older than LABFORGE_LOG_DAYS (default 14) are dropped.

Personal details are kept out by default: no student names or UIDs, IP addresses only as a
salted hash (enough to spot abuse, not to identify anyone), and only the start of the sheet.
LABFORGE_LOG_PERSONAL=1 keeps names and UIDs; say so in the privacy policy if you turn it on.
"""
from __future__ import annotations

import hashlib
import json
import os
import queue
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLE = "labforge_activity"
SHEET_CHARS = 2000


def _personal() -> bool:
    return os.environ.get("LABFORGE_LOG_PERSONAL", "0") == "1"


def hash_ip(ip: str) -> str:
    if not ip:
        return ""
    salt = os.environ.get("LABFORGE_LOG_SALT") or os.environ.get("LABFORGE_ADMIN_TOKEN") or "labforge"
    return "ip-" + hashlib.sha256(f"{salt}|{ip}".encode()).hexdigest()[:12]


def scrub(row: dict) -> dict:
    row = dict(row)
    if not _personal():
        row.pop("name", None)
        row.pop("uid", None)
        if row.get("ip"):
            row["ip"] = hash_ip(row["ip"])
    if isinstance(row.get("sheet"), str):
        row["sheet"] = row["sheet"][:SHEET_CHARS]
    return row


def task_summary(tasks: list) -> list[dict]:
    return [{"title": t.get("title", ""), "language": t.get("language", ""), "status": t.get("status", ""),
             "note": (t.get("note") or "")[:300], "output": (t.get("output") or "")[-600:]} for t in tasks]


class ActivityLog:
    def __init__(self, db_url: str | None = None, path: Path | None = None, keep_days: int | None = None):
        from core.db import database_url

        self.db_url = db_url if db_url is not None else database_url()
        self.path = path or Path(os.environ.get("LABFORGE_ACTIVITY_LOG", ROOT / "artifacts" / "activity.jsonl"))
        self.keep_days = keep_days or int(os.environ.get("LABFORGE_LOG_DAYS", "14") or 14)
        self._queue: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self._ready = False
        self._thread: threading.Thread | None = None

    @property
    def storage(self) -> str:
        return "postgres" if self.db_url else "file"

    # ── writing ────────────────────────────────────────────────────
    def record(self, kind: str, job: str, **data) -> None:
        row = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "kind": kind, "job": job,
               **scrub(data)}
        if self._thread is None:
            with self._lock:
                if self._thread is None:
                    self._thread = threading.Thread(target=self._drain, daemon=True, name="activity-log")
                    self._thread.start()
        self._queue.put(row)

    def flush(self, timeout: float = 5) -> None:
        """Wait until queued rows are written (tests, shutdown)."""
        done = threading.Event()
        self._queue.put(done)
        done.wait(timeout)

    def _drain(self) -> None:
        while True:
            row = self._queue.get()
            if isinstance(row, threading.Event):
                row.set()
                continue
            try:
                self._write(row)
            except Exception as exc:  # noqa: BLE001 - the log must never break the app
                print(f"[activity] {type(exc).__name__}: {exc}")
                if self.db_url:
                    try:
                        self._write_file(row)
                    except OSError:
                        pass

    def _write(self, row: dict) -> None:
        if not self.db_url:
            self._write_file(row)
            return
        data = {k: v for k, v in row.items() if k not in ("ts", "kind", "job")}
        with self._connect() as conn:
            conn.execute(f"INSERT INTO {TABLE} (ts, kind, job, data) VALUES (%s, %s, %s, %s)",
                         (row["ts"], row["kind"], row["job"], json.dumps(data, ensure_ascii=False)))

    def _write_file(self, row: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    @contextmanager
    def _connect(self):
        from core.db import connect

        with connect(self.db_url) as conn:
            if not self._ready:
                conn.execute(f"CREATE TABLE IF NOT EXISTS {TABLE} (id BIGSERIAL PRIMARY KEY, ts TIMESTAMPTZ NOT NULL, "
                             "kind TEXT NOT NULL, job TEXT NOT NULL, data JSONB NOT NULL)")
                conn.execute(f"CREATE INDEX IF NOT EXISTS {TABLE}_ts ON {TABLE} (ts)")
                conn.execute(f"CREATE INDEX IF NOT EXISTS {TABLE}_job ON {TABLE} (job)")
                conn.execute(f"DELETE FROM {TABLE} WHERE ts < now() - make_interval(days => %s)", (self.keep_days,))
                self._ready = True
            yield conn

    # ── deleting ───────────────────────────────────────────────────
    def delete_job(self, job: str) -> None:
        """A student asked for their report to be deleted: its log rows go too."""
        self.flush()
        with self._lock:
            if self.db_url:
                with self._connect() as conn:
                    conn.execute(f"DELETE FROM {TABLE} WHERE job = %s", (job,))
            if self.path.exists():
                keep = [line for line in self.path.read_text(encoding="utf-8").splitlines()
                        if f'"job": "{job}"' not in line]
                self.path.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")

    # ── reading ────────────────────────────────────────────────────
    def rows(self, days: int = 7) -> list[dict]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        if self.db_url:
            with self._connect() as conn:
                cur = conn.execute(f"SELECT ts, kind, job, data FROM {TABLE} WHERE ts >= %s ORDER BY ts", (cutoff,))
                return [{"ts": ts.isoformat(timespec="seconds"), "kind": kind, "job": job, **data}
                        for ts, kind, job, data in cur.fetchall()]
        out = []
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                    if datetime.fromisoformat(row["ts"]) >= cutoff:
                        out.append(row)
                except (ValueError, KeyError):
                    continue
        return out

    def reports(self, days: int = 7) -> list[dict]:
        return group_reports(self.rows(days))


def group_reports(rows: list[dict]) -> list[dict]:
    """One entry per report (job): the draft, then later re-runs and downloads folded in. Newest first."""
    jobs: dict[str, dict] = {}
    for row in rows:
        rep = jobs.setdefault(row["job"], {
            "job": row["job"], "ts": row["ts"], "updated": row["ts"], "name": "", "uid": "", "ip": "",
            "title": "", "subject": "", "language": "", "cached": False, "error": "", "tasks": [],
            "seconds": None, "sheet": "", "downloads": 0, "warnings": [], "reruns": 0, "feedback": None,
            "reports": [],
        })
        rep["updated"] = row["ts"]
        for key in ("name", "uid", "ip", "title", "subject"):
            if row.get(key):
                rep[key] = row[key]
        kind = row["kind"]
        if kind == "draft":
            rep.update({k: row[k] for k in ("language", "cached", "error", "seconds", "sheet") if k in row})
            rep["tasks"] = row.get("tasks") or []
        elif kind == "run":
            i = row.get("index", -1)
            rep["reruns"] += 1
            if 0 <= i < len(rep["tasks"]):
                rep["tasks"][i] = {**rep["tasks"][i], **{k: row[k] for k in ("status", "note", "output") if k in row}}
        elif kind == "render":
            rep["downloads"] += 1
            rep["warnings"] = row.get("warnings") or []
            if row.get("tasks"):
                rep["tasks"] = row["tasks"]
        elif kind == "report":
            rep["reports"].append({k: row.get(k) for k in ("reason", "comment", "task")} | {"ts": row["ts"]})
        elif kind == "feedback":  # the latest vote counts
            rep["feedback"] = {k: row.get(k) for k in ("rating", "reasons", "comment")} | {"ts": row["ts"]}
    for rep in jobs.values():
        statuses = [t.get("status") for t in rep["tasks"]]
        rep["issue"] = (bool(rep["error"]) or any(s != "passed" for s in statuses) or not statuses
                        or (rep["feedback"] or {}).get("rating") == "down" or bool(rep["reports"]))
    return sorted(jobs.values(), key=lambda r: r["ts"], reverse=True)
