"""Versioned expected-anchor ledger for verified research citations.

The ledger is data, not row-specific program logic.  It supplements (never
relabels) ESCAP Master Known anchors and provides a deterministic trace through
acquisition, structure, screening, mapping and gates.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


def _plain(value: str) -> str:
    value = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", value)
    value = value.replace("**", "").replace("`", "")
    return re.sub(r"\s+", " ", value).strip()


def _url(value: str) -> str:
    match = re.search(r"\((https?://[^)]+)\)|`(https?://[^`]+)`", value)
    return (match.group(1) or match.group(2)) if match else ""


def citation_refs(value: str) -> list[str]:
    """Expand common legislative list notation without knowing any economy."""
    text = _plain(value).replace("–", "-").replace("—", "-")
    refs: list[str] = []
    schedule = re.search(r"\bSch(?:edule)?\.?\s*(\d+[A-Za-z]?)", text, re.I)
    for match in re.finditer(
        r"\b(Art(?:icle)?|s(?:s)?|reg(?:s)?|r|cl(?:ause)?)\.?\s+"
        r"([^;]+?)(?=\bread with\b|\bvia\b|$)",
        text,
        re.I,
    ):
        prefix, group = match.group(1).lower(), match.group(2)
        group = re.sub(r"-\([^)]+\)", "", group)
        canonical = ("Art." if prefix.startswith("art") else
                     "reg." if prefix.startswith("reg") or prefix == "r" else
                     "cl." if prefix.startswith("cl") else "s.")
        for token in re.findall(r"\d+[A-Za-z]?(?:\.\d+[A-Za-z]?)?(?:\([^)]*\))*", group):
            ref = f"{canonical} {token}"
            if schedule and canonical == "cl.":
                ref = f"Sch {schedule.group(1)}, {ref}"
            if ref not in refs:
                refs.append(ref)
    return refs


def parse_research_reports(paths: list[Path]) -> list[dict]:
    rows: list[dict] = []
    for path in paths:
        lines = path.read_text(encoding="utf-8").splitlines()
        headers: list[str] | None = None
        for line in lines:
            if not line.startswith("|"):
                headers = None
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if "Economy" in cells and "Indicator" in cells:
                headers = cells
                continue
            if not headers or all(set(cell) <= {"-", ":"} for cell in cells):
                continue
            if len(cells) != len(headers):
                continue
            record = dict(zip(headers, cells, strict=True))
            economy_raw = _plain(record.get("Economy", ""))
            economy = next((name for name in ("Singapore", "Malaysia", "Australia")
                            if economy_raw.startswith(name)), "")
            indicator = _plain(record.get("Indicator", ""))
            instrument = _plain(record.get("Instrument (official title, number, year)", ""))
            provision = _plain(record.get("Provision", ""))
            if not economy or not re.fullmatch(r"P[67]-I\d", indicator) or not instrument:
                continue
            refs = citation_refs(provision)
            for ref in refs:
                identity = "\x1f".join((economy, indicator, instrument, ref, path.name))
                rows.append({
                    "anchor_id": hashlib.sha256(identity.encode()).hexdigest(),
                    "economy": economy,
                    "indicator_id": indicator,
                    "instrument": instrument,
                    "citation": ref,
                    "citation_text": provision,
                    "operative_quote": _plain(
                        record.get("≤25-word quote of the operative text", "")
                        or record.get("≤25-word quote of operative text", "")
                    ),
                    "official_url": _url(record.get("Official URL", "")),
                    "confidence": _plain(record.get("Confidence", "")),
                    "source_report": path.name,
                    "status": "VERIFIED_RESEARCH_EXPECTATION",
                })
    unique = {row["anchor_id"]: row for row in rows}
    return sorted(unique.values(), key=lambda row: (
        row["economy"], row["indicator_id"], row["instrument"], row["citation"]
    ))


def load_expected_anchors(path: str | Path = "configs/expected_anchors.json") -> list[dict]:
    ledger = Path(path)
    if not ledger.is_file():
        return []
    payload = json.loads(ledger.read_text(encoding="utf-8"))
    return list(payload.get("anchors") or [])
