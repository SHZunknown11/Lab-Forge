"""Run LabForge from Telegram: a private admin bot.

Who may use it. Only the chats in TELEGRAM_ADMIN_CHAT_IDS (default: TELEGRAM_CHAT_ID). Telegram
tells us which chat a message really came from, so another account can't pose as you; anyone
else is ignored without a reply. On top of that, if LABFORGE_BOT_PASSCODE is set you sign in with
/login <passcode> (the message is deleted at once) and stay signed in for 12 hours; five wrong
tries lock the chat for 15 minutes. /logout ends it early.

How updates arrive. On the live site Telegram calls POST /api/telegram/webhook (checked with a
secret Telegram sends back; set up once with scripts/telegram_setup.py). For trying it on a
computer without a public address, TELEGRAM_POLL=1 fetches updates instead.

The admin panel. /panel (or the menu button next to the message box) opens /admin inside Telegram
as a mini app. Telegram signs the data it launches the page with; the server checks that
signature with the bot token, that the user is one of your chats, and (if there is a passcode)
that you are signed in, and hands the page a key that works for four hours. Nothing to type.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import threading
import time
from urllib.parse import parse_qsl
from dataclasses import dataclass
from datetime import datetime, timezone

SESSION_HOURS = 12
LOCK_TRIES = 5
LOCK_SECONDS = 900
CHUNK = 3800

HELP = """LabForge admin bot

Look
/status  server, AI, runner, mail, database
/today  /week  summary of reports, accounts, money
/logs [n]  latest reports (what ran, what failed)
/failed [n]  sessions that went wrong
/flag <id>  one failed session: the student's code and the error
/serverlog [n] [word]  the server's own log lines
/gaps  what LabForge couldn't do, most common first
/subjects  subjects waiting for approval
/users [n]  recent accounts
/user <email>  one account

Manage
/grant <email> <n>  give (or take back, with a minus) reports
/block <email>  /unblock <email>
/resolve <n>  mark gap n (from /gaps) as dealt with
/approve <n>  /hide <n>  subject n from /subjects

