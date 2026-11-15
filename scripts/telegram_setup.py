"""Point your Telegram bot at the live site. Run once after deploying (and again if the address changes).

    python scripts/telegram_setup.py                      # uses LABFORGE_PUBLIC_URL from .env
    python scripts/telegram_setup.py --url https://labforge.onrender.com
    python scripts/telegram_setup.py --remove             # back to no webhook (local polling)

It sets the bot's webhook (with a secret only Telegram and the server know), its command menu, and
the menu button next to the message box that opens the admin panel inside Telegram.
Needs TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env, the same values as on the server.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from core import telegram_bot as bot  # noqa: E402

def check(label: str, answer: dict) -> None:
    ok = bool(answer.get("ok"))
    print(f"{'ok ' if ok else 'FAILED'} {label}" + ("" if ok else f": {answer.get('description', answer)}"))
    if not ok:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default=os.environ.get("LABFORGE_PUBLIC_URL", ""), help="the site's https address")
    parser.add_argument("--remove", action="store_true", help="remove the webhook (use TELEGRAM_POLL=1 locally)")
    args = parser.parse_args()
    if not bot.token():
        sys.exit("TELEGRAM_BOT_TOKEN isn't set in .env")

    me = bot.api("getMe")
    check(f"bot is @{(me.get('result') or {}).get('username', '?')}", me)
    if args.remove:
        check("webhook removed", bot.api("deleteWebhook"))
        return
    url = args.url.strip().rstrip("/")
    if not url.startswith("https://"):
        sys.exit("Telegram only calls https addresses. Pass --url https://your-site or set LABFORGE_PUBLIC_URL.")
    check(f"webhook set to {url}/api/telegram/webhook", bot.api(
        "setWebhook", url=f"{url}/api/telegram/webhook", secret_token=bot.webhook_secret(),
        allowed_updates=["message"], drop_pending_updates=True))
    check("command menu set (the list that pops up when you type /)", {"ok": bot.publish_commands()})
    for chat in sorted(bot.allowed_chats()):
        check(f"panel button set for chat {chat}", bot.api(
            "setChatMenuButton", chat_id=chat,
            menu_button={"type": "web_app", "text": "Admin", "web_app": {"url": f"{url}/admin"}}))
    info = bot.api("getWebhookInfo").get("result", {})
    print(f"Telegram will call: {info.get('url')}  (pending: {info.get('pending_update_count')})")
    print("On the server set: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, LABFORGE_BOT_PASSCODE and "
          f"LABFORGE_PUBLIC_URL={url}")


if __name__ == "__main__":
    main()
