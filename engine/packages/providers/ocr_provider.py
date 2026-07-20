from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Iterator

import httpx

from packages.core.schemas import ExtractedPage, OCRToken

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


def _tesseract_lines(data: dict) -> str:
    """Reconstruct reading lines from Tesseract's layout identifiers."""
    lines: dict[tuple[int, int, int], list[str]] = {}
    order: list[tuple[int, int, int]] = []
    for index, raw in enumerate(data.get("text", [])):
        word = str(raw).strip()
        if not word:
            continue
        key = tuple(int(data.get(name, [0] * len(data["text"]))[index])
                    for name in ("block_num", "par_num", "line_num"))
        if key not in lines:
            lines[key] = []
            order.append(key)
        lines[key].append(word)
    return "\n".join(" ".join(lines[key]) for key in order)


class LocalOCRPlaceholder:
    """P0 local OCR placeholder. It treats text files as already extracted text."""

    def extract(self, file_path: str) -> list[ExtractedPage]:
        return [
            ExtractedPage(
                document_id=file_path,
                page_number=1,
                text="",
                source_url=f"file://{file_path}",
                location_reference="local file page 1",
                confidence=None,
            )
        ]


class TesseractOCR:
    """Local OCR fallback preserving token boxes and page numbers."""

    def ocr_image(self, image_bytes: bytes, page_number: int = 1,
                  document_id: str = "image") -> ExtractedPage:
        import io
        import pytesseract
        from PIL import Image

        image = Image.open(io.BytesIO(image_bytes))
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        tokens = []
        for i, raw in enumerate(data.get("text", [])):
            text = str(raw).strip()
            if not text:
                continue
            confidence = float(data["conf"][i])
            confidence = confidence / 100 if confidence >= 0 else None
            x, y, w, h = (float(data[k][i]) for k in ("left", "top", "width", "height"))
            tokens.append(OCRToken(text=text, confidence=confidence,
                                   bbox=[x, y, x + w, y + h], page_number=page_number))
        confidences = [t.confidence for t in tokens if t.confidence is not None]
        return ExtractedPage(document_id=document_id, page_number=page_number,
            text=_tesseract_lines(data), source_url=f"file://{document_id}",
            location_reference=f"page {page_number}",
            confidence=sum(confidences) / len(confidences) if confidences else None,
            tokens=tokens, metadata={"ocr_engine": "tesseract", "engine_version": str(pytesseract.get_tesseract_version())})

    def extract(self, file_path: str) -> list[ExtractedPage]:
        return [self.ocr_image(image, page_no, file_path)
                for page_no, image in _rasterize(file_path)]


def _rasterize(file_path: str, dpi: int = 200) -> Iterator[tuple[int, bytes]]:
    """Yield (page_number, PNG bytes) for a PDF, or the raw bytes for an image file."""
    path = Path(file_path)
    if path.suffix.lower() in IMAGE_SUFFIXES:
        yield 1, path.read_bytes()
        return
    import fitz  # PyMuPDF — already a core dependency

    with fitz.open(file_path) as doc:
        for index, page in enumerate(doc, start=1):
            yield index, page.get_pixmap(dpi=dpi).tobytes("png")


def _region_to_bbox(region) -> list[float] | None:
    """Accept [[x,y] x4] polygons or flat [x0,y0,x1,y1] boxes."""
    try:
        if not region:
            return None
        if isinstance(region[0], (list, tuple)):
            xs = [float(pt[0]) for pt in region]
            ys = [float(pt[1]) for pt in region]
            return [min(xs), min(ys), max(xs), max(ys)]
        return [float(v) for v in region][:4]
    except Exception:
        return None


