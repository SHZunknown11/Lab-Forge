"""Sign-in by emailed code, report credits and the saved copies of sessions that went wrong.

The model and the programs are stubbed, so these run without a JDK or an AI key.
"""
import json
import time

import pytest
from fastapi.testclient import TestClient

from core.accounts import AccountError, Accounts, NoCredits

SHEET = "Experiment 4. Aim: write a Java program that reads two numbers and prints their sum and product."
ADMIN = {"X-Admin-Token": "owner-key-for-tests"}


def task(status="passed", language="java", title="Easy"):
    return {"title": title, "problem": "Add two numbers", "objectives": [], "language": language,
            "files": [{"name": "Main.java", "code": "class Main { }"}], "stdin": "2 3", "output": "5",
            "status": status, "note": "" if status == "passed" else "error: ';' expected", "images": [],
            "show_console": True}


def draft_of(*tasks):
    return {"experiment_no": "4", "title": "Sum of two numbers", "aim": "Add", "tasks": list(tasks),
            "learning_outcomes": []}


@pytest.fixture()
def app(monkeypatch):
    monkeypatch.setenv("LABFORGE_REQUIRE_LOGIN", "1")
    monkeypatch.setenv("LABFORGE_ADMIN_TOKEN", ADMIN["X-Admin-Token"])
    from apps.api import main

    main.limiter.clear()
    sent: dict[str, str] = {}
    monkeypatch.setattr(main.mailer, "ready", lambda: True)
    monkeypatch.setattr(main.mailer, "send_code", lambda email, code, minutes: sent.__setitem__(email, code))
    outcome = {"events": [{"type": "done", "draft": draft_of(task()), "cached": False}]}

    def fake_build(sheet, job_dir, language, subject, fresh, cache=None, runner=None):
        yield from outcome["events"]

    monkeypatch.setattr(main, "build_draft", fake_build)
    main.sent, main.outcome = sent, outcome
    return main


def sign_in(main, email="24bcs10001@cuchd.in") -> TestClient:
    client = TestClient(main.app)
    assert client.post("/api/auth/code", json={"email": email}).status_code == 200
    res = client.post("/api/auth/verify", json={"email": email, "code": main.sent[email]})
    assert res.status_code == 200, res.text
    return client


def write(client):
    res = client.post("/api/drafts", data={"text": SHEET, "language": "auto", "subject": "PBLJ"})
    events = [json.loads(line) for line in res.text.splitlines() if line.strip()] if res.status_code == 200 else []
    return res, events


