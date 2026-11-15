"""Personal notes, paid packs, the subject list, referrals and the owner's summary.

The model, the programs and Razorpay are stubbed: no AI key, JDK or payment account needed.
"""
import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient

from core.gaps import detect

SHEET = "Experiment 5. Aim: write a Java program that sorts an array of numbers using bubble sort."
ADMIN = {"X-Admin-Token": "owner-key-for-tests"}
KEY_SECRET = "rzp-test-secret"
HOOK_SECRET = "rzp-hook-secret"


def draft_of(status="passed"):
    return {"experiment_no": "5", "title": "Experiment 5", "aim": "Sort", "learning_outcomes": [],
            "tasks": [{"title": "Easy", "problem": "", "objectives": [], "language": "java",
                       "files": [{"name": "Main.java", "code": "class Main { }"}], "stdin": "", "output": "1 2 3",
                       "status": status, "note": "", "images": [], "show_console": True}]}


@pytest.fixture()
def app(monkeypatch):
    monkeypatch.setenv("LABFORGE_REQUIRE_LOGIN", "1")
    monkeypatch.setenv("LABFORGE_ADMIN_TOKEN", ADMIN["X-Admin-Token"])
    monkeypatch.setenv("LABFORGE_FREE_REPORTS", "3")
    from apps.api import main

    main.limiter.clear()
    sent: dict[str, str] = {}
    seen: dict[str, str] = {}
    monkeypatch.setattr(main.mailer, "ready", lambda: True)
    monkeypatch.setattr(main.mailer, "send_code", lambda email, code, minutes: sent.__setitem__(email, code))
    outcome = {"events": [{"type": "done", "draft": draft_of(), "cached": False}]}

    def fake_build(sheet, job_dir, language, subject, fresh, cache=None, runner=None):
        seen["sheet"] = sheet
        yield from outcome["events"]

    monkeypatch.setattr(main, "build_draft", fake_build)
    main.sent, main.outcome, main.seen = sent, outcome, seen
    return main


def sign_in(main, email="24bcs10001@cuchd.in", ref="") -> TestClient:
    client = TestClient(main.app)
    assert client.post("/api/auth/code", json={"email": email}).status_code == 200
    res = client.post("/api/auth/verify", json={"email": email, "code": main.sent[email], "ref": ref})
    assert res.status_code == 200, res.text
    return client


def write(client, **form):
    res = client.post("/api/drafts", data={"text": SHEET, "language": "auto", "subject": "DSA Lab", **form})
    return res, [json.loads(line) for line in res.text.splitlines() if line.strip()] if res.status_code == 200 else []


def left(client):
    return client.get("/api/me").json()["credits"]["left"]


def until(check, seconds=5.0):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if check():
            return True
        time.sleep(0.05)
    return check()


# ── a personal note ────────────────────────────────────────────────

def test_a_note_goes_to_the_model_and_costs_one_more_report(app):
    client = sign_in(app)
    assert client.get("/api/meta").json()["note"] == {"max": 300, "extra_cost": 1}
    res, _ = write(client, note="  I used a while loop\nand my array is 9 4 7  ")
    assert res.status_code == 200
    assert app.seen["sheet"].endswith("Student's note: I used a while loop and my array is 9 4 7")
    assert left(client) == 1  # 3 free, minus the report and the note

    write(client)  # an ordinary report: one
    assert "Student's note" not in app.seen["sheet"] and left(client) == 0


def test_a_note_needs_enough_reports_and_is_refunded_in_full(app):
    client = sign_in(app)
    write(client)
    write(client)
    res, _ = write(client, note="use recursion")
    assert res.status_code == 402 and "uses 2 reports and you have 1" in res.json()["detail"]
    assert left(client) == 1

    client2 = sign_in(app, "24bcs10002@cuchd.in")
    app.outcome["events"] = [{"type": "error", "message": "The AI service is busy."}]
    write(client2, note="use recursion")
    assert until(lambda: left(client2) == 3)  # both came back


def test_a_long_note_is_cut(app):
    client = sign_in(app)
    write(client, note="x" * 1000)
    assert len(app.seen["sheet"].split("Student's note: ")[1]) == 300


# ── paid packs ─────────────────────────────────────────────────────

@pytest.fixture()
def shop(app, monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_key")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", KEY_SECRET)
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", HOOK_SECRET)
    monkeypatch.setenv("LABFORGE_PACKS", "10:10, 49:70, nonsense, 0:5")
    made = []

    def create_order(amount_paise, receipt, notes):
        made.append({"amount": amount_paise, "receipt": receipt, "notes": notes})
        return f"order_test{len(made)}"

    monkeypatch.setattr(app.payments, "create_order", create_order)
    app.made = made
    return app


def sign(secret, text):
    return hmac.new(secret.encode(), text.encode(), hashlib.sha256).hexdigest()


def test_packs_are_off_without_keys(app):
    client = sign_in(app)
    assert client.get("/api/meta").json()["pay"] == {"enabled": False, "key_id": "", "packs": []}
    assert client.post("/api/pay/order", json={"pack": "p10"}).status_code == 404


