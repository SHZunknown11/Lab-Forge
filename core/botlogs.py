"""The last few hundred lines the server printed, for the Telegram bot's /serverlog.

LabForge's own messages are short tagged lines ("[ai] all providers failed: ...", "[mail] ...",
"[runner] worker call failed: ..."). Printing goes through a tee that keeps the tail in memory
and still writes to the real console. Keys and tokens are blanked before a line is kept, so
the tail is safe to send to a chat.
"""
from __future__ import annotations

import re
import sys
import threading
import time
from collections import deque

_LINES: deque = deque(maxlen=500)
_LOCK = threading.Lock()
_SECRETS = re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}|xkeysib-[A-Za-z0-9-]+|re_[A-Za-z0-9]{20,}|"
                      r"\b(?:sk|rzp|gsk)_[A-Za-z0-9_-]{16,}|(?i:token|secret|password|api[_-]?key)=\S+")


class _Tee:
    def __init__(self, stream):
        self._stream = stream
        self._partial = ""

    def write(self, text):
        written = self._stream.write(text)
        self._partial += text
        *done, self._partial = self._partial.split("\n")
        if done:
            stamp = time.strftime("%H:%M:%S")
            with _LOCK:
                for line in done:
                    if line.strip():
                        _LINES.append(f"{stamp} {_SECRETS.sub('***', line.rstrip())[:300]}")
        return written

    def __getattr__(self, name):
        return getattr(self._stream, name)


def install() -> None:
    """Attach the tee to stdout and stderr (again, if something replaced them)."""
    if not isinstance(sys.stdout, _Tee):
        sys.stdout = _Tee(sys.stdout)
    if not isinstance(sys.stderr, _Tee):
        sys.stderr = _Tee(sys.stderr)


def tail(count: int = 30, pattern: str = "") -> list[str]:
    with _LOCK:
        lines = list(_LINES)
    if pattern:
        lines = [ln for ln in lines if pattern.lower() in ln.lower()]
    return lines[-max(1, min(count, 200)):]
