"""The website's guard rails: what runs, what a report may show, limits, headers, deletion."""
import json
import os
import threading
import time

import pytest
from fastapi.testclient import TestClient

from core.execution.runner import CodeRunner

needs_java = pytest.mark.skipif(not CodeRunner().available().get("java"), reason="JDK not installed")
CID = {"X-Client-Id": "test-browser-0123456789"}


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("PDF_BACKEND", "gotenberg")
    monkeypatch.setenv("GOTENBERG_URL", "")
    from apps.api import main

    main.limiter.clear()
    return TestClient(main.app)


def draft(client, headers=CID):
    with open("examples/source-notes.md", "rb") as fh:
        res = client.post("/api/drafts", files={"file": ("sheet.md", fh, "text/markdown")},
                          data={"language": "auto", "subject": "PBLJ"}, headers=headers)
    assert res.status_code == 200, res.text
    return [json.loads(line) for line in res.text.splitlines() if line.strip()]


FIELDS = [{"label": "Student Name", "value": "Asha"}]


# ── output can't be invented ───────────────────────────────────────

@needs_java
def test_render_ignores_output_sent_by_the_browser(client):
    events = draft(client)
    job, done = events[0]["job"], events[-1]["draft"]
    real = done["tasks"][0]["output"]
    done["tasks"][0]["output"] = "Totally made up output"
    done["tasks"][0]["status"] = "passed"
    client.post(f"/api/jobs/{job}/render", json={"draft": done, "fields": FIELDS, "template": "plain", "pdf": False},
                headers=CID)
    from apps.api import main
    from core.pipeline.orchestrator import apply_results
    from core.schemas import ReportDraft

    d = ReportDraft.model_validate(done)
    apply_results(main.job_path(job), d)
    assert d.tasks[0].output == real != "Totally made up output"


@needs_java
def test_changed_code_has_no_output_until_it_runs_again(client):
    events = draft(client)
    job, done = events[0]["job"], events[-1]["draft"]
    done["tasks"][0]["files"][0]["code"] += "\n// changed\n"
    res = client.post(f"/api/jobs/{job}/render", json={"draft": done, "fields": FIELDS, "template": "plain",
                                                         "pdf": False}, headers=CID).json()
    assert any("changed after it ran" in w for w in res["warnings"])
    assert any("no output yet" in w for w in res["warnings"])


def test_fabricated_figure_names_are_dropped(tmp_path):
    from core.pipeline.orchestrator import apply_results
    from core.schemas import ReportDraft, Task

    (tmp_path / "up_abc.png").write_bytes(b"x")
    (tmp_path / "t0_fig1_aaaa.png").write_bytes(b"x")
    d = ReportDraft(tasks=[Task(images=["up_abc.png", "t0_fig1_aaaa.png", "up_missing.png"])])
    apply_results(tmp_path, d)
    assert d.tasks[0].images == ["up_abc.png"]  # never ran: no captured figure counts


# ── what may run ───────────────────────────────────────────────────

@needs_java
def test_generated_code_reruns_but_edited_code_has_its_own_limit(client, monkeypatch):
    monkeypatch.setenv("LABFORGE_EDITED_RUNS_PER_HOUR", "1")
    events = draft(client)
    job, task = events[0]["job"], events[-1]["draft"]["tasks"][0]
    for stdin in ("4\n", "9\n"):  # the server's own code, new input: normal runs
        task["stdin"] = stdin
        assert client.post(f"/api/jobs/{job}/run", json={"index": 0, "task": task}, headers=CID).status_code == 200
    task["files"][0]["code"] += "\n// my change\n"
    assert client.post(f"/api/jobs/{job}/run", json={"index": 0, "task": task}, headers=CID).status_code == 200
    task["files"][0]["code"] += "\n// another\n"
    res = client.post(f"/api/jobs/{job}/run", json={"index": 0, "task": task}, headers=CID)
    assert res.status_code == 429


@needs_java
def test_edited_shell_scripts_are_refused(client):
    job = draft(client)[0]["job"]
    task = {"title": "x", "language": "shell", "files": [{"name": "script.sh", "code": "cat /etc/passwd"}], "stdin": ""}
    res = client.post(f"/api/jobs/{job}/run", json={"index": 0, "task": task}, headers=CID)
    assert res.status_code == 403


@needs_java
def test_programs_run_outside_the_job_folders(client, tmp_path):
    from apps.api import main
    from core.pipeline import orchestrator

    job = draft(client)[0]["job"]
    code = "import os\nprint(os.getcwd())\nprint(os.path.exists('../sheet.txt'))\n"
    task = {"title": "x", "language": "python", "files": [{"name": "main.py", "code": code}], "stdin": ""}
    out = client.post(f"/api/jobs/{job}/run", json={"index": 0, "task": task}, headers=CID).json()["output"]
    assert str(orchestrator.RUN_ROOT.name) in out and "False" in out
    assert str(main.job_path(job)) not in out


