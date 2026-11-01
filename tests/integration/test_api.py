"""End to end through the HTTP API, offline (AI_MODE=local), no PDF."""
import json

import pytest
from fastapi.testclient import TestClient

from core.execution.runner import CodeRunner

pytestmark = pytest.mark.skipif(not CodeRunner().available().get("java"), reason="JDK not installed")


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("PDF_BACKEND", "gotenberg")  # no GOTENBERG_URL: PDF is skipped, DOCX still made
    monkeypatch.setenv("GOTENBERG_URL", "")
    from apps.api import main

    main.limiter._hits.clear()
    return TestClient(main.app)


def draft(client, **form):
    with open("examples/source-notes.md", "rb") as fh:
        res = client.post("/api/drafts", files={"file": ("sheet.md", fh, "text/markdown")},
                          data={"language": "auto", "subject": "PBLJ", **form})
    assert res.status_code == 200, res.text
    events = [json.loads(line) for line in res.text.splitlines() if line.strip()]
    return events


def test_meta(client):
    meta = client.get("/api/meta").json()
    assert {t["id"] for t in meta["templates"]} == {"cu-cse", "plain"}
    assert "Student Name" in meta["default_fields"]


def test_sheet_to_word_file(client):
    events = draft(client)
    job = events[0]["job"]
    done = events[-1]
    assert done["type"] == "done", events[-1]
    tasks = done["draft"]["tasks"]
    assert tasks and all(t["status"] == "passed" for t in tasks)
    assert "Enter a number:" in tasks[0]["output"]

    fields = [{"label": "Student Name", "value": "Asha"}, {"label": "UID", "value": "24BCS1"}]
    res = client.post(f"/api/jobs/{job}/render",
                      json={"draft": done["draft"], "fields": fields, "template": "plain", "pdf": True})
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["docx"].endswith(".docx") and out["pdf"] is None and out["pdf_error"]
    file = client.get(f"/api/jobs/{job}/files/{out['render']}/{out['docx']}")
    assert file.status_code == 200 and file.content[:2] == b"PK"

    # Edit the code and run it again: no model involved.
    task = tasks[0]
    task["stdin"] = "81\n"
    rerun = client.post(f"/api/jobs/{job}/run", json={"index": 0, "task": task}).json()
    assert "Enter a number: 81" in rerun["output"]


def test_second_upload_is_served_from_cache(client):
    draft(client)
    events = draft(client)
    assert events[-1]["cached"] is True


def test_bad_job_ids_and_paths_are_rejected(client):
    traversal = client.get("/api/jobs/../../etc/files/passwd")  # normalised to /etc/...: SPA page or 404
    assert traversal.status_code == 404 or '<div id="root">' in traversal.text
    assert client.get("/api/jobs/" + "a" * 32 + "/files/..%2F..%2F.env").status_code == 404
    assert client.get("/api/jobs/" + "a" * 32 + "/files/r_12345678/..%2F.env").status_code == 404
    assert client.post("/api/jobs/nope/render", json={"draft": {}, "fields": []}).status_code in (404, 422)


def test_screenshot_upload_must_be_an_image(client):
    job = draft(client)[0]["job"]
    res = client.post(f"/api/jobs/{job}/images", files={"file": ("x.png", b"not an image", "image/png")})
    assert res.status_code == 415


def test_empty_sheet_is_refused(client):
    res = client.post("/api/drafts", data={"text": "hi"})
    assert res.status_code == 422


def test_client_ip_ignores_spoofed_forwarded_for(monkeypatch):
    from apps.api import main

    class Req:
        headers = {"x-forwarded-for": "6.6.6.6, 203.0.113.9"}
        client = type("C", (), {"host": "10.0.0.1"})()

    monkeypatch.setattr(main, "TRUST_PROXY", 0)
    assert main.client_ip(Req()) == "10.0.0.1"
    monkeypatch.setattr(main, "TRUST_PROXY", 1)
    assert main.client_ip(Req()) == "203.0.113.9"  # the hop our proxy added, not the visitor's claim
    Req.headers = {**Req.headers, "true-client-ip": "198.51.100.7"}
    monkeypatch.setattr(main, "CLIENT_IP_HEADER", "true-client-ip")
    assert main.client_ip(Req()) == "198.51.100.7"


def test_health_and_hidden_admin(client):
    assert client.get("/api/health").json() == {"ok": True}
    assert client.get("/api/admin/status?token=x").status_code == 404
