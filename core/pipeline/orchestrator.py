"""Report pipeline.

draft:  sheet text -> model (or cache) -> run every program -> one batched fix
        round for failures -> ReportDraft the student can edit
run:    re-run one edited task (no model call)
render: draft + student fields -> DOCX (+ PDF and page previews); no model call
"""
from __future__ import annotations

import os
import random
import re
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from core.ai.provider import AIError, DraftCache, get_provider
from core.documents.generator import ReportWriter, safe_filename
from core.documents.pdf_converter import PdfConversionError, PdfConverter
from core.execution.runner import SPRING_IMPORT, CodeRunner, prepare_java, unlink_node_modules
from core.schemas import AIFile, AIReport, AITask, CodeFile, RenderRequest, ReportDraft, RunResult, Task
from core.screenshots.terminal_renderer import fit_output, render_console
from core.validation.pdf_renderer import PdfPreviewRenderer

ROOT = Path(__file__).resolve().parents[2]
JOBS_ROOT = Path(os.environ.get("LABFORGE_JOBS_DIR", ROOT / "artifacts" / "jobs"))
JOB_ID = re.compile(r"^[a-f0-9]{32}$")
FILE_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,120}$")
CONSOLE_PPI = 192  # console PNGs are drawn at 2x
IMAGE_PPI = 110


# ── jobs ───────────────────────────────────────────────────────────

def new_job() -> tuple[str, Path]:
    job_id = uuid.uuid4().hex
    path = JOBS_ROOT / job_id
    path.mkdir(parents=True, exist_ok=True)
    return job_id, path


def job_path(job_id: str) -> Path | None:
    if not JOB_ID.match(job_id or ""):
        return None
    path = JOBS_ROOT / job_id
    return path if path.is_dir() else None


RENDER_ID = re.compile(r"^r_[a-f0-9]{8}$")


def job_file(job_id: str, name: str, render_id: str = "") -> Path | None:
    base = job_path(job_id)
    if base is None or not FILE_NAME.match(name or "") or name.startswith("."):
        return None
    if render_id:
        if not RENDER_ID.match(render_id):
            return None
        base = base / render_id
    candidate = base / name
    return candidate if candidate.is_file() else None


def purge_old_jobs(max_age_hours: float) -> int:
    if not JOBS_ROOT.exists():
        return 0
    cutoff = time.time() - max_age_hours * 3600
    removed = 0
    for path in JOBS_ROOT.iterdir():
        try:
            if path.is_dir() and path.stat().st_mtime < cutoff:
                shutil.rmtree(path, ignore_errors=True)
                removed += 1
        except OSError:
            continue
    return removed


# ── draft ──────────────────────────────────────────────────────────

_writing_locks: dict[str, threading.Lock] = {}
_writing_guard = threading.Lock()


@contextmanager
def _writing(key: str):
    with _writing_guard:
        lock = _writing_locks.setdefault(key, threading.Lock())
    with lock:
        yield
    with _writing_guard:
        if not lock.locked():
            _writing_locks.pop(key, None)


