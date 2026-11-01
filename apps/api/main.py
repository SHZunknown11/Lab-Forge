"""LabForge HTTP API and static frontend.

No accounts: student details live in the browser. Spend is protected by
per-IP limits on AI calls (cache hits are free), runs, renders and uploads.
"""
from __future__ import annotations

import io
import json
import os
import threading
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from core.ai.provider import AIError, DraftCache, get_provider, usage_summary  # noqa: E402
from core.documents.pdf_converter import PdfConverter  # noqa: E402
from core.documents.templates import DEFAULT_FIELDS, TEMPLATES  # noqa: E402
from core.execution.runner import LANGUAGE_LABELS, CodeRunner  # noqa: E402
from core.ingestion.extract import UnsupportedFile, condense, extract_text  # noqa: E402
from core.pipeline.orchestrator import (  # noqa: E402
    build_draft, job_file, job_path, new_job, purge_old_jobs, render_report, run_task,
)
from core.schemas import RenderRequest, Task  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)  # artifacts/ and templates/ are relative to the project root

MAX_UPLOAD = int(os.environ.get("LABFORGE_MAX_UPLOAD_MB", "8")) * 1024 * 1024
MAX_IMAGE = 6 * 1024 * 1024
JOB_TTL_HOURS = float(os.environ.get("LABFORGE_JOB_TTL_HOURS", "24"))
AI_DAILY = int(os.environ.get("LABFORGE_AI_DAILY_LIMIT", "10"))
TRUST_PROXY = os.environ.get("LABFORGE_TRUST_PROXY", "0") == "1"
DIST = ROOT / "apps" / "frontend" / "dist"

app = FastAPI(title="LabForge", docs_url=None, redoc_url=None)
runner = CodeRunner()


# ── limits ─────────────────────────────────────────────────────────

class Limiter:
    def __init__(self):
        self._hits: dict[tuple[str, str], deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, ip: str, bucket: str, limit: int, window: int, consume: bool = True) -> int:
        """Returns the remaining allowance; raises 429 when it's used up."""
        now = time.time()
        with self._lock:
            q = self._hits[(ip, bucket)]
            while q and q[0] < now - window:
                q.popleft()
            if len(q) >= limit:
                wait = int(q[0] + window - now) + 1
                raise HTTPException(429, _limit_message(bucket, wait))
            if consume:
                q.append(now)
            return limit - len(q)

    def remaining(self, ip: str, bucket: str, limit: int, window: int) -> int:
        now = time.time()
        with self._lock:
            q = self._hits[(ip, bucket)]
            return max(0, limit - sum(1 for t in q if t >= now - window))


def _limit_message(bucket: str, wait: int) -> str:
    when = f"{wait // 3600 + 1} hours" if wait > 3600 else f"{wait // 60 + 1} minutes"
    if bucket == "ai":
        return f"You've used today's {AI_DAILY} new sheets. Sheets someone already uploaded still work. More in {when}."
    return f"Too many requests. Try again in {when}."


limiter = Limiter()


def client_ip(request: Request) -> str:
    if TRUST_PROXY:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.on_event("startup")
def _startup() -> None:
    removed = purge_old_jobs(JOB_TTL_HOURS)
    if removed:
        print(f"[jobs] removed {removed} expired job folders")


_last_purge = [time.time()]


def _maybe_purge() -> None:
    if time.time() - _last_purge[0] > 3600:
        _last_purge[0] = time.time()
        threading.Thread(target=purge_old_jobs, args=(JOB_TTL_HOURS,), daemon=True).start()


def _job(job_id: str) -> Path:
    path = job_path(job_id)
    if path is None:
        raise HTTPException(404, "This report has expired. Upload the sheet again to start over.")
    return path


# ── endpoints ──────────────────────────────────────────────────────

@app.get("/api/meta")
def meta(request: Request):
    provider = get_provider()
    caps = runner.available()
    return {
        "templates": [
            {"id": t.id, "name": t.name, "description": t.description, "header_image": t.header_image}
            for t in TEMPLATES.values()
        ],
        "default_fields": DEFAULT_FIELDS,
        "languages": [{"id": k, "label": v, "runnable": caps.get(k, False)} for k, v in LANGUAGE_LABELS.items()],
        "pdf": PdfConverter().available(),
        "ai_ready": provider.configured,
        "limits": {"daily": AI_DAILY, "remaining": limiter.remaining(client_ip(request), "ai", AI_DAILY, 86400)},
        "job_ttl_hours": JOB_TTL_HOURS,
    }


