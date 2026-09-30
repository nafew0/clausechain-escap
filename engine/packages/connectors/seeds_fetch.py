"""Seeds-driven fetcher: download the ESCAP Legal Inventory's actual documents.

Reads data/seeds.json (384 acts with official URLs; MY = 146, 107 direct PDFs),
downloads each politely, archives bytes + sha256 + access date, and records
dead links (which feed the Malaysia error-audit — a broken URL in ESCAP's own
inventory is exactly the planted-error class we must catch).

Cache policy: a URL fetched successfully once is never refetched (act PDFs are
static); dead links are retried on each run.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import os

from packages.core import progress

_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/125.0 Safari/537.36 ClauseChain-research/0.1"),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
}
POLITE_DELAY_S = 3.0
ECON_CC = {"Singapore": "sg", "Malaysia": "my", "Australia": "au",
           # Round 2 — seeds live in data/seeds_r2.json (pass seeds_path)
           "Thailand": "th", "India": "in", "Indonesia": "id",
           "Russian Federation": "ru", "Mongolia": "mn", "Lao PDR": "la",
           "Timor-Leste": "tl"}

# Superscript digits for inserted articles ("Статья 18¹"): rendered as Unicode
# superscripts so the text layer keeps "18¹" instead of merging to "181". Covers
# <sup> and styled spans (pravo.gov.ru prints them as <span class="W9"> with
# vertical-align: top) — any digit-only leaf the browser draws raised.
_SUP_TO_UNICODE_JS = """() => {
  const map = {'0':'⁰','1':'¹','2':'²','3':'³','4':'⁴',
               '5':'⁵','6':'⁶','7':'⁷','8':'⁸','9':'⁹'};
  const raised = el => el.tagName === 'SUP' ||
    ['super', 'top', 'text-top'].includes(getComputedStyle(el).verticalAlign);
  let n = 0;
  for (const el of Array.from(document.querySelectorAll('sup, span, font'))) {
    const t = (el.textContent || '').trim();
    if (el.children.length === 0 && /^[0-9]{1,3}$/.test(t) && raised(el)) {
      el.replaceWith(document.createTextNode(t.replace(/[0-9]/g, d => map[d])));
      n += 1;
    }
  }
  return n;
}"""


def _chromium_executable() -> str | None:
    """Browser for Playwright: CLAUSECHAIN_CHROMIUM overrides; otherwise None
    (Playwright's own build). _launch_chromium falls back to the newest
    headless shell in the ms-playwright cache when the pinned build is absent."""
    return os.getenv("CLAUSECHAIN_CHROMIUM") or None


def _launch_chromium(p):
    executable = _chromium_executable()
    try:
        return p.chromium.launch(headless=True, executable_path=executable)
    except Exception:  # noqa: BLE001 — pinned build missing: try any cached shell
        cache = Path.home() / "Library/Caches/ms-playwright"
        if not cache.is_dir():
            cache = Path.home() / ".cache/ms-playwright"
        shells = sorted(cache.glob("chromium_headless_shell-*/*/chrome-headless-shell"))
        if not shells:
            raise
        return p.chromium.launch(headless=True, executable_path=str(shells[-1]))


def _aia_verified_get(url: str) -> httpx.Response | None:
    """Fetch from a host that omits its intermediate certificate (verified 29 Sep:
    www.bol.gov.la sends only its leaf). Like a browser, read the leaf's AIA
    caIssuers URL, download that intermediate, and verify the full chain against
    certifi's roots — verification stays on; nothing is trusted that a browser
    would not trust."""
    import ssl
    import tempfile
    from urllib.parse import urlsplit

    import certifi

    parts = urlsplit(url)
    try:
        leaf = ssl.get_server_certificate((parts.hostname, parts.port or 443), timeout=30)
        with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as handle:
            handle.write(leaf)
        decoded = ssl._ssl._test_decode_cert(handle.name)  # stdlib cert parser (no deps)
        Path(handle.name).unlink(missing_ok=True)
        issuers = [u for u in decoded.get("caIssuers") or () if u.startswith("http")]
        if not issuers:
            return None
        der = httpx.get(issuers[0], timeout=30, follow_redirects=True).content
        pem = der.decode() if der.startswith(b"-----") else ssl.DER_cert_to_PEM_cert(der)
        context = ssl.create_default_context(cafile=certifi.where())
        context.load_verify_locations(cadata=pem)
        with httpx.Client(verify=context, headers=_HEADERS, follow_redirects=True,
                          timeout=120) as client:
            return client.get(url)
    except (OSError, ValueError, httpx.HTTPError, ssl.SSLError):
        return None


def _system_trust_get(url: str) -> tuple[int, bytes, str] | None:
    """Host whose chain ends at a root the OS trusts but certifi does not yet ship
    (verified 29 Sep: egazette.gov.in -> Let's Encrypt YR2 -> ISRG Root YR). curl
    verifies against the system trust store, as a browser would; never -k."""
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as handle:
        target = Path(handle.name)
    try:
        done = subprocess.run(
            ["curl", "-sSL", "--max-time", "300", "-A", _HEADERS["User-Agent"],
             "-o", str(target), "-w", "%{http_code} %{content_type}", url.split("#")[0]],
            capture_output=True, text=True, timeout=320)
        if done.returncode != 0:
            return None
        code, _, content_type = done.stdout.partition(" ")
        return int(code or 0), target.read_bytes(), content_type
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    finally:
        target.unlink(missing_ok=True)


def _legalinfo_pdf_export(client: httpx.Client, url: str) -> tuple[int, bytes, str]:
    """Mongolia: legalinfo.mn's official "Pdf" export of a law detail page.

    The detail page is server-rendered HTML; its Pdf button POSTs the law's file id
    to /mn/pdfExport, which returns the portal-generated PDF (Cyrillic text layer,
    "N дүгээр зүйл" article headings). Verified 29 Sep 2026."""
    page = client.get(url)
    if page.status_code != 200:
        return page.status_code, b"", url
    import re as _re
    match = _re.search(r"downloadlaw\('1',\s*'(\d+)'\)", page.text)
    file_id = match.group(1) if match else None
    if not file_id:
        return 0, b"", url
    export = "https://legalinfo.mn/mn/pdfExport"
    response = client.post(export, headers={"Referer": url}, data={
        "fileid": file_id, "orientation": "portrait", "size": "a4", "top": "1cm",
        "left": "1.5cm", "bottom": "1cm", "right": "0.5cm", "width": "", "height": "",
        "fontfamily": "Arial, Helvetica, sans-serif", "fDownload": "1"})
    return response.status_code, response.content, f"{export}?fileid={file_id}"


def _html_render(url: str, render_url: str | None) -> tuple[int, bytes, bytes, int] | None:
    """Official consolidated text published only as HTML (Russia: pravo.gov.ru
    ИПС print view). Chromium prints the official page to PDF so the corpus keeps
    one evidence format (text layer + page images for Source Match). The raw HTML
    bytes are archived beside the PDF; the only DOM change is <sup>digits</sup>
    -> Unicode superscript digits (presentation preserved, see _SUP_TO_UNICODE_JS).
    Returns (status, pdf_bytes, html_bytes, superscripts_converted) or None."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    try:
        with sync_playwright() as p:
            browser = _launch_chromium(p)
            page = browser.new_page(user_agent=_HEADERS["User-Agent"])
            response = page.goto(render_url or url, timeout=120_000, wait_until="networkidle")
            status = response.status if response else 0
            html = page.content().encode("utf-8")
            converted = page.evaluate(_SUP_TO_UNICODE_JS)
            pdf = page.pdf(format="A4", print_background=False,
                           margin={"top": "15mm", "bottom": "15mm",
                                   "left": "15mm", "right": "15mm"})
            browser.close()
        return status, pdf, html, int(converted or 0)
    except Exception:  # noqa: BLE001 — a failed render leaves the row dead
        return None


def _suffix(url: str, content_type: str) -> str:
    if ".pdf" in url.lower() or "pdf" in content_type:
        return ".pdf"
    return ".html"


def _browser_fetch(url: str) -> tuple[int, bytes] | None:
    """Real-browser fallback for TLS-fingerprint blocks (e.g. Akamai on dfat.gov.au:
    TCP connects, TLS handshake refused for non-browser clients — verified 19 Jul).
    Chromium's network stack negotiates normally; response.body() returns the raw
    bytes for both HTML and PDF responses. Returns None when Playwright is absent."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    try:
        with sync_playwright() as p:
            browser = _launch_chromium(p)
            page = browser.new_page(user_agent=_HEADERS["User-Agent"])
            response = page.goto(url, timeout=90_000, wait_until="commit")
            status = response.status if response else 0
            body = response.body() if response else b""
            browser.close()
        return status, body
    except Exception:  # noqa: BLE001 — fallback failure just leaves the row dead
        return None


def fetch_seeds(economy: str, only_pillars: tuple[str, ...] | None = None,
                seeds_path: str = "data/seeds.json") -> dict:
    """Download all (or pillar-filtered) seed documents for an economy.

    Returns the manifest dict {url: entry}; also written to
    data/raw/{cc}/seeds_manifest.json after every row (resumable).
    """
    cc = ECON_CC[economy]
    out_dir = Path(f"data/raw/{cc}")
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "seeds_manifest.json"
    manifest: dict = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}

    rows = json.loads(Path(seeds_path).read_text())["economies"][economy]
    if only_pillars:
        rows = [r for r in rows if str(r.get("indicator_code", "")).startswith(only_pillars)]

    # Manifest reconciliation (Sol review, 19 Jul): every builder run re-walks the
    # full seed list — prior successes keep their archived bytes but have their
    # descriptive fields (act, source_type, cluster, ...) refreshed from seeds.json,
    # and rows the manifest has never seen are fetched now. The summary is written
    # beside the manifest so "did the new research reach the corpus?" is checkable.
    recon = {"economy": economy, "seed_rows": len(rows), "already_ok": 0,
             "fetched_now": 0, "dead": 0, "refreshed_metadata": 0}
    progress.emit("fetch", f"{economy}: {len(rows)} source documents"
                           f"{' for ' + ', '.join(only_pillars) if only_pillars else ''}")
    offline = os.getenv("CLAUSECHAIN_OFFLINE") == "1"
    with httpx.Client(headers=_HEADERS, follow_redirects=True,
                      timeout=float(os.getenv("SEEDS_FETCH_TIMEOUT", "90"))) as client:
        for row in rows:
            url = (row.get("url") or "").strip()
            if not url.startswith("http"):
                continue
            meta_fields = {"act": row.get("act"), "indicator_code": row.get("indicator_code"),
                           "policy": row.get("policy"), "coverage": row.get("coverage"),
                           "source_type": row.get("source_type"), "cluster": row.get("cluster"),
                           "expected_citations": row.get("expected_citations"),
                           "expected_phrases": row.get("expected_phrases"),
                           # R2 finals: acquisition strategy, per-seed parse scope
                           # (one instrument inside a multi-instrument gazette issue)
                           # and citation style.
                           "acquire": row.get("acquire"), "render_url": row.get("render_url"),
                           "page_range": row.get("page_range"),
                           "citation_template": row.get("citation_template"),
                           "section_grammars": row.get("section_grammars")}
            prior = manifest.get(url)
            if prior and prior.get("status") == "ok":
                recon["already_ok"] += 1
                progress.emit("fetch", f"already downloaded · {str(row.get('act') or url)[:70]}",
                              detail=json.dumps({"kind": "cached", "url": url,
                                                 "act": row.get("act")}))
                if any(prior.get(k) != v for k, v in meta_fields.items() if v is not None):
                    prior.update({k: v for k, v in meta_fields.items() if v is not None})
                    recon["refreshed_metadata"] += 1
                    manifest_path.write_text(json.dumps(manifest, indent=1))
                continue  # static docs: never refetch a success
            if offline:
                # Offline evaluation is archive-authoritative: preserve the
                # unresolved acquisition honestly, without attempting network or
                # manufacturing a successful source record.
                entry = dict(prior or {}, **{k: v for k, v in meta_fields.items()
                                             if v is not None})
                entry.setdefault("status", "dead")
                entry.setdefault("http_status", 0)
                entry["offline_not_retried"] = True
                manifest[url] = entry
                recon["dead"] += 1
                continue
            time.sleep(POLITE_DELAY_S)
            entry = dict(meta_fields, access_date=date.today().isoformat())
            status_code, content, content_type, final_url, via = 0, b"", "", url, "httpx"
            acquire = str(row.get("acquire") or "").strip().lower()
            if acquire == "legalinfo_pdf_export":
                try:
                    status_code, content, final_url = _legalinfo_pdf_export(client, url)
                    via = "legalinfo-pdf-export"
                except httpx.HTTPError as error:
                    entry.update(error=str(error)[:200])
                if content[:5] != b"%PDF-":
                    status_code, content = 0, b""
            elif acquire == "html_render":
                rendered = _html_render(url, row.get("render_url"))
                if rendered is not None and rendered[1][:5] == b"%PDF-":
                    status_code, content, html_bytes, converted = rendered
                    html_sha = hashlib.sha256(html_bytes).hexdigest()
                    html_path = out_dir / f"seed_{html_sha[:12]}.source.html"
                    html_path.write_bytes(html_bytes)
                    final_url, via = row.get("render_url") or url, "html-render"
                    entry.update(source_html_file=str(html_path), source_html_sha256=html_sha,
                                 render_normalization=(f"sup-digits->unicode-superscript "
                                                       f"({converted} converted)"))
                else:
                    entry.update(error="html render failed (Playwright/Chromium unavailable "
                                       "or page error)")
            else:
                try:
                    response = client.get(url)
                    status_code, content = response.status_code, response.content
                    content_type = response.headers.get("content-type", "")
                    final_url = str(response.url)
                except httpx.HTTPError as error:
                    entry.update(error=str(error)[:200])
                    if "CERTIFICATE_VERIFY_FAILED" in str(error):
                        response = _aia_verified_get(url)
                        if response is not None:
                            status_code, content = response.status_code, response.content
                            content_type = response.headers.get("content-type", "")
                            final_url, via = str(response.url), "httpx+aia-chain"
                        else:
                            fetched = _system_trust_get(url)
                            if fetched is not None:
                                status_code, content, content_type = fetched
                                via = "curl+system-trust"
            if not acquire and not (status_code == 200 and len(content) > 500):
                # Same-origin Referer retry: several gazette hosts (verified:
                # ratchakitcha.soc.go.th 403 -> 200, 31 Jul) gate direct deep links
                # but serve the same bytes when the request looks site-internal.
                from urllib.parse import urlsplit
                parts = urlsplit(url)
                try:
                    response = client.get(url, headers={
                        "Referer": f"{parts.scheme}://{parts.netloc}/",
                        "Accept-Language": "th-TH,th;q=0.9,id;q=0.9,hi;q=0.9,en;q=0.8"})
                    status_code, content = response.status_code, response.content
                    content_type = response.headers.get("content-type", "")
                    final_url, via = str(response.url), "httpx+referer"
                except httpx.HTTPError:
                    pass
            if not acquire and not (status_code == 200 and len(content) > 500):
                browser = _browser_fetch(url)
                if browser is not None:
                    status_code, content = browser
                    content_type, final_url, via = "", url, "playwright"
            if status_code == 200 and len(content) > 500:
                sha = hashlib.sha256(content).hexdigest()
                suffix = ".pdf" if content[:5] == b"%PDF-" else _suffix(url, content_type)
                path = out_dir / f"seed_{sha[:12]}{suffix}"
                path.write_bytes(content)
                entry.pop("error", None)
                entry.update(status="ok", http_status=status_code, sha256=sha,
                             bytes=len(content), file=str(path), final_url=final_url,
                             via=via)
                file_type = "PDF" if suffix == ".pdf" else suffix.lstrip(".").upper() or "HTML"
                # One event per document downloaded now: the live console line and
                # the Run Record's "every document downloaded" list both read it.
                progress.emit("fetch", f"downloaded · {str(row.get('act') or url)[:70]} · "
                                       f"{len(content) / 1024:,.0f} KB {file_type}",
                              detail=json.dumps({
                                  "kind": "download", "url": url, "final_url": final_url,
                                  "act": row.get("act"), "bytes": len(content),
                                  "file_type": file_type, "via": via, "sha256": sha,
                                  "fetched_at": datetime.now(timezone.utc).isoformat()}))
            else:
                entry.update(status="dead", http_status=status_code, bytes=len(content))
                progress.emit("fetch", f"not available · {str(row.get('act') or url)[:70]} · "
                                       f"HTTP {status_code or 'no response'}", level="warn",
                              detail=json.dumps({"kind": "dead", "url": url, "act": row.get("act"),
                                                 "http_status": status_code,
                                                 "error": entry.get("error")}))
            manifest[url] = entry
            recon["fetched_now" if entry.get("status") == "ok" else "dead"] += 1
            manifest_path.write_text(json.dumps(manifest, indent=1))
    recon["generated_at"] = date.today().isoformat()
    (out_dir / "seeds_reconciliation.json").write_text(json.dumps(recon, indent=1))
    progress.emit("fetch", f"{economy}: {recon['fetched_now']} downloaded now, "
                           f"{recon['already_ok']} already downloaded, {recon['dead']} unavailable")
    print(f"[seeds] {economy}: {recon['seed_rows']} rows -> {recon['already_ok']} cached, "
          f"{recon['fetched_now']} fetched now, {recon['dead']} dead, "
          f"{recon['refreshed_metadata']} metadata-refreshed")
    return manifest


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch ESCAP seed documents for an economy.")
    parser.add_argument("--economy", default="Malaysia")
    parser.add_argument("--all-pillars", action="store_true",
                        help="fetch every row (default: P6/P7 only)")
    parser.add_argument("--seeds", default="data/seeds.json",
                        help="seeds file (Round-2 economies: data/seeds_r2.json)")
    args = parser.parse_args()
    result = fetch_seeds(args.economy, None if args.all_pillars else ("P6", "P7"),
                         seeds_path=args.seeds)
    ok = sum(1 for e in result.values() if e.get("status") == "ok")
    dead = sum(1 for e in result.values() if e.get("status") == "dead")
    print(f"{args.economy}: {ok} archived, {dead} DEAD links (audit leads) "
          f"-> data/raw/{ECON_CC[args.economy]}/seeds_manifest.json")
