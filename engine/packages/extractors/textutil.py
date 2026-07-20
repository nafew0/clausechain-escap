"""Shared text utilities for the markup extractors (HTML / XHTML / EPUB paths)."""
from __future__ import annotations

import html as html_lib
import re

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\r\n   ]+")


def clean_text(fragment: str) -> str:
    """Tag-strip + entity-unescape + whitespace-normalize, preserving legal characters."""
    text = _TAG.sub(" ", fragment)
    text = html_lib.unescape(text)
    return _WS.sub(" ", text).strip()
