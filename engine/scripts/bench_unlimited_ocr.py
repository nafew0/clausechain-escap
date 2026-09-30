"""OCR quality bench: self-hosted Unlimited-OCR vs Google Vision (incumbent).

Three page sets, all sent to the OCR engines as PNG images (the endpoint is
image-only; the engine already rasterizes PDFs page by page):

  native     pages WITH a healthy text layer (Thai, English) rendered to an
             image; reference = the PDF's own text layer -> true CER
  synthetic  pages rendered from known text (th, hi + the final-round scripts we
             hold no documents for: zh, ru, mn, vi, kk, lo) -> true CER
  scans      real image-only pages (Lao sample kit, Thai/India seeds, Pakistan)
             plus Hindi pages whose text layer is garbled; no reference ->
             Unlimited-vs-Vision agreement + saved outputs for inspection

Also records whether Unlimited-OCR returned <|det|> boxes (the audit trail's
CitationProof needs spans with boxes) and per-page latency.

Usage (from engine/):
    .venv/bin/python scripts/bench_unlimited_ocr.py                 # all sets
    .venv/bin/python scripts/bench_unlimited_ocr.py --sets synthetic --no-vision
Config (.env): OCR_BASE_URL, OCR_API_KEY, OCR_MODEL; GOOGLE_VISION_API_KEY optional.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fitz  # noqa: E402
import httpx  # noqa: E402

from packages.core.envfile import load_env_file  # noqa: E402
from packages.extractors.metrics import cer  # noqa: E402

load_env_file()

ENGINE = Path(__file__).resolve().parents[1]
KIT = ENGINE.parent / "Hackthon_Knowledge" / "Sample Kit" / "Sample legislations"
DPI = 200

# (path relative to engine/ or absolute, page number 1-based, language label)
NATIVE_PAGES = [
    # Thai text layers screened 23 Sep: no broken SARA AM ("กำร") and no watermark text.
    ("data/raw/th/seed_0114d241103a.pdf", 3, "th"),
    ("data/raw/th/seed_2c0f2264a27b.pdf", 2, "th"),
    ("data/raw/th/seed_0aa6c5b6dd4e.pdf", 4, "th"),
    ("data/raw/th/seed_38ae790fba5a.pdf", 3, "th"),
    ("data/raw/th/seed_d61140f7f036.pdf", 2, "th"),
    (str(KIT / "General" / "PERSONAL DATA PROTECTION ACT 2010.pdf"), 20, "en"),
    (str(KIT / "General" / "Telecommunications Act 1999.pdf"), 15, "en"),
]

SCAN_PAGES = [
    # Indian Hindi text layers are legacy-font garbled ("जनयम" for "नियम"), so they
    # cannot serve as a reference: scored by Unlimited-vs-Vision agreement instead.
    ("data/raw/in/seed_4abb772a15cf.pdf", 3, "hi"),
    ("data/raw/in/seed_9223b941381e.pdf", 4, "hi"),
    ("data/raw/in/seed_96ff14161fe3.pdf", 2, "hi+en"),
    (str(KIT / "Domestic language only" / "Lao PDR-Law on Electronic Transaction (Amended) No. 31.pdf"), 1, "lo"),
    (str(KIT / "Domestic language only" / "Lao PDR-Law on Electronic Transaction (Amended) No. 31.pdf"), 4, "lo"),
    (str(KIT / "Domestic language only" / "Lao PDR-Law on Electronic Transaction (Amended) No. 31.pdf"), 10, "lo"),
    ("data/raw/th/seed_376c83d5b245.pdf", 3, "th"),
    ("data/raw/th/seed_e2e07d154229.pdf", 2, "th"),
    ("data/raw/in/seed_e918fa508c96.pdf", 2, "hi/en"),
    (str(KIT / "PDF of scanned documents" / "India-Public_Procurement_order_2017.pdf"), 1, "en"),
    (str(KIT / "PDF of scanned documents" / "Pakistan_PECA.pdf"), 1, "en"),
]

FONT_DIR = Path("/System/Library/Fonts")
SUPP = FONT_DIR / "Supplemental"
SYNTHETIC = {
    "th": (SUPP / "Thonburi.ttc" if (SUPP / "Thonburi.ttc").exists() else FONT_DIR / "Thonburi.ttc",
           "พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล พ.ศ. ๒๕๖๒\n"
           "มาตรา ๒๘ ในกรณีที่ผู้ควบคุมข้อมูลส่วนบุคคลส่งหรือโอนข้อมูลส่วนบุคคลไปยังต่างประเทศ "
           "ประเทศปลายทางหรือองค์การระหว่างประเทศที่รับข้อมูลส่วนบุคคลต้องมีมาตรฐานการคุ้มครองข้อมูลส่วนบุคคลที่เพียงพอ\n"
           "มาตรา ๒๙ ในกรณีที่ผู้ควบคุมข้อมูลส่วนบุคคลหรือผู้ประมวลผลข้อมูลส่วนบุคคลซึ่งอยู่ในราชอาณาจักร "
           "ได้กำหนดนโยบายในการคุ้มครองข้อมูลส่วนบุคคลเพื่อการส่งหรือโอนข้อมูลส่วนบุคคล"),
    "hi": (SUPP / "DevanagariMT.ttc",
           "डिजिटल व्यक्तिगत डेटा संरक्षण अधिनियम, 2023\n"
           "धारा 16. भारत के बाहर व्यक्तिगत डेटा का प्रसंस्करण\n"
           "(1) केंद्रीय सरकार, ऐसे कारकों के मूल्यांकन के पश्चात् जिन्हें वह आवश्यक समझे, अधिसूचना द्वारा, "
           "किसी डेटा न्यासी द्वारा भारत के बाहर ऐसे देश या राज्यक्षेत्र को व्यक्तिगत डेटा के अंतरण को निर्बंधित कर सकेगी।\n"
           "(2) इस धारा की कोई बात किसी अन्य विधि के अधीन उच्चतर स्तर के संरक्षण को प्रभावित नहीं करेगी।"),
    "zh": (FONT_DIR / "Hiragino Sans GB.ttc",
           "中华人民共和国个人信息保护法\n第三十八条　个人信息处理者因业务等需要，确需向中华人民共和国境外提供个人信息的，"
           "应当具备下列条件之一：\n（一）依照本法第四十条的规定通过国家网信部门组织的安全评估；\n"
           "（二）按照国家网信部门的规定经专业机构进行个人信息保护认证；\n"
           "（三）按照国家网信部门制定的标准合同与境外接收方订立合同，约定双方的权利和义务。"),
    "ru": (SUPP / "Times New Roman.ttf",
           "Федеральный закон от 27.07.2006 № 152-ФЗ «О персональных данных»\n"
           "Статья 12. Трансграничная передача персональных данных\n"
           "1. Трансграничная передача персональных данных на территории иностранных государств, "
           "являющихся сторонами Конвенции Совета Европы о защите физических лиц при автоматизированной "
           "обработке персональных данных, осуществляется в соответствии с настоящим Федеральным законом.\n"
           "2. Оператор обязан убедиться в том, что иностранным государством обеспечивается адекватная защита прав субъектов."),
    "mn": (SUPP / "Times New Roman.ttf",
           "ХУВЬ ХҮНИЙ МЭДЭЭЛЭЛ ХАМГААЛАХ ТУХАЙ ХУУЛЬ\n"
           "8 дугаар зүйл. Хувь хүний мэдээллийг цуглуулах, боловсруулах, ашиглах\n"
           "8.1. Хувь хүний мэдээллийг цуглуулах, боловсруулах, ашиглахдаа мэдээллийн эзний зөвшөөрлийг авна.\n"
           "8.2. Мэдээллийн эзэн зөвшөөрлөө хэдийд ч цуцлах эрхтэй бөгөөд энэ тухай мэдээлэл хариуцагчид мэдэгдэнэ.\n"
           "8.3. Энэ хуулийн 8.1-д заасан зөвшөөрлийг бичгээр, эсхүл цахим хэлбэрээр авна."),
    "vi": (SUPP / "Times New Roman.ttf",
           "NGHỊ ĐỊNH SỐ 13/2023/NĐ-CP VỀ BẢO VỆ DỮ LIỆU CÁ NHÂN\n"
           "Điều 25. Chuyển dữ liệu cá nhân ra nước ngoài\n"
           "1. Dữ liệu cá nhân của công dân Việt Nam được chuyển ra nước ngoài trong trường hợp Bên Chuyển dữ liệu "
           "lập Hồ sơ đánh giá tác động chuyển dữ liệu cá nhân ra nước ngoài.\n"
           "2. Bên Chuyển dữ liệu lưu giữ Hồ sơ đánh giá tác động để phục vụ hoạt động kiểm tra, đánh giá của Bộ Công an."),
    "kk": (SUPP / "Times New Roman.ttf",
           "Дербес деректер және оларды қорғау туралы Қазақстан Республикасының Заңы\n"
           "16-бап. Дербес деректерді трансшекаралық беру\n"
           "1. Дербес деректерді шет мемлекеттердің аумағына трансшекаралық беру осы Заңның талаптарына сәйкес жүзеге асырылады.\n"
           "2. Дербес деректерді қорғауды қамтамасыз ететін шет мемлекеттердің аумағына трансшекаралық беру "
           "субъектінің келісімімен жүзеге асырылады."),
    "lo": (SUPP / "Lao Sangam MN.ttf",
           "ກົດໝາຍວ່າດ້ວຍການປົກປ້ອງຂໍ້ມູນເອເລັກໂຕຣນິກ\n"
           "ມາດຕາ 12 ການເກັບກຳຂໍ້ມູນສ່ວນບຸກຄົນ\n"
           "ບຸກຄົນ, ນິຕິບຸກຄົນ ຫຼື ການຈັດຕັ້ງ ທີ່ເກັບກຳຂໍ້ມູນສ່ວນບຸກຄົນ ຕ້ອງໄດ້ຮັບການຍິນຍອມຈາກເຈົ້າຂອງຂໍ້ມູນກ່ອນ.\n"
           "ມາດຕາ 13 ການສົ່ງຂໍ້ມູນໄປຕ່າງປະເທດ\n"
           "ການສົ່ງຂໍ້ມູນສ່ວນບຸກຄົນໄປຕ່າງປະເທດ ຕ້ອງປະຕິບັດຕາມລະບຽບການທີ່ກະຊວງກ່ຽວຂ້ອງກຳນົດ."),
}

DET = re.compile(r"<\|det\|>(.*?)<\|/det\|>", re.S)
SPECIAL = re.compile(r"<\|[^|>]{1,40}\|>")
REF = re.compile(r"<\|ref\|>(.*?)<\|/ref\|>", re.S)
MARKUP = re.compile(r"<[^>]{1,80}>|[#*|`_>\-=~]")


def normalize(text: str) -> str:
    """Compare glyph content only: NFKC, drop markdown/HTML furniture and all whitespace."""
    text = unicodedata.normalize("NFKC", text or "")
    text = MARKUP.sub("", text)
    return re.sub(r"\s+", "", text)


def parse_unlimited(raw: str) -> tuple[str, list[dict]]:
    """Split raw model output into plain text + detected boxes.

    Box blocks look like `<|det|>type [x0, y0, x1, y1]<|/det|>` (model card);
    DeepSeek-style `<|ref|>label<|/ref|><|det|>[[...]]<|/det|>` is tolerated too.
    """
    boxes = []
    for match in DET.finditer(raw):
        body = match.group(1)
        numbers = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", body)]
        label = re.sub(r"[\[\]\d.,\s-]+", " ", body).strip()
        boxes.append({"label": label, "coords": numbers[:4], "raw": body[:80]})
    text = DET.sub("", raw)
    text = REF.sub("", text)
    text = SPECIAL.sub("", text)
    return text.strip(), boxes


def render_pdf_page(path: str, page_number: int) -> tuple[bytes, str]:
    with fitz.open(path) as doc:
        page = doc[page_number - 1]
        return page.get_pixmap(dpi=DPI).tobytes("png"), page.get_text()


def render_synthetic(font_path: Path, text: str) -> bytes:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    width, margin, size = 1654, 120, 34          # A4 @ 200 DPI, ~12pt body
    font = ImageFont.truetype(str(font_path), size)
    probe = ImageDraw.Draw(Image.new("L", (10, 10)))
    lines: list[str] = []
    for paragraph in text.split("\n"):
        # wrap by characters so CJK/Lao (no spaces) wrap too
        current = ""
        for ch in paragraph:
            if probe.textlength(current + ch, font=font) > width - 2 * margin:
                cut = current.rfind(" ")
                if cut > len(current) * 0.6:
                    lines.append(current[:cut]); current = current[cut + 1:] + ch
                else:
                    lines.append(current); current = ch
            else:
                current += ch
        lines.append(current)
    line_h = int(size * 1.9)
    img = Image.new("L", (width, margin * 2 + line_h * len(lines)), 255)
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        draw.text((margin, margin + i * line_h), line, font=font, fill=20)
    img = img.rotate(0.4, fillcolor=255, resample=Image.BICUBIC)  # mild scan skew
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    buf = io.BytesIO(); img.save(buf, "PNG")
    return buf.getvalue()


class Unlimited:
    def __init__(self) -> None:
        self.base = os.getenv("OCR_BASE_URL", "").rstrip("/")
        self.model = os.getenv("OCR_MODEL", "unlimited-ocr")
        key = os.getenv("OCR_API_KEY", "")
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        self.client = httpx.Client(timeout=300, headers=headers)

    def ocr(self, png: bytes) -> dict:
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": "<image>document parsing."},
                {"type": "image_url", "image_url": {
                    "url": "data:image/png;base64," + base64.b64encode(png).decode()}},
            ]}],
            "max_tokens": 8192, "temperature": 0.0, "skip_special_tokens": False,
            "vllm_xargs": {"ngram_size": 35, "window_size": 128},
        }
        start = time.time()
        response = self.client.post(f"{self.base}/chat/completions", json=body)
        elapsed = time.time() - start
        if response.status_code == 401:
            raise PermissionError("Unlimited-OCR returned 401 — set OCR_API_KEY in engine/.env")
        response.raise_for_status()
        data = response.json()
        raw = data["choices"][0]["message"]["content"] or ""
        text, boxes = parse_unlimited(raw)
        return {"raw": raw, "text": text, "boxes": boxes, "seconds": round(elapsed, 2),
                "usage": data.get("usage"), "finish_reason": data["choices"][0].get("finish_reason")}


class Vision:
    def __init__(self) -> None:
        self.key = os.getenv("GOOGLE_VISION_API_KEY", "")
        self.client = httpx.Client(timeout=120)

    def ocr(self, png: bytes, hints: list[str]) -> dict:
        body = {"requests": [{"image": {"content": base64.b64encode(png).decode()},
                              "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
                              "imageContext": {"languageHints": hints}}]}
        start = time.time()
        response = self.client.post(
            f"https://vision.googleapis.com/v1/images:annotate?key={self.key}", json=body)
        response.raise_for_status()
        result = response.json()["responses"][0]
        text = (result.get("fullTextAnnotation") or {}).get("text", "")
        return {"text": text, "seconds": round(time.time() - start, 2), "error": result.get("error")}


HINTS = {"th": ["th"], "hi": ["hi"], "hi+en": ["hi", "en"], "hi/en": ["hi", "en"], "en": ["en"],
         "zh": ["zh"], "ru": ["ru"], "mn": ["mn"], "vi": ["vi"], "kk": ["kk"], "lo": ["lo"]}


def build_cases(sets: list[str]) -> list[dict]:
    cases = []
    if "native" in sets:
        for path, page, lang in NATIVE_PAGES:
            full = path if os.path.isabs(path) else str(ENGINE / path)
            if not Path(full).exists():
                print(f"skip missing {path}"); continue
            png, reference = render_pdf_page(full, page)
            cases.append({"set": "native", "lang": lang, "source": Path(full).name, "page": page,
                          "png": png, "reference": reference})
    if "synthetic" in sets:
        for lang, (font, text) in SYNTHETIC.items():
            if not font.exists():
                print(f"skip {lang}: font missing {font}"); continue
            cases.append({"set": "synthetic", "lang": lang, "source": f"synthetic_{lang}", "page": 1,
                          "png": render_synthetic(font, text), "reference": text})
    if "scans" in sets:
        for path, page, lang in SCAN_PAGES:
            full = path if os.path.isabs(path) else str(ENGINE / path)
            if not Path(full).exists():
                print(f"skip missing {path}"); continue
            png, _ = render_pdf_page(full, page)
            cases.append({"set": "scans", "lang": lang, "source": Path(full).name, "page": page,
                          "png": png, "reference": None})
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sets", default="native,synthetic,scans")
    parser.add_argument("--no-vision", action="store_true")
    parser.add_argument("--workers", type=int, default=1,
                        help="concurrent OCR requests; keep low — the self-hosted endpoint is one GPU")
    args = parser.parse_args()

    if not os.getenv("OCR_BASE_URL"):
        raise SystemExit("OCR_BASE_URL is not set in engine/.env")
    unlimited = Unlimited()
    vision = None if args.no_vision or not os.getenv("GOOGLE_VISION_API_KEY") else Vision()
    cases = build_cases(args.sets.split(","))
    out = ENGINE / "reports" / "ocr_bench_unlimited" / datetime.now().strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    print(f"{len(cases)} pages -> {out}  (vision={'on' if vision else 'off'})")

    def run(case: dict) -> dict:
        tag = re.sub(r"[^\w.+-]", "_",
                     f"{case['set']}_{case['lang']}_{Path(case['source']).stem[:40]}_p{case['page']}")
        (out / f"{tag}.png").write_bytes(case["png"])
        row = {k: case[k] for k in ("set", "lang", "source", "page")} | {"tag": tag}
        try:
            u = unlimited.ocr(case["png"])
        except PermissionError:
            raise
        except Exception as exc:  # keep the bench going; record the failure
            u = {"error": repr(exc), "text": "", "raw": "", "boxes": [], "seconds": None}
        (out / f"{tag}.unlimited.raw.txt").write_text(u.get("raw", ""), encoding="utf-8")
        row.update(u_seconds=u.get("seconds"), u_boxes=len(u.get("boxes", [])),
                   u_box_sample=u.get("boxes", [])[:3], u_finish=u.get("finish_reason"),
                   u_error=u.get("error"),
                   u_max_coord=max((c for b in u.get("boxes", []) for c in b["coords"]), default=None))
        v = None
        if vision:
            try:
                v = vision.ocr(case["png"], HINTS.get(case["lang"], []))
            except Exception as exc:
                v = {"text": "", "error": repr(exc)}
            (out / f"{tag}.vision.txt").write_text(v.get("text", ""), encoding="utf-8")
        ref = case["reference"]
        if ref is not None:
            (out / f"{tag}.reference.txt").write_text(ref, encoding="utf-8")
            nref = normalize(ref)
            row["ref_chars"] = len(nref)
            row["u_cer"] = round(cer(nref, normalize(u["text"])), 4) if u.get("text") else 1.0
            if v is not None:
                row["v_cer"] = round(cer(nref, normalize(v["text"])), 4) if v.get("text") else 1.0
        if v is not None and v.get("text") and u.get("text"):
            row["u_vs_v_disagreement"] = round(cer(normalize(v["text"]), normalize(u["text"])), 4)
        print(f"  {tag}: u_cer={row.get('u_cer')} v_cer={row.get('v_cer')} "
              f"boxes={row['u_boxes']} {row['u_seconds']}s {row.get('u_error') or ''}")
        return row

    first, rest = cases[:1], cases[1:]
    rows = [run(c) for c in first]  # fail fast on auth before fanning out
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows += list(pool.map(run, rest))

    (out / "results.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = ["| set | lang | source | page | Unlimited CER | Vision CER | U↔V disagree | boxes | sec |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['set']} | {r['lang']} | {r['source'][:34]} | {r['page']} | {r.get('u_cer', '—')} | "
                     f"{r.get('v_cer', '—')} | {r.get('u_vs_v_disagreement', '—')} | {r['u_boxes']} | {r['u_seconds']} |")
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
