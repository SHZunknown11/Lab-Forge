"""LabForge HTTP API and static frontend.

No accounts: student details live in the browser. Spend is protected by limits per browser
(an anonymous id the page keeps) and per IP address, on AI calls (cache hits are free), runs,
renders and uploads. Limits and the draft cache live in Postgres when LABFORGE_DATABASE_URL
is set, so they survive restarts.
"""
from __future__ import annotations

import base64
import hmac
import html
import io
import json
import os
import re
import secrets
import shutil
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from dotenv import load_dotenv

load_dotenv()


def _protect_secrets() -> None:
    """Student programs may run as the same user. Marking this process non-dumpable makes
    /proc/<pid>/environ and /proc/<pid>/mem root-only, so they can't read the API keys."""
    if sys.platform.startswith("linux"):
        try:
            import ctypes

            ctypes.CDLL(None, use_errno=True).prctl(4, 0, 0, 0, 0)  # PR_SET_DUMPABLE, 0
        except (OSError, AttributeError):
            pass


_protect_secrets()


def _init_sentry() -> None:
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return
    try:
        import sentry_sdk

        sentry_sdk.init(dsn=dsn, send_default_pii=False, traces_sample_rate=0.0,
                        environment=os.environ.get("SENTRY_ENVIRONMENT", "production"))
    except ImportError:
        print("[sentry] SENTRY_DSN is set but sentry-sdk isn't installed")


_init_sentry()

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile  # noqa: E402
from fastapi.responses import (  # noqa: E402
    FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response, StreamingResponse,
)
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from core.activity import ActivityLog, task_summary  # noqa: E402
from core.ai.provider import AIError, DraftCache, ExplainCache, get_provider, usage_summary  # noqa: E402
from core.documents.pdf_converter import PdfConverter  # noqa: E402
from core.documents.templates import DEFAULT_FIELDS, TEMPLATES  # noqa: E402
from core.execution.runner import LANGUAGE_LABELS, CodeRunner, sandbox_report  # noqa: E402
from core.ingestion.extract import UnsupportedFile, condense, extract_text  # noqa: E402
from core.ingestion.header import read_header, strip_personal  # noqa: E402
from core.limits import RateLimited, limits, make_limiter  # noqa: E402
from core.pipeline.jobs import DraftJobs  # noqa: E402
from core.pipeline.orchestrator import (  # noqa: E402
    JOB_ID, build_draft, is_generated, job_file, job_path, new_job, purge_old_jobs, render_report, run_task,
)
from core.schemas import RenderRequest, Task  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)  # artifacts/ and templates/ are relative to the project root

MAX_UPLOAD = int(os.environ.get("LABFORGE_MAX_UPLOAD_MB", "8")) * 1024 * 1024
MAX_IMAGE = 6 * 1024 * 1024
JOB_TTL_HOURS = float(os.environ.get("LABFORGE_JOB_TTL_HOURS", "24"))
# Number of reverse proxies in front of the app that append to X-Forwarded-For (0 = none).
TRUST_PROXY = int(os.environ.get("LABFORGE_TRUST_PROXY", "0") or 0)
# Or a header the edge sets and visitors can't forge, e.g. true-client-ip on Render (Cloudflare).
CLIENT_IP_HEADER = os.environ.get("LABFORGE_CLIENT_IP_HEADER", "").strip().lower()
DIST = ROOT / "apps" / "frontend" / "dist"
STREAM_PING_SECONDS = 10
CLIENT_ID = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


@asynccontextmanager
async def lifespan(_app):
    removed = purge_old_jobs(JOB_TTL_HOURS)
    if removed:
        print(f"[jobs] removed {removed} expired job folders")
    yield
    from core.db import close_all

    activity.flush(timeout=3)
    close_all()


app = FastAPI(title="LabForge", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
runner = CodeRunner()
activity = ActivityLog()
limiter = make_limiter()
jobs = DraftJobs()


# ── who is asking, and how much they may ask ───────────────────────

def client_ip(request: Request) -> str:
    if CLIENT_IP_HEADER:
        value = request.headers.get(CLIENT_IP_HEADER, "").split(",")[0].strip()
        if value:
            return value
    if TRUST_PROXY:
        # Visitors can send their own X-Forwarded-For; only the entries our proxies append count.
        hops = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]
        if hops:
            return hops[-min(TRUST_PROXY, len(hops))]
    return request.client.host if request.client else "unknown"