def _parse_ocr_response(data: dict) -> tuple[str, float | None, list[OCRToken]]:
    """Tolerate both our micro-server schema and PaddleHub/PaddleServing-style responses."""
    if "tokens" in data:  # scripts/paddle_ocr_server.py schema
        tokens = [OCRToken(**token) for token in data.get("tokens", [])]
        return data.get("text", ""), data.get("confidence"), tokens

    results = data.get("results") or data.get("data") or data.get("result") or []

    # User's FastAPI PaddleOCR service: {"results": [{"texts": [...], "scores": [...]}]}
    if isinstance(results, list) and results and isinstance(results[0], dict) and "texts" in results[0]:
        tokens = []
        for res in results:
            texts = res.get("texts") or []
            scores = res.get("scores") or []
            boxes = res.get("boxes") or res.get("polys") or res.get("text_regions") or []
            for index, text in enumerate(texts):
                confidence = scores[index] if index < len(scores) else None
                bbox = _region_to_bbox(boxes[index]) if index < len(boxes) else None
                tokens.append(
                    OCRToken(
                        text=str(text),
                        confidence=float(confidence) if confidence is not None else None,
                        bbox=bbox,
                    )
                )
        confidences = [t.confidence for t in tokens if t.confidence is not None]
        mean_conf = sum(confidences) / len(confidences) if confidences else None
        return "\n".join(t.text for t in tokens), mean_conf, tokens

    flat: list[dict] = []
    stack = [results]
    while stack:
        item = stack.pop(0)
        if isinstance(item, dict):
            flat.append(item)
        elif isinstance(item, list):
            stack = list(item) + stack
    tokens = []
    for item in flat:
        text = item.get("text") or item.get("rec_text") or ""
        if not text:
            continue
        confidence = item.get("confidence", item.get("score"))
        bbox = _region_to_bbox(item.get("text_region") or item.get("box") or item.get("bbox"))
        tokens.append(
            OCRToken(
                text=str(text),
                confidence=float(confidence) if confidence is not None else None,
                bbox=bbox,
            )
        )
    confidences = [t.confidence for t in tokens if t.confidence is not None]
    mean_conf = sum(confidences) / len(confidences) if confidences else None
    return "\n".join(t.text for t in tokens), mean_conf, tokens