def test_buying_a_pack_adds_its_reports_once(shop):
    client = sign_in(shop)
    pay = client.get("/api/meta").json()["pay"]
    assert pay["enabled"] and pay["key_id"] == "rzp_test_key"
    assert pay["packs"] == [{"id": "p10", "price": 10, "reports": 10}, {"id": "p49", "price": 49, "reports": 70}]

    order = client.post("/api/pay/order", json={"pack": "p49"}).json()
    assert order["order_id"] == "order_test1" and order["amount"] == 4900 and order["currency"] == "INR"
    assert shop.made[0]["amount"] == 4900 and "cuchd" not in json.dumps(shop.made[0])  # no email leaves the server
    assert client.post("/api/pay/order", json={"pack": "p999"}).status_code == 404

    proof = {"order_id": "order_test1", "payment_id": "pay_abc"}
    bad = client.post("/api/pay/verify", json={**proof, "signature": "0" * 64})
    assert bad.status_code == 400 and client.get("/api/me").json()["credits"]["extra"] == 0

    good = {**proof, "signature": sign(KEY_SECRET, "order_test1|pay_abc")}
    other = sign_in(shop, "24bcs10002@cuchd.in")
    assert other.post("/api/pay/verify", json=good).status_code == 400  # not their order
    me = client.post("/api/pay/verify", json=good)
    assert me.status_code == 200 and me.json()["credits"]["extra"] == 70
    client.post("/api/pay/verify", json=good)  # the page sends it twice
    assert client.get("/api/me").json()["credits"]["extra"] == 70


def test_the_webhook_pays_when_the_page_closed_early(shop):
    client = sign_in(shop)
    client.post("/api/pay/order", json={"pack": "p10"})
    body = json.dumps({"event": "payment.captured",
                       "payload": {"payment": {"entity": {"id": "pay_xyz", "order_id": "order_test1"}}}})
    forged = client.post("/api/pay/webhook", content=body, headers={"X-Razorpay-Signature": "f" * 64})
    assert forged.status_code == 400 and client.get("/api/me").json()["credits"]["extra"] == 0
    real = client.post("/api/pay/webhook", content=body, headers={"X-Razorpay-Signature": sign(HOOK_SECRET, body)})
    assert real.status_code == 200 and client.get("/api/me").json()["credits"]["extra"] == 10
    # The page's own confirmation arriving afterwards adds nothing more.
    client.post("/api/pay/verify", json={"order_id": "order_test1", "payment_id": "pay_xyz",
                                         "signature": sign(KEY_SECRET, "order_test1|pay_xyz")})
    assert client.get("/api/me").json()["credits"]["extra"] == 10

    summary = client.get("/api/admin/summary", headers=ADMIN).json()
    assert summary["orders"] == 1 and summary["revenue"] == 10


def test_paying_needs_sign_in(shop):
    assert TestClient(shop.app).post("/api/pay/order", json={"pack": "p10"}).status_code == 401


# ── subjects ───────────────────────────────────────────────────────

def test_subjects_students_type_wait_for_the_owner(app):
    client = sign_in(app)
    names = [s["name"] for s in client.get("/api/subjects").json()["subjects"]]
    assert "Project Based Learning in Java" in names and "Compiler Design Lab" not in names

    write(client, subject="Compiler  Design Lab", subject_code="24CSP-401")
    write(client, subject="compiler design lab")

    def waiting():
        return [s for s in client.get("/api/admin/subjects", headers=ADMIN).json()["subjects"]
                if s["key"] == "compiler design lab"]

    assert until(lambda: waiting() and waiting()[0]["uses"] == 2)
    assert waiting()[0] == {**waiting()[0], "name": "Compiler Design Lab", "code": "24CSP-401", "status": "pending"}
    assert "Compiler Design Lab" not in [s["name"] for s in client.get("/api/subjects").json()["subjects"]]

    assert client.post("/api/admin/subjects", json={"key": "compiler design lab", "status": "approved"}).status_code == 404
    client.post("/api/admin/subjects", headers=ADMIN, json={"key": "compiler design lab", "status": "approved"})
    listed = client.get("/api/subjects").json()["subjects"]
    assert {"name": "Compiler Design Lab", "code": "24CSP-401"} in listed


# ── referrals ──────────────────────────────────────────────────────

def test_inviting_a_friend_pays_both_once_the_friend_writes_a_report(app):
    asha = sign_in(app)
    link = asha.get("/api/me").json()["referral"]
    assert link == {"enabled": True, "code": link["code"], "reward": 2, "welcome": 1, "joined": 0, "waiting": 0}
    assert len(link["code"]) == 10

    ravi = sign_in(app, "24bcs10002@cuchd.in", ref=link["code"])
    assert ravi.get("/api/me").json()["credits"]["extra"] == 1  # the welcome report
    assert asha.get("/api/me").json()["referral"]["waiting"] == 1
    assert asha.get("/api/me").json()["credits"]["extra"] == 0  # not until Ravi really uses it

    write(ravi)
    assert until(lambda: asha.get("/api/me").json()["credits"]["extra"] == 2)
    assert asha.get("/api/me").json()["referral"] == {**link, "joined": 1, "waiting": 0}
    write(ravi)
    time.sleep(0.3)
    assert asha.get("/api/me").json()["credits"]["extra"] == 2  # once per friend