def client_id(request: Request) -> str:
    """The anonymous id this browser made for itself (no account, nothing personal)."""
    value = request.headers.get("x-client-id", "").strip()
    return value if CLIENT_ID.match(value) else ""


def _limit_message(bucket: str, wait: int) -> str:
    when = f"{wait // 3600 + 1} hours" if wait > 3600 else f"{wait // 60 + 1} minutes"
    if bucket == "ai":
        daily = limits()["ai"][0]
        return f"You've used today's {daily} new sheets. Sheets someone already uploaded still work. More in {when}."
    if bucket == "edited_runs":
        return f"You've run a lot of changed code this hour. Try again in {when}, or add your own screenshot."
    if bucket == "explain":
        return f"You've used today's explanations. More in {when}."
    return f"Too many requests. Try again in {when}."


def guard(request: Request, bucket: str) -> int:
    """Count one request against the browser's and the IP's allowance. Returns what the browser has left."""
    per_client, per_ip, window = limits()[bucket]
    if _is_owner(request):  # the site owner's own checks (deploy smoke test) aren't limited
        return per_client
    ip, cid = client_ip(request), client_id(request)
    try:
        limiter.hit(f"ip:{ip}", bucket, per_ip, window, consume=False)  # check before spending
        left = limiter.hit(f"c:{cid}", bucket, per_client, window) if cid else None
        ip_left = limiter.hit(f"ip:{ip}", bucket, per_ip if cid else per_client, window)
    except RateLimited as exc:
        raise HTTPException(429, _limit_message(exc.bucket, exc.wait)) from exc
    return left if left is not None else ip_left


def remaining(request: Request, bucket: str) -> int:
    per_client, per_ip, window = limits()[bucket]
    cid = client_id(request)
    if cid:
        return min(limiter.remaining(f"c:{cid}", bucket, per_client, window),
                   limiter.remaining(f"ip:{client_ip(request)}", bucket, per_ip, window))
    return limiter.remaining(f"ip:{client_ip(request)}", bucket, per_client, window)


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
    daily = limits()["ai"][0]
    return {
        "templates": [
            {"id": t.id, "name": t.name, "description": t.description, "header_image": t.header_image}
            for t in TEMPLATES.values()
        ],
        "default_fields": DEFAULT_FIELDS,
        "languages": [{"id": k, "label": v, "runnable": caps.get(k, False)} for k, v in LANGUAGE_LABELS.items()],
        "pdf": PdfConverter().available(),
        "ai_ready": provider.configured,
        "limits": {"daily": daily, "remaining": remaining(request, "ai")},
        "job_ttl_hours": JOB_TTL_HOURS,
        "log_days": activity.keep_days,
        "log_personal": os.environ.get("LABFORGE_LOG_PERSONAL", "0") == "1",
    }


