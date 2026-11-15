"""The Telegram admin bot: who may use it, signing in, each command, and the webhook.

Telegram itself is stubbed: replies are collected, nothing is sent.
"""
import json
import time

import pytest
from fastapi.testclient import TestClient

from core import botlogs, telegram_bot
from core.accounts import Accounts
from core.telegram_bot import Bot, Context

ME, STRANGER = 111, 222
PASS = "correct horse"


def task(status="passed", title="Easy", language="java", note="", output="", code="class Main { }", edited=False):
    return {"title": title, "language": language, "status": status, "note": note, "output": output, "stdin": "",
            "problem": "", "edited": edited, "files": [{"name": "Main.java", "code": code}]}


class FakeActivity:
    def reports(self, days):
        return [{"ts": "2026-11-14T10:00:00+00:00", "title": "Experiment 4", "subject": "PBLJ", "error": "",
                 "cached": False, "tasks": [{"status": "passed"}, {"status": "failed"}, {"status": "not_run"}]}]


@pytest.fixture()
def bot(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456789:AAFakeTokenFakeTokenFakeTokenFakeToken")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", str(ME))
    monkeypatch.setenv("LABFORGE_BOT_PASSCODE", PASS)
    monkeypatch.setenv("TELEGRAM_ADMIN_CHAT_IDS", "")
    store = Accounts()
    status = {"providers": ["groq:gpt-oss"], "runtimes": {"java": True, "matlab": False}, "exec_backend": "local",
              "database": False, "login_required": True, "mail": "brevo", "owner_alerts": "telegram",
              "payments": "not set up"}
    ctx = Context(accounts=store, activity=FakeActivity(), status=lambda: status,
                  summary_text=lambda days: f"summary for {days} days", serverlog=botlogs.tail)
    b = Bot(ctx)
    b.store = store
    return b


def say(bot, text, chat=ME, signed_in=True):
    if signed_in and not bot._signed_in(chat):
        bot.respond(chat, f"/login {PASS}")
    replies, _ = bot.respond(chat, text)
    return "\n".join(replies)


def sign_up(store, email, ip="ip-abc"):
    return store.verify_code(email, store.start_code(email), ip)[0]


# ── who may use it ─────────────────────────────────────────────────

def test_other_chats_get_no_answer_at_all(bot):
    assert bot.respond(STRANGER, "/status") == ([], False)
    assert bot.respond(STRANGER, f"/login {PASS}") == ([], False)
    assert bot.respond(STRANGER, "/help") == ([], False)


def test_you_must_log_in_with_the_passcode_first(bot):
    assert "Sign in first" in say(bot, "/status", signed_in=False)
    help_text = say(bot, "/help", signed_in=False)
    assert "/failed" in help_text and "Sign in first" in help_text
    replies, delete = bot.respond(ME, f"/login {PASS}")
    assert delete is True and "Signed in for 12 hours" in replies[0]  # the passcode message is removed
    assert "AI: groq" in say(bot, "/status", signed_in=False)
    bot.respond(ME, "/logout")
    assert "Sign in first" in say(bot, "/status", signed_in=False)


def test_five_wrong_passcodes_lock_the_chat(bot):
    for _ in range(4):
        assert bot.respond(ME, "/login nope")[0] == ["Wrong passcode."]
    assert "Locked for 15 minutes" in bot.respond(ME, "/login nope")[0][0]
    assert "Too many wrong tries" in bot.respond(ME, f"/login {PASS}")[0][0]  # even the right one, for now
    bot.store.meta_set(f"tg_lock:{ME}", "0|0")
    assert "Signed in" in bot.respond(ME, f"/login {PASS}")[0][0]


def test_a_session_ends_after_twelve_hours(bot):
    bot.respond(ME, f"/login {PASS}")
    assert bot._signed_in(ME)
    bot.store.meta_set(f"tg_session:{ME}", str(time.time() - 1))
    assert not bot._signed_in(ME)


def test_without_a_passcode_your_chat_is_signed_in(bot, monkeypatch):
    monkeypatch.setenv("LABFORGE_BOT_PASSCODE", "")
    assert "AI: groq" in bot.respond(ME, "/status")[0][0]
    assert "no passcode" in bot.respond(ME, "/login x")[0][0].lower()
    assert bot.respond(STRANGER, "/status") == ([], False)


