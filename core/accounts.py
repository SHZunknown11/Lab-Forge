"""Accounts: sign-in with a code sent to a college email address, sessions, report credits,
and saved copies of the sessions that went wrong.

Everything lives in Postgres when LABFORGE_DATABASE_URL is set, otherwise in a SQLite file
(LABFORGE_ACCOUNTS_DB, default artifacts/accounts.sqlite3), which is fine on one machine.

- No passwords. A 6-digit code is emailed, kept only as a keyed hash, and expires in minutes.
- A session is a random token in an HttpOnly cookie; the database holds only its hash.
- Credits: LABFORGE_FREE_REPORTS free reports per LABFORGE_FREE_PERIOD (day or month), plus
  extra credits the owner grants (later: rewarded ads). Every change is one ledger row.
- A report whose programs failed or couldn't be run is copied to lf_flags (sheet, code, input,
  output, errors) so the owner can see what went wrong. Kept LABFORGE_FLAG_DAYS days.
- Rewarded ads: the page asks for a ticket, shows the ad, then claims the ticket for an extra
  report. A ticket can't be claimed sooner than an ad lasts, and only
  LABFORGE_AD_REWARDS_PER_DAY a day (0, the default, turns the whole thing off). The browser
  tells us the ad was watched and we can't check that, so the daily cap is the real limit.
- Gaps (core/gaps.py): one row per report that hit something LabForge can't do, counted per gap
  for /admin, with one alert to the owner when LABFORGE_GAP_ALERT_AT reports have hit it.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import random
import re
import secrets
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
EMAIL = re.compile(r"^[a-z0-9][a-z0-9._%+-]{0,63}@[a-z0-9][a-z0-9.-]{0,190}\.[a-z]{2,24}$")
CODE_MINUTES = 10
CODE_ATTEMPTS = 5
RESEND_SECONDS = 60
SESSION_DAYS = 30
MAX_FILE_CHARS = 20_000
MAX_SHEET_CHARS = 30_000
AD_TICKET_MINUTES = 15
GAP_DAYS = 180
IST = 19800  # days and months roll over at midnight in India

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS lf_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS lf_users (id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, "
    "created DOUBLE PRECISION NOT NULL, last_login DOUBLE PRECISION NOT NULL, last_ip TEXT NOT NULL DEFAULT '', "
    "blocked INTEGER NOT NULL DEFAULT 0)",
    "CREATE TABLE IF NOT EXISTS lf_codes (email TEXT PRIMARY KEY, code_hash TEXT NOT NULL, "
    "expires DOUBLE PRECISION NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, sent DOUBLE PRECISION NOT NULL)",
    "CREATE TABLE IF NOT EXISTS lf_sessions (token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, "
    "created DOUBLE PRECISION NOT NULL, expires DOUBLE PRECISION NOT NULL)",
    "CREATE INDEX IF NOT EXISTS lf_sessions_user ON lf_sessions (user_id)",
    "CREATE TABLE IF NOT EXISTS lf_credits (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, delta INTEGER NOT NULL, "
    "kind TEXT NOT NULL, period TEXT NOT NULL, reason TEXT NOT NULL, job TEXT NOT NULL DEFAULT '', "
    "ts DOUBLE PRECISION NOT NULL, uniq TEXT UNIQUE)",
    "CREATE INDEX IF NOT EXISTS lf_credits_user ON lf_credits (user_id, kind, period)",
    "CREATE TABLE IF NOT EXISTS lf_flags (id TEXT PRIMARY KEY, ts DOUBLE PRECISION NOT NULL, user_id TEXT NOT NULL, "
    "email TEXT NOT NULL, job TEXT NOT NULL, kind TEXT NOT NULL, reason TEXT NOT NULL, data TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS lf_flags_ts ON lf_flags (ts)",
    "CREATE TABLE IF NOT EXISTS lf_ad_tickets (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, "
    "created DOUBLE PRECISION NOT NULL, claimed INTEGER NOT NULL DEFAULT 0)",
    "CREATE TABLE IF NOT EXISTS lf_gaps (id TEXT PRIMARY KEY, key TEXT NOT NULL, kind TEXT NOT NULL, "
    "label TEXT NOT NULL, ts DOUBLE PRECISION NOT NULL, user_id TEXT NOT NULL DEFAULT '', job TEXT NOT NULL, "
    "subject TEXT NOT NULL DEFAULT '', uniq TEXT UNIQUE)",
    "CREATE INDEX IF NOT EXISTS lf_gaps_key ON lf_gaps (key, ts)",
)


class AccountError(Exception):
    """Something the student can fix; `status` is the HTTP status to answer with."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class NoCredits(Exception):
    pass


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def free_reports() -> int:
    return max(0, _env_int("LABFORGE_FREE_REPORTS", 3))