# ── limits ─────────────────────────────────────────────────────────

def test_limits_are_per_browser_with_a_bigger_per_ip_allowance():
    from apps.api import main

    class Req:
        def __init__(self, cid):
            self.headers = {"x-client-id": cid} if cid else {}
            self.client = type("C", (), {"host": "10.9.9.9"})()

    main.limiter.clear()
    per_client, per_ip, _ = main.limits()["feedback"]
    for _ in range(per_client):
        main.guard(Req("browser-a-0123456789abc"), "feedback")
    with pytest.raises(Exception) as exc:
        main.guard(Req("browser-a-0123456789abc"), "feedback")
    assert getattr(exc.value, "status_code", 0) == 429
    main.guard(Req("browser-b-0123456789abc"), "feedback")  # a classmate on the same Wi-Fi still gets in
    assert per_ip > per_client


# ── resuming after the connection drops ────────────────────────────

def test_events_can_be_replayed_after_a_disconnect(tmp_path):
    from core.pipeline.jobs import DraftJobs

    jobs = DraftJobs(max_active=1)

    def produce(stop):
        yield {"type": "stage", "text": "one"}
        time.sleep(0.2)
        yield {"type": "done", "draft": {}}

    jobs.start("j" * 32, tmp_path, {"type": "job", "job": "j" * 32}, produce)
    first = next(iter(jobs.stream("j" * 32, tmp_path, -1, 0.05)))
    assert first["type"] == "job" and first["seq"] == 0
    rest = [e for e in jobs.stream("j" * 32, tmp_path, 0, 0.05) if e["type"] != "ping"]
    assert [e["type"] for e in rest] == ["stage", "done"]
    # After a restart nothing is in memory: the file still has it.
    replay = list(DraftJobs()._replay(tmp_path, 1))
    assert [e["type"] for e in replay] == ["done"]


def test_a_job_cut_off_by_a_restart_says_so(tmp_path):
    from core.pipeline.jobs import DraftJobs

    (tmp_path / "events.jsonl").write_text(json.dumps({"type": "job", "seq": 0}) + "\n")
    events = list(DraftJobs().stream("x" * 32, tmp_path, -1))
    assert events[-1]["type"] == "error" and "restarted" in events[-1]["message"]


def test_busy_server_queues_reports(tmp_path):
    from core.pipeline.jobs import DraftJobs

    jobs = DraftJobs(max_active=1)
    gate = threading.Event()

    def slow(stop):
        gate.wait(5)
        yield {"type": "done", "draft": {}}

    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    jobs.start("a" * 32, tmp_path / "a", {"type": "job"}, slow)
    time.sleep(0.1)
    jobs.start("b" * 32, tmp_path / "b", {"type": "job"}, slow)
    time.sleep(0.3)
    gate.set()
    b = [e for e in jobs.stream("b" * 32, tmp_path / "b", -1, 0.05) if e["type"] != "ping"]
    assert any(e.get("stage") == "queue" for e in b) and b[-1]["type"] == "done"


@needs_java
def test_report_events_endpoint_resumes(client):
    events = draft(client)
    job = events[0]["job"]
    res = client.get(f"/api/jobs/{job}/events?after=1")
    replay = [json.loads(line) for line in res.text.splitlines() if line.strip()]
    assert replay and replay[0]["seq"] == 2 and replay[-1]["type"] == "done"


# ── deleting, reporting, explaining ────────────────────────────────

@needs_java
def test_student_can_delete_their_report(client):
    job = draft(client)[0]["job"]
    assert client.delete(f"/api/jobs/{job}", headers=CID).json() == {"ok": True}
    assert client.get(f"/api/jobs/{job}/alive").status_code == 404


def test_content_can_be_reported(client):
    job = "cd" * 16
    assert client.post(f"/api/jobs/{job}/report", json={"reason": "nonsense"}).status_code == 422
    assert client.post(f"/api/jobs/{job}/report", json={"reason": "offensive", "task": 0},
                       headers=CID).json() == {"ok": True}


@needs_java
def test_explanations_are_cached_by_code(client, monkeypatch):
    from apps.api import main
    from core.schemas import AIExplain

    calls = []

    class P:
        def explain(self, prompt):
            calls.append(prompt)
            return AIExplain(summary="Reads a number.", steps=["Scanner reads input"],
                             viva=[{"q": "What is Scanner?", "a": "A class that reads input."}])

    monkeypatch.setattr(main, "get_provider", lambda: P())
    events = draft(client)
    job, task = events[0]["job"], events[-1]["draft"]["tasks"][0]
    first = client.post(f"/api/jobs/{job}/explain", json={"index": 0, "task": task}, headers=CID).json()
    again = client.post(f"/api/jobs/{job}/explain", json={"index": 0, "task": task}, headers=CID).json()
    assert first["summary"] == again["summary"] == "Reads a number." and len(calls) == 1