def _ndjson(events) -> StreamingResponse:
    def body():
        for event in events:
            yield json.dumps(event, ensure_ascii=False) + "\n"

    return StreamingResponse(body(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


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
    owner = _is_owner(request)
    guard(request, "drafts")
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
    details = read_header(sheet)  # fills the student's form; never sent to the AI or the cache key
    sheet = strip_personal(sheet)
    if len(sheet) < 30:
        raise HTTPException(422, "There isn't enough text in that sheet. Paste the experiment text instead.")

    language = (language or "auto").lower()
    language = language if language in LANGUAGE_LABELS or language == "auto" else "auto"
    subject = subject.strip()[:120]
    cache = DraftCache()
    hit = not fresh and cache.get(DraftCache.key(sheet, language)) is not None
    if not hit:
        guard(request, "ai")

    job_id, job_dir = new_job()
    (job_dir / "sheet.txt").write_text(sheet, encoding="utf-8")
    started = time.monotonic()
    log = {"name": details.get("Student Name", ""), "uid": details.get("UID", ""), "ip": ip, "subject": subject,
           "language": language, "sheet": sheet, "error": "", "tasks": [], "cached": False}

    def produce(stop: threading.Event):
        # Runs in the background: the report keeps being written if the page goes away.
        try:
            for event in build_draft(sheet, job_dir, language, subject, fresh, cache=cache, runner=runner):
                if event["type"] in ("draft", "done"):
                    log["title"] = event["draft"].get("title", "")
                    log["tasks"] = task_summary(event["draft"]["tasks"])
                    log["cached"] = event.get("cached", False)
                yield event
                if stop.is_set():
                    log["error"] = "Stopped by the student."
                    return
        except AIError as exc:
            log["error"] = str(exc)
            yield {"type": "error", "message": str(exc)}
        except Exception as exc:  # noqa: BLE001
            print(f"[draft] {type(exc).__name__}: {exc}")
            log["error"] = f"{type(exc).__name__}: {exc}"
            yield {"type": "error", "message": "Something went wrong while writing. Try again."}

    def finished(_events):
        if not owner:
            activity.record("draft", job_id, seconds=round(time.monotonic() - started), **log)

    jobs.start(job_id, job_dir, {"type": "job", "job": job_id, "details": details}, produce, finished)
    return _ndjson(jobs.stream(job_id, job_dir, -1, STREAM_PING_SECONDS))


@app.get("/api/jobs/{job_id}/events")
def job_events(job_id: str, after: int = -1):
    """Pick a report up again after the connection dropped: every event after `after`."""
    job_dir = _job(job_id)
    return _ndjson(jobs.stream(job_id, job_dir, max(-1, after), STREAM_PING_SECONDS))


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    _job(job_id)
    return {"ok": jobs.cancel(job_id)}


class RunRequest(BaseModel):
    index: int
    task: Task


@app.get("/api/jobs/{job_id}/alive")
def job_alive(job_id: str):
    """Lets the page find out whether a report it remembers is still on the server."""
    _job(job_id)
    return {"ok": True, "writing": jobs.running(job_id)}


@app.post("/api/jobs/{job_id}/run")
def run_one(job_id: str, body: RunRequest, request: Request):
    job_dir = _job(job_id)
    task = body.task
    index = max(0, min(body.index, 50))
    if len(task.files) > 20:
        raise HTTPException(413, "That's too many files for one task.")
    # Code the server wrote can be run again with any input. Changed code is someone's own
    # program: it gets a smaller allowance, and changed shell scripts aren't run at all.
    edited = not is_generated(job_dir, index, task)
    if (edited and task.language == "shell" and os.environ.get("LABFORGE_ALLOW_EDITED_SHELL") != "1"
            and not _is_owner(request)):
        raise HTTPException(403, "Changed shell scripts can't be run on this server. "
                                 "Run it on your machine and add a screenshot of the output.")
    guard(request, "runs")
    if edited:
        guard(request, "edited_runs")
    run_task(job_dir, index, task, runner)
    if not _is_owner(request):
        activity.record("run", job_id, index=index, ip=client_ip(request), title=task.title, status=task.status,
                        edited=edited, note=task.note[:300], output=task.output[-600:])
    return task


@app.post("/api/jobs/{job_id}/images")
async def upload_image(job_id: str, request: Request, file: UploadFile = File(...)):
    job_dir = _job(job_id)
    guard(request, "uploads")
    data = await file.read(MAX_IMAGE + 1)
    if len(data) > MAX_IMAGE:
        raise HTTPException(413, "Screenshots must be under 6 MB.")
    from PIL import Image, UnidentifiedImageError

    Image.MAX_IMAGE_PIXELS = 40_000_000
    try:
        with Image.open(io.BytesIO(data)) as img:
            if img.format not in ("PNG", "JPEG", "WEBP"):
                raise HTTPException(415, "Upload a PNG, JPG or WebP screenshot.")
            if img.width * img.height > 40_000_000:
                raise HTTPException(413, "That image is too large.")
            img.load()
            clean = img.convert("RGB")  # re-encode: drops metadata and anything that isn't pixels
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise HTTPException(415, "That file isn't an image. Upload a PNG or JPG screenshot.") from exc
    name = f"up_{uuid.uuid4().hex[:12]}.png"
    clean.save(job_dir / name, optimize=True)
    return {"name": name, "width": clean.width, "height": clean.height}


class FeedbackRequest(BaseModel):
    rating: Literal["up", "down"]
    reasons: list[Annotated[str, Field(max_length=60)]] = Field(default_factory=list, max_length=8)
    comment: str = Field(default="", max_length=1000)


@app.post("/api/jobs/{job_id}/feedback")
def feedback(job_id: str, body: FeedbackRequest, request: Request):
    # The report's files may have expired by now; the vote still counts.
    if not JOB_ID.match(job_id or ""):
        raise HTTPException(404, "Unknown report.")
    guard(request, "feedback")
    if not _is_owner(request):
        activity.record("feedback", job_id, ip=client_ip(request), rating=body.rating, reasons=body.reasons,
                        comment=body.comment.strip())
    return {"ok": True}


class ContentReport(BaseModel):
    reason: Literal["offensive", "unsafe", "wrong", "copyright", "other"]
    comment: str = Field(default="", max_length=1000)
    task: int | None = Field(default=None, ge=0, le=50)


@app.post("/api/jobs/{job_id}/report")
def report_content(job_id: str, body: ContentReport, request: Request):
    """Flag AI-written content (offensive, harmful, wrong). Shown to the site owner in /admin."""
    if not JOB_ID.match(job_id or ""):
        raise HTTPException(404, "Unknown report.")
    guard(request, "feedback")
    activity.record("report", job_id, ip=client_ip(request), reason=body.reason, comment=body.comment.strip(),
                    task=body.task)
    return {"ok": True}


class ExplainRequest(BaseModel):
    index: int = Field(ge=0, le=50)
    task: Task


@app.post("/api/jobs/{job_id}/explain")
def explain(job_id: str, body: ExplainRequest, request: Request):
    """How the program works and likely viva questions, so the student can explain their own report."""
    _job(job_id)
    task = body.task
    files = [f for f in task.files if f.code.strip()][:10]
    if not files:
        raise HTTPException(422, "There's no code to explain.")
    cache = ExplainCache()
    key = ExplainCache.key(task.language, files)
    found = cache.get(key)
    if found is not None:
        return found
    guard(request, "explain")
    prompt = f"Language: {task.language}\nTask: {task.title}\n{task.problem[:1500]}\n\n" + "\n\n".join(
        f"File {f.name}:\n{f.code}" for f in files)
    try:
        result = get_provider().explain(prompt[:30_000])
    except AIError as exc:
        raise HTTPException(503, str(exc)) from exc
    cache.put(key, result)
    return result


@app.post("/api/jobs/{job_id}/render")
def render(job_id: str, body: RenderRequest, request: Request):
    job_dir = _job(job_id)
    guard(request, "renders")
    if body.template not in TEMPLATES:
        body.template = "cu-cse"
    result = render_report(job_dir, body)
    values = {f.label.strip().lower(): f.value.strip() for f in body.fields}
    if not _is_owner(request):
        activity.record("render", job_id, ip=client_ip(request), name=values.get("student name", ""),
                        uid=values.get("uid", ""), subject=values.get("subject name", ""), title=body.draft.title,
                        template=body.template, pdf=body.pdf, warnings=result["warnings"],
                        tasks=task_summary([t.model_dump() for t in body.draft.tasks]))
    return result


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str, request: Request):
    """Delete a report from the server: its files, and its rows in the activity log."""
    if not JOB_ID.match(job_id or ""):
        raise HTTPException(404, "Unknown report.")
    guard(request, "deletes")
    jobs.cancel(job_id)
    path = job_path(job_id)
    if path is not None:
        from core.execution.runner import unlink_node_modules

        unlink_node_modules(path)
        shutil.rmtree(path, ignore_errors=True)
    threading.Thread(target=_forget, args=(job_id,), daemon=True).start()
    return {"ok": True}


def _forget(job_id: str) -> None:
    try:
        activity.delete_job(job_id)
    except Exception as exc:  # noqa: BLE001
        print(f"[delete] activity log: {type(exc).__name__}: {exc}")


@app.get("/api/jobs/{job_id}/files/{name}")
def get_file(job_id: str, name: str):
    return _send(job_file(job_id, name))


@app.get("/api/jobs/{job_id}/files/{render_id}/{name}")
def get_render_file(job_id: str, render_id: str, name: str):
    return _send(job_file(job_id, name, render_id), download=name.endswith((".docx", ".pdf")))


def _send(path: Path | None, download: bool = False):
    if path is None:
        raise HTTPException(404, "File not found. It may have expired.")
    headers = {"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff",
               "X-Robots-Tag": "noindex"}
    if download:
        return FileResponse(path, filename=path.name, headers=headers)
    return FileResponse(path, headers=headers)


@app.get("/api/health")
def health():
    return {"ok": True}


# ── admin (header token only: tokens in URLs end up in logs) ───────

def _is_owner(request: Request) -> bool:
    """Requests carrying the admin key (the deploy smoke test, the owner's own checks) aren't logged."""
    expected = os.environ.get("LABFORGE_ADMIN_TOKEN", "")
    given = request.headers.get("x-admin-token", "")
    return bool(expected and given) and hmac.compare_digest(given.encode(), expected.encode())


def _admin(request: Request) -> None:
    if not _is_owner(request):
        raise HTTPException(404)


@app.get("/api/admin/usage")
def admin_usage(request: Request, days: int = 1):
    _admin(request)
    days = max(1, min(days, 90))
    return {"days": days, "by_model": usage_summary(days)}


@app.get("/api/admin/activity")
def admin_activity(request: Request, days: int = 7):
    _admin(request)
    days = max(1, min(days, 90))
    try:
        reports = activity.reports(days)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"The activity log couldn't be read: {type(exc).__name__}") from exc
    return {"days": days, "storage": activity.storage, "reports": reports}