def free_period() -> str:
    return "month" if os.environ.get("LABFORGE_FREE_PERIOD", "day").strip().lower() == "month" else "day"


def _period_key(now: float | None = None) -> str:
    t = time.gmtime((now or time.time()) + IST)
    return time.strftime("%Y-%m" if free_period() == "month" else "%Y-%m-%d", t)


def ad_rewards_per_day() -> int:
    return max(0, _env_int("LABFORGE_AD_REWARDS_PER_DAY", 0))


def ad_reward() -> int:
    return max(1, _env_int("LABFORGE_AD_REWARD", 1))


def ad_min_seconds() -> int:
    return max(0, _env_int("LABFORGE_AD_MIN_SECONDS", 15))


def gap_alert_at() -> int:
    return max(1, _env_int("LABFORGE_GAP_ALERT_AT", 3))


def _day_start(now: float | None = None) -> float:
    now = now or time.time()
    return now - ((now + IST) % 86400)


def allowed_domains() -> list[str]:
    """Email domains that may sign in. `*` allows any address."""
    raw = os.environ.get("LABFORGE_EMAIL_DOMAINS", "cuchd.in")
    return [d.strip().lower().lstrip("@") for d in raw.split(",") if d.strip()]


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class _Conn:
    """The same SQL on Postgres (%s) and SQLite (?)."""

    def __init__(self, raw, sqlite: bool):
        self.raw, self.sqlite = raw, sqlite

    def execute(self, sql: str, params: tuple = ()):
        return self.raw.execute(sql.replace("%s", "?") if self.sqlite else sql, params)


