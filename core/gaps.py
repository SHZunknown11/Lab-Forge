"""What LabForge couldn't do for a student: languages it can't run, libraries that aren't
installed, a database server that isn't set up, programs that need a window, and a runner that
is offline.

`detect` reads the tasks of a finished report and names each gap with a stable key, so the same
gap from fifty students is one line in /admin ("MATLAB: 37 reports") instead of fifty.
Ordinary bugs in a program (a compile error, a wrong answer) aren't gaps; they are in the
saved failed sessions.
"""
from __future__ import annotations

import re

# (pattern on the program's output, language it applies to or "", kind, what to call it)
_MISSING = (
    (re.compile(r"ModuleNotFoundError: No module named '([\w.]+)'"), "python"),
    (re.compile(r"error: package ([\w.]+) does not exist"), "java"),
    (re.compile(r"Cannot find module '([^'./][^']*)'"), "javascript"),
    (re.compile(r"fatal error: ([\w./+-]+): No such file or directory"), ""),
)
# The runner's own messages (core/execution/runner.py): Java says "library", Python "package",
# Node lists npm packages in brackets.
_NEEDS_ONE = re.compile(r"Needs the (.+?) (?:library|package|module), which isn't installed here")
_NEEDS_NPM = re.compile(r"Needs npm packages that aren't installed here \(([^)]*)\)")
_NEEDS_SERVICE = re.compile(r"Needs an? (.+?) server, which isn't set up here")


def detect(tasks: list[dict], labels: dict[str, str] | None = None) -> list[dict]:
    """Gaps in these tasks: [{"key", "kind", "label"}], each key once."""
    labels = labels or {}
    found: dict[str, dict] = {}

    def add(kind: str, key: str, label: str) -> None:
        found.setdefault(key, {"key": key[:120], "kind": kind, "label": label[:120]})

    for t in tasks:
        language = (t.get("language") or "other").lower()
        name = labels.get(language, language)
        note, output, status = t.get("note") or "", t.get("output") or "", t.get("status") or ""
        if status == "passed":
            continue
        if language == "other" or (labels and language not in labels):
            add("language", f"language:{language}", f"A language LabForge doesn't know ({language})")
        elif "programs can't be run here" in note:
            add("language", f"language:{language}", f"{name} can't be run")
        missing = [m.group(1) for m in [_NEEDS_ONE.search(note)] if m]
        npm = _NEEDS_NPM.search(note)
        if npm:
            missing += npm.group(1).split(",")
        for lib in (m.strip() for m in missing[:6]):
            if lib:
                add("library", f"library:{language}:{lib.lower()}", f"{name} library: {lib}")
        service = _NEEDS_SERVICE.search(note)
        if service:
            add("service", f"service:{service.group(1).strip().lower()}", f"{service.group(1).strip()} server isn't set up")
        for pattern, only in _MISSING:
            if only and only != language:
                continue
            for lib in pattern.findall(output)[:3]:
                lib = lib.split(".")[0] if language == "python" else lib
                add("library", f"library:{language}:{lib.lower()}", f"{name} library: {lib}")
        if "opens a window" in note or "runs in a browser page" in note:
            add("window", f"window:{language}", f"{name} programs that need a window or a browser")
        if ("can't be run right now" in note or "runner couldn't start" in note or "program runner" in note
                or "runner is busy or offline" in note):
            add("runner", "runner:offline", "The program runner was offline or failing")
    return list(found.values())