@app.get("/api/admin/status")
def admin_status(request: Request):
    _admin(request)
    from core.db import database_url

    return {
        "providers": get_provider().describe(),
        "runtimes": runner.available(),
        "exec_backend": runner.backend,
        "sandbox": sandbox_report(),
        "pdf": PdfConverter().available(),
        "database": bool(database_url()),
        "limiter": type(limiter).__name__,
        "client_ip": client_ip(request),
        "ip_headers": {h: request.headers.get(h, "") for h in (
            "x-forwarded-for", "x-real-ip", "true-client-ip", "cf-connecting-ip")},
    }


# ── crawlers, ads and the Android app ──────────────────────────────

AUTHOR = os.environ.get("LABFORGE_AUTHOR_NAME", "Mohammad Taha").strip() or "Mohammad Taha"
AUTHOR_AFFILIATION = os.environ.get("LABFORGE_AUTHOR_AFFILIATION", "Chandigarh University").strip()
AUTHOR_PATH = "/mohammad-taha"
REPO_URL = os.environ.get("LABFORGE_REPO_URL", "https://github.com/SHZunknown11/Lab-Forge").strip()


def author_links() -> list[str]:
    raw = os.environ.get("LABFORGE_AUTHOR_LINKS") or os.environ.get("VITE_AUTHOR_LINKS") or ""
    return [u.strip() for u in raw.split(",") if u.strip().startswith("https://")]


