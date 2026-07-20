"""Spike: prove the PaddleOCR VM works end-to-end from the engine.

Usage (from engine/, with OCR_ENDPOINT set in .env):
    .venv/bin/python scripts/spike_remote_ocr.py [path-to-scanned-pdf-or-image]

Defaults to the sample kit's image-only Pakistan_PECA.pdf (4 pages, 0 text chars
— the canonical OCR stress fixture).
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.core.envfile import load_env_file  # noqa: E402

load_env_file()

from packages.providers.ocr_provider import RemotePaddleOCR  # noqa: E402

DEFAULT_DOC = (
    Path(__file__).resolve().parents[2]
    / "Hackthon_Knowledge/Sample Kit/Sample legislations/PDF of scanned documents/Pakistan_PECA.pdf"
)


def main() -> int:
    endpoint = os.getenv("OCR_ENDPOINT", "http://localhost:8089")
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DOC
    if not target.is_file():
        print(f"FAIL: test document not found: {target}")
        return 1

    engine = RemotePaddleOCR(endpoint, api_key=os.getenv("OCR_API_KEY") or None)
    print(f"endpoint : {endpoint}")
    print(f"health   : {'OK' if engine.health() else 'no /health route (not fatal — trying /ocr directly)'}")

    started = time.time()
    pages = engine.extract(str(target))
    elapsed = time.time() - started

    total_tokens = sum(len(p.tokens) for p in pages)
    confidences = [p.confidence for p in pages if p.confidence is not None]
    mean_conf = sum(confidences) / len(confidences) if confidences else None
    print(f"document : {target.name}")
    print(f"pages    : {len(pages)}  tokens: {total_tokens}  time: {elapsed:.1f}s")
    print(f"mean conf: {mean_conf:.3f}" if mean_conf is not None else "mean conf: n/a")
    if pages and pages[0].text:
        preview = " ".join(pages[0].text.split())[:200]
        print(f"page 1   : {preview}...")
    ok = total_tokens > 0
    print("RESULT   :", "PASS" if ok else "FAIL (no tokens returned)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