/panel  open the admin panel here in Telegram
/login <passcode>  /logout  /help"""


# ── configuration ──────────────────────────────────────────────────

def token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


def allowed_chats() -> set[int]:
    raw = os.environ.get("TELEGRAM_ADMIN_CHAT_IDS") or os.environ.get("TELEGRAM_CHAT_ID", "")
    return {int(x) for x in re.findall(r"-?\d+", raw)}


def passcode() -> str:
    return os.environ.get("LABFORGE_BOT_PASSCODE", "").strip()


def enabled() -> bool:
    return bool(token() and allowed_chats())


def webhook_secret() -> str:
    """What Telegram sends back with every update, so only Telegram can reach the webhook."""
    return hashlib.sha256(f"{token()}|labforge-webhook".encode()).hexdigest()[:48]


def valid_webhook_secret(given: str) -> bool:
    return enabled() and hmac.compare_digest((given or "").encode(), webhook_secret().encode())


# ── the panel (a Telegram mini app) ────────────────────────────────
PANEL_HOURS = 4
INIT_MAX_AGE = 3600  # Telegram's launch data older than this is refused


def panel_url() -> str:
    """The admin page, only usable from Telegram when the site has an https address."""
    base = os.environ.get("LABFORGE_PUBLIC_URL", "").strip().rstrip("/")
    return f"{base}/admin" if base.startswith("https://") else ""


def verify_init_data(init_data: str, now: float | None = None) -> int | None:
    """The Telegram user id if `init_data` (from the mini app's launch link) was signed by Telegram
    for our bot and is fresh, else None. https://core.telegram.org/bots/webapps#validating-data"""
    if not token() or not init_data:
        return None
    fields = dict(parse_qsl(init_data, keep_blank_values=True))
    given = fields.pop("hash", "")
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token().encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not given or not hmac.compare_digest(given, expected):
        return None
    try:
        if (now or time.time()) - int(fields.get("auth_date", "0")) > INIT_MAX_AGE:
            return None
        return int(json.loads(fields.get("user", "{}")).get("id"))
    except (ValueError, TypeError):
        return None


def _panel_mac(exp: str) -> str:
    key = hashlib.sha256(f"{token()}|labforge-panel".encode()).digest()
    return hmac.new(key, f"tgs|{exp}".encode(), hashlib.sha256).hexdigest()[:40]


def panel_token(now: float | None = None) -> str:
    exp = str(int((now or time.time()) + PANEL_HOURS * 3600))
    return f"tgs.{exp}.{_panel_mac(exp)}"


def valid_panel_token(given: str, now: float | None = None) -> bool:
    """A key made by panel_token (it works wherever the admin key does, for four hours)."""
    parts = (given or "").split(".")
    if len(parts) != 3 or parts[0] != "tgs" or not enabled() or not parts[1].isdigit():
        return False
    return int(parts[1]) > (now or time.time()) and hmac.compare_digest(parts[2], _panel_mac(parts[1]))


# Shown when you type "/" in the chat. Only your chat gets the list; anyone else sees nothing.
COMMANDS = [
    ("status", "Server, AI, runner, mail, database"),
    ("today", "Summary of today"),
    ("week", "Summary of the last 7 days"),
    ("logs", "Latest reports"),
    ("failed", "Sessions that went wrong"),
    ("flag", "One failed session with the code"),
    ("serverlog", "The server's own log lines"),
    ("gaps", "What LabForge couldn't do"),
    ("subjects", "Subjects waiting for approval"),
    ("users", "Recent accounts"),
    ("user", "One account: /user email"),
    ("grant", "Give reports: /grant email 5"),
    ("block", "Block an account: /block email"),
    ("unblock", "Unblock an account"),
    ("resolve", "Mark a gap as dealt with"),
    ("approve", "Approve a waiting subject"),
    ("hide", "Hide a waiting subject"),
    ("panel", "Open the admin panel here"),
    ("login", "Sign in: /login passcode"),
    ("logout", "Sign out"),
    ("help", "All commands"),
]


def publish_commands() -> bool:
    """Put COMMANDS in the "/" menu of each admin chat (and only those chats)."""
    ok = True
    for chat in sorted(allowed_chats()):
        answer = api("setMyCommands", scope={"type": "chat", "chat_id": chat},
                     commands=[{"command": c, "description": d} for c, d in COMMANDS])
        ok = ok and bool(answer.get("ok"))
    return ok


# ── Telegram's HTTP API ────────────────────────────────────────────

def api(method: str, **payload):
    import httpx

    res = httpx.post(f"https://api.telegram.org/bot{token()}/{method}", json=payload, timeout=40)
    return res.json() if res.headers.get("content-type", "").startswith("application/json") else {"ok": False}


def chunks(text: str) -> list[str]:
    """Telegram takes 4096 characters a message: cut at line ends."""
    out, cur = [], ""
    for line in text.split("\n"):
        while len(line) > CHUNK:
            if cur:
                out.append(cur)
                cur = ""
            out.append(line[:CHUNK])
            line = line[CHUNK:]
        if len(cur) + len(line) + 1 > CHUNK:
            out.append(cur)
            cur = ""
        cur += line + "\n"
    if cur.strip():
        out.append(cur)
    return [c.rstrip() for c in out]


def ago(ts: float | str) -> str:
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts).timestamp()
    s = max(0, time.time() - float(ts))
    if s < 90:
        return "just now"
    if s < 5400:
        return f"{int(s // 60)}m ago"
    if s < 172800:
        return f"{int(s // 3600)}h ago"
    return f"{int(s // 86400)}d ago"


def _count(arg: str, default: int, top: int) -> int:
    try:
        return max(1, min(int(arg), top))
    except (TypeError, ValueError):
        return default


@dataclass
class Context:
    """What the bot needs from the app (apps/api/main.py builds one)."""
    accounts: object
    activity: object
    status: object        # () -> dict
    summary_text: object  # (days) -> str
    serverlog: object     # (count, word) -> list[str]


