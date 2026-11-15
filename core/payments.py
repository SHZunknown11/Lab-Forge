"""Paid report packs through Razorpay (UPI, cards, net banking).

RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET turn it on; LABFORGE_PACKS lists what is for sale.
The flow: the server creates an order for a pack's price, the page opens Razorpay Checkout,
and Razorpay hands the page a signature that only the key secret can produce. The server
checks that signature (and, as a backstop for a page that closed too early, Razorpay's
webhook signed with RAZORPAY_WEBHOOK_SECRET) before adding the reports. The amount always
comes from the pack on the server, never from the page.
"""
from __future__ import annotations

import hashlib
import hmac
import os


class PaymentError(Exception):
    pass


def key_id() -> str:
    return os.environ.get("RAZORPAY_KEY_ID", "").strip()


def _secret() -> str:
    return os.environ.get("RAZORPAY_KEY_SECRET", "").strip()


def configured() -> bool:
    return bool(key_id() and _secret())


def create_order(amount_paise: int, receipt: str, notes: dict) -> str:
    """A Razorpay order for this amount. Returns its id."""
    import httpx

    try:
        res = httpx.post("https://api.razorpay.com/v1/orders", auth=(key_id(), _secret()), timeout=20,
                         json={"amount": int(amount_paise), "currency": "INR", "receipt": receipt[:40],
                               "notes": notes})
    except httpx.HTTPError as exc:
        raise PaymentError(f"Razorpay unreachable: {type(exc).__name__}") from exc
    if res.status_code >= 300:
        raise PaymentError(f"Razorpay answered {res.status_code}: {res.text[:200]}")
    order_id = str(res.json().get("id", ""))
    if not order_id.startswith("order_"):
        raise PaymentError("Razorpay returned no order id.")
    return order_id


def _matches(secret: str, message: bytes, signature: str) -> bool:
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip())


def verify_payment(order_id: str, payment_id: str, signature: str) -> bool:
    """True when Razorpay signed this payment for this order."""
    return _matches(_secret(), f"{order_id}|{payment_id}".encode(), signature)


def verify_webhook(body: bytes, signature: str) -> bool:
    return _matches(os.environ.get("RAZORPAY_WEBHOOK_SECRET", "").strip(), body, signature)