# ── admin, crawlers, headers ───────────────────────────────────────

def test_admin_token_only_works_as_a_header(client, monkeypatch):
    monkeypatch.setenv("LABFORGE_ADMIN_TOKEN", "secret-key")
    assert client.get("/api/admin/status?token=secret-key").status_code == 404
    assert client.get("/api/admin/usage?token=secret-key").status_code == 404
    assert client.get("/api/admin/status", headers={"X-Admin-Token": "secret-key"}).status_code == 200


def test_security_headers(client):
    res = client.get("/api/health")
    assert res.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in res.headers["content-security-policy"]
    assert "strict-transport-security" not in res.headers  # plain http in tests
    https = client.get("/api/health", headers={"X-Forwarded-Proto": "https"})
    assert "max-age" in https.headers["strict-transport-security"]


def test_robots_sitemap_and_ads_txt(client, monkeypatch):
    monkeypatch.setenv("LABFORGE_PUBLIC_URL", "https://labforge.example")
    assert "Disallow: /api/" in client.get("/robots.txt").text
    sitemap = client.get("/sitemap.xml").text
    assert "https://labforge.example/privacy" in sitemap and "/api/" not in sitemap
    monkeypatch.delenv("ADSENSE_CLIENT", raising=False)
    monkeypatch.delenv("VITE_ADSENSE_CLIENT", raising=False)
    assert client.get("/ads.txt").status_code == 404
    monkeypatch.setenv("ADSENSE_CLIENT", "ca-pub-1234567890123456")
    assert client.get("/ads.txt").text.strip() == "google.com, pub-1234567890123456, DIRECT, f08c47fec0942fa0"


def test_assetlinks_for_the_android_app(client, monkeypatch):
    assert client.get("/.well-known/assetlinks.json").status_code == 404
    monkeypatch.setenv("ANDROID_APP_PACKAGE", "com.example.labforge")
    monkeypatch.setenv("ANDROID_APP_SHA256", "AA:BB")
    links = client.get("/.well-known/assetlinks.json").json()
    assert links[0]["target"]["package_name"] == "com.example.labforge"


def test_pages_get_their_own_title_and_a_nonce(monkeypatch):
    from starlette.requests import Request

    from apps.api import main

    page = ('<!doctype html><html><head><title>x</title><meta name="description" content="d" />'
            '<meta property="og:title" content="t" /><meta property="og:description" content="o" /></head>'
            '<body><script type="module" src="/assets/a.js"></script></body></html>')
    monkeypatch.setattr(main, "_index_template", lambda: page)
    scope = {"type": "http", "headers": [(b"host", b"labforge.example")], "path": "/privacy", "scheme": "https",
             "server": ("labforge.example", 443), "query_string": b"", "method": "GET"}
    res = main.render_index(Request(scope), "/privacy")
    body = res.body.decode()
    assert res.status_code == 200 and "<title>Privacy policy | LabForge</title>" in body
    nonce = body.split('nonce="')[1].split('"')[0]
    assert f"'nonce-{nonce}'" in res.headers["content-security-policy"]
    assert 'rel="canonical"' in body
    missing = main.render_index(Request({**scope, "path": "/nope"}), "/nope")
    assert missing.status_code == 404 and "noindex" in missing.body.decode()


# ── Postgres-backed cache and limits (when a test database is available) ──

PG = os.environ.get("LABFORGE_TEST_DATABASE_URL", "")
needs_pg = pytest.mark.skipif(not PG, reason="set LABFORGE_TEST_DATABASE_URL to test against Postgres")


@needs_pg
def test_postgres_cache_and_limits():
    from core.ai.provider import DraftCache
    from core.limits import PostgresLimiter, RateLimited
    from core.schemas import AIReport

    cache = DraftCache(db_url=PG)
    report = AIReport(experiment_no="1", title="T", aim="A", tasks=[], learning_outcomes=[])
    key = "test-" + os.urandom(4).hex()
    assert cache.get(key) is None
    cache.put(key, report)
    cache.put(key, report)  # upsert
    assert DraftCache(db_url=PG).get(key).aim == "A"

    limiter = PostgresLimiter(PG)
    who = "c:" + os.urandom(4).hex()
    assert limiter.hit(who, "t", 2, 60) == 1
    assert limiter.hit(who, "t", 2, 60) == 0
    with pytest.raises(RateLimited):
        limiter.hit(who, "t", 2, 60)
    assert limiter.remaining(who, "t", 2, 60) == 0


@needs_pg
def test_postgres_activity_log_and_delete():
    from core.activity import ActivityLog

    log = ActivityLog(db_url=PG)
    job = os.urandom(16).hex()
    log.record("draft", job, tasks=[], ip="1.1.1.1")
    log.flush()
    assert any(r["job"] == job for r in log.rows(days=1))
    log.delete_job(job)
    assert not any(r["job"] == job for r in log.rows(days=1))