def test_unknown_commands_and_plain_text(bot):
    assert "don't know" in say(bot, "/nonsense")
    assert say(bot, "hello") == "Send /help for the commands."
    assert "AI: groq" in say(bot, "/status@LabForgeAdminbot")


# ── looking ────────────────────────────────────────────────────────

def test_status_summary_and_logs(bot):
    out = say(bot, "/status")
    assert "java, matlab (no)" in out and "local file (lost on redeploy)" in out and "mail: brevo" in out
    assert say(bot, "/today") == "summary for 1 days" and say(bot, "/week") == "summary for 7 days"
    logs = say(bot, "/logs")
    assert "[+x-]" in logs and "Experiment 4 | PBLJ" in logs


def test_failed_sessions_and_the_students_code(bot):
    user = sign_up(bot.store, "24bcs1@cuchd.in")
    bad = [task(), task("failed", "Medium", note="The program didn't compile.", output="error: ';' expected",
                        code="int x = 5", edited=True)]
    bot.store.flag("job1", "job1", "draft", "Failed: Medium (java)", {"sheet": "Experiment 4", "subject": "PBLJ",
                                                                      "tasks": bad}, user)
    listing = say(bot, "/failed")
    assert "24bcs1@cuchd.in" in listing and "Failed: Medium (java)" in listing
    flag_id = listing.split("/flag ")[1].split()[0]
    detail = say(bot, f"/flag {flag_id}")
    assert "the student changed the code" in detail and "error: ';' expected" in detail and "int x = 5" in detail
    assert "Easy" not in detail  # what passed isn't repeated
    assert "No saved session" in say(bot, "/flag nothere")


def test_gaps_can_be_resolved_from_the_chat(bot):
    bot.store.record_gaps([{"key": "language:matlab", "kind": "language", "label": "MATLAB can't be run"}], "j1",
                          None, "FIP")
    assert "1. MATLAB can't be run: 1 reports" in say(bot, "/gaps")
    assert "Marked as dealt with" in say(bot, "/resolve 1")
    assert say(bot, "/gaps") == "Nothing missing so far."
    assert "Usage" in say(bot, "/resolve 9")


def test_subjects_are_approved_from_the_chat(bot):
    bot.store.note_subject("Compiler Design Lab", "24CSP-401")
    bot.store.note_subject("Typo Subject")
    assert "1. Compiler Design Lab 24CSP-401 (1 reports)" in say(bot, "/subjects").replace("2. Typo", "")
    first = bot.store.subjects("pending")[0]["name"]
    assert f"Approved: {first}" in say(bot, "/approve 1")
    assert first not in [s["name"] for s in bot.store.subjects("pending")]
    assert "Hidden:" in say(bot, "/hide 1")
    assert say(bot, "/subjects") == "No subjects waiting."


def test_server_log_lines_are_kept_and_secrets_blanked(bot):
    botlogs.install()
    print("[ai] all providers failed: groq returned 429")
    print("[mail] sending with xkeysib-abc123def456 and token=hunter2")
    out = say(bot, "/serverlog 10")
    assert "all providers failed" in out and "xkeysib-abc123" not in out and "hunter2" not in out and "***" in out
    assert "all providers failed" not in say(bot, "/serverlog 10 mail")


# ── managing ───────────────────────────────────────────────────────

def test_users_grant_and_block(bot):
    sign_up(bot.store, "24bcs1@cuchd.in")
    assert "24bcs1@cuchd.in | 0 reports | 3 left" in say(bot, "/users")
    assert "Left: 3 free + 0 extra" in say(bot, "/user 24BCS1@cuchd.in")
    assert "now has 8 reports (5 extra)" in say(bot, "/grant 24bcs1@cuchd.in 5")
    assert "now has 6 reports (3 extra)" in say(bot, "/grant 24bcs1@cuchd.in -2")
    assert "No account" in say(bot, "/grant nobody@cuchd.in 5")
    assert "Usage" in say(bot, "/grant 24bcs1@cuchd.in lots") and "not 0" in say(bot, "/grant 24bcs1@cuchd.in 0")
    assert "Blocked and signed out" in say(bot, "/block 24bcs1@cuchd.in")
    assert "BLOCKED" in say(bot, "/users")
    assert "Unblocked" in say(bot, "/unblock 24bcs1@cuchd.in") and "BLOCKED" not in say(bot, "/users")
    assert "Usage" in say(bot, "/user nobody")