class RemotePaddleOCR:
    """OCREngine impl that calls a PaddleOCR HTTP service on a separate machine/VM.

    PDFs are rasterized locally (PyMuPDF) and sent one page-image per request.
    `endpoint` may be a base URL (``http://host:8868``) or the full OCR route
    (``http://host:8868/ocr``). If `api_key` is set it is sent as both
    ``Authorization: Bearer`` and ``X-API-Key`` headers.
    """

    def __init__(
        self,
        endpoint: str,
        api_key: str | None = None,
        timeout: float = 600.0,
        dpi: int = 200,
        request_format: str = "multipart",
        send_pdf: bool = True,
        lang: str | None = None,
        transport: httpx.BaseTransport | None = None,
        engine_name: str = "remote_paddle",
    ) -> None:
        self._request_format = request_format
        self._send_pdf = send_pdf      # upload whole PDFs (server v2.0+ rasterizes them)
        self._lang = lang              # optional per-request language (server v2.1+)
        endpoint = endpoint.rstrip("/")
        if endpoint.endswith("/ocr") or "/predict/" in endpoint:
            self._ocr_url = endpoint
            self._base = endpoint.rsplit("/", 1)[0]
        else:
            self._ocr_url = f"{endpoint}/ocr"
            self._base = endpoint
        self._endpoint = self._base  # kept for logging/metadata
        self._dpi = dpi
        self._engine_name = engine_name
        headers = {}
        if api_key:
            headers = {"Authorization": f"Bearer {api_key}", "X-API-Key": api_key}
        self._client = httpx.Client(timeout=timeout, transport=transport, headers=headers)

    def health(self) -> bool:
        for url in (f"{self._base}/health", self._base):
            try:
                if self._client.get(url).status_code < 500:
                    return True
            except httpx.HTTPError:
                continue
        return False

    def _form_data(self) -> dict | None:
        return {"lang": self._lang} if self._lang else None

    def _page_from(self, file_path: str, page_number: int, data: dict) -> ExtractedPage:
        text, confidence, tokens = _parse_ocr_response(data)
        for token in tokens:
            token.page_number = page_number
        return ExtractedPage(
            document_id=file_path,
            page_number=page_number,
            text=text,
            source_url=f"file://{file_path}",
            location_reference=f"page {page_number}",
            confidence=confidence,
            tokens=tokens,
            metadata={"ocr_engine": self._engine_name, "endpoint": self._ocr_url},
        )

    def ocr_image(
        self, image_bytes: bytes, page_number: int = 1, document_id: str = "image"
    ) -> ExtractedPage:
        """OCR one page image (used by the PDF router for the scanned pages of MIXED docs)."""
        if self._request_format == "multipart":
            response = self._client.post(
                self._ocr_url,
                files={"file": (f"page{page_number}.png", image_bytes, "image/png")},
                data=self._form_data(),
            )
        else:
            encoded = base64.b64encode(image_bytes).decode("ascii")
            response = self._client.post(
                self._ocr_url, json={"image_b64": encoded, "images": [encoded]}
            )
        response.raise_for_status()
        return self._page_from(document_id, page_number, response.json())

    def extract(self, file_path: str) -> list[ExtractedPage]:
        path = Path(file_path)
        is_pdf = path.suffix.lower() == ".pdf"

        # Preferred: upload the whole PDF once — the server rasterizes + OCRs per page.
        if self._request_format == "multipart" and is_pdf and self._send_pdf:
            response = self._client.post(
                self._ocr_url,
                files={"file": (path.name, path.read_bytes(), "application/pdf")},
                data=self._form_data(),
            )
            if response.status_code not in (413, 415):  # too big / not supported -> fallback
                response.raise_for_status()
                data = response.json()
                if data.get("type") == "pdf" and "pages" in data:
                    return [
                        self._page_from(file_path, page.get("page", i + 1),
                                        {"results": page.get("results", [])})
                        for i, page in enumerate(data["pages"])
                    ]
                return [self._page_from(file_path, 1, data)]

        # Fallback / images: rasterize locally, one page-image per request.
        pages: list[ExtractedPage] = []
        for page_number, image_bytes in _rasterize(file_path, dpi=self._dpi):
            if self._request_format == "multipart":
                response = self._client.post(
                    self._ocr_url,
                    files={"file": (f"page{page_number}.png", image_bytes, "image/png")},
                    data=self._form_data(),
                )
            else:  # json_b64 — PaddleHub-style servers
                encoded = base64.b64encode(image_bytes).decode("ascii")
                response = self._client.post(
                    self._ocr_url, json={"image_b64": encoded, "images": [encoded]}
                )
            response.raise_for_status()
            pages.append(self._page_from(file_path, page_number, response.json()))
        return pages


