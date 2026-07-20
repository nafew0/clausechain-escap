"""AI-1 P0 spike: prove the scanned-PDF detection path on a real sample-kit document.

Opens a sample legislation PDF, measures the native text layer per page (image-only
pages have ~zero text), and renders page 1 to PNG (the future OCR input).
If pytesseract + tesseract are installed (optional `ocr` group), OCRs page 1 as a taste.

Usage (from engine/):
    uv run python scripts/spike_ocr_check.py            # defaults to Pakistan_PECA.pdf
    uv run python scripts/spike_ocr_check.py --pdf "/path/to/some.pdf"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fitz  # noqa: E402  (PyMuPDF)

DEFAULT_PDF = (Path(__file__).resolve().parents[2] / "Hackthon_Knowledge" / "Sample Kit"
               / "Sample legislations" / "PDF of scanned documents" / "Pakistan_PECA.pdf")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", default=str(DEFAULT_PDF))
    parser.add_argument("--max-pages", type=int, default=10)
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"FAIL: PDF not found: {pdf_path}", file=sys.stderr)
        return 1

    doc = fitz.open(pdf_path)
    print(f"{pdf_path.name}: {doc.page_count} pages")
    text_chars = []
    for number in range(min(doc.page_count, args.max_pages)):
        chars = len(doc[number].get_text().strip())
        text_chars.append(chars)
        print(f"  page {number + 1}: native text chars = {chars}")

    scanned = all(chars < 50 for chars in text_chars)
    print(f"VERDICT: {'SCANNED (image-only) -> OCR path required' if scanned else 'has native text layer'}")

    out_dir = Path("data/tmp")
    out_dir.mkdir(parents=True, exist_ok=True)
    pix = doc[0].get_pixmap(dpi=200)
    png_path = out_dir / f"{pdf_path.stem}_p1.png"
    pix.save(png_path)
    print(f"PASS: rendered page 1 -> {png_path} ({pix.width}x{pix.height}px) — future OCR input")

    try:
        import pytesseract
        from PIL import Image

        sample = pytesseract.image_to_string(Image.open(png_path))[:300].strip()
        print(f"OCR taste (tesseract, first 300 chars):\n{sample}")
    except Exception:  # noqa: BLE001
        print("SKIP OCR taste (install: uv sync --group ocr; plus the tesseract binary). "
              "Full OCR engine lands in P2 per the Dev Plan.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
