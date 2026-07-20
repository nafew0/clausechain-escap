from __future__ import annotations

import fitz
import pytest

from packages.core.schemas import ExtractedPage
from packages.extractors.pdf import classify_pages, extract_pdf, is_scanned_pdf


def _make_text_pdf(path, pages=2):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text(
            (72, 72),
            f"Section {i + 1}. An organisation shall not transfer personal data "
            "unless the prescribed requirements are satisfied.",
        )
    doc.save(str(path))
    doc.close()


def _make_blank_pdf(path, pages=2):
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page()
    doc.save(str(path))
    doc.close()


def _make_mixed_pdf(path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Cover page with a perfectly readable native text layer here.")
    doc.new_page()  # blank = image-classified
    doc.save(str(path))
    doc.close()


def _make_furniture_pdf(path):
    doc = fitz.open()
    for i in range(3):
        page = doc.new_page()
        page.insert_text((72, 35), "Repeated Act Header")
        page.insert_text((72, 200), f"Section {i + 1}. Operative legal text for this page.")
        page.insert_text((72, 810), f"Compilation page {i + 1}")
    doc.save(str(path)); doc.close()


class SpyOCR:
    def __init__(self):
        self.extract_calls = []
        self.image_calls = []

    def extract(self, file_path):
        self.extract_calls.append(file_path)
        return [
            ExtractedPage(document_id=file_path, page_number=1, text="OCR TEXT",
                          source_url=f"file://{file_path}", location_reference="page 1",
                          confidence=0.98)
        ]

    def ocr_image(self, image_bytes, page_number=1, document_id="image"):
        self.image_calls.append(page_number)
        return ExtractedPage(document_id=document_id, page_number=page_number,
                             text="OCR PAGE", source_url=f"file://{document_id}",
                             location_reference=f"page {page_number}", confidence=0.97)


def test_text_pdf_never_touches_ocr(tmp_path):
    pdf = tmp_path / "native.pdf"
    _make_text_pdf(pdf)
    spy = SpyOCR()

    assert not is_scanned_pdf(str(pdf))
    pages = extract_pdf(str(pdf), ocr_engine=spy)

    assert spy.extract_calls == [] and spy.image_calls == []  # THE guarantee
    assert len(pages) == 2
    assert all(p.metadata["extraction"] == "native_text" for p in pages)
    assert "shall not transfer" in pages[0].text
    # text-only docs work with no OCR engine at all
    assert len(extract_pdf(str(pdf), ocr_engine=None)) == 2


def test_scanned_pdf_goes_to_ocr_whole_doc(tmp_path):
    pdf = tmp_path / "scan.pdf"
    _make_blank_pdf(pdf)
    spy = SpyOCR()

    assert is_scanned_pdf(str(pdf))
    pages = extract_pdf(str(pdf), ocr_engine=spy)

    assert spy.extract_calls == [str(pdf)]  # one whole-document OCR call
    assert pages[0].metadata["extraction"] == "ocr"


def test_scanned_pdf_without_engine_raises(tmp_path):
    pdf = tmp_path / "scan.pdf"
    _make_blank_pdf(pdf, pages=1)
    with pytest.raises(RuntimeError, match="need OCR"):
        extract_pdf(str(pdf), ocr_engine=None)


def test_mixed_pdf_ocrs_only_image_pages(tmp_path):
    pdf = tmp_path / "mixed.pdf"
    _make_mixed_pdf(pdf)
    spy = SpyOCR()

    kinds = [p["kind"] for p in classify_pages(str(pdf))]
    assert kinds == ["text", "image"]

    pages = extract_pdf(str(pdf), ocr_engine=spy)

    assert spy.extract_calls == []          # whole-doc OCR NOT used
    assert spy.image_calls == [2]           # only the scanned page went to OCR
    assert pages[0].metadata["extraction"] == "native_text"
    assert pages[1].metadata["extraction"] == "ocr"
    assert [p.page_number for p in pages] == [1, 2]


def test_native_preserves_both_orders_and_excludes_repeated_furniture_from_search(tmp_path):
    pdf = tmp_path / "furniture.pdf"; _make_furniture_pdf(pdf)
    pages = extract_pdf(str(pdf))
    assert all(p.metadata["source_order_text"] for p in pages)
    assert all(p.metadata["coordinate_order_text"] for p in pages)
    assert "Repeated Act Header" in pages[0].text
    assert "Repeated Act Header" not in pages[0].metadata["searchable_text"]
    assert "Operative legal text" in pages[0].metadata["searchable_text"]
    assert pages[0].metadata["repeated_furniture_span_indices"]


def test_docling_cannot_be_enabled_as_canonical_text(tmp_path):
    pdf = tmp_path / "native.pdf"; _make_text_pdf(pdf, pages=1)
    with pytest.raises(RuntimeError, match="disabled"):
        extract_pdf(str(pdf), engine="docling")