class Accounts:
    def __init__(self):
        self._ready: set[str] = set()
        self._lock = threading.Lock()   # one writer at a time for check-then-insert steps
        self._secret: dict[str, bytes] = {}

    # ── storage ────────────────────────────────────────────────────
    @staticmethod
    def _sqlite_path() -> str:
        return os.environ.get("LABFORGE_ACCOUNTS_DB") or str(ROOT / "artifacts" / "accounts.sqlite3")

    @contextmanager
    def _db(self) -> Iterator[_Conn]:
        from core.db import connect, database_url

        url = database_url()
        if url:
            with connect(url) as raw:
                conn = _Conn(raw, False)
                self._init(conn, url)
                yield conn
            return
        path = self._sqlite_path()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        raw = sqlite3.connect(path, timeout=10, isolation_level=None)
        try:
            conn = _Conn(raw, True)
            self._init(conn, path)
            yield conn
        finally:
            raw.close()

    def _init(self, conn: _Conn, where: str) -> None:
        if where in self._ready:
            return
        for statement in SCHEMA:
            conn.execute(statement)
        self._ready.add(where)

    def storage(self) -> str:
        from core.db import database_url

        return "postgres" if database_url() else "file"

    def secret(self) -> bytes:
        """Keys the code hashes and each student's history key. LABFORGE_SECRET, or one made on
        first use and kept in the database so it survives restarts."""
        configured = os.environ.get("LABFORGE_SECRET", "").strip()
        if configured:
            return configured.encode()
        from core.db import database_url

        where = database_url() or self._sqlite_path()
        if where not in self._secret:
            with self._db() as conn:
                conn.execute("INSERT INTO lf_meta (key, value) VALUES ('secret', %s) ON CONFLICT (key) DO NOTHING",
                             (secrets.token_hex(32),))
                row = conn.execute("SELECT value FROM lf_meta WHERE key = 'secret'").fetchone()
            self._secret[where] = row[0].encode()
        return self._secret[where]

    def _mac(self, purpose: str, value: str) -> str:
        return hmac.new(self.secret(), f"{purpose}|{value}".encode(), hashlib.sha256).hexdigest()

    # ── signing in ─────────────────────────────────────────────────
    @staticmethod
    def check_email(email: str) -> str:
        email = (email or "").strip().lower()
        if not EMAIL.match(email) or ".." in email:
            raise AccountError("That doesn't look like an email address.", 422)
        domains = allowed_domains()
        if "*" not in domains and email.rsplit("@", 1)[1] not in domains:
            wanted = " or ".join("@" + d for d in domains)
            raise AccountError(f"Use your college email address ({wanted}).", 422)
        return email

    def start_code(self, email: str) -> str:
        """A fresh 6-digit code for this address. Only its keyed hash is stored."""
        now = time.time()
        code = f"{secrets.randbelow(1_000_000):06d}"
        with self._lock, self._db() as conn:
            row = conn.execute("SELECT sent FROM lf_codes WHERE email = %s", (email,)).fetchone()
            if row and now - float(row[0]) < RESEND_SECONDS:
                wait = int(RESEND_SECONDS - (now - float(row[0]))) + 1
                raise AccountError(f"We just sent a code. You can ask for another in {wait} seconds.", 429)
            conn.execute(
                "INSERT INTO lf_codes (email, code_hash, expires, attempts, sent) VALUES (%s, %s, %s, 0, %s) "
                "ON CONFLICT (email) DO UPDATE SET code_hash = excluded.code_hash, expires = excluded.expires, "
                "attempts = 0, sent = excluded.sent",
                (email, self._mac("code", f"{email}|{code}"), now + CODE_MINUTES * 60, now))
            if random.random() < 0.05:
                conn.execute("DELETE FROM lf_codes WHERE expires < %s", (now - 3600,))
                conn.execute("DELETE FROM lf_sessions WHERE expires < %s", (now,))
        return code

    def drop_code(self, email: str) -> None:
        with self._db() as conn:
            conn.execute("DELETE FROM lf_codes WHERE email = %s", (email,))

    def verify_code(self, email: str, code: str, ip: str = "") -> tuple[dict, str]:
        """The user (made on first sign-in) and a new session token, or AccountError."""
        now = time.time()
        code = re.sub(r"\D", "", code or "")
        with self._lock, self._db() as conn:
            row = conn.execute("SELECT code_hash, expires, attempts FROM lf_codes WHERE email = %s", (email,)).fetchone()
            if not row or float(row[1]) < now:
                raise AccountError("That code has expired. Ask for a new one.", 400)
            if int(row[2]) >= CODE_ATTEMPTS:
                conn.execute("DELETE FROM lf_codes WHERE email = %s", (email,))
                raise AccountError("Too many wrong tries. Ask for a new code.", 400)
            if not hmac.compare_digest(row[0], self._mac("code", f"{email}|{code}")):
                conn.execute("UPDATE lf_codes SET attempts = attempts + 1 WHERE email = %s", (email,))
                raise AccountError("That code isn't right. Check the email and try again.", 400)
            conn.execute("DELETE FROM lf_codes WHERE email = %s", (email,))
            conn.execute(
                "INSERT INTO lf_users (id, email, created, last_login, last_ip) VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (email) DO UPDATE SET last_login = excluded.last_login, last_ip = excluded.last_ip",
                (uuid.uuid4().hex, email, now, now, ip))
            user = self._user(conn, "email = %s", email)
            if user["blocked"]:
                raise AccountError("This account has been blocked. Contact us if that's a mistake.", 403)
            token = secrets.token_urlsafe(32)
            conn.execute("INSERT INTO lf_sessions (token_hash, user_id, created, expires) VALUES (%s, %s, %s, %s)",
                         (_hash(token), user["id"], now, now + SESSION_DAYS * 86400))
        return user, token

    @staticmethod
    def _user(conn: _Conn, where: str, value: str) -> dict | None:
        row = conn.execute(f"SELECT id, email, created, last_login, blocked FROM lf_users WHERE {where}",
                           (value,)).fetchone()
        if not row:
            return None
        return {"id": row[0], "email": row[1], "created": float(row[2]), "last_login": float(row[3]),
                "blocked": bool(row[4])}

    def user_for(self, token: str) -> dict | None:
        if not token or len(token) > 200:
            return None
        with self._db() as conn:
            row = conn.execute("SELECT user_id, expires FROM lf_sessions WHERE token_hash = %s",
                               (_hash(token),)).fetchone()
            if not row or float(row[1]) < time.time():
                return None
            return self._user(conn, "id = %s", row[0])

    def logout(self, token: str) -> None:
        if token:
            with self._db() as conn:
                conn.execute("DELETE FROM lf_sessions WHERE token_hash = %s", (_hash(token),))

    def history_key(self, user_id: str) -> str:
        """An AES key only this account gets: the browser uses it to lock the reports it keeps
        on the device. Reports themselves never come back to the server."""
        raw = hmac.new(self.secret(), f"history|{user_id}".encode(), hashlib.sha256).digest()
        return base64.b64encode(raw).decode()

    # ── credits ────────────────────────────────────────────────────
    def _balance(self, conn: _Conn, user_id: str) -> dict:
        period = _period_key()
        used = conn.execute("SELECT COALESCE(SUM(delta), 0) FROM lf_credits WHERE user_id = %s AND kind = 'free' "
                            "AND period = %s", (user_id, period)).fetchone()[0]
        extra = conn.execute("SELECT COALESCE(SUM(delta), 0) FROM lf_credits WHERE user_id = %s AND kind = 'extra'",
                             (user_id,)).fetchone()[0]
        free = max(0, free_reports() + int(used))
        extra = max(0, int(extra))
        return {"free": free, "free_total": free_reports(), "extra": extra, "left": free + extra,
                "period": free_period()}

    def credits(self, user_id: str) -> dict:
        with self._db() as conn:
            return self._balance(conn, user_id)

    def spend(self, user_id: str, job: str) -> str:
        """One report: a free one while this period has any left, then an extra credit."""
        with self._lock, self._db() as conn:
            balance = self._balance(conn, user_id)
            if balance["left"] <= 0:
                raise NoCredits()
            kind = "free" if balance["free"] > 0 else "extra"
            conn.execute(
                "INSERT INTO lf_credits (id, user_id, delta, kind, period, reason, job, ts, uniq) "
                "VALUES (%s, %s, -1, %s, %s, 'report', %s, %s, %s) ON CONFLICT (uniq) DO NOTHING",
                (uuid.uuid4().hex, user_id, kind, _period_key(), job, time.time(), f"spend:{job}"))
            return kind

    def refund(self, user_id: str, job: str) -> None:
        """The report didn't get written: give the credit back (once)."""
        with self._lock, self._db() as conn:
            row = conn.execute("SELECT kind, period FROM lf_credits WHERE uniq = %s AND user_id = %s",
                               (f"spend:{job}", user_id)).fetchone()
            if row:
                conn.execute(
                    "INSERT INTO lf_credits (id, user_id, delta, kind, period, reason, job, ts, uniq) "
                    "VALUES (%s, %s, 1, %s, %s, 'refund', %s, %s, %s) ON CONFLICT (uniq) DO NOTHING",
                    (uuid.uuid4().hex, user_id, row[0], row[1], job, time.time(), f"refund:{job}"))

    def grant(self, email: str, amount: int, reason: str = "grant") -> dict:
        """Extra credits (they don't expire). A negative amount takes them back."""
        with self._lock, self._db() as conn:
            user = self._user(conn, "email = %s", (email or "").strip().lower())
            if not user:
                raise AccountError("No account with that email address.", 404)
            conn.execute(
                "INSERT INTO lf_credits (id, user_id, delta, kind, period, reason, ts) VALUES (%s, %s, %s, 'extra', '', %s, %s)",
                (uuid.uuid4().hex, user["id"], int(amount), reason[:60], time.time()))
            return self._balance(conn, user["id"])

    # ── rewarded ads ───────────────────────────────────────────────
    @staticmethod
    def _ads_left(conn: _Conn, user_id: str) -> int:
        used = conn.execute("SELECT COUNT(*) FROM lf_credits WHERE user_id = %s AND reason = 'ad' AND ts >= %s",
                            (user_id, _day_start())).fetchone()[0]
        return max(0, ad_rewards_per_day() - int(used))

    def ads(self, user_id: str) -> dict:
        """What the page needs to offer "watch an ad for another report"."""
        per_day = ad_rewards_per_day()
        if not per_day:
            return {"enabled": False, "left": 0, "per_day": 0, "reward": 0, "min_seconds": 0}
        with self._db() as conn:
            left = self._ads_left(conn, user_id)
        return {"enabled": True, "left": left, "per_day": per_day, "reward": ad_reward(),
                "min_seconds": ad_min_seconds()}

    def ad_ticket(self, user_id: str) -> str:
        """Handed out before the ad starts; claimed after it ends."""
        if not ad_rewards_per_day():
            raise AccountError("Ads for extra reports aren't turned on.", 404)
        now = time.time()
        with self._lock, self._db() as conn:
            if self._ads_left(conn, user_id) <= 0:
                raise AccountError("You've had today's extra reports from ads. More tomorrow.", 429)
            ticket = secrets.token_urlsafe(24)
            conn.execute("INSERT INTO lf_ad_tickets (id, user_id, created) VALUES (%s, %s, %s)", (ticket, user_id, now))
            if random.random() < 0.05:
                conn.execute("DELETE FROM lf_ad_tickets WHERE created < %s", (now - 86400,))
        return ticket

    def ad_claim(self, user_id: str, ticket: str) -> dict:
        """The ad was watched: one more report. Each ticket pays out once."""
        now = time.time()
        with self._lock, self._db() as conn:
            row = conn.execute("SELECT created, claimed FROM lf_ad_tickets WHERE id = %s AND user_id = %s",
                               ((ticket or "")[:100], user_id)).fetchone()
            if not row or int(row[1]) or now - float(row[0]) > AD_TICKET_MINUTES * 60:
                raise AccountError("That ad has expired. Start it again.", 400)
            if now - float(row[0]) < ad_min_seconds():
                raise AccountError("The ad hasn't finished yet.", 400)
            if self._ads_left(conn, user_id) <= 0:
                raise AccountError("You've had today's extra reports from ads. More tomorrow.", 429)
            conn.execute("UPDATE lf_ad_tickets SET claimed = 1 WHERE id = %s", (ticket,))
            conn.execute(
                "INSERT INTO lf_credits (id, user_id, delta, kind, period, reason, ts, uniq) "
                "VALUES (%s, %s, %s, 'extra', '', 'ad', %s, %s) ON CONFLICT (uniq) DO NOTHING",
                (uuid.uuid4().hex, user_id, ad_reward(), now, f"ad:{ticket}"))
            return self._balance(conn, user_id)

    # ── gaps ───────────────────────────────────────────────────────
    def record_gaps(self, gaps: list[dict], job: str, user: dict | None = None, subject: str = "") -> list[dict]:
        """Count each gap once per report. Returns the gaps that just reached the alert level
        (each gap alerts once; a runner that is offline alerts the first time)."""
        now = time.time()
        crossed = []
        with self._lock, self._db() as conn:
            for gap in gaps:
                conn.execute(
                    "INSERT INTO lf_gaps (id, key, kind, label, ts, user_id, job, subject, uniq) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (uniq) DO NOTHING",
                    (uuid.uuid4().hex, gap["key"], gap["kind"], gap["label"], now, (user or {}).get("id", ""), job,
                     subject[:120], f"{gap['key']}|{job}"))
                count = int(conn.execute("SELECT COUNT(*) FROM lf_gaps WHERE key = %s", (gap["key"],)).fetchone()[0])
                if count >= (1 if gap["kind"] == "runner" else gap_alert_at()):
                    marker = f"gap_alert:{gap['key']}"
                    if not conn.execute("SELECT 1 FROM lf_meta WHERE key = %s", (marker,)).fetchone():
                        conn.execute("INSERT INTO lf_meta (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING",
                                     (marker, str(now)))
                        crossed.append({**gap, "count": count})
            if random.random() < 0.02:
                conn.execute("DELETE FROM lf_gaps WHERE ts < %s", (now - GAP_DAYS * 86400,))
        return crossed

    def gaps(self, days: int = 90) -> list[dict]:
        """One entry per gap, most reports first."""
        with self._db() as conn:
            rows = conn.execute("SELECT key, kind, label, ts, user_id, job, subject FROM lf_gaps WHERE ts >= %s "
                                "ORDER BY ts DESC LIMIT 20000", (time.time() - days * 86400,)).fetchall()
        out: dict[str, dict] = {}
        for key, kind, label, ts, user_id, job, subject in rows:
            g = out.setdefault(key, {"key": key, "kind": kind, "label": label, "reports": 0, "students": set(),
                                     "subjects": [], "last": float(ts), "first": float(ts), "job": job})
            g["reports"] += 1
            g["first"] = float(ts)
            if user_id:
                g["students"].add(user_id)
            if subject and subject not in g["subjects"] and len(g["subjects"]) < 8:
                g["subjects"].append(subject)
        for g in out.values():
            g["students"] = len(g["students"])
        return sorted(out.values(), key=lambda g: (-g["reports"], -g["last"]))

    def resolve_gap(self, key: str) -> None:
        """The owner dealt with it: forget the gap, so it alerts again if it ever comes back."""
        with self._db() as conn:
            conn.execute("DELETE FROM lf_gaps WHERE key = %s", (key,))
            conn.execute("DELETE FROM lf_meta WHERE key = %s", (f"gap_alert:{key}",))

    def set_blocked(self, email: str, blocked: bool) -> None:
        with self._db() as conn:
            user = self._user(conn, "email = %s", (email or "").strip().lower())
            if not user:
                raise AccountError("No account with that email address.", 404)
            conn.execute("UPDATE lf_users SET blocked = %s WHERE id = %s", (1 if blocked else 0, user["id"]))
            if blocked:
                conn.execute("DELETE FROM lf_sessions WHERE user_id = %s", (user["id"],))

    def users(self, limit: int = 500) -> list[dict]:
        with self._db() as conn:
            rows = conn.execute(
                "SELECT u.id, u.email, u.created, u.last_login, u.last_ip, u.blocked, "
                "(SELECT COUNT(*) FROM lf_credits c WHERE c.user_id = u.id AND c.reason = 'report') - "
                "(SELECT COUNT(*) FROM lf_credits c WHERE c.user_id = u.id AND c.reason = 'refund') "
                "FROM lf_users u ORDER BY u.last_login DESC LIMIT %s", (max(1, min(limit, 5000)),)).fetchall()
            return [{"email": r[1], "created": float(r[2]), "last_login": float(r[3]), "ip": r[4],
                     "blocked": bool(r[5]), "reports": int(r[6]), "credits": self._balance(conn, r[0])}
                    for r in rows]

    # ── sessions that went wrong ───────────────────────────────────
    @staticmethod
    def flag_days() -> int:
        return max(1, _env_int("LABFORGE_FLAG_DAYS", 30))

    def flag(self, flag_id: str, job: str, kind: str, reason: str, data: dict, user: dict | None = None) -> None:
        """Keep a copy of a session that had a problem. The same id replaces the older copy."""
        now = time.time()
        body = json.dumps(_trim(data), ensure_ascii=False)
        with self._db() as conn:
            conn.execute(
                "INSERT INTO lf_flags (id, ts, user_id, email, job, kind, reason, data) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (id) DO UPDATE SET ts = excluded.ts, reason = excluded.reason, data = excluded.data, "
                "user_id = excluded.user_id, email = excluded.email",
                (flag_id, now, (user or {}).get("id", ""), (user or {}).get("email", ""), job, kind, reason[:500], body))
            if random.random() < 0.05:
                conn.execute("DELETE FROM lf_flags WHERE ts < %s", (now - self.flag_days() * 86400,))

    def flags(self, days: int = 30) -> list[dict]:
        with self._db() as conn:
            rows = conn.execute("SELECT id, ts, email, job, kind, reason FROM lf_flags WHERE ts >= %s ORDER BY ts DESC "
                                "LIMIT 1000", (time.time() - days * 86400,)).fetchall()
        return [{"id": r[0], "ts": float(r[1]), "email": r[2], "job": r[3], "kind": r[4], "reason": r[5]} for r in rows]

    def flag_detail(self, flag_id: str) -> dict | None:
        with self._db() as conn:
            r = conn.execute("SELECT id, ts, email, job, kind, reason, data FROM lf_flags WHERE id = %s",
                             (flag_id,)).fetchone()
        if not r:
            return None
        return {"id": r[0], "ts": float(r[1]), "email": r[2], "job": r[3], "kind": r[4], "reason": r[5],
                **json.loads(r[6])}

    def delete_flag(self, flag_id: str) -> None:
        with self._db() as conn:
            conn.execute("DELETE FROM lf_flags WHERE id = %s", (flag_id,))


