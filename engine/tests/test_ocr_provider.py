from __future__ import annotations

import base64
import json

import httpx

from packages.core.schemas import ExtractedPage, OCRToken
from packages.providers.ocr_provider import (FallbackRemotePaddleOCR, LocalOCRPlaceholder,
                                             PaddleVLCascade, RemotePaddleOCR, TesseractOCR,
                                             build_ocr)


CANNED = {
    "text": "An organisation shall not transfer\npersonal data",
    "confidence": 0.94,
    "tokens": [
        {"text": "An organisation shall not transfer", "confidence": 0.95, "bbox": [10.0, 10.0, 400.0, 30.0]},
        {"text": "personal data", "confidence": 0.93, "bbox": [10.0, 34.0, 150.0, 54.0]},
    ],
}


def _mock_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ocr"
        payload = json.loads(request.content)
        assert base64.b64decode(payload["image_b64"]) == b"fake-png-bytes"
        return httpx.Response(200, json=CANNED)

    return httpx.MockTransport(handler)


def test_remote_paddle_ocr_parses_pages_and_tokens(tmp_path):
    image = tmp_path / "scan.png"
    image.write_bytes(b"fake-png-bytes")

    engine = RemotePaddleOCR(
        "http://ocr-vm:8089", request_format="json_b64", transport=_mock_transport()
    )
    pages = engine.extract(str(image))

    assert len(pages) == 1
    page = pages[0]
    assert page.page_number == 1
    assert page.confidence == 0.94
    assert "shall not transfer" in page.text
    assert len(page.tokens) == 2
    assert page.tokens[0].bbox == [10.0, 10.0, 400.0, 30.0]
    assert page.tokens[0].page_number == 1
    assert page.metadata["ocr_engine"] == "remote_paddle"


def test_remote_paddle_ocr_multipart_texts_scores_and_auth(tmp_path):
    """The real VM contract: multipart `file` upload, api-key headers, {"results":[{"texts","scores"}]}."""
    image = tmp_path / "scan.png"
    image.write_bytes(b"fake-png-bytes")
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("Authorization")
        seen["x_api_key"] = request.headers.get("X-API-Key")
        seen["content_type"] = request.headers.get("Content-Type", "")
        assert b"fake-png-bytes" in request.read()  # the image travelled as a file part
        return httpx.Response(
            200,
            json={"results": [{"texts": ["Section 26(1)", "shall not transfer"], "scores": [0.91, 0.89]}]},
        )

    engine = RemotePaddleOCR(
        "http://ocr-vm:8868/ocr", api_key="secret-key", transport=httpx.MockTransport(handler)
    )
    pages = engine.extract(str(image))

    assert seen["path"] == "/ocr"  # endpoint with path is not doubled to /ocr/ocr
    assert seen["content_type"].startswith("multipart/form-data")
    assert seen["auth"] == "Bearer secret-key"
    assert seen["x_api_key"] == "secret-key"
    page = pages[0]
    assert page.text == "Section 26(1)\nshall not transfer"
    assert page.tokens[0].confidence == 0.91 and page.tokens[0].bbox is None
    assert page.confidence == (0.91 + 0.89) / 2


def test_remote_paddle_ocr_whole_pdf_upload_with_boxes(tmp_path):
    """Server v2.0+ PDF mode: one upload -> per-page results; v2.1 boxes populate token bboxes."""
    pdf = tmp_path / "gazette.pdf"
    pdf.write_bytes(b"%PDF-fake-bytes")  # never rasterized locally — sent as-is
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        seen["is_pdf_upload"] = b"%PDF-fake-bytes" in body and b"application/pdf" in body
        seen["lang_field"] = b'name="lang"' in body
        return httpx.Response(
            200,
            json={
                "type": "pdf",
                "page_count": 2,
                "pages": [
                    {"page": 1, "results": [{"texts": ["Akta 709"], "scores": [0.97],
                                             "boxes": [[10.0, 20.0, 90.0, 40.0]]}]},
                    {"page": 2, "results": [{"texts": ["Seksyen 129"], "scores": [0.95],
                                             "boxes": [[12.0, 22.0, 95.0, 44.0]]}]},
                ],
            },
        )

    engine = RemotePaddleOCR(
        "http://ocr-vm:8868/ocr", api_key="k", lang="en", transport=httpx.MockTransport(handler)
    )
    pages = engine.extract(str(pdf))

    assert seen["is_pdf_upload"] and seen["lang_field"]
    assert [p.page_number for p in pages] == [1, 2]
    assert pages[0].text == "Akta 709"
    assert pages[0].tokens[0].bbox == [10.0, 20.0, 90.0, 40.0]
    assert pages[1].confidence == 0.95