def build_draft(
    sheet: str,
    job_dir: Path,
    language: str = "",
    subject: str = "",
    fresh: bool = False,
    provider=None,
    cache: DraftCache | None = None,
    runner: CodeRunner | None = None,
) -> Iterator[dict]:
    provider = provider or get_provider()
    cache = cache or DraftCache()
    runner = runner or CodeRunner()

    offline = getattr(provider, "name", "") == "local"
    # Offline drafts get their own cache entries so they never stand in for real ones.
    key = DraftCache.key(sheet, language + ("|offline" if offline else ""))
    report = None if fresh else cache.get(key)
    if report is None and not fresh:
        # Classmates often send the same sheet within seconds: the first writes it, the rest wait and reuse it.
        with _writing(key):
            report = cache.get(key)
            if report is None:
                yield {"type": "stage", "stage": "write", "text": "Writing the report and programs"}
                report = provider.generate(sheet, language, subject, 0)
                cache.put(key, report)
                cached = False
            else:
                cached = True
    else:
        cached = report is not None
        if not cached:
            yield {"type": "stage", "stage": "write", "text": "Writing the report and programs"}
            report = provider.generate(sheet, language, subject, random.randint(1, 999))
    if cached:
        yield {"type": "stage", "stage": "write", "text": "Found this sheet already written, reusing it"}

    draft = to_draft(report)
    yield {"type": "draft", "draft": draft.model_dump()}

    yield {"type": "stage", "stage": "run", "text": "Compiling and running each program"}
    results = yield from _run_all(draft, job_dir, runner, range(len(draft.tasks)))

    failing = [i for i, r in results.items() if r.status == "failed" and r.retryable]
    if failing and getattr(provider, "name", "") != "local":
        yield {"type": "stage", "stage": "fix",
               "text": f"Fixing {len(failing)} program{'s' if len(failing) > 1 else ''} that didn't run"}
        items = [{
            "index": i,
            "language": draft.tasks[i].language,
            "error": (draft.tasks[i].output or draft.tasks[i].note)[-1500:],
            "files": [f.model_dump() for f in draft.tasks[i].files],
            "stdin": draft.tasks[i].stdin,
        } for i in failing]
        try:
            fixes = provider.fix(items).fixes
        except AIError:
            fixes = []
        changed = []
        for fx in fixes:
            if fx.index in failing and any(f.code.strip() for f in fx.files):
                draft.tasks[fx.index].files = [CodeFile(name=f.name, code=f.code.rstrip()) for f in fx.files]
                draft.tasks[fx.index].stdin = fx.stdin
                changed.append(fx.index)
        if changed:
            fixed = yield from _run_all(draft, job_dir, runner, changed)
            if not fresh and any(r.status == "passed" for r in fixed.values()):
                for i in changed:
                    report.tasks[i].files = [AIFile(name=f.name, code=f.code) for f in draft.tasks[i].files]
                    report.tasks[i].stdin = draft.tasks[i].stdin
                cache.put(key, report)  # the next student skips the fix

    yield {"type": "done", "draft": draft.model_dump(), "cached": cached}


def to_draft(report: AIReport) -> ReportDraft:
    no = str(report.experiment_no).strip()
    return ReportDraft(
        experiment_no=no,
        title=report.title.strip() or (f"Experiment {no}" if no else "Experiment"),
        aim=report.aim.strip(),
        tasks=[_task(t) for t in report.tasks],
        learning_outcomes=[o.strip() for o in report.learning_outcomes if o.strip()],
    )


def _task(t: AITask) -> Task:
    return Task(
        title=t.title.strip(), problem=t.problem.strip(), objectives=t.objectives,
        language=(t.language or "other").lower().strip(),
        files=[CodeFile(name=f.name.strip(), code=f.code.rstrip()) for f in t.files if f.code.strip()],
        stdin=t.stdin,
    )


def _run_all(draft: ReportDraft, job_dir: Path, runner: CodeRunner, indexes) -> Iterator[dict]:
    results: dict[int, RunResult] = {}
    indexes = list(indexes)
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(run_task, job_dir, i, draft.tasks[i], runner): i for i in indexes}
        for fut in as_completed(futures):
            i = futures[fut]
            results[i] = fut.result()
            t = draft.tasks[i]
            yield {"type": "task", "index": i, "title": t.title, "status": t.status, "note": t.note}
    return results


def run_task(job_dir: Path, index: int, task: Task, runner: CodeRunner | None = None) -> RunResult:
    """Run `task` and write the result (output, status, note, figures) back onto it."""
    runner = runner or CodeRunner()
    work = job_dir / f".run_{index}_{uuid.uuid4().hex[:6]}"
    try:
        result = runner.run(task.language, task.files, task.stdin, work)
        # Captured figures replace earlier captured figures; uploads are kept.
        captured = [n for n in task.images if re.match(r"t\d+_fig", n)]
        for name in captured:
            if FILE_NAME.match(name):
                (job_dir / name).unlink(missing_ok=True)
        kept = [n for n in task.images if n not in captured]
        figures = []
        stamp = uuid.uuid4().hex[:4]
        for n, src in enumerate(result.figures, start=1):
            name = f"t{index}_fig{n}_{stamp}.png"
            shutil.move(src, job_dir / name)
            figures.append(name)
        task.output = fit_output(result.output)  # at most one page in the report
        task.status = result.status
        task.note = result.note
        task.images = figures + kept
        return result
    finally:
        unlink_node_modules(work)  # never follow the junction into the shared runtime
        shutil.rmtree(work, ignore_errors=True)