class FallbackRemotePaddleOCR(RemotePaddleOCR):
    """Paddle primary with boxed Tesseract fallback and citation-token comparison."""

    def __init__(self, *args, fallback=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._fallback = fallback or TesseractOCR()

    def extract(self, file_path: str) -> list[ExtractedPage]:
        from packages.extractors.metrics import citation_tokens_disagree
        try:
            primary = super().extract(file_path)
        except (httpx.HTTPError, OSError):
            pages = self._fallback.extract(file_path)
            for page in pages:
                page.metadata["ocr_fallback_reason"] = "Paddle unavailable"
            return pages
        if os.getenv("OCR_VERIFY_CROSS_ENGINE", "1") != "1":
            return primary
        secondary = self._fallback.extract(file_path)
        by_page = {p.page_number: p for p in secondary}
        for page in primary:
            other = by_page.get(page.page_number)
            page.metadata["citation_token_disagreement"] = bool(
                other and citation_tokens_disagree(page.text, other.text))
            page.metadata["cross_engine"] = "tesseract"
        return primary

    def ocr_image(self, image_bytes: bytes, page_number: int = 1,
                  document_id: str = "image") -> ExtractedPage:
        from packages.extractors.metrics import citation_tokens_disagree
        try:
            primary = super().ocr_image(image_bytes, page_number, document_id)
        except (httpx.HTTPError, OSError):
            fallback = self._fallback.ocr_image(image_bytes, page_number, document_id)
            fallback.metadata["ocr_fallback_reason"] = "Paddle unavailable"
            return fallback
        if os.getenv("OCR_VERIFY_CROSS_ENGINE", "1") == "1":
            other = self._fallback.ocr_image(image_bytes, page_number, document_id)
            primary.metadata["citation_token_disagreement"] = citation_tokens_disagree(
                primary.text, other.text)
            primary.metadata["cross_engine"] = "tesseract"
        return primary


class PaddleVLCascade:
    """Scanned-page route: PaddleOCR-VL -> PaddleOCR -> Tesseract.

    The VL response is accepted as canonical OCR only when it preserves token
    boxes. Text-only/Markdown VL output remains useful diagnostically but cannot
    create CitationProof, so the deterministic OCR fallback is used instead.
    """

    def __init__(self, vl: RemotePaddleOCR, fallback: FallbackRemotePaddleOCR):
        self._vl = vl
        self._fallback = fallback

    @staticmethod
    def _proof_capable(pages: list[ExtractedPage]) -> bool:
        return bool(pages) and all(
            page.text.strip() and page.tokens
            and all(token.bbox is not None for token in page.tokens)
            for page in pages
        )

    def extract(self, file_path: str) -> list[ExtractedPage]:
        try:
            pages = self._vl.extract(file_path)
            if not self._proof_capable(pages):
                raise ValueError("PaddleOCR-VL response lacks citation-capable token boxes")
            return pages
        except (httpx.HTTPError, OSError, ValueError):
            pages = self._fallback.extract(file_path)
            for page in pages:
                page.metadata["ocr_fallback_reason"] = "PaddleOCR-VL unavailable or proof-incomplete"
            return pages

    def ocr_image(self, image_bytes: bytes, page_number: int = 1,
                  document_id: str = "image") -> ExtractedPage:
        try:
            page = self._vl.ocr_image(image_bytes, page_number, document_id)
            if not self._proof_capable([page]):
                raise ValueError("PaddleOCR-VL response lacks citation-capable token boxes")
            return page
        except (httpx.HTTPError, OSError, ValueError):
            page = self._fallback.ocr_image(image_bytes, page_number, document_id)
            page.metadata["ocr_fallback_reason"] = (
                "PaddleOCR-VL unavailable or proof-incomplete"
            )
            return page

def build_ocr(config: dict | None):
    """Factory keyed on the profile's ocr.provider (models.yaml) — the config-only swap."""
    config = config or {}
    provider = str(config.get("provider", "local")).strip().lower()
    if provider in {"tesseract", "local_tesseract"}:
        return TesseractOCR()
    if provider in {"remote_paddle", "paddle_remote", "remote"}:
        endpoint = config.get("endpoint") or os.getenv("OCR_ENDPOINT", "http://localhost:8089")
        api_key = config.get("api_key") or os.getenv("OCR_API_KEY") or None
        request_format = (
            config.get("request_format") or os.getenv("OCR_REQUEST_FORMAT") or "multipart"
        )
        lang = config.get("lang") or os.getenv("OCR_LANG") or None
        standard = FallbackRemotePaddleOCR(
            endpoint, api_key=api_key, request_format=request_format, lang=lang
        )
        vl_endpoint = config.get("vl_endpoint") or os.getenv("OCR_VL_ENDPOINT")
        if vl_endpoint:
            vl_request_format = (
                config.get("vl_request_format") or
                os.getenv("OCR_VL_REQUEST_FORMAT") or request_format
            )
            vl = RemotePaddleOCR(
                vl_endpoint, api_key=(config.get("vl_api_key") or
                                      os.getenv("OCR_VL_API_KEY") or api_key),
                request_format=vl_request_format, lang=lang,
                engine_name="remote_paddle_vl",
            )
            return PaddleVLCascade(vl, standard)
        return standard
    return LocalOCRPlaceholder()
