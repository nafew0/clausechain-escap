"""Minimal .env loader (stdlib-only) — keeps the README's `.env` contract true.

Real environment variables always win; the file never overrides them.
"""
from __future__ import annotations

import os
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[2]


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
        value = value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value
