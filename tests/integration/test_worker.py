"""EXEC_BACKEND=remote: programs run on a separate worker, the web server only sends them."""
import socket
import threading
import time

import pytest

from core.execution.runner import CodeRunner
from core.schemas import CodeFile

TOKEN = "worker-test-token-0123456789abcdef"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def worker_url():
    import os

    os.environ["EXEC_WORKER_TOKEN"] = TOKEN
    import uvicorn

    from apps.worker.main import app

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True


def test_remote_backend_runs_on_the_worker(worker_url, monkeypatch, tmp_path):
    from core.execution import runner as mod

    monkeypatch.setenv("EXEC_WORKER_URL", worker_url)
    monkeypatch.setenv("EXEC_WORKER_TOKEN", TOKEN)
    mod._caps_cache.update(at=0.0, caps={})
    remote = CodeRunner(backend="remote")
    assert remote.available().get("python")
    result = remote.run("python", [CodeFile(name="main.py", code="print(input('n? '))")], "7", tmp_path)
    assert result.status == "passed" and "n? 7" in result.output


def test_worker_returns_figures(worker_url, monkeypatch, tmp_path):
    from core.execution import runner as mod

    page = [CodeFile(name="index.html", code="<h1>Hi</h1>")]
    if CodeRunner().run("html", page, "", tmp_path / "probe").status != "passed":
        pytest.skip("Chrome can't take screenshots on this machine")
    monkeypatch.setenv("EXEC_WORKER_URL", worker_url)
    monkeypatch.setenv("EXEC_WORKER_TOKEN", TOKEN)
    mod._caps_cache.update(at=0.0, caps={})
    result = CodeRunner(backend="remote").run("html", [CodeFile(name="index.html", code="<h1>Hi</h1>")], "", tmp_path)
    assert result.status == "passed" and result.figures
    assert open(result.figures[0], "rb").read(4) == b"\x89PNG"


def test_worker_needs_its_token(worker_url):
    import httpx

    assert httpx.get(f"{worker_url}/capabilities").status_code == 404
    assert httpx.get(f"{worker_url}/capabilities", headers={"X-Worker-Token": "wrong"}).status_code == 404
    assert httpx.get(f"{worker_url}/health").json() == {"ok": True}


def test_unreachable_worker_means_not_run(monkeypatch, tmp_path):
    from core.execution import runner as mod

    monkeypatch.setenv("EXEC_WORKER_URL", f"http://127.0.0.1:{_free_port()}")
    mod._caps_cache.update(at=0.0, caps={})
    result = CodeRunner(backend="remote").run("python", [CodeFile(name="main.py", code="print(1)")], "", tmp_path)
    assert result.status == "not_run"