PAGES = {
    "/": (f"LabForge: lab reports from your experiment sheet, by {AUTHOR}",
          "Free AI lab report generator: upload your experiment sheet and get a lab report with working code and "
          "the output it really printed. Java, Python, C++, React, Node.js and more, in your college's format. "
          f"Made by {AUTHOR}."),
    "/guide": ("How to use LabForge",
               "Step by step: upload your experiment sheet, check the code and its real output, and download "
               "your lab report as Word or PDF."),
    "/faq": ("LabForge FAQ", "Answers about languages, output screenshots, limits, privacy and using LabForge honestly."),
    "/about": ("How LabForge works", "How LabForge writes, runs and formats your lab report, and what it can't do."),
    "/privacy": ("Privacy policy | LabForge", "What LabForge collects, why, how long it keeps it, and how to delete it."),
    "/terms": ("Terms of use | LabForge", "The rules for using LabForge, including academic honesty."),
    AUTHOR_PATH: (f"{AUTHOR}, creator of LabForge",
                  f"{AUTHOR} is a student at {AUTHOR_AFFILIATION} and the developer of LabForge, a free AI lab "
                  "report generator that runs your code and shows its real output."),
}
BUILT = time.strftime("%Y-%m-%d", time.gmtime())
NOINDEX = {"/admin"}


