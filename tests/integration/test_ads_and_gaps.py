"""Extra reports for watching an ad, and the log of what LabForge couldn't do.

The model, the programs and the ad itself are stubbed: these run without a JDK, an AI key or
an ad network.
"""
import json
import time

import pytest
from fastapi.testclient import TestClient

from core.gaps import detect

SHEET = "Experiment 2. Aim: apply a mean filter to an image to remove salt and pepper noise in MATLAB."
ADMIN = {"X-Admin-Token": "owner-key-for-tests"}
LABELS = {"java": "Java", "python": "Python", "matlab": "MATLAB", "javascript": "Node.js", "c": "C"}
CANT_RUN = "MATLAB programs can't be run here. Run it on your machine and add a screenshot of the output."


def task(status="passed", language="java", title="Easy", note="", output=""):
    return {"title": title, "problem": "", "objectives": [], "language": language,
            "files": [{"name": "main.txt", "code": "x"}], "stdin": "", "output": output, "status": status,
            "note": note, "images": [], "show_console": True}


def draft_of(*tasks):
    return {"experiment_no": "2", "title": "Experiment 2", "aim": "Filter", "tasks": list(tasks),
            "learning_outcomes": []}


@pytest.fixture()
def app(monkeypatch):
    monkeypatch.setenv("LABFORGE_REQUIRE_LOGIN", "1")
    monkeypatch.setenv("LABFORGE_ADMIN_TOKEN", ADMIN["X-Admin-Token"])
    monkeypatch.setenv("LABFORGE_AD_REWARDS_PER_DAY", "2")
    monkeypatch.setenv("LABFORGE_AD_MIN_SECONDS", "0")
    monkeypatch.setenv("LABFORGE_FREE_REPORTS", "1")
    monkeypatch.setenv("LABFORGE_GAP_ALERT_AT", "3")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    from apps.api import main

    main.limiter.clear()
    sent: dict[str, str] = {}
    alerts: list[tuple[str, str]] = []
    monkeypatch.setattr(main.mailer, "ready", lambda: True)
    monkeypatch.setattr(main.mailer, "send_code", lambda email, code, minutes: sent.__setitem__(email, code))
    monkeypatch.setattr(main.notify, "notify_owner", lambda subject, text: alerts.append((subject, text)) or True)
    outcome = {"events": [{"type": "done", "draft": draft_of(task()), "cached": False}]}

    def fake_build(sheet, job_dir, language, subject, fresh, cache=None, runner=None):
        yield from outcome["events"]

    monkeypatch.setattr(main, "build_draft", fake_build)
    main.sent, main.outcome, main.alerts = sent, outcome, alerts
    return main


def sign_in(main, email="24bcs10001@cuchd.in") -> TestClient:
    client = TestClient(main.app)
    assert client.post("/api/auth/code", json={"email": email}).status_code == 200
    assert client.post("/api/auth/verify", json={"email": email, "code": main.sent[email]}).status_code == 200
    return client


def write(client, subject="Image Processing"):
    res = client.post("/api/drafts", data={"text": SHEET, "language": "auto", "subject": subject})
    return res, [json.loads(line) for line in res.text.splitlines() if line.strip()] if res.status_code == 200 else []


def until(check, seconds=5.0):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if check():
            return True
        time.sleep(0.05)
    return check()


def watch_ad(client):
    ticket = client.post("/api/ads/ticket").json()["ticket"]
    return client.post("/api/ads/claim", json={"ticket": ticket})


# ── rewarded ads ───────────────────────────────────────────────────

def test_ads_are_off_until_the_owner_turns_them_on(app, monkeypatch):
    monkeypatch.setenv("LABFORGE_AD_REWARDS_PER_DAY", "0")
    client = sign_in(app)
    assert client.get("/api/me").json()["ads"]["enabled"] is False
    assert client.post("/api/ads/ticket").status_code == 404


def test_an_ad_buys_one_more_report(app):
    client = sign_in(app)
    assert client.get("/api/me").json()["ads"] == {"enabled": True, "left": 2, "per_day": 2, "reward": 1,
                                                   "min_seconds": 0}
    assert write(client)[0].status_code == 200  # the one free report
    res, _ = write(client)
    assert res.status_code == 402 and "Watch an ad" in res.json()["detail"]

    me = watch_ad(client)
    assert me.status_code == 200
    assert me.json()["credits"]["extra"] == 1 and me.json()["ads"]["left"] == 1
    assert write(client)[0].status_code == 200
    assert client.get("/api/me").json()["credits"]["left"] == 0


def test_a_ticket_pays_once_and_only_its_owner(app):
    client = sign_in(app)
    ticket = client.post("/api/ads/ticket").json()["ticket"]
    other = sign_in(app, "24bcs10002@cuchd.in")
    assert other.post("/api/ads/claim", json={"ticket": ticket}).status_code == 400  # someone else's
    assert client.post("/api/ads/claim", json={"ticket": "made-up"}).status_code == 400
    assert client.post("/api/ads/claim", json={"ticket": ticket}).status_code == 200
    assert client.post("/api/ads/claim", json={"ticket": ticket}).status_code == 400  # already paid
    assert client.get("/api/me").json()["credits"]["extra"] == 1
    assert other.get("/api/me").json()["credits"]["extra"] == 0


def test_only_so_many_ads_a_day(app):
    client = sign_in(app)
    assert watch_ad(client).status_code == 200
    assert watch_ad(client).status_code == 200
    blocked = client.post("/api/ads/ticket")
    assert blocked.status_code == 429 and "tomorrow" in blocked.json()["detail"]
    assert client.get("/api/me").json()["credits"]["extra"] == 2


