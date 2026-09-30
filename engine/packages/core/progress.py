"""Live run progress: one event stream for the terminal and the web console.

Every pipeline step calls ``emit(stage, message, detail=...)``. The event is
printed immediately to stderr as a readable line (so ``python run.py ...`` shows
progress live), and, when the engine worker sets ``CLAUSECHAIN_EVENT_LOG``,
appended as one JSON line to that file, which the worker copies into the app
database for the Runs page console.

``detail`` carries the long form (prompt text, model reply, candidate lists);
it is printed only with ``CLAUSECHAIN_VERBOSE=1`` (``run.py --verbose``) and
always stored, capped, for the web console. API keys and headers are never
passed here.
"""
from __future__ import annotations

import contextvars
import json
import os
import sys
import threading
import time

DETAIL_CAP = 12_000  # characters kept per event detail (prompts are ~2-8k)

_label: contextvars.ContextVar[str] = contextvars.ContextVar("clausechain_progress_label",
                                                             default="")
_lock = threading.Lock()
_seq = 0


def set_label(label: str) -> contextvars.Token:
    """Tag subsequent events in this context (e.g. "P6-I4 · screen")."""
    return _label.set(label)


def reset_label(token: contextvars.Token) -> None:
    _label.reset(token)


def current_label() -> str:
    return _label.get()


def emit(stage: str, message: str, *, detail: str | None = None,
         level: str = "info", label: str | None = None) -> None:
    global _seq
    tag = _label.get() if label is None else label
    line = f"{time.strftime('%H:%M:%S')}  {stage.upper():<9} {tag + ' · ' if tag else ''}{message}"
    with _lock:
        _seq += 1
        seq = _seq
        print(line, file=sys.stderr, flush=True)
        if detail and os.getenv("CLAUSECHAIN_VERBOSE") == "1":
            for detail_line in str(detail)[:4000].splitlines():
                print(f"             | {detail_line}", file=sys.stderr)
            sys.stderr.flush()
        path = os.getenv("CLAUSECHAIN_EVENT_LOG")
        if path:
            event = {"seq": seq, "ts": time.time(), "stage": stage, "label": tag,
                     "message": message[:1000], "level": level,
                     "detail": (str(detail)[:DETAIL_CAP] if detail else "")}
            try:
                with open(path, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(event, ensure_ascii=False) + "\n")
            except OSError:
                pass  # progress must never break a run