def _trim(data: dict) -> dict:
    """Enough to see what went wrong, without keeping megabytes."""
    out = dict(data)
    if isinstance(out.get("sheet"), str):
        out["sheet"] = out["sheet"][:MAX_SHEET_CHARS]
    tasks = []
    for t in (out.get("tasks") or [])[:30]:
        tasks.append({
            "title": str(t.get("title", ""))[:300], "language": t.get("language", ""), "status": t.get("status", ""),
            "note": str(t.get("note") or "")[:2000], "stdin": str(t.get("stdin") or "")[:4000],
            "output": str(t.get("output") or "")[-8000:], "problem": str(t.get("problem") or "")[:4000],
            "edited": bool(t.get("edited", False)),
            "files": [{"name": str(f.get("name", ""))[:200], "code": str(f.get("code", ""))[:MAX_FILE_CHARS]}
                      for f in (t.get("files") or [])[:20]],
        })
    out["tasks"] = tasks
    return out


def flag_reason(error: str, tasks: list[dict]) -> str:
    """Why a session is worth a look, or '' when everything ran."""
    parts = []
    if error:
        parts.append(error)
    failed = [t for t in tasks if t.get("status") == "failed"]
    skipped = [t for t in tasks if t.get("status") not in ("passed", "failed")]
    if failed:
        parts.append("Failed: " + ", ".join(f"{t.get('title') or 'task'} ({t.get('language', '')})" for t in failed))
    if skipped:
        parts.append("Not run: " + ", ".join(f"{t.get('title') or 'task'} ({t.get('language', '')})" for t in skipped))
    return ". ".join(parts)
