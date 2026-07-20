from __future__ import annotations

import re


_SECTION = re.compile(r"\b(?:s(?:ection)?\.?\s*)?(\d+(?:\.\d+)?[A-Z]{0,3})", re.I)
_SCHEDULE = re.compile(r"\b(?:Sch(?:edule)?\.?\s*)([A-Z0-9]+)", re.I)
_CLAUSE = re.compile(r"\b(?:cl(?:ause)?\.?\s*)(\d+(?:\.\d+)?[A-Z]{0,3})", re.I)
_REG = re.compile(r"\b(?:reg(?:ulation)?\.?\s*)(\d+(?:\.\d+)?[A-Z]{0,3})", re.I)
_ARTICLE = re.compile(r"\b(?:art(?:icle)?\.?\s*)(\d+(?:\.\d+)?[A-Z]{0,3})", re.I)
_QUALIFIERS = re.compile(r"\(([0-9]+|[a-z]{1,3}|[ivxlcdm]+)\)", re.I)


def citation_path(citation: str) -> list[str]:
    """Canonical hierarchy for statutes, schedules, clauses and nested items."""
    path: list[str] = []
    schedule = _SCHEDULE.search(citation)
    if schedule:
        path.append(f"Schedule {schedule.group(1)}")
    for label, pattern in (("regulation", _REG), ("article", _ARTICLE),
                           ("clause", _CLAUSE), ("section", _SECTION)):
        match = pattern.search(citation)
        if match:
            value = match.group(1)
            if label == "section" and schedule and value == schedule.group(1):
                continue
            path.append(f"{label} {value}")
            suffix = citation[match.end():]
            path.extend(f"item ({m.group(1)})" for m in _QUALIFIERS.finditer(suffix))
            break
    if not path:
        for heading in ("Part", "Division", "Chapter"):
            match = re.search(rf"\b{heading}\s+([A-Z0-9]+)", citation, re.I)
            if match:
                path.append(f"{heading} {match.group(1)}")
    return path
