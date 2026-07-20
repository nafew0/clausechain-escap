"""Create a stratified 30-page DRAFT gold manifest; never self-label it human checked."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from packages.extractors.pdf import classify_pages  # noqa: E402

TARGETS = {"clean_native": 8, "complex_native": 8, "scanned": 8, "mixed": 3, "multilingual": 3}
MALAY = re.compile(r"\b(dan|yang|akta|seksyen|kerajaan|hendaklah|tidak)\b", re.I)
MANDATORY = [
    ("data/raw/au/C2026C00227.pdf", 267, "AU Privacy Act s.33D(1)/(2)"),
    ("data/raw/au/C2026C00209_vol2.pdf", 16, "AU TIA s.187A"),
    ("data/raw/au/C2026C00209_vol2.pdf", 22, "AU TIA s.187B / note guard"),
    ("data/raw/au/C2026C00224_vol2.pdf", 130, "AU Telecommunications s.317ZH / page-number guard"),
    ("data/raw/au/C2026C00243_vol3.pdf", 110, "AU Criminal Code 474.17A / Roman item"),
]


def draft_page(path: Path, page_number: int, category: str, case: str | None = None) -> dict:
    report = classify_pages(str(path))[page_number - 1]
    with fitz.open(path) as doc:
        text = doc[page_number - 1].get_text()
    return {"category": category, "source_path": str(path),
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "page_number": page_number, "route": report["route"],
        "route_reasons": report["reasons"], "mandatory_case": case,
        "draft_transcription": text,
        "draft_structure_labels": re.findall(
            r"(?m)^\s*(?:Section\s+)?\d+(?:\.\d+)?[A-Z]{0,3}(?:\([^)]*\))*", text),
        "human_transcription": None, "human_structure_labels": None,
        "human_checked": False, "reviewer_name": None, "reviewed_at": None}


def main() -> int:
    selected = {k: [] for k in TARGETS}
    used: set[tuple[str, int]] = set()
    for raw_path, page_number, case in MANDATORY:
        path = Path(raw_path)
        if not path.is_file():
            continue
        category = "complex_native" if len(selected["complex_native"]) < TARGETS["complex_native"] else "clean_native"
        selected[category].append(draft_page(path, page_number, category, case))
        used.add((str(path), page_number))
    files = sorted(Path("data/raw").glob("**/*.pdf"))
    for path in files:
        try:
            report = classify_pages(str(path))
            with fitz.open(path) as doc:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                for info in report:
                    if (str(path), info["page"]) in used:
                        continue
                    text = doc[info["page"] - 1].get_text()
                    if MALAY.search(text) and len(selected["multilingual"]) < TARGETS["multilingual"]:
                        category = "multilingual"
                    else:
                        category = {"NATIVE_SIMPLE": "clean_native", "NATIVE_COMPLEX": "complex_native",
                                    "SCANNED": "scanned", "MIXED": "mixed"}.get(info["route"])
                    if not category or len(selected[category]) >= TARGETS[category]:
                        continue
                    selected[category].append(draft_page(path, info["page"], category))
                    used.add((str(path), info["page"]))
        except Exception:
            continue
        if all(len(selected[k]) >= n for k, n in TARGETS.items()):
            break
    missing = {k: TARGETS[k] - len(v) for k, v in selected.items() if len(v) < TARGETS[k]}
    payload = {"version": 1, "status": "DRAFT_NOT_HUMAN_GOLD", "targets": TARGETS,
               "mandatory_cases": [case for _, _, case in MANDATORY],
               "missing": missing, "pages": sum(selected.values(), [])}
    out = Path("tests/fixtures/extraction_gold_v1.draft.json")
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"gold draft: {len(payload['pages'])}/30 pages; missing={missing}; requires user sign-off")
    return 1 if missing else 0


if __name__ == "__main__": raise SystemExit(main())
