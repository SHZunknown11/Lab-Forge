"""The header block a filled-in sheet carries: Student Name, UID, Branch, ..., Subject Code.

read_header() pulls those values out so the form can fill itself in. strip_personal()
removes the student's own lines before the sheet goes to the AI and the cache key, so
every classmate with the same sheet shares one AI call (and no names reach the provider).
"""
from __future__ import annotations

import re

HEADER_LINES = 40
_SEP = r"\s*[:\-–]\s*"
FIELDS = {
    "Student Name": rf"(?:student\s*)?name{_SEP}",
    "UID": r"uid\s*[:\-–]?\s*",
    "Branch": rf"branch{_SEP}",
    "Section/Group": rf"(?:section\s*/\s*group|section|group){_SEP}",
    "Semester": rf"sem(?:ester)?{_SEP}",
    "Date": rf"date(?:\s+of\s+\w+)?{_SEP}",
    "Subject Code": rf"(?:subject|course)\s*code{_SEP}",
    "Subject Name": rf"(?:subject|course)(?:\s*name)?{_SEP}",
}
PERSONAL = ("Student Name", "UID", "Branch", "Section/Group", "Semester", "Date")
_PATTERNS = {label: re.compile(rf"^\s*{prefix}(.+?)\s*$", re.IGNORECASE) for label, prefix in FIELDS.items()}
_UID_VALUE = re.compile(r"^[A-Za-z0-9]{4,20}$")
# The header ends where the sheet's body starts: the aim, a task, or any code.
_BODY = re.compile(r"^\s*(?:\d+[.)]\s*)?(?:aim|objective|problem|theory|code|implementation|easy|medium|hard)\b"
                   r"|[{};]|^\s*(?:import|from|def|class|public|#include|package)\b", re.IGNORECASE)


def _head(lines: list[str]) -> int:
    for i, line in enumerate(lines[:HEADER_LINES]):
        if _BODY.search(line):
            return i
    return min(len(lines), HEADER_LINES)


def _cells(line: str) -> list[str]:
    """'Name: Asha     UID: 24BCS1' holds two fields; split on wide gaps and tabs."""
    return [c for c in re.split(r"\t+|\s{3,}|\s+\|\s+", line) if c.strip()]


def _match(cell: str) -> tuple[str, str] | None:
    for label, pattern in _PATTERNS.items():
        m = pattern.match(cell)
        if not m:
            continue
        value = m.group(1).strip(" .,;")
        if label == "UID" and not _UID_VALUE.match(value):
            return None
        if 1 <= len(value) <= 80:
            return label, value.upper() if label == "UID" else value
        return None
    return None


def read_header(sheet: str) -> dict[str, str]:
    found: dict[str, str] = {}
    lines = sheet.splitlines()
    for line in lines[:_head(lines)]:
        for cell in _cells(line):
            hit = _match(cell)
            if hit and hit[0] not in found:
                found[hit[0]] = hit[1]
    return found


def strip_personal(sheet: str) -> str:
    lines = sheet.splitlines()
    end = _head(lines)
    head, rest = lines[:end], lines[end:]
    kept = []
    for line in head:
        cells = _cells(line)
        hits = [_match(c) for c in cells]
        if cells and all(h and h[0] in PERSONAL for h in hits):
            continue  # a line holding only the student's own details
        kept.append(line)
    return "\n".join(kept + rest).strip()