def until(check, seconds=5.0):
    """The credit refund and the saved copy happen just after the stream ends."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        if check():
            return True
        time.sleep(0.05)
    return check()


# ── the store ──────────────────────────────────────────────────────

def test_only_college_addresses():
    assert Accounts.check_email(" 24BCS10001@CUCHD.in ") == "24bcs10001@cuchd.in"
    for bad in ("someone@gmail.com", "not-an-email", "a@cuchd.in.evil.com", ""):
        with pytest.raises(AccountError):
            Accounts.check_email(bad)


def test_code_signs_in_once_and_wrong_codes_run_out():
    store = Accounts()
    email = "24bcs10001@cuchd.in"
    code = store.start_code(email)
    with pytest.raises(AccountError):  # asking again straight away
        store.start_code(email)
    wrong = "000000" if code != "000000" else "111111"
    with pytest.raises(AccountError):
        store.verify_code(email, wrong)
    user, token = store.verify_code(email, code)
    assert store.user_for(token)["email"] == email
    with pytest.raises(AccountError):  # a code works once
        store.verify_code(email, code)
    store.logout(token)
    assert store.user_for(token) is None
    assert store.user_for("made-up-token") is None

    store.drop_code(email)
    code = store.start_code(email)
    for _ in range(5):
        with pytest.raises(AccountError):
            store.verify_code(email, wrong)
    with pytest.raises(AccountError):  # even the right code is refused after five wrong tries
        store.verify_code(email, code)


def test_credits_spend_refund_and_grant():
    store = Accounts()
    email = "24bcs10002@cuchd.in"
    user, _ = store.verify_code(email, store.start_code(email))
    assert store.credits(user["id"]) == {"free": 3, "free_total": 3, "extra": 0, "left": 3, "period": "day"}
    for job in ("a", "b", "c"):
        assert store.spend(user["id"], job) == "free"
    with pytest.raises(NoCredits):
        store.spend(user["id"], "d")
    store.refund(user["id"], "c")
    store.refund(user["id"], "c")  # only once
    assert store.credits(user["id"])["left"] == 1
    assert store.grant(email, 2)["extra"] == 2
    store.spend(user["id"], "e")
    assert store.spend(user["id"], "f") == "extra"
    assert store.credits(user["id"]) == {"free": 0, "free_total": 3, "extra": 1, "left": 1, "period": "day"}


def test_history_key_is_stable_and_per_account():
    store = Accounts()
    a, _ = store.verify_code("24bcs1@cuchd.in", store.start_code("24bcs1@cuchd.in"))
    b, _ = store.verify_code("24bcs2@cuchd.in", store.start_code("24bcs2@cuchd.in"))
    assert store.history_key(a["id"]) == Accounts().history_key(a["id"])
    assert store.history_key(a["id"]) != store.history_key(b["id"])


# ── through the API ────────────────────────────────────────────────

def test_writing_needs_sign_in(app):
    client = TestClient(app.app)
    assert client.get("/api/meta").json()["auth"]["required"] is True
    assert client.get("/api/me").json() == {"user": None}
    res, _ = write(client)
    assert res.status_code == 401
    assert client.post("/api/auth/code", json={"email": "someone@gmail.com"}).status_code == 422


def test_wrong_code_is_refused(app):
    client = TestClient(app.app)
    email = "24bcs10003@cuchd.in"
    client.post("/api/auth/code", json={"email": email})
    wrong = "000000" if app.sent[email] != "000000" else "111111"
    assert client.post("/api/auth/verify", json={"email": email, "code": wrong}).status_code == 400
    assert client.get("/api/me").json() == {"user": None}


def test_sign_in_write_and_run_out(app):
    client = sign_in(app)
    me = client.get("/api/me").json()
    assert me["user"] == {"email": "24bcs10001@cuchd.in"} and me["credits"]["left"] == 3 and me["history_key"]
    for left in (2, 1, 0):
        res, events = write(client)
        assert res.status_code == 200 and events[-1]["type"] == "done"
        assert client.get("/api/me").json()["credits"]["left"] == left
    res, _ = write(client)
    assert res.status_code == 402 and "free reports" in res.json()["detail"]

    # The owner tops the account up.
    granted = client.post("/api/admin/credits", headers=ADMIN, json={"email": "24bcs10001@cuchd.in", "amount": 1})
    assert granted.status_code == 200 and granted.json()["left"] == 1
    assert write(client)[0].status_code == 200

    client.post("/api/auth/logout")
    assert client.get("/api/me").json() == {"user": None}
    assert write(client)[0].status_code == 401


def test_a_report_that_fails_costs_nothing(app):
    client = sign_in(app)
    app.outcome["events"] = [{"type": "error", "message": "The AI service is busy."}]
    res, events = write(client)
    assert res.status_code == 200 and events[-1]["type"] == "error"
    assert until(lambda: client.get("/api/me").json()["credits"]["left"] == 3)


def test_sessions_with_problems_are_kept_for_the_owner(app):
    client = sign_in(app)
    write(client)  # everything ran: nothing kept
    bad = draft_of(task(), task("failed", title="Medium"), task("not_run", "matlab", "Hard"))
    app.outcome["events"] = [{"type": "done", "draft": bad, "cached": False}]
    _, events = write(client)
    job = events[0]["job"]

    assert client.get("/api/admin/flags").status_code == 404  # students can't read them
    assert until(lambda: len(client.get("/api/admin/flags", headers=ADMIN).json()["flags"]) == 1)
    listed = client.get("/api/admin/flags", headers=ADMIN).json()["flags"][0]
    assert listed["email"] == "24bcs10001@cuchd.in" and listed["job"] == job
    assert "Failed: Medium (java)" in listed["reason"] and "Not run: Hard (matlab)" in listed["reason"]

    detail = client.get(f"/api/admin/flags/{listed['id']}", headers=ADMIN).json()
    assert detail["sheet"].startswith("Experiment 4") and len(detail["tasks"]) == 3
    assert detail["tasks"][1]["files"][0]["code"] == "class Main { }"
    assert detail["tasks"][1]["note"] == "error: ';' expected"

    users = client.get("/api/admin/users", headers=ADMIN).json()["users"]
    assert users[0]["email"] == "24bcs10001@cuchd.in" and users[0]["reports"] == 2

    assert client.delete(f"/api/admin/flags/{listed['id']}", headers=ADMIN).json() == {"ok": True}
    assert client.get("/api/admin/flags", headers=ADMIN).json()["flags"] == []


def test_blocked_accounts_are_signed_out(app):
    client = sign_in(app)
    assert client.post("/api/admin/block", headers=ADMIN,
                       json={"email": "24bcs10001@cuchd.in", "blocked": True}).status_code == 200
    assert client.get("/api/me").json() == {"user": None}
    assert write(client)[0].status_code == 401