def test_referral_codes_cannot_be_farmed(app):
    asha = sign_in(app)
    code = asha.get("/api/me").json()["referral"]["code"]
    # Signing in again with your own code, or an existing account using a code, gives nothing.
    again = sign_in(app, ref=code)
    assert again.get("/api/me").json()["credits"]["extra"] == 0
    ravi = sign_in(app, "24bcs10002@cuchd.in")
    ravi_again = sign_in(app, "24bcs10002@cuchd.in", ref=code)
    assert ravi_again.get("/api/me").json()["credits"]["extra"] == 0
    stranger = sign_in(app, "24bcs10003@cuchd.in", ref="zzzzzzzzzz")  # not a code
    assert stranger.get("/api/me").json()["credits"]["extra"] == 0
    assert asha.get("/api/me").json()["referral"]["waiting"] == 0
    assert ravi.get("/api/me").json()["user"]["email"] == "24bcs10002@cuchd.in"


# ── the owner's summary ────────────────────────────────────────────

def test_summary_counts_the_week(app):
    client = sign_in(app)
    write(client)
    write(client, note="my own way")  # one report, even though it cost two
    assert until(lambda: client.get("/api/admin/summary", headers=ADMIN).json()["reports"] == 2)
    s = client.get("/api/admin/summary", headers=ADMIN).json()
    assert (s["accounts"], s["new_accounts"], s["active_accounts"], s["orders"], s["revenue"]) == (1, 1, 1, 0, 0)
    assert client.get("/api/admin/summary").status_code == 404
    users = client.get("/api/admin/users", headers=ADMIN).json()["users"]
    assert users[0]["reports"] == 2
    assert "2 reports by 1 students" in app._summary_text(s)


def test_the_weekly_digest_goes_out_once_a_week():
    from core.accounts import Accounts

    store = Accounts()
    assert store.digest_due() is False  # the first call starts the clock
    assert store.digest_due() is False
    with store._db() as conn:
        conn.execute("UPDATE lf_meta SET value = %s WHERE key = 'digest_at'", (str(time.time() - 8 * 86400),))
    assert store.digest_due() is True
    assert store.digest_due() is False


# ── MATLAB and several workers ─────────────────────────────────────

def test_a_matlab_function_octave_lacks_is_a_gap():
    note = "Uses imsegkmeans, which Octave (the free MATLAB stand-in used here) doesn't have. Run it in MATLAB."
    found = detect([{"language": "matlab", "status": "not_run", "note": note, "output": ""}], {"matlab": "MATLAB"})
    assert found == [{"key": "library:matlab:imsegkmeans", "kind": "library", "label": "MATLAB function: imsegkmeans"}]


def test_matlab_without_octave_still_asks_for_a_screenshot(tmp_path, monkeypatch):
    from core.execution.runner import CodeRunner
    from core.schemas import CodeFile

    monkeypatch.setenv("EXEC_MATLAB", "0")
    monkeypatch.setenv("EXEC_BACKEND", "local")
    result = CodeRunner().run("matlab", [CodeFile(name="main.m", code="disp(1)")], "", tmp_path)
    assert result.status == "not_run" and "MATLAB programs can't be run here" in result.note


def test_several_workers_can_be_listed(monkeypatch):
    from core.execution import runner

    monkeypatch.setenv("EXEC_WORKER_URL", "http://w1:8100/, http://w2:8100 ,")
    monkeypatch.setenv("EXEC_WORKER_TOKEN", "t")
    urls, token = runner._workers()
    assert sorted(urls) == ["http://w1:8100", "http://w2:8100"] and token == "t"
    assert runner._worker()[0] in urls
    monkeypatch.setenv("EXEC_WORKER_URL", "")
    assert runner._workers() == ([], "t") and runner._worker() == ("", "t")


def test_a_worker_that_is_down_hands_over_to_the_next(tmp_path, monkeypatch):
    import httpx

    from core.execution import runner
    from core.schemas import CodeFile

    monkeypatch.setenv("EXEC_WORKER_URL", "http://down:8100,http://up:8100")
    monkeypatch.setenv("EXEC_WORKER_TOKEN", "t")
    asked = []

    def post(url, **kwargs):
        asked.append(url)
        if "down" in url:
            raise httpx.ConnectError("refused")
        return httpx.Response(200, json={"status": "passed", "output": "hello", "note": "", "figures": []})

    monkeypatch.setattr(httpx, "post", post)
    result = runner._run_remote("python", [CodeFile(name="main.py", code="print('hello')")], "", tmp_path)
    assert result.status == "passed" and result.output == "hello" and asked[-1] == "http://up:8100/run"