def public_url(request: Request) -> str:
    configured = os.environ.get("LABFORGE_PUBLIC_URL", "").strip().rstrip("/")
    if configured:
        return configured
    proto = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
    return f"{proto}://{request.headers.get('host', request.url.netloc)}"


# Search engines and the crawlers behind AI assistants: all welcome on the public pages.
AI_CRAWLERS = ("GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-SearchBot", "Claude-User",
               "PerplexityBot", "Perplexity-User", "Google-Extended", "Applebot-Extended", "Bingbot", "CCBot")


@app.get("/robots.txt", include_in_schema=False)
def robots(request: Request):
    base = public_url(request)
    rules = "Allow: /\nDisallow: /api/\nDisallow: /admin\n"
    named = "".join(f"User-agent: {bot}\n" for bot in AI_CRAWLERS)
    return PlainTextResponse(f"User-agent: *\n{rules}\n{named}{rules}\nSitemap: {base}/sitemap.xml\n")


@app.get("/llms.txt", include_in_schema=False)
def llms_txt(request: Request):
    """A plain summary for AI assistants (the llms.txt convention)."""
    base = public_url(request)
    links = "".join(f"- {u}\n" for u in author_links())
    faq = "".join(f"### {x['q']}\n{x['a']}\n\n" for x in _seo().get("faq", []))
    text = f"""# LabForge

> LabForge is a free AI lab report generator for university students, created by {AUTHOR} ({AUTHOR_AFFILIATION}). \
Upload a lab experiment sheet (PDF, Word, PowerPoint, text or a .zip) and it writes the report: aim, objectives, \
working code for each problem, the output each program really printed (it compiles and runs every program), and \
learning outcomes, as a Word or PDF file in a university format.

- Website: {base}/
- Made by: {AUTHOR}, a student at {AUTHOR_AFFILIATION}. About the maker: {base}{AUTHOR_PATH}
- Source code: {REPO_URL}
- Price: free (ad-supported), no account needed
- Languages it runs: Java (incl. Spring Boot), Python (NumPy, Matplotlib, OpenCV, scikit-image), C, C++, Node.js \
(Express, Mongoose), React, SQL, HTML/CSS/JS
- Independent project, not affiliated with any university

## Pages
- [Guide]({base}/guide): how to use it, step by step
- [FAQ]({base}/faq)
- [How it works]({base}/about)
- [About {AUTHOR}]({base}{AUTHOR_PATH})
- [Privacy]({base}/privacy)
- [Terms]({base}/terms)

## Good to know
- Output in a report is always what the program printed; it can't be typed in by hand.
- "Explain this code" walks through each program and offers likely viva questions with answers.
- Students should read, run and understand the code and follow their institution's rules.

## FAQ
{faq}"""
    if links:
        text += f"## {AUTHOR} online\n{links}"
    return PlainTextResponse(text)


@app.get("/humans.txt", include_in_schema=False)
def humans_txt():
    return PlainTextResponse(f"/* TEAM */\nCreator and developer: {AUTHOR}\nFrom: {AUTHOR_AFFILIATION}\n"
                             f"Source: {REPO_URL}\n")


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap(request: Request):
    base = public_url(request)
    urls = "".join(f"<url><loc>{html.escape(base + path)}</loc><lastmod>{BUILT}</lastmod></url>" for path in PAGES)
    xml = f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n'
    return Response(xml, media_type="application/xml")


@app.get("/ads.txt", include_in_schema=False)
def ads_txt():
    client = (os.environ.get("ADSENSE_CLIENT") or os.environ.get("VITE_ADSENSE_CLIENT") or "").strip()
    match = re.fullmatch(r"(?:ca-)?(pub-\d{10,20})", client)
    if not match:
        raise HTTPException(404)
    return PlainTextResponse(f"google.com, {match.group(1)}, DIRECT, f08c47fec0942fa0\n")


