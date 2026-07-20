"""
PaddleOCR API Server — v2.1 (ClauseChain edition)
Location: D:\\paddleocr-server\\server.py   (copy this whole file there)
Run:      uvicorn server:app --host 0.0.0.0 --port 8868

v2.1 changes on top of v2.0 (backward-compatible — old clients keep working):
  - BOUNDING BOXES: every result now carries "boxes": [[x0,y0,x1,y1], ...] aligned
    with texts/scores (from rec_boxes, falling back to rec_polys). ClauseChain uses
    these for precise Location References and highlight-on-page in the audit UI.
  - Per-request language: optional form field `lang` (e.g. "en", "ch", "ru", "th");
    engines are created once per language and cached. Unknown/invalid lang -> 422.
  - /health reports version, loaded languages, and box support.
  - Everything else (auth, limits, validation, logging, PDF mode) unchanged.

Deps: pip install paddleocr fastapi uvicorn pymupdf pillow python-multipart
"""

import io
import logging
import os
import secrets
import tempfile
import threading
import time
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path

import fitz  # PyMuPDF
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from PIL import Image
from paddleocr import PaddleOCR

# ----------------------------------------------------------------------------
# Configuration (override any of these with environment variables)
# ----------------------------------------------------------------------------
API_KEY = os.environ.get("OCR_API_KEY", "CHANGE-ME-long-random-string")
BASE_DIR = Path(os.environ.get("OCR_BASE_DIR", r"D:\paddleocr-server"))
TMP_DIR = BASE_DIR / "tmp"
LOG_DIR = BASE_DIR / "logs"
MAX_BYTES = int(os.environ.get("OCR_MAX_UPLOAD_MB", "50")) * 1024 * 1024
MAX_PDF_PAGES = int(os.environ.get("OCR_MAX_PDF_PAGES", "100"))
PDF_DPI = int(os.environ.get("OCR_PDF_DPI", "200"))
DEFAULT_LANG = os.environ.get("OCR_LANG", "en")
# Languages a request may ask for (comma-separated env override). Engines load lazily.
ALLOWED_LANGS = set(
    filter(None, os.environ.get("OCR_ALLOWED_LANGS", "en,ch,ru,th,korean,japan").split(","))
)
ALLOWED_LANGS.add(DEFAULT_LANG)

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp", ".gif"}
PDF_EXTS = {".pdf"}
ALLOWED_EXTS = IMAGE_EXTS | PDF_EXTS

TMP_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ----------------------------------------------------------------------------
# Logging: console + rotating file (10 MB x 5 files, stays on D:)
# ----------------------------------------------------------------------------
logger = logging.getLogger("ocr-server")
logger.setLevel(logging.INFO)
_fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
_fh = RotatingFileHandler(LOG_DIR / "server.log", maxBytes=10_000_000,
                          backupCount=5, encoding="utf-8")
_fh.setFormatter(_fmt)
_sh = logging.StreamHandler()
_sh.setFormatter(_fmt)
logger.addHandler(_fh)
logger.addHandler(_sh)

# ----------------------------------------------------------------------------
# OCR engines: one per language, created lazily, cached forever.
# A single lock serializes GPU access — PaddleOCR pipelines are not safe for
# concurrent predict() calls, so parallel requests queue here.
# ----------------------------------------------------------------------------
_engines: dict[str, PaddleOCR] = {}
_engines_guard = threading.Lock()
ocr_lock = threading.Lock()


def get_engine(lang: str) -> PaddleOCR:
    if lang not in ALLOWED_LANGS:
        raise HTTPException(
            status_code=422,
            detail=f"Language '{lang}' not enabled. Allowed: {', '.join(sorted(ALLOWED_LANGS))}",
        )
    with _engines_guard:
        if lang not in _engines:
            logger.info("Loading PaddleOCR pipeline (lang=%s)...", lang)
            _engines[lang] = PaddleOCR(lang=lang)
            logger.info("PaddleOCR pipeline ready (lang=%s).", lang)
        return _engines[lang]


get_engine(DEFAULT_LANG)  # preload the default so the first request isn't slow

