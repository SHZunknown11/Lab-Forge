"""Tells the site owner when something needs them: a gap several students have hit, or the
program runner going offline.

Telegram when TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set (create a bot with @BotFather,
send it a message, read your chat id from https://api.telegram.org/bot<token>/getUpdates);
otherwise an email to LABFORGE_OWNER_EMAIL through the mailer. Sent on a background thread and
never raises: a failed alert must not break a student's report.
"""
from __future__ import annotations

import os
import threading

from core import mailer


def backend() -> str:
    if os.environ.get("TELEGRAM_BOT_TOKEN", "").strip() and os.environ.get("TELEGRAM_CHAT_ID", "").strip():
        return "telegram"
    if os.environ.get("LABFORGE_OWNER_EMAIL", "").strip() and mailer.ready():
        return "email"
    return ""


def send(subject: str, text: str) -> None:
    kind = backend()
    try:
        if kind == "telegram":
            import httpx

            token = os.environ["TELEGRAM_BOT_TOKEN"].strip()
            res = httpx.post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=15,
                             json={"chat_id": os.environ["TELEGRAM_CHAT_ID"].strip(),
                                   "text": f"{subject}\n\n{text}"[:3900], "disable_web_page_preview": True})
            if res.status_code >= 300:
                print(f"[notify] telegram answered {res.status_code}")
        elif kind == "email":
            mailer.send(os.environ["LABFORGE_OWNER_EMAIL"].strip(), subject, text)
    except Exception as exc:  # noqa: BLE001
        print(f"[notify] {kind}: {type(exc).__name__}")


def notify_owner(subject: str, text: str) -> bool:
    """Queue an alert. False when no way of reaching the owner is set up."""
    if not backend():
        return False
    threading.Thread(target=send, args=(subject, text), daemon=True, name="notify").start()
    return True