@app.get("/.well-known/assetlinks.json", include_in_schema=False)
def assetlinks():
    """Digital Asset Links for the Android app (Trusted Web Activity), once it exists."""
    package = os.environ.get("ANDROID_APP_PACKAGE", "").strip()
    prints = [p.strip() for p in os.environ.get("ANDROID_APP_SHA256", "").split(",") if p.strip()]
    if not package or not prints:
        raise HTTPException(404)
    return JSONResponse([{"relation": ["delegate_permission/common.handle_all_urls"],
                          "target": {"namespace": "android_app", "package_name": package,
                                     "sha256_cert_fingerprints": prints}}])


# ── security headers ───────────────────────────────────────────────

def page_csp(nonce: str) -> str:
    # Strict CSP the way Google recommends for pages with AdSense: only scripts carrying this
    # page's nonce run, and they may load others ('strict-dynamic'). Older browsers fall back
    # to https: + 'unsafe-inline', which newer ones ignore when a nonce is present.
    return "; ".join([
        "default-src 'self'",
        f"script-src 'nonce-{nonce}' 'strict-dynamic' https: 'unsafe-inline'",
        "style-src 'self' 'unsafe-inline' https:",
        "img-src 'self' data: blob: https:",
        "font-src 'self' data: https:",
        "connect-src 'self' https:",
        "frame-src https:",
        "worker-src 'self' blob:",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ])


API_CSP = "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; frame-ancestors 'none'"


@app.middleware("http")
async def _headers(request: Request, call_next):
    response = await call_next(request)
    h = response.headers
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
    h.setdefault("Cross-Origin-Opener-Policy", "same-origin-allow-popups")
    if "content-security-policy" not in h and not h.get("content-type", "").startswith("text/html"):
        h["Content-Security-Policy"] = API_CSP
    proto = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
    if proto == "https":
        h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@app.exception_handler(HTTPException)
async def _http_error(request: Request, exc: HTTPException):
    return JSONResponse({"detail": exc.detail or "Not found."}, status_code=exc.status_code)