app = FastAPI(title="PaddleOCR Service", version="2.1")


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def check_api_key(x_api_key: str | None) -> None:
    if not secrets.compare_digest(x_api_key or "", API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")


def _to_list(value):
    return value.tolist() if hasattr(value, "tolist") else value


def _extract_boxes(j: dict) -> list[list[float]]:
    """Return [[x0,y0,x1,y1], ...] aligned with rec_texts.

    Prefers rec_boxes (already rectangles in PaddleOCR 3.x); falls back to
    rec_polys / dt_polys (4-point polygons -> bounding rectangle).
    """
    rec_boxes = j.get("rec_boxes")
    if rec_boxes is not None and len(rec_boxes) > 0:
        out = []
        for box in rec_boxes:
            vals = [float(v) for v in _to_list(box)]
            out.append([round(v, 1) for v in vals[:4]])
        return out
    polys = j.get("rec_polys")
    if polys is None or len(polys) == 0:
        polys = j.get("dt_polys") or []
    out = []
    for poly in polys:
        pts = _to_list(poly)
        try:
            xs = [float(p[0]) for p in pts]
            ys = [float(p[1]) for p in pts]
            out.append([round(min(xs), 1), round(min(ys), 1),
                        round(max(xs), 1), round(max(ys), 1)])
        except Exception:
            out.append(None)
    return out


def run_ocr_on_image_file(path: str, lang: str) -> list[dict]:
    """Run the pipeline on a single image file. Serialized by ocr_lock."""
    engine = get_engine(lang)
    with ocr_lock:
        result = engine.predict(path)
    out = []
    for res in result:
        j = res.json["res"]
        texts = list(j.get("rec_texts", []))
        scores = [round(float(s), 4) for s in j.get("rec_scores", [])]
        boxes = _extract_boxes(j)
        # keep the three lists aligned even if boxes came back short
        if len(boxes) < len(texts):
            boxes = boxes + [None] * (len(texts) - len(boxes))
        out.append({"texts": texts, "scores": scores, "boxes": boxes[: len(texts)]})
    return out


def validate_image_bytes(data: bytes) -> None:
    """Reject corrupt or masquerading image files before they reach the GPU."""
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()
    except Exception:
        raise HTTPException(status_code=422,
                            detail="File is not a valid or readable image")


def save_temp(data: bytes, suffix: str) -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix,
                                     dir=str(TMP_DIR)) as tmp:
        tmp.write(data)
        return tmp.name


def cleanup(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


# ----------------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------------
@app.post("/ocr")
async def run_ocr(
    file: UploadFile = File(...),
    lang: str = Form(None),
    x_api_key: str = Header(None),
):
    check_api_key(x_api_key)
    req_id = uuid.uuid4().hex[:8]
    t0 = time.time()
    lang = (lang or DEFAULT_LANG).strip().lower()

    filename = file.filename or "upload"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{ext}'. "
                   f"Allowed: {', '.join(sorted(ALLOWED_EXTS))}",
        )

    data = await file.read()
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(data) // 1024 // 1024} MB). "
                   f"Limit is {MAX_BYTES // 1024 // 1024} MB.",
        )

    logger.info("[%s] %s (%d KB, %s, lang=%s)", req_id, filename,
                len(data) // 1024, ext, lang)

    try:
        if ext in PDF_EXTS:
            response = process_pdf(data, req_id, lang)
        else:
            validate_image_bytes(data)
            tmp_path = save_temp(data, ext)
            try:
                response = {"type": "image",
                            "results": run_ocr_on_image_file(tmp_path, lang)}
            finally:
                cleanup(tmp_path)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[%s] OCR failed: %s", req_id, e)
        raise HTTPException(status_code=500, detail="OCR processing failed")

    elapsed = round(time.time() - t0, 2)
    response["request_id"] = req_id
    response["seconds"] = elapsed
    response["lang"] = lang
    logger.info("[%s] done in %.2fs", req_id, elapsed)
    return response


def process_pdf(data: bytes, req_id: str, lang: str) -> dict:
    """Rasterize each PDF page and OCR it. Returns per-page results."""
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid or corrupt PDF")

    if doc.is_encrypted:
        doc.close()
        raise HTTPException(status_code=422, detail="Encrypted PDFs are not supported")

    n_pages = doc.page_count
    if n_pages > MAX_PDF_PAGES:
        doc.close()
        raise HTTPException(
            status_code=413,
            detail=f"PDF has {n_pages} pages; limit is {MAX_PDF_PAGES}.",
        )

    pages = []
    try:
        for page_num in range(n_pages):
            page = doc.load_page(page_num)
            pix = page.get_pixmap(dpi=PDF_DPI)
            tmp_path = save_temp(pix.tobytes("png"), ".png")
            try:
                results = run_ocr_on_image_file(tmp_path, lang)
            finally:
                cleanup(tmp_path)
            pages.append({"page": page_num + 1, "results": results,
                          "dpi": PDF_DPI})
            logger.info("[%s] page %d/%d done", req_id, page_num + 1, n_pages)
    finally:
        doc.close()

    return {"type": "pdf", "page_count": n_pages, "pages": pages}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": "2.1",
        "default_lang": DEFAULT_LANG,
        "loaded_langs": sorted(_engines.keys()),
        "allowed_langs": sorted(ALLOWED_LANGS),
        "boxes": True,
        "max_upload_mb": MAX_BYTES // 1024 // 1024,
        "max_pdf_pages": MAX_PDF_PAGES,
        "allowed_types": sorted(ALLOWED_EXTS),
    }
