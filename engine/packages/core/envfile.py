"""Minimal .env loader (stdlib-only) — keeps the README's `.env` contract true.

Real environment variables always win; the file never overrides them.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[2]

# An unquoted trailing ` # comment` (whitespace then hash) is stripped, matching
# .env.example's own style (e.g. `LOCALAI_MODEL=  # id the server expects...`,
# meant to be replaced, but easy to instead append a real value before the
# comment — verified 29 Sep 2026: that left "claude-sonnet-4-5   # id the..."
# as the literal value sent to the LLM server). A quoted value is taken
# verbatim between its matching quotes, so a literal " #" inside one is safe.
_INLINE_COMMENT = re.compile(r"\s+#.*$")


def load_env_file(path: str | os.PathLike[str] | None = None) -> None:
    p = Path(path) if path else ENGINE_ROOT / ".env"
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if value[:1] in ('"', "'") and value[-1:] == value[:1] and len(value) >= 2:
            value = value[1:-1]
        else:
            value = _INLINE_COMMENT.sub("", value).strip()
        if key and value and key not in os.environ:
            os.environ[key] = value