def test_a_ticket_cannot_be_claimed_faster_than_an_ad_lasts(app, monkeypatch):
    monkeypatch.setenv("LABFORGE_AD_MIN_SECONDS", "30")
    client = sign_in(app)
    res = watch_ad(client)
    assert res.status_code == 400 and "hasn't finished" in res.json()["detail"]
    assert client.get("/api/me").json()["credits"]["extra"] == 0


def test_ads_need_sign_in(app):
    client = TestClient(app.app)
    assert client.post("/api/ads/ticket").status_code == 401
    assert client.post("/api/ads/claim", json={"ticket": "x"}).status_code == 401


# ── what counts as a gap ───────────────────────────────────────────

def test_detect_names_each_gap_once():
    found = detect([
        task("not_run", "matlab", note=CANT_RUN),
        task("not_run", "matlab", "Medium", note=CANT_RUN),
        task("not_run", "python", note="Needs the tensorflow package, which isn't installed here. Add a screenshot "
                                       "of the output from your machine."),
        task("not_run", "java", note="Needs the gson library, which isn't installed here. Add a screenshot."),
        task("not_run", "javascript", note="Needs npm packages that aren't installed here (socket.io, redis). "
                                           "Run it on your machine and add a screenshot."),
        task("not_run", "javascript", note="Needs a MongoDB server, which isn't set up here. Run it on your machine "
                                           "and add a screenshot."),
        task("failed", "python", output="Traceback...\nModuleNotFoundError: No module named 'torch.nn'"),
        task("failed", "java", output="Main.java:1: error: package lombok does not exist"),
        task("failed", "javascript", output="Error: Cannot find module 'ws'\nRequire stack:"),
        task("not_run", "python", note="This program opens a window. Add a screenshot of it."),
        task("not_run", "java", note="Programs can't be run right now. Add a screenshot of the output."),
        task("not_run", "cobol"),
    ], LABELS)
    assert {g["key"] for g in found} == {
        "language:matlab", "library:python:tensorflow", "library:python:torch", "library:java:lombok",
        "library:java:gson", "library:javascript:socket.io", "library:javascript:redis", "library:javascript:ws",
        "service:mongodb", "window:python", "runner:offline", "language:cobol"}
    assert next(g for g in found if g["key"] == "language:matlab") == {
        "key": "language:matlab", "kind": "language", "label": "MATLAB can't be run"}


def test_ordinary_bugs_and_working_programs_are_not_gaps():
    assert detect([
        task("passed", "java"),
        task("failed", "java", output="Main.java:3: error: ';' expected", note="The program didn't compile."),
        task("failed", "javascript", output="Error: Cannot find module './routes/users'"),  # their own file
        task("failed", "python", note="It didn't finish in time. If it waits for input, add more lines under Input."),
    ], LABELS) == []


# ── the gap log ────────────────────────────────────────────────────

def test_gaps_are_counted_and_the_owner_is_told_once(app, monkeypatch):
    monkeypatch.setenv("LABFORGE_FREE_REPORTS", "10")
    app.outcome["events"] = [{"type": "done", "cached": False,
                              "draft": draft_of(task("not_run", "matlab", "Mean filter", note=CANT_RUN))}]
    first, second = sign_in(app), sign_in(app, "24bcs10002@cuchd.in")

    def gaps():
        return first.get("/api/admin/gaps", headers=ADMIN).json()["gaps"]

    write(first)
    write(second, "FIP Lab")
    assert until(lambda: gaps() and gaps()[0]["reports"] == 2)
    assert app.alerts == []  # not yet: two reports
    write(first)
    assert until(lambda: len(app.alerts) == 1)
    assert "MATLAB can't be run" in app.alerts[0][0] and "3 reports" in app.alerts[0][1]
    write(second)
    assert until(lambda: gaps()[0]["reports"] == 4)
    assert len(app.alerts) == 1  # one alert per gap, not one per report

    gap = gaps()[0]
    assert gap["key"] == "language:matlab" and gap["kind"] == "language" and gap["students"] == 2
    assert set(gap["subjects"]) == {"Image Processing", "FIP Lab"}
    # The latest report that hit it is one of the saved failed sessions.
    flags = first.get("/api/admin/flags", headers=ADMIN).json()["flags"]
    assert gap["job"] in {f["job"] for f in flags}

    assert first.get("/api/admin/gaps").status_code == 404  # students can't read it
    assert first.post("/api/admin/gaps/resolve", headers=ADMIN, json={"key": gap["key"]}).json() == {"ok": True}
    assert gaps() == []


def test_a_report_where_everything_ran_leaves_no_gap(app):
    client = sign_in(app)
    write(client)
    time.sleep(0.3)
    assert client.get("/api/admin/gaps", headers=ADMIN).json()["gaps"] == []


def test_running_a_program_labforge_cannot_run_is_a_gap_with_a_saved_session(app):
    # "Latest session" on a gap opens the saved session of the report that hit it, so a
    # re-run that couldn't be run must leave both.
    client = sign_in(app)
    _, events = write(client)
    job = events[0]["job"]
    ran = client.post(f"/api/jobs/{job}/run", json={"index": 0, "task": task("not_run", "matlab", "Filter")})
    assert ran.status_code == 200 and ran.json()["status"] == "not_run"
    gap = client.get("/api/admin/gaps", headers=ADMIN).json()["gaps"][0]
    assert gap["key"] == "language:matlab" and gap["job"] == job
    flags = client.get("/api/admin/flags", headers=ADMIN).json()["flags"]
    assert [(f["job"], f["kind"]) for f in flags] == [(job, "run")] and "Not run: Filter (matlab)" in flags[0]["reason"]
