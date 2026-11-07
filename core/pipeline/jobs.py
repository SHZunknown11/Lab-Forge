"""Report writing runs in the background, not inside the HTTP request.

A phone that locks its screen or switches apps drops the connection; the report keeps being
written and the page picks it up again with GET /api/jobs/{id}/events?after=<seq>. Every event
is kept in memory and appended to the job's events.jsonl, so a reconnect gets everything it
missed, in order.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

TERMINAL = ("done", "error")
KEEP_SECONDS = 3600  # finished jobs stay in memory this long; after that they replay from disk
MAX_ACTIVE = max(1, int(os.environ.get("LABFORGE_MAX_ACTIVE_DRAFTS", "4") or 4))


@dataclass
class _Job:
    events: list[dict] = field(default_factory=list)
    done: bool = False
    finished_at: float = 0.0
    stop: threading.Event = field(default_factory=threading.Event)
    cond: threading.Condition = field(default_factory=threading.Condition)


class DraftJobs:
    def __init__(self, max_active: int = MAX_ACTIVE):
        self._jobs: dict[str, _Job] = {}
        self._lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(max_active)

    # ── producing ──────────────────────────────────────────────────
    def start(self, job_id: str, job_dir: Path, first: dict,
              produce: Callable[[threading.Event], Iterator[dict]],
              on_finish: Callable[[list[dict]], None] | None = None) -> None:
        self._prune()
        job = _Job()
        with self._lock:
            self._jobs[job_id] = job
        self._emit(job, job_dir, first)

        def work():
            try:
                if not self._slots.acquire(blocking=False):
                    self._emit(job, job_dir, {"type": "stage", "stage": "queue",
                                              "text": "Lots of students right now. Waiting for a free spot"})
                    while not self._slots.acquire(timeout=1):
                        if job.stop.is_set():
                            self._emit(job, job_dir, {"type": "error", "message": "Stopped."})
                            return
                try:
                    ended = False
                    for event in produce(job.stop):
                        self._emit(job, job_dir, event)
                        ended = ended or event.get("type") in TERMINAL
                        if job.stop.is_set() and not ended:
                            self._emit(job, job_dir, {"type": "error", "message": "Stopped."})
                            return
                    if not ended:
                        self._emit(job, job_dir, {"type": "error", "message": "Something went wrong while writing."})
                finally:
                    self._slots.release()
            except Exception as exc:  # noqa: BLE001 - the stream must always end
                print(f"[jobs] {type(exc).__name__}: {exc}")
                self._emit(job, job_dir, {"type": "error", "message": "Something went wrong while writing. Try again."})
            finally:
                with job.cond:
                    job.done = True
                    job.finished_at = time.time()
                    job.cond.notify_all()
                if on_finish:
                    try:
                        on_finish(job.events)
                    except Exception as exc:  # noqa: BLE001
                        print(f"[jobs] on_finish: {type(exc).__name__}: {exc}")

        threading.Thread(target=work, daemon=True, name=f"draft-{job_id[:8]}").start()

    def _emit(self, job: _Job, job_dir: Path, event: dict) -> None:
        with job.cond:
            event = {**event, "seq": len(job.events)}
            job.events.append(event)
            job.cond.notify_all()
        try:
            with (job_dir / "events.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        except OSError:
            pass  # the job folder was deleted (expired, or the student deleted the report)

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            return False
        job.stop.set()
        return True

    def running(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
        return job is not None and not job.done

    def _prune(self) -> None:
        cutoff = time.time() - KEEP_SECONDS
        with self._lock:
            for key in [k for k, j in self._jobs.items() if j.done and j.finished_at < cutoff]:
                del self._jobs[key]

    # ── reading ────────────────────────────────────────────────────
    def stream(self, job_id: str, job_dir: Path, after: int = -1, ping_seconds: float = 10) -> Iterator[dict]:
        """Events with seq > `after`; pings while waiting; ends after the last event."""
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            yield from self._replay(job_dir, after)
            return
        sent = after + 1
        while True:
            with job.cond:
                if sent >= len(job.events) and not job.done:
                    job.cond.wait(ping_seconds)
                batch = job.events[sent:]
                finished = job.done
            if not batch and not finished:
                yield {"type": "ping"}
                continue
            for event in batch:
                yield event
            sent += len(batch)
            if finished and sent >= len(job.events):
                return

    @staticmethod
    def _replay(job_dir: Path, after: int) -> Iterator[dict]:
        events = []
        try:
            for line in (job_dir / "events.jsonl").read_text(encoding="utf-8").splitlines():
                try:
                    events.append(json.loads(line))
                except ValueError:
                    continue
        except OSError:
            pass
        for event in events:
            if event.get("seq", -1) > after:
                yield event
        if not any(e.get("type") in TERMINAL for e in events):
            # Written by a server process that has since restarted: it won't finish.
            yield {"type": "error", "seq": len(events),
                   "message": "Writing this report was interrupted when the server restarted. Write it again."}
