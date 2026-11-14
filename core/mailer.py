"""Sends the sign-in code.

Backends, picked by LABFORGE_MAIL_BACKEND or by which settings are present:
- resend:  RESEND_API_KEY (HTTPS, works on hosts that block SMTP ports; needs a verified domain)
- smtp:    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD (e.g. Gmail with an app password)
- console: prints the code to the server log. For development only.
LABFORGE_MAIL_FROM is the sender, e.g. "LabForge <login@labforge.in>".
"""
from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage


class MailError(Exception):
    pass


def backend() -> str:
    explicit = os.environ.get("LABFORGE_MAIL_BACKEND", "").strip().lower()
    if explicit in ("resend", "smtp", "console"):
        return explicit
    if os.environ.get("RESEND_API_KEY", "").strip():
        return "resend"
    if os.environ.get("SMTP_HOST", "").strip():
        return "smtp"
    return ""


def ready() -> bool:
    return bool(backend())


def _sender() -> str:
    return (os.environ.get("LABFORGE_MAIL_FROM", "").strip() or os.environ.get("SMTP_USER", "").strip()
            or "LabForge <onboarding@resend.dev>")


def send_code(email: str, code: str, minutes: int) -> None:
    subject = f"{code} is your LabForge sign-in code"
    text = (f"Your LabForge sign-in code is {code}\n\n"
            f"It works for {minutes} minutes. If you didn't ask for it, ignore this email: "
            "nobody can sign in without the code.\n")
    kind = backend()
    try:
        if kind == "resend":
            _resend(email, subject, text)
        elif kind == "smtp":
            _smtp(email, subject, text)
        elif kind == "console":
            print(f"[mail] sign-in code for {email}: {code}")
        else:
            raise MailError("No mail backend is configured.")
    except MailError:
        raise
    except Exception as exc:  # noqa: BLE001 - network and provider errors all mean "not sent"
        print(f"[mail] {kind}: {type(exc).__name__}: {exc}")
        raise MailError(str(exc)) from exc


def _resend(email: str, subject: str, text: str) -> None:
    import httpx

    res = httpx.post("https://api.resend.com/emails", timeout=15,
                     headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY'].strip()}"},
                     json={"from": _sender(), "to": [email], "subject": subject, "text": text})
    if res.status_code >= 300:
        raise MailError(f"Resend answered {res.status_code}: {res.text[:200]}")


def _smtp(email: str, subject: str, text: str) -> None:
    host = os.environ["SMTP_HOST"].strip()
    port = int(os.environ.get("SMTP_PORT", "587") or 587)
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "")
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = _sender(), email, subject
    msg.set_content(text)
    context = ssl.create_default_context()
    if port == 465:
        server = smtplib.SMTP_SSL(host, port, timeout=15, context=context)
    else:
        server = smtplib.SMTP(host, port, timeout=15)
        server.starttls(context=context)
    with server:
        if user:
            server.login(user, password)
        server.send_message(msg)
