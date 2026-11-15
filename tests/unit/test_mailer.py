import httpx
import pytest

from core import mailer


def test_brevo_is_picked_by_its_key_and_sends_over_https(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setenv("LABFORGE_MAIL_FROM", "LabForge <me@gmail.com>")
    assert mailer.backend() == "brevo" and mailer.ready()
    sent = {}

    def post(url, **kwargs):
        sent.update(url=url, **kwargs)
        return httpx.Response(201, json={"messageId": "x"})

    monkeypatch.setattr(httpx, "post", post)
    mailer.send_code("24bcs1@cuchd.in", "123456", 10)
    assert sent["url"] == "https://api.brevo.com/v3/smtp/email" and sent["headers"]["api-key"] == "xkeysib-test"
    body = sent["json"]
    assert body["sender"] == {"name": "LabForge", "email": "me@gmail.com"}
    assert body["to"] == [{"email": "24bcs1@cuchd.in"}] and "123456" in body["textContent"]
    assert body["subject"].startswith("123456")


def test_brevo_refusal_is_a_mail_error(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "bad")
    monkeypatch.setenv("LABFORGE_MAIL_FROM", "me@gmail.com")
    monkeypatch.setattr(httpx, "post", lambda url, **kw: httpx.Response(401, text="Key not found"))
    with pytest.raises(mailer.MailError, match="Brevo answered 401"):
        mailer.send_code("24bcs1@cuchd.in", "123456", 10)


def test_resend_still_wins_when_both_are_set(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_x")
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-x")
    assert mailer.backend() == "resend"
