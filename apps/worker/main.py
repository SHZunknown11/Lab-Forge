"""Execution worker: runs student programs on a machine of its own.

The web server (EXEC_BACKEND=remote) sends each program here, so untrusted code never runs next
to the API keys, the draft cache or other students' reports. Run it on a separate VM or
container with no secrets, ideally with EXEC_BACKEND=docker (one network-less container per
program) or at least EXEC_ALLOW_NETWORK=0 on a host that allows network namespaces.

    EXEC_WORKER_TOKEN=<long random> uvicorn apps.worker.main:app --host 0.0.0.0 --port 8100

Endpoints (all need the X-Worker-Token header):
    GET  /capabilities   which languages this worker can run
    POST /run            {language, files: [{name, code}], stdin} -> {status, output, note, retryable, figures}
    GET  /health         no token needed
"""
from __future__ import annotations

import base64
import hmac
import os
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from core.execution.runner import CodeRunner
from core.schemas import CodeFile

TOKEN = os.environ.get("EXEC_WORKER_TOKEN", "")
if len(TOKEN) < 24:
    raise RuntimeError("Set EXEC_WORKER_TOKEN to a random value of at least 24 characters.")

# The worker itself runs programs locally or in Docker, never "remote" (that would loop).
_backend = os.environ.get("WORKER_EXEC_BACKEND", "local").lower()
runner = CodeRunner(backend="local" if _backend == "remote" else _backend)
WORK_ROOT = Path(os.environ.get("WORKER_RUN_DIR", Path(tempfile.gettempdir()) / "labforge-worker"))

app = FastAPI(title="LabForge worker", docs_url=None, redoc_url=None)


def _check(token: str | None) -> None:
    if not token or not hmac.compare_digest(token.encode(), TOKEN.encode()):
        raise HTTPException(404)


class RunBody(BaseModel):
    language: str = Field(max_length=20)
    stdin: str = Field(default="", max_length=20_000)
    files: list[CodeFile] = Field(max_length=30)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/capabilities")
def capabilities(x_worker_token: str | None = Header(default=None)):
    _check(x_worker_token)
    return runner.available()


@app.post("/run")
def run(body: RunBody, x_worker_token: str | None = Header(default=None)):
    _check(x_worker_token)
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="run-", dir=WORK_ROOT))
    try:
        result = runner.run(body.language, body.files, body.stdin, work)
        figures = []
        for path in result.figures[:12]:
            try:
                figures.append(base64.b64encode(Path(path).read_bytes()).decode())
            except OSError:
                continue
        return {"status": result.status, "output": result.output, "note": result.note,
                "retryable": result.retryable, "figures": figures}
    finally:
        from core.execution.runner import unlink_node_modules

        unlink_node_modules(work)  # never follow the link into the shared runtime
        shutil.rmtree(work, ignore_errors=True)