class Bot:
    def __init__(self, ctx: Context):
        self.ctx = ctx

    # ── who is signed in ───────────────────────────────────────────
    def _signed_in(self, chat: int) -> bool:
        if not passcode():
            return True
        expires = self.ctx.accounts.meta_get(f"tg_session:{chat}")
        return bool(expires) and float(expires) > time.time()

    def _login(self, chat: int, given: str) -> str:
        if not passcode():
            return "No passcode is set (LABFORGE_BOT_PASSCODE), so this chat is signed in already."
        lock_key, now = f"tg_lock:{chat}", time.time()
        tries, until = (self.ctx.accounts.meta_get(lock_key) or "0|0").split("|")
        if float(until) > now:
            return f"Too many wrong tries. Try again in {int((float(until) - now) // 60) + 1} minutes."
        if given and hmac.compare_digest(given.encode(), passcode().encode()):
            self.ctx.accounts.meta_set(lock_key, "0|0")
            self.ctx.accounts.meta_set(f"tg_session:{chat}", str(now + SESSION_HOURS * 3600))
            print(f"[bot] chat {chat} signed in")
            return f"Signed in for {SESSION_HOURS} hours. /help lists what you can do."
        tries_now = int(tries) + 1
        locked = tries_now >= LOCK_TRIES
        self.ctx.accounts.meta_set(lock_key, f"{0 if locked else tries_now}|{now + LOCK_SECONDS if locked else 0}")
        print(f"[bot] wrong passcode from chat {chat} ({tries_now})")
        return "Wrong passcode." + (" Locked for 15 minutes." if locked else "")

    # ── one message in, replies out ────────────────────────────────
    def respond(self, chat: int, text: str) -> tuple[list[str], bool]:
        """(replies, delete the incoming message). Chats that aren't yours get nothing."""
        if chat not in allowed_chats():
            return [], False
        parts = (text or "").strip().split()
        if not parts or not parts[0].startswith("/"):
            return ["Send /help for the commands."], False
        cmd, args = parts[0].lower().split("@")[0], parts[1:]
        if cmd in ("/start", "/help"):
            return [HELP + ("" if self._signed_in(chat) else "\n\nSign in first: /login <passcode>")], False
        if cmd == "/login":
            # A passphrase may have spaces. The message with it is deleted right away.
            return [self._login(chat, " ".join(args))], True
        if cmd == "/logout":
            self.ctx.accounts.meta_set(f"tg_session:{chat}", "0")
            return ["Signed out."], False
        if not self._signed_in(chat):
            return ["Sign in first: /login <passcode>"], False
        handler = getattr(self, "cmd_" + cmd[1:], None)
        if handler is None:
            return ["I don't know that one. /help lists the commands."], False
        try:
            return chunks(handler(args)), False
        except Exception as exc:  # noqa: BLE001 - a bad command must not kill the bot
            print(f"[bot] {cmd} failed: {type(exc).__name__}: {exc}")
            return [f"{cmd} failed: {type(exc).__name__}"], False

    # ── looking ────────────────────────────────────────────────────
    def cmd_status(self, args) -> str:
        s = self.ctx.status()
        runtimes = ", ".join(f"{k}{'' if v else ' (no)'}" for k, v in sorted(s["runtimes"].items()))
        return "\n".join([
            f"AI: {', '.join(s['providers']) or 'none configured'}",
            f"Runner: {s['exec_backend']} | runs: {runtimes}",
            f"Database: {'Postgres' if s['database'] else 'local file (lost on redeploy)'}",
            f"Sign-in: {'required' if s['login_required'] else 'off'} | mail: {s['mail']}",
            f"Alerts: {s['owner_alerts']} | payments: {s['payments']}",
            f"Server time: {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC",
        ])

    def cmd_today(self, args) -> str:
        return self.ctx.summary_text(1)

    def cmd_week(self, args) -> str:
        return self.ctx.summary_text(7)

    def cmd_logs(self, args) -> str:
        rows = self.ctx.activity.reports(2)[:_count(args[0] if args else "", 10, 30)]
        if not rows:
            return "No reports in the last two days."
        out = []
        for r in rows:
            marks = "".join({"passed": "+", "failed": "x"}.get(t.get("status"), "-") for t in r["tasks"]) or "?"
            out.append(f"{ago(r['ts'])} [{marks}] {r['title'] or 'Untitled'} | {r['subject'] or 'no subject'}"
                       f"{' | ' + r['error'][:80] if r['error'] else ''}{' | cached' if r['cached'] else ''}")
        return "+ ran, x failed, - not run\n" + "\n".join(out)

    def cmd_failed(self, args) -> str:
        rows = self.ctx.accounts.flags(30)[:_count(args[0] if args else "", 8, 25)]
        if not rows:
            return "No failed sessions in the last 30 days."
        return "\n\n".join(f"{ago(f['ts'])} | {f['email'] or 'not signed in'}\n{f['reason'][:200]}\n/flag {f['id'][:10]}"
                           for f in rows)

    def cmd_flag(self, args) -> str:
        if not args:
            return "Usage: /flag <id from /failed>"
        match = next((f for f in self.ctx.accounts.flags(90) if f["id"].startswith(args[0])), None)
        detail = self.ctx.accounts.flag_detail(match["id"]) if match else None
        if not detail:
            return "No saved session with that id (they're kept for a limited time)."
        out = [f"{ago(detail['ts'])} | {detail['email'] or 'not signed in'} | {detail.get('subject') or 'no subject'}",
               f"Why: {detail['reason']}"]
        if detail.get("error"):
            out.append(f"Error: {detail['error'][:300]}")
        for t in detail["tasks"]:
            if t["status"] == "passed":
                continue
            out.append(f"\n== {t['title']} ({t['language']}): {t['status']}{' - the student changed the code' if t.get('edited') else ''}")
            if t["note"]:
                out.append(t["note"][:300])
            if t["output"]:
                out.append("Output:\n" + t["output"][-700:])
            for f in t["files"][:3]:
                out.append(f"-- {f['name']}\n{f['code'][:1500]}")
        return "\n".join(out)

    def cmd_serverlog(self, args) -> str:
        count = _count(args[0], 25, 100) if args and args[0].isdigit() else 25
        word = " ".join(a for a in args if not a.isdigit())
        lines = self.ctx.serverlog(count, word)
        return "\n".join(lines) if lines else "Nothing logged" + (f" with '{word}'" if word else "") + " since the server started."

    def cmd_gaps(self, args) -> str:
        gaps = self.ctx.accounts.gaps(180)[:12]
        if not gaps:
            return "Nothing missing so far."
        return "\n".join(f"{i}. {g['label']}: {g['reports']} reports, {g['students']} students ({ago(g['last'])})"
                         for i, g in enumerate(gaps, 1)) + "\n\n/resolve <n> when you've dealt with one"

    def cmd_resolve(self, args) -> str:
        gaps = self.ctx.accounts.gaps(180)[:12]
        if not args or not args[0].isdigit() or not 1 <= int(args[0]) <= len(gaps):
            return "Usage: /resolve <n>, with n from /gaps"
        gap = gaps[int(args[0]) - 1]
        self.ctx.accounts.resolve_gap(gap["key"])
        print(f"[bot] gap resolved: {gap['key']}")
        return f"Marked as dealt with: {gap['label']}"

    def cmd_subjects(self, args) -> str:
        rows = self.ctx.accounts.subjects("pending")[:15]
        if not rows:
            return "No subjects waiting."
        return "\n".join(f"{i}. {s['name']} {s['code'] or ''} ({s['uses']} reports)" for i, s in enumerate(rows, 1)) + \
            "\n\n/approve <n>  or  /hide <n>"

    def _subject(self, args, status: str) -> str:
        rows = self.ctx.accounts.subjects("pending")[:15]
        if not args or not args[0].isdigit() or not 1 <= int(args[0]) <= len(rows):
            return f"Usage: /{'approve' if status == 'approved' else 'hide'} <n>, with n from /subjects"
        subject = rows[int(args[0]) - 1]
        self.ctx.accounts.set_subject(subject["key"], status)
        print(f"[bot] subject {status}: {subject['name']}")
        return f"{'Approved' if status == 'approved' else 'Hidden'}: {subject['name']}"

    def cmd_approve(self, args) -> str:
        return self._subject(args, "approved")

    def cmd_hide(self, args) -> str:
        return self._subject(args, "hidden")

    def cmd_users(self, args) -> str:
        users = self.ctx.accounts.users(_count(args[0] if args else "", 10, 40))
        if not users:
            return "Nobody has signed in yet."
        return "\n".join(f"{ago(u['last_login'])} | {u['email']} | {u['reports']} reports | "
                         f"{u['credits']['left']} left{' | BLOCKED' if u['blocked'] else ''}" for u in users)

    def _find(self, email: str):
        email = (email or "").strip().lower()
        return next((u for u in self.ctx.accounts.users(5000) if u["email"] == email), None)

    def cmd_user(self, args) -> str:
        u = self._find(args[0] if args else "")
        if not u:
            return "Usage: /user <email> (an account that has signed in)"
        c = u["credits"]
        return (f"{u['email']}{' (BLOCKED)' if u['blocked'] else ''}\nJoined {ago(u['created'])}, last here {ago(u['last_login'])}\n"
                f"Reports written: {u['reports']}\nLeft: {c['free']} free + {c['extra']} extra\nIP code: {u['ip'] or 'none'}")

    # ── managing ───────────────────────────────────────────────────
    def cmd_grant(self, args) -> str:
        try:
            amount = int(args[1])
        except (IndexError, ValueError):
            return "Usage: /grant <email> <number>  (a minus number takes reports back)"
        if not -1000 <= amount <= 1000 or amount == 0:
            return "Use a number between -1000 and 1000, not 0."
        from core.accounts import AccountError

        try:
            left = self.ctx.accounts.grant(args[0], amount, "owner via bot")
        except AccountError as exc:
            return str(exc)
        print(f"[bot] granted {amount} to {args[0].lower()}")
        return f"Done. {args[0].lower()} now has {left['left']} reports ({left['extra']} extra)."

    def _block(self, args, blocked: bool) -> str:
        from core.accounts import AccountError

        if not args:
            return f"Usage: /{'block' if blocked else 'unblock'} <email>"
        try:
            self.ctx.accounts.set_blocked(args[0], blocked)
        except AccountError as exc:
            return str(exc)
        print(f"[bot] {'blocked' if blocked else 'unblocked'} {args[0].lower()}")
        return f"{'Blocked and signed out' if blocked else 'Unblocked'}: {args[0].lower()}"

    def cmd_block(self, args) -> str:
        return self._block(args, True)

    def cmd_unblock(self, args) -> str:
        return self._block(args, False)

    # ── plumbing ───────────────────────────────────────────────────
    def panel_signed_in(self, user_id: int) -> bool:
        """May this Telegram user open the panel? Your chat, and signed in when there's a passcode."""
        return user_id in allowed_chats() and self._signed_in(user_id)

    def handle_update(self, update: dict) -> None:
        msg = update.get("message") or {}
        chat = (msg.get("chat") or {}).get("id")
        if chat is None or "text" not in msg:
            return
        first = (msg["text"].strip().split() or [""])[0].lower().split("@")[0]
        if first == "/panel" and int(chat) in allowed_chats():
            if not self._signed_in(int(chat)):
                api("sendMessage", chat_id=chat, text="Sign in first: /login <passcode>")
            elif not panel_url():
                api("sendMessage", chat_id=chat, text="The panel needs the site's https address: set "
                    "LABFORGE_PUBLIC_URL (for example https://labforge.onrender.com) and run scripts/telegram_setup.py.")
            else:
                api("sendMessage", chat_id=chat, text="LabForge admin panel",
                    reply_markup={"inline_keyboard": [[{"text": "Open the panel", "web_app": {"url": panel_url()}}]]})
            return
        replies, delete = self.respond(int(chat), msg["text"])
        if delete:
            api("deleteMessage", chat_id=chat, message_id=msg.get("message_id"))
        for text in replies:
            api("sendMessage", chat_id=chat, text=text, disable_web_page_preview=True)


def poll_forever(bot: Bot, stop: threading.Event) -> None:
    """For a computer with no public address: ask Telegram for new messages."""
    api("deleteWebhook")  # polling and a webhook can't both be on
    offset = 0
    while not stop.is_set():
        try:
            got = api("getUpdates", offset=offset, timeout=25, allowed_updates=["message"])
            for update in got.get("result", []):
                offset = update["update_id"] + 1
                bot.handle_update(update)
        except Exception as exc:  # noqa: BLE001
            print(f"[bot] polling: {type(exc).__name__}")
            stop.wait(5)