def test_parse_paddlehub_nested_results():
    from packages.providers.ocr_provider import _parse_ocr_response

    text, confidence, tokens = _parse_ocr_response(
        {"results": [[{"text": "s. 26(1)", "confidence": 0.9,
                       "text_region": [[5, 5], [100, 5], [100, 20], [5, 20]]}]]}
    )
    assert text == "s. 26(1)" and confidence == 0.9
    assert tokens[0].bbox == [5.0, 5.0, 100.0, 20.0]


def test_build_ocr_selects_by_provider(monkeypatch):
    monkeypatch.setenv("OCR_ENDPOINT", "http://ocr-vm:8089")
    assert isinstance(build_ocr({"provider": "local"}), LocalOCRPlaceholder)
    assert isinstance(build_ocr(None), LocalOCRPlaceholder)
    remote = build_ocr({"provider": "remote_paddle"})
    assert isinstance(remote, RemotePaddleOCR)
    remote_explicit = build_ocr({"provider": "remote_paddle", "endpoint": "http://other:9000/"})
    assert remote_explicit._endpoint == "http://other:9000"
    assert isinstance(build_ocr({"provider": "tesseract"}), TesseractOCR)
    monkeypatch.setenv("OCR_VL_ENDPOINT", "http://ocr-vl:9000")
    assert isinstance(build_ocr({"provider": "remote_paddle"}), PaddleVLCascade)


def test_vl_text_without_boxes_falls_back_to_proof_capable_ocr():
    class VL:
        def extract(self, path):
            return [ExtractedPage(
                document_id=path, page_number=1, text="s. 26(1)",
                source_url=f"file://{path}", location_reference="page 1",
                tokens=[OCRToken(text="s. 26(1)", confidence=.9, bbox=None)],
            )]
    fallback = _FallbackSpy("s. 26(1)")
    pages = PaddleVLCascade(VL(), fallback).extract("scan.pdf")
    assert fallback.calls == 1
    assert pages[0].tokens[0].bbox == [1.0, 2.0, 3.0, 4.0]


class _FallbackSpy:
    def __init__(self, text="s. 26(1)"): self.text = text; self.calls = 0
    def extract(self, file_path):
        self.calls += 1
        return [ExtractedPage(document_id=file_path, page_number=1, text=self.text,
            source_url=f"file://{file_path}", location_reference="page 1", confidence=.8,
            tokens=[OCRToken(text=self.text, confidence=.8, bbox=[1, 2, 3, 4], page_number=1)],
            metadata={"ocr_engine": "tesseract"})]


def test_remote_failure_uses_boxed_tesseract_fallback(tmp_path):
    image = tmp_path / "scan.png"; image.write_bytes(b"image")
    def fail(_request): raise httpx.ConnectError("offline")
    fallback = _FallbackSpy()
    engine = FallbackRemotePaddleOCR("http://ocr-vm", request_format="json_b64",
        transport=httpx.MockTransport(fail), fallback=fallback)
    pages = engine.extract(str(image))
    assert fallback.calls == 1 and pages[0].tokens[0].bbox
    assert pages[0].metadata["ocr_fallback_reason"] == "Paddle unavailable"


def test_cross_engine_citation_disagreement_is_flagged(tmp_path, monkeypatch):
    image = tmp_path / "scan.png"; image.write_bytes(b"fake-png-bytes")
    fallback = _FallbackSpy("s. 28(1)")
    engine = FallbackRemotePaddleOCR("http://ocr-vm", request_format="json_b64",
        transport=_mock_transport(), fallback=fallback)
    monkeypatch.setenv("OCR_VERIFY_CROSS_ENGINE", "1")
    pages = engine.extract(str(image))
    assert pages[0].metadata["citation_token_disagreement"] is True


def test_true_ocr_metrics_are_gold_based_not_confidence():
    from packages.extractors.metrics import (cer, citation_token_accuracy,
                                             section_structure_accuracy, wer)
    assert cer("section 26", "section 26") == 0
    assert wer("one two", "one three") == .5
    assert citation_token_accuracy("s. 26(1)", "s. 28(1)") < 1
    assert section_structure_accuracy([["section 26"]], [["section 26"]]) == 1