def test_long_answers_are_split_for_telegram():
    text = "\n".join(f"line {i} " + "x" * 100 for i in range(200))
    parts = telegram_bot.chunks(text)
    assert len(parts) > 1 and all(len(p) <= 3800 for p in parts) and "".join(parts).count("line") == 200
    assert len(telegram_bot.chunks("y" * 9000)) == 3


# ── the webhook ────────────────────────────────────────────────────

def test_webhook_only_answers_to_telegram(bot, monkeypatch):
    from apps.api import main

    seen, sent = [], []
    monkeypatch.setattr(main.bot, "handle_update", lambda update: seen.append(update))
    monkeypatch.setattr(telegram_bot, "api", lambda method, **kw: sent.append((method, kw)) or {"ok": True})
    client = TestClient(main.app)
    update = {"update_id": 1, "message": {"chat": {"id": ME}, "text": "/status"}}
    assert client.post("/api/telegram/webhook", json=update).status_code == 404
    assert client.post("/api/telegram/webhook", json=update,
                       headers={"X-Telegram-Bot-Api-Secret-Token": "guess"}).status_code == 404
    ok = client.post("/api/telegram/webhook", json=update,
                     headers={"X-Telegram-Bot-Api-Secret-Token": telegram_bot.webhook_secret()})
    assert ok.status_code == 200 and ok.json() == {"ok": True}
    deadline = time.time() + 3
    while not seen and time.time() < deadline:
        time.sleep(0.02)
    assert seen == [update]


def test_handle_update_sends_the_replies_and_deletes_the_login_message(bot, monkeypatch):
    calls = []
    monkeypatch.setattr(telegram_bot, "api", lambda method, **kw: calls.append((method, kw)) or {"ok": True})
    bot.handle_update({"message": {"message_id": 7, "chat": {"id": ME}, "text": f"/login {PASS}"}})
    assert [c[0] for c in calls] == ["deleteMessage", "sendMessage"] and calls[0][1]["message_id"] == 7
    calls.clear()
    bot.handle_update({"message": {"message_id": 8, "chat": {"id": ME}, "text": "/status"}})
    assert calls[0][0] == "sendMessage" and "AI: groq" in calls[0][1]["text"]
    calls.clear()
    bot.handle_update({"message": {"message_id": 9, "chat": {"id": STRANGER}, "text": "/status"}})
    bot.handle_update({"message": {"message_id": 10, "chat": {"id": ME}, "photo": []}})
    assert calls == []


def test_the_admin_status_shows_the_bot(bot):
    from apps.api import main

    assert main.telegram_bot.enabled() and json.dumps({"x": main.telegram_bot.passcode() != ""})


# ── the panel, opened inside Telegram ──────────────────────────────

def launch_data(user_id=ME, age=0, token="123456789:AAFakeTokenFakeTokenFakeTokenFakeToken", tamper=False):
    """What Telegram puts in the mini app's launch link: fields signed with a key made from the bot token."""
    import hashlib
    import hmac
    from urllib.parse import urlencode

    fields = {"auth_date": str(int(time.time()) - age), "query_id": "AAH", "user": json.dumps({"id": user_id, "first_name": "Taha"})}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if tamper:
        fields["user"] = json.dumps({"id": STRANGER})
    return urlencode(fields)


def test_launch_data_is_checked_against_the_bot_token(bot):
    assert telegram_bot.verify_init_data(launch_data()) == ME
    assert telegram_bot.verify_init_data(launch_data(tamper=True)) is None        # someone edited the user
    assert telegram_bot.verify_init_data(launch_data(token="1:wrong")) is None    # not signed by our bot
    assert telegram_bot.verify_init_data(launch_data(age=4000)) is None          # too old
    assert telegram_bot.verify_init_data("") is None and telegram_bot.verify_init_data("hash=abc") is None