# ── frontend ───────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _index_template() -> str:
    return (DIST / "index.html").read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _seo() -> dict:
    try:
        return json.loads((DIST / "prerender" / "seo.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


@lru_cache(maxsize=16)
def _prerendered(page: str) -> str:
    name = "home" if page == "/" else page.strip("/")
    if not re.fullmatch(r"[a-z-]+", name):
        return ""
    try:
        return (DIST / "prerender" / f"{name}.html").read_text(encoding="utf-8")
    except OSError:
        return ""


def structured_data(base: str, page: str) -> list[dict]:
    """schema.org data so search engines (and the AI assistants that read them) know what LabForge is
    and who made it. Only facts that are also on the page."""
    person_id = f"{base}{AUTHOR_PATH}#person"
    app_id = f"{base}/#app"
    person = {"@type": "Person", "@id": person_id, "name": AUTHOR, "url": base + AUTHOR_PATH,
              "description": f"Student at {AUTHOR_AFFILIATION} and creator of LabForge.",
              "affiliation": {"@type": "CollegeOrUniversity", "name": AUTHOR_AFFILIATION},
              "knowsAbout": ["Software development", "Python", "Java", "React", "AI"]}
    if author_links():
        person["sameAs"] = author_links()
    graph: list[dict] = [
        {"@type": "WebSite", "@id": f"{base}/#website", "url": base + "/", "name": "LabForge",
         "description": PAGES["/"][1], "inLanguage": "en", "creator": {"@id": person_id},
         "publisher": {"@id": person_id}},
        {"@type": "WebApplication", "@id": app_id, "name": "LabForge", "url": base + "/",
         "description": PAGES["/"][1], "applicationCategory": "EducationalApplication",
         "applicationSubCategory": "Lab report generator", "operatingSystem": "Any (web browser)",
         "browserRequirements": "Requires JavaScript", "isAccessibleForFree": True, "inLanguage": "en",
         "offers": {"@type": "Offer", "price": "0", "priceCurrency": "INR"},
         "audience": {"@type": "EducationalAudience", "educationalRole": "student"},
         "featureList": ["Writes lab reports from experiment sheets", "Compiles and runs every program",
                         "Real output screenshots", "Word and PDF download", "Explains code with viva questions"],
         "author": {"@id": person_id}, "creator": {"@id": person_id}, "image": base + "/icon-512.png",
         "sameAs": [REPO_URL] if REPO_URL else []},
        person,
    ]
    if page == "/faq" and _seo().get("faq"):
        graph.append({"@type": "FAQPage", "@id": f"{base}/faq#faq", "mainEntity": [
            {"@type": "Question", "name": x["q"], "acceptedAnswer": {"@type": "Answer", "text": x["a"]}}
            for x in _seo()["faq"]]})
    if page == AUTHOR_PATH:
        graph.append({"@type": "ProfilePage", "@id": f"{base}{AUTHOR_PATH}#page", "url": base + AUTHOR_PATH,
                      "name": PAGES[AUTHOR_PATH][0], "mainEntity": {"@id": person_id}, "about": {"@id": app_id}})
    return [{"@context": "https://schema.org", "@graph": graph}]


def render_index(request: Request, path: str) -> HTMLResponse:
    """index.html with this page's title and description (for search engines and link previews)
    and a fresh CSP nonce on every script tag."""
    page = path.rstrip("/") or "/"
    known = page in PAGES or page in NOINDEX
    title, description = PAGES.get(page, PAGES["/"])
    nonce = base64.b64encode(secrets.token_bytes(16)).decode()
    doc = _index_template()
    doc = re.sub(r"<title>.*?</title>", f"<title>{html.escape(title)}</title>", doc, count=1, flags=re.S)
    doc = re.sub(r'(<meta\s+name="description"\s+content=")[^"]*(")', rf'\g<1>{html.escape(description)}\g<2>', doc,
                 count=1)
    doc = re.sub(r'(<meta\s+property="og:title"\s+content=")[^"]*(")', rf'\g<1>{html.escape(title)}\g<2>', doc, count=1)
    doc = re.sub(r'(<meta\s+property="og:description"\s+content=")[^"]*(")',
                 rf'\g<1>{html.escape(description)}\g<2>', doc, count=1)
    base = public_url(request)
    url = base + (page if page != "/" else "/")
    extra = f'<link rel="canonical" href="{html.escape(url)}" />'
    extra += f'\n    <meta property="og:url" content="{html.escape(url)}" />'
    extra += f'\n    <meta property="og:image" content="{html.escape(base)}/icon-512.png" />'
    if page in NOINDEX or not known:
        extra += '\n    <meta name="robots" content="noindex" />'
    else:
        data = json.dumps(structured_data(base, page), ensure_ascii=False).replace("</", "<\\/")
        extra += f'\n    <script type="application/ld+json">{data}</script>'
    doc = re.sub(r'\s*<meta property="og:image" content="[^"]*" />', "", doc, count=1)
    doc = doc.replace("</head>", f"    {extra}\n  </head>", 1)
    if known and page not in NOINDEX:
        # The page's text as plain HTML for crawlers that don't run JavaScript; the app replaces it.
        doc = doc.replace('<div id="root"></div>', f'<div id="root">{_prerendered(page)}</div>', 1)
    doc = re.sub(r"<script\b", f'<script nonce="{nonce}"', doc)
    doc = doc.replace("<head>", f'<head>\n    <meta name="csp-nonce" content="{nonce}" />', 1)
    return HTMLResponse(doc, status_code=200 if known else 404, headers={
        "Content-Security-Policy": page_csp(nonce), "Cache-Control": "no-cache"})


class SPAStatic(StaticFiles):
    async def get_response(self, path, scope):
        from starlette.exceptions import HTTPException as StarletteHTTPException
        from starlette.requests import Request as StarletteRequest

        if scope["path"].startswith("/api/"):  # unknown API URL: a real 404, not the app page
            return JSONResponse({"detail": "Not found."}, status_code=404)
        if path in ("", ".", "index.html"):
            return render_index(StarletteRequest(scope), "/")
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException:
            response = None
        if response is None or response.status_code == 404:
            if "." in path.rsplit("/", 1)[-1]:  # a missing asset: a plain 404
                return PlainTextResponse("Not found.", status_code=404)
            return render_index(StarletteRequest(scope), scope["path"])
        if path.startswith("assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"  # hashed file names
        return response


if DIST.exists():
    app.mount("/", SPAStatic(directory=DIST, html=True), name="web")
else:
    @app.get("/")
    def _no_build():
        return JSONResponse({"detail": "Frontend not built. Run: cd apps/frontend && npm install && npm run build"})