# ── render ─────────────────────────────────────────────────────────

def render_report(job_dir: Path, req: RenderRequest) -> dict:
    # Each render gets its own folder, so a file that is still being downloaded
    # (and locked, on Windows) never blocks the next render.
    for old in job_dir.glob("r_*"):
        shutil.rmtree(old, ignore_errors=True)
    render_id = f"r_{uuid.uuid4().hex[:8]}"
    out = job_dir / render_id
    out.mkdir(parents=True)

    draft = req.draft
    task_images: list[list[tuple[Path, float]]] = []
    warnings: list[str] = []
    for i, task in enumerate(draft.tasks):
        images: list[tuple[Path, float]] = []
        own = [job_dir / n for n in task.images if FILE_NAME.match(n) and (job_dir / n).is_file()]
        if task.show_console and (task.output.strip() or (task.status == "passed" and not own)):
            shot = out / f"console_{i + 1}.png"
            render_console(task.output, shot, command=_command(task))
            images.append((shot, CONSOLE_PPI))
        images += [(p, IMAGE_PPI) for p in own]
        if not images:
            warnings.append(f"{task.title or f'Task {i + 1}'} has no output yet.")
        task_images.append(images)

    values = {f.label.strip().lower(): f.value.strip() for f in req.fields}
    base = safe_filename(draft.title or f"Experiment {draft.experiment_no}", values.get("student name", ""))
    signature = ""
    if req.sign_code:
        signature = " - ".join(v for v in (values.get("student name", ""), values.get("uid", "")) if v)
    docx = ReportWriter().write(req.template, out / f"{base}.docx", req.fields, draft, task_images,
                                signature=signature)
    for f in req.fields:
        if f.label.strip() and not f.value.strip():
            warnings.append(f"{f.label.strip()} is blank.")

    result = {"render": render_id, "docx": docx.name, "pdf": None, "pages": [], "warnings": warnings}
    if req.pdf:
        converter = PdfConverter()
        if converter.available():
            try:
                pdf = converter.convert(str(docx), str(out / f"{base}.pdf"))
                result["pdf"] = Path(pdf.pdf_path).name
                previews = PdfPreviewRenderer(dpi=60).render(pdf.pdf_path, str(out / "pages"), max_pages=30)
                for n, src in enumerate(previews, start=1):
                    name = f"page_{n:02d}.png"
                    shutil.move(src, out / name)
                    result["pages"].append(name)
                shutil.rmtree(out / "pages", ignore_errors=True)
            except PdfConversionError as exc:
                result["pdf_error"] = str(exc)
        else:
            result["pdf_error"] = "PDF export isn't set up on this server. The Word file has everything."
    return result


def _command(task: Task) -> str:
    lang = task.language
    names = [f.name for f in task.files]
    if lang == "java" and any(SPRING_IMPORT.search(f.code) for f in task.files):
        return "mvn spring-boot:run"
    if lang == "java" and task.files:
        main = next((f.code for f in task.files if "void main" in f.code), task.files[0].code)
        return f"java {prepare_java(main)[1]}"
    if lang == "python":
        entry = next((n for n in names if n.endswith("main.py")), names[0] if names else "main.py")
        return f"python {entry}"
    if lang == "javascript":
        js = [n for n in names if n.endswith((".js", ".mjs", ".cjs"))] or ["index.js"]
        preferred = [n for n in js if n.rsplit("/", 1)[-1] in ("index.js", "server.js", "app.js", "main.js")]
        return f"node {(preferred or js)[0]}"
    return {"c": "./a.out", "cpp": "./a.out"}.get(lang, "")