def test_the_panel_gives_an_admin_key_only_to_you_when_signed_in(bot):
    from apps.api import main

    client = TestClient(main.app)

    def auth(data):
        return client.post("/api/telegram/auth", json={"init_data": data})

    assert auth(launch_data()).status_code == 401                       # not signed in with the passcode yet
    assert "login" in auth(launch_data()).json()["detail"].lower()
    bot.respond(ME, f"/login {PASS}")
    assert auth(launch_data(tamper=True)).status_code == 401            # forged
    assert auth(launch_data(user_id=STRANGER)).status_code == 401       # a real Telegram user, but not you
    key = auth(launch_data()).json()["token"]
    assert key.startswith("tgs.")

    status = client.get("/api/admin/status", headers={"X-Admin-Token": key})
    assert status.status_code == 200 and status.json()["telegram_bot"] == "on, passcode"
    assert client.get("/api/admin/users", headers={"X-Admin-Token": key}).status_code == 200
    assert client.get("/api/admin/status", headers={"X-Admin-Token": key[:-3] + "abc"}).status_code == 404
    expired = telegram_bot.panel_token(now=time.time() - 5 * 3600)
    assert client.get("/api/admin/status", headers={"X-Admin-Token": expired}).status_code == 404
    bot.respond(ME, "/logout")
    assert auth(launch_data()).status_code == 401                       # signed out in the chat: no new keys


def test_panel_keys_stop_working_when_the_bot_is_switched_off(bot, monkeypatch):
    key = telegram_bot.panel_token()
    assert telegram_bot.valid_panel_token(key)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    assert not telegram_bot.valid_panel_token(key)


def test_the_panel_command_sends_a_button_that_opens_the_page(bot, monkeypatch):
    calls = []
    monkeypatch.setattr(telegram_bot, "api", lambda method, **kw: calls.append((method, kw)) or {"ok": True})
    monkeypatch.setenv("LABFORGE_PUBLIC_URL", "https://labforge.example.com/")
    bot.handle_update({"message": {"chat": {"id": ME}, "text": "/panel"}})
    assert "Sign in first" in calls[-1][1]["text"]
    bot.respond(ME, f"/login {PASS}")
    bot.handle_update({"message": {"chat": {"id": ME}, "text": "/panel"}})
    button = calls[-1][1]["reply_markup"]["inline_keyboard"][0][0]
    assert button["web_app"] == {"url": "https://labforge.example.com/admin"}
    monkeypatch.setenv("LABFORGE_PUBLIC_URL", "http://localhost:8000")
    bot.handle_update({"message": {"chat": {"id": ME}, "text": "/panel"}})
    assert "https address" in calls[-1][1]["text"] and "reply_markup" not in calls[-1][1]
    calls.clear()
    bot.handle_update({"message": {"chat": {"id": STRANGER}, "text": "/panel"}})
    assert calls == []


def test_server_log_endpoint_for_the_panel(bot):
    from apps.api import main

    botlogs.install()
    print("[runner] worker call failed: ConnectError")
    client = TestClient(main.app)
    key = {"X-Admin-Token": telegram_bot.panel_token()}
    lines = client.get("/api/admin/serverlog?count=20&word=worker", headers=key).json()["lines"]
    assert any("worker call failed" in ln for ln in lines)
    assert client.get("/api/admin/serverlog").status_code == 404


def test_the_slash_menu_is_published_for_your_chat_only(bot, monkeypatch):
    calls = []
    monkeypatch.setattr(telegram_bot, "api", lambda method, **kw: calls.append((method, kw)) or {"ok": True})
    assert telegram_bot.publish_commands() is True
    assert len(calls) == 1 and calls[0][0] == "setMyCommands"
    assert calls[0][1]["scope"] == {"type": "chat", "chat_id": ME}
    names = [c["command"] for c in calls[0][1]["commands"]]
    handled = {n[4:] for n in dir(Bot) if n.startswith("cmd_")} | {"panel", "login", "logout", "help"}
    assert set(names) == handled and all(len(c["description"]) <= 256 for c in calls[0][1]["commands"])