@app.post("/api/drafts")
async def create_draft(
    request: Request,
    file: UploadFile | None = File(None),
    text: str = Form(""),
    language: str = Form("auto"),
    subject: str = Form(""),
    fresh: bool = Form(False),
    from_job: str = Form(""),
):
    _maybe_purge()
    ip = client_ip(request)
    limiter.check(ip, "drafts", 30, 3600)
    raw = ""
    previous = job_path(from_job) if from_job else None
    if previous is not None and (previous / "sheet.txt").is_file():
        raw = (previous / "sheet.txt").read_text(encoding="utf-8")
    elif from_job:
        raise HTTPException(404, "This report expired on the server. Upload the sheet again to start over.")
    if file is not None and file.filename:
        data = await file.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, f"That file is over {MAX_UPLOAD // (1024 * 1024)} MB. Upload only the experiment sheet.")
        try:
            raw = extract_text(data, file.filename)
        except UnsupportedFile as exc:
            raise HTTPException(415, str(exc)) from exc
    if text.strip():
        raw = (raw + "\n\n" + text).strip() if raw else text
    sheet = condense(raw)
    if len(sheet) < 30:
        raise HTTPException(422, "There isn't enough text in that sheet. Paste the experiment text instead.")

    language = (language or "auto").lower()
    language = language if language in LANGUAGE_LABELS or language == "auto" else "auto"
    subject = subject.strip()[:120]
    cache = DraftCache()
    hit = not fresh and cache.get(DraftCache.key(sheet, language, subject)) is not None
    if not hit:
        limiter.check(ip, "ai", AI_DAILY, 86400)

    job_id, job_dir = new_job()
    (job_dir / "sheet.txt").write_text(sheet, encoding="utf-8")

    def stream():
        yield json.dumps({"type": "job", "job": job_id}) + "\n"
        try:
            for event in build_draft(sheet, job_dir, language, subject, fresh, cache=cache, runner=runner):
                yield json.dumps(event) + "\n"
        except AIError as exc:
            yield json.dumps({"type": "error", "message": str(exc)}) + "\n"
        except Exception as exc:  # noqa: BLE001
            print(f"[draft] {type(exc).__name__}: {exc}")
            yield json.dumps({"type": "error", "message": "Something went wrong while writing. Try again."}) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


class RunRequest(BaseModel):
    index: int
    task: Task


@app.post("/api/jobs/{job_id}/run")
def run_one(job_id: str, body: RunRequest, request: Request):
    job_dir = _job(job_id)
    limiter.check(client_ip(request), "runs", 60, 3600)
    task = body.task
    run_task(job_dir, max(0, min(body.index, 50)), task, runner)
    return task


@app.post("/api/jobs/{job_id}/images")
async def upload_image(job_id: str, request: Request, file: UploadFile = File(...)):
    job_dir = _job(job_id)
    limiter.check(client_ip(request), "uploads", 80, 3600)
    data = await file.read(MAX_IMAGE + 1)
    if len(data) > MAX_IMAGE:
        raise HTTPException(413, "Screenshots must be under 6 MB.")
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            if img.width * img.height > 40_000_000:
                raise HTTPException(413, "That image is too large.")
            clean = img.convert("RGB")  # re-encode: drops metadata and anything that isn't pixels
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(415, "That file isn't an image. Upload a PNG or JPG screenshot.") from exc
    name = f"up_{uuid.uuid4().hex[:12]}.png"
    clean.save(job_dir / name, optimize=True)
    return {"name": name, "width": clean.width, "height": clean.height}


@app.post("/api/jobs/{job_id}/render")
def render(job_id: str, body: RenderRequest, request: Request):
    job_dir = _job(job_id)
    limiter.check(client_ip(request), "renders", 60, 3600)
    if body.template not in TEMPLATES:
        body.template = "cu-cse"
    return render_report(job_dir, body)


@app.get("/api/jobs/{job_id}/files/{name}")
def get_file(job_id: str, name: str):
    return _send(job_file(job_id, name))


@app.get("/api/jobs/{job_id}/files/{render_id}/{name}")
def get_render_file(job_id: str, render_id: str, name: str):
    return _send(job_file(job_id, name, render_id), download=name.endswith((".docx", ".pdf")))


def _send(path: Path | None, download: bool = False):
    if path is None:
        raise HTTPException(404, "File not found. It may have expired.")
    headers = {"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"}
    if download:
        return FileResponse(path, filename=path.name, headers=headers)
    return FileResponse(path, headers=headers)


@app.get("/api/admin/usage")
def admin_usage(token: str = "", days: int = 1):
    expected = os.environ.get("LABFORGE_ADMIN_TOKEN", "")
    if not expected or token != expected:
        raise HTTPException(404)
    return {"days": days, "by_model": usage_summary(days)}


@app.exception_handler(HTTPException)
async def _http_error(request: Request, exc: HTTPException):
    return JSONResponse({"detail": exc.detail or "Not found."}, status_code=exc.status_code)


# ── frontend ───────────────────────────────────────────────────────

class SPAStatic(StaticFiles):
    async def get_response(self, path, scope):
        from starlette.exceptions import HTTPException as StarletteHTTPException

        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException:
            response = None
        if response is None or response.status_code == 404:
            if scope["path"].startswith("/api/"):  # unknown API URL: a real 404, not the app page
                return JSONResponse({"detail": "Not found."}, status_code=404)
            return await super().get_response("index.html", scope)
        return response


if DIST.exists():
    app.mount("/", SPAStatic(directory=DIST, html=True), name="web")
else:
    @app.get("/")
    def _no_build():
        return JSONResponse({"detail": "Frontend not built. Run: cd apps/frontend && npm install && npm run build"})
