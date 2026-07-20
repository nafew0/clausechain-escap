"""PDF extraction router: native text layer first, OCR ONLY for scanned pages.

The rule (Build Guide §3 stage [4]): a PDF page with a real text layer is read
directly with PyMuPDF — it must NEVER be sent to the OCR service. OCR is the
fallback for image-only (scanned) pages. Detection is per PAGE, so a mixed
document (typed cover + scanned gazette body) gets native text where it exists
and OCR only where it must.

Classification heuristic per page:
  - text layer with >= MIN_TEXT_CHARS characters -> "text"  (native extraction)
  - otherwise, if the page renders anything      -> "image" (needs OCR)
Pages that are text-classified but also carry a full-page image are flagged
`embedded_text_layer` (already-OCRed scans) — we still use the text layer, but
the flag is surfaced in metadata/Notes.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import re
import unicodedata

import fitz  # PyMuPDF

from packages.core.schemas import ExtractedPage, PageArtifact, TextSpan

MIN_TEXT_CHARS = 25


def _unicode_quality(text: str) -> float:
    if not text:
        return 0.0
    bad = text.count("\ufffd") + sum(1 for c in text if unicodedata.category(c) == "Cc" and c not in "\n\t\r")
    return 1.0 - bad / len(text)


def classify_pages(file_path: str) -> list[dict]:
    """Per-page classification: [{'page': 1, 'kind': 'text'|'image', 'chars': n, 'has_image': bool}]"""
    report: list[dict] = []
    with fitz.open(file_path) as doc:
        for index, page in enumerate(doc, start=1):
            text = page.get_text().strip()
            raw = page.get_text("rawdict")
            spans = [s for b in raw.get("blocks", []) if b.get("type") == 0
                     for line in b.get("lines", []) for s in line.get("spans", [])]
            images = page.get_images(full=True)
            has_image = bool(images)
            area = max(page.rect.width * page.rect.height, 1)
            text_area = sum(max(0, s["bbox"][2] - s["bbox"][0]) *
                            max(0, s["bbox"][3] - s["bbox"][1]) for s in spans) / area
            quality = _unicode_quality(text)
            reasons: list[str] = []
            if len(text) < MIN_TEXT_CHARS:
                route = "SCANNED" if has_image else "REVIEW"
                reasons.append("insufficient native text")
            elif quality < 0.995:
                route = "REVIEW"
                reasons.append("suspicious Unicode/control characters")
            elif has_image and text_area < 0.03:
                route = "MIXED"
                reasons.append("image-dominant page with sparse text layer")
            elif len(spans) > 250 or len({round(s["bbox"][0] / 40) for s in spans}) > 8:
                route = "NATIVE_COMPLEX"
                reasons.append("dense or multi-column native layout")
            else:
                route = "NATIVE_SIMPLE"
                reasons.append("healthy native text layer")
            kind = "text" if route in {"NATIVE_SIMPLE", "NATIVE_COMPLEX", "MIXED"} else "image"
            report.append(
                {"page": index, "kind": kind, "route": route, "reasons": reasons,
                 "chars": len(text), "has_image": has_image, "span_count": len(spans),
                 "text_coverage": round(text_area, 6), "unicode_quality": round(quality, 6)}
            )
    return report


def is_scanned_pdf(file_path: str) -> bool:
    """True when NO page has a usable text layer (the whole doc needs OCR)."""
    return all(p["kind"] == "image" for p in classify_pages(file_path))


def extract_pdf_docling(file_path: str) -> list[ExtractedPage]:
    """Layout-aware extraction via Docling (optional tier — `uv sync --group pdf-advanced`).

    For COMPLEX born-digital PDFs where naive text extraction mangles reading order:
    multi-column gazettes, dual-language files, huge consolidated volumes (Round-2
    fixtures). Select with PDF_LAYOUT_ENGINE=docling or extract_pdf(engine=...).
    Never the judged default — PyMuPDF stays the slim path.
    """
    try:
        from docling.document_converter import DocumentConverter
    except ImportError as error:
        raise RuntimeError(
            "Docling not installed — run: uv sync --group pdf-advanced"
        ) from error

    result = DocumentConverter().convert(file_path)
    doc = result.document
    by_page: dict[int, list[str]] = {}
    for item, _level in doc.iterate_items():
        text = getattr(item, "text", "") or ""
        if not text.strip():
            continue
        prov = getattr(item, "prov", None)
        page_no = prov[0].page_no if prov else 1
        by_page.setdefault(page_no, []).append(text)
    return [
        ExtractedPage(
            document_id=file_path,
            page_number=page_no,
            text="\n".join(chunks),
            source_url=f"file://{file_path}",
            location_reference=f"page {page_no}",
            confidence=1.0,
            metadata={"extraction": "docling_layout"},
        )
        for page_no, chunks in sorted(by_page.items())
    ]


def _native_page(file_path: str, page: "fitz.Page", page_number: int, info: dict) -> ExtractedPage:
    raw = page.get_text("rawdict")
    spans = []
    order = 0
    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = "".join(ch.get("c", "") for ch in span.get("chars", []))
                if not text:
                    continue
                spans.append({"text": text, "bbox": list(span["bbox"]), "font": span.get("font"),
                              "size": span.get("size"), "flags": span.get("flags"), "order": order})
                order += 1
    coordinate_spans = sorted(spans, key=lambda s: (round(s["bbox"][1], 1), s["bbox"][0]))
    coordinate_text = "\n".join(s["text"] for s in coordinate_spans)
    return ExtractedPage(
        document_id=file_path,
        page_number=page_number,
        text=page.get_text(),
        source_url=f"file://{file_path}",
        location_reference=f"page {page_number}",
        confidence=1.0,  # native text layer — not an OCR estimate
        metadata={
            "extraction": "native_text",
            "route": info["route"],
            "route_reasons": info["reasons"],
            "quality_signals": {k: info[k] for k in ("chars", "has_image", "span_count", "text_coverage", "unicode_quality")},
            "native_spans": spans,
            "source_order_text": page.get_text(),
            "coordinate_order_text": coordinate_text,
            "searchable_text": coordinate_text,
            "page_width": page.rect.width,
            "page_height": page.rect.height,
            "page_image_sha256": hashlib.sha256(page.get_pixmap(dpi=96).tobytes("png")).hexdigest(),
        },
    )


def _furniture_fingerprint(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"\d+", "#", text)
    return re.sub(r"\s+", " ", text).strip()


def _annotate_repeated_furniture(pages: list[ExtractedPage]) -> list[ExtractedPage]:
    """Detect recurring headers/footers by geometry + cross-page frequency."""
    occurrences: dict[str, set[int]] = {}
    candidates: dict[int, list[tuple[int, str]]] = {}
    for page in pages:
        height = float(page.metadata.get("page_height") or 1)
        for index, span in enumerate(page.metadata.get("native_spans") or []):
            y0, y1 = span["bbox"][1], span["bbox"][3]
            if y0 <= height * .15 or y1 >= height * .74:
                fingerprint = _furniture_fingerprint(span["text"])
                if len(fingerprint) >= 3:
                    occurrences.setdefault(fingerprint, set()).add(page.page_number)
                    candidates.setdefault(page.page_number, []).append((index, fingerprint))
    threshold = max(2, int(len(pages) * .30 + .999))
    repeated = {fp for fp, page_numbers in occurrences.items()
                if len(page_numbers) >= threshold}
    for page in pages:
        furniture_indices = {index for index, fp in candidates.get(page.page_number, [])
                             if fp in repeated}
        page.metadata["repeated_furniture_span_indices"] = sorted(furniture_indices)
        native_spans = page.metadata.get("native_spans") or []
        if not native_spans:
            page.metadata["searchable_text"] = page.text
            continue
        coordinate = sorted(enumerate(native_spans),
                            key=lambda item: (round(item[1]["bbox"][1], 1), item[1]["bbox"][0]))
        page.metadata["searchable_text"] = "\n".join(
            span["text"] for original_index, span in coordinate
            if original_index not in furniture_indices
        )
    return pages


def extract_pdf(file_path: str, ocr_engine=None, engine: str | None = None) -> list[ExtractedPage]:
    """Route each page: native text layer -> PyMuPDF; image-only page -> OCR engine.

    `engine="docling"` (or env PDF_LAYOUT_ENGINE=docling) switches TEXT-layer docs
    to Docling's layout-aware extraction (complex/multi-column/dual-language PDFs);
    scanned pages still go to the OCR engine either way.

    `ocr_engine` may be None for text-only documents; it is REQUIRED (raises
    RuntimeError) only if an image page is actually encountered. A fully
    scanned document is sent to the OCR engine as one whole-PDF call (fast
    path); mixed documents OCR only their image pages, one page at a time.
    """
    import os as _os

    classes = classify_pages(file_path)
    engine = engine or _os.getenv("PDF_LAYOUT_ENGINE", "pymupdf")

    # Fast path 1: every page has a text layer -> never touches OCR.
    if all(p["kind"] == "text" for p in classes):
        if engine == "docling":
            raise RuntimeError(
                "Docling canonical extraction is disabled until a versioned fixture proves "
                "it fixes a mandatory failure and aligns back to PDF spans"
            )
        with fitz.open(file_path) as doc:
            pages = [
                _native_page(file_path, doc[p["page"] - 1], p["page"], p)
                for p in classes
            ]
        return _annotate_repeated_furniture(pages)

    if ocr_engine is None:
        raise RuntimeError(
            f"{Path(file_path).name}: image-only page(s) "
            f"{[p['page'] for p in classes if p['kind'] == 'image']} need OCR, "
            "but no OCR engine was provided."
        )

    # Fast path 2: fully scanned -> one whole-document OCR call.
    if all(p["kind"] == "image" for p in classes):
        pages = ocr_engine.extract(file_path)
        for page in pages:
            page.metadata.setdefault("extraction", "ocr")
        return pages

    # Mixed document: native where text exists, OCR only the image pages.
    ocr_single = getattr(ocr_engine, "ocr_image", None)
    pages: list[ExtractedPage] = []
    with fitz.open(file_path) as doc:
        for info in classes:
            page_number = info["page"]
            page = doc[page_number - 1]
            if info["kind"] == "text":
                pages.append(_native_page(file_path, page, page_number, info))
            elif ocr_single is not None:
                image_bytes = page.get_pixmap(dpi=200).tobytes("png")
                extracted = ocr_single(image_bytes, page_number=page_number, document_id=file_path)
                extracted.metadata.setdefault("extraction", "ocr")
                extracted.metadata.setdefault("route", info["route"])
                for token in extracted.tokens:
                    token.page_number = page_number
                pages.append(extracted)
            else:  # engine without per-image support: degrade to whole-doc OCR for this page set
                raise RuntimeError(
                    "Mixed text/image PDF needs an OCR engine with ocr_image() support."
                )
    return _annotate_repeated_furniture(pages)


def materialize_page_evidence(pages: list[ExtractedPage], source_artifact_id: str
                              ) -> tuple[list[PageArtifact], list[TextSpan]]:
    """Convert canonical native/OCR output into immutable page/span records."""
    page_records: list[PageArtifact] = []
    all_spans: list[TextSpan] = []
    for page in pages:
        spans: list[TextSpan] = []
        cursor = 0
        native = page.metadata.get("native_spans") or []
        if native:
            for order, item in enumerate(native):
                text = item["text"]
                start, end = cursor, cursor + len(text)
                span = TextSpan(
                    id=f"{source_artifact_id}:p{page.page_number}:s{order}",
                    source_artifact_id=source_artifact_id, page_number=page.page_number,
                    text=text, start_char=start, end_char=end, bbox=tuple(item["bbox"]),
                    reading_order=order, extraction_method="pymupdf_rawdict",
                    engine_version=getattr(fitz, "VersionBind", "unknown"),
                )
                spans.append(span); cursor = end + 1
        else:
            for order, token in enumerate(page.tokens):
                if not token.bbox:
                    continue
                text = token.text
                start, end = cursor, cursor + len(text)
                spans.append(TextSpan(
                    id=f"{source_artifact_id}:p{page.page_number}:s{order}",
                    source_artifact_id=source_artifact_id, page_number=page.page_number,
                    text=text, start_char=start, end_char=end, bbox=tuple(token.bbox),
                    reading_order=order, extraction_method=page.metadata.get("ocr_engine", "ocr"),
                    engine_version=str(page.metadata.get("engine_version", "unknown")),
                    confidence=token.confidence,
                ))
                cursor = end + 1
        route = page.metadata.get("route")
        if route not in {"NATIVE_SIMPLE", "NATIVE_COMPLEX", "SCANNED", "MIXED", "REVIEW"}:
            route = "SCANNED" if str(page.metadata.get("extraction", "")).startswith("ocr") else "NATIVE_SIMPLE"
        image_hash = page.metadata.get("page_image_sha256") or hashlib.sha256(
            f"{source_artifact_id}:{page.page_number}:{page.text}".encode()
        ).hexdigest()
        page_records.append(PageArtifact(
            id=f"{source_artifact_id}:p{page.page_number}",
            source_artifact_id=source_artifact_id, page_number=page.page_number,
            width=float(page.metadata.get("page_width") or 1),
            height=float(page.metadata.get("page_height") or 1), route=route,
            route_reasons=list(page.metadata.get("route_reasons") or []),
            raw_text=page.text,
            searchable_text=" ".join(
                str(page.metadata.get("searchable_text") or page.text).split()).lower(),
            page_image_sha256=image_hash, span_ids=[s.id for s in spans],
            quality_signals=dict(page.metadata.get("quality_signals") or {}),
        ))
        all_spans.extend(spans)
    return page_records, all_spans
