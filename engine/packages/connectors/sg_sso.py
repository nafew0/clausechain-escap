"""Singapore Statutes Online (sso.agc.gov.sg) connector.

The 1-June workshop flagged SG as having anti-bot protection; handling it is an
explicit scoring differentiator. Strategy: plain httpx first (cheap), Playwright
fallback when blocked (install via the `crawl` dependency group).

KEY ROUTE (discovered 7 Jul from the portal's own legis JS bundle): the statute
pages lazy-load their body via AJAX fragments, BUT the print view returns the
ENTIRE act as one HTML document:
    GET /Act/{ref}?ViewType=Print&PrintType=html&ProvIds=all-.,toc-.
This keeps us on plain httpx (no browser) for whole-act acquisition. Politeness:
we sleep between requests and never fetch an act we already archived today.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx

PDPA_URL = "https://sso.agc.gov.sg/Act/PDPA2012"
BASE = "https://sso.agc.gov.sg"
POLITE_DELAY_S = 8.0                 # CloudFront rate-limits burst traffic — stay slow
BLOCK_BACKOFFS_S = (45.0, 120.0)     # waits before retrying a 403/429 block

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36 ClauseChain-research/0.1"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass
class FetchResult:
    url: str
    final_url: str
    status_code: int
    content: bytes
    via: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()

    @property
    def looks_blocked(self) -> bool:
        if self.status_code in (403, 429, 503):
            return True
        sample = self.content[:4000].lower()
        return self.status_code == 200 and (
            b"captcha" in sample or b"are you a robot" in sample or len(self.content) < 2000
        )

    def raise_or_ok(self) -> None:
        if self.status_code != 200:
            raise RuntimeError(f"Fetch failed: {self.status_code} for {self.url}")


def fetch_httpx(url: str, timeout: float = 30.0) -> FetchResult:
    with httpx.Client(headers=_HEADERS, follow_redirects=True, timeout=timeout) as client:
        response = client.get(url)
    return FetchResult(
        url=url, final_url=str(response.url), status_code=response.status_code,
        content=response.content, via="httpx",
    )


def fetch_playwright(url: str, timeout_ms: int = 45000) -> FetchResult:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:  # pragma: no cover
        raise RuntimeError(
            "Playwright not installed. Run: uv sync --group crawl && uv run playwright install chromium"
        ) from error
    with sync_playwright() as p:  # pragma: no cover — needs browser install
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=_HEADERS["User-Agent"])
        page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        html = page.content()
        final_url = page.url
        browser.close()
    return FetchResult(url=url, final_url=final_url, status_code=200,
                       content=html.encode("utf-8"), via="playwright")


def save_raw(result: FetchResult, out_dir: str | Path = "data/raw/sg") -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    name = result.url.rstrip("/").rsplit("/", 1)[-1] or "index"
    path = out / f"{name}.{result.sha256[:12]}.html"
    path.write_bytes(result.content)
    return path


_SESSION: httpx.Client | None = None


def _session() -> httpx.Client:
    """One shared client (cookie jar persists across fetches — looks like a browser session)."""
    global _SESSION
    if _SESSION is None:
        _SESSION = httpx.Client(headers=_HEADERS, follow_redirects=True, timeout=180.0)
    return _SESSION


def fetch_act_full(act_ref: str, timeout: float = 180.0, kind: str = "Act") -> FetchResult:
    """Fetch the WHOLE instrument as one HTML document via the portal's print view,
    with backoff-retry when the CloudFront anti-bot blocks us (403/429).

    `act_ref` is the SSO path segment, e.g. "PDPA2012", "CA2018". `kind` selects
    the portal collection: "Act" (default) or "SL" (subsidiary legislation —
    same print-view markup, verified 19 Jul on PDPA2012-S63-2021).
    """
    if kind not in ("Act", "SL"):
        raise ValueError(f"Unsupported SSO collection {kind!r} (Act|SL)")
    url = f"{BASE}/{kind}/{act_ref}"
    params = {"ViewType": "Print", "PrintType": "html", "ProvIds": "all-.,toc-."}
    attempts = 1 + len(BLOCK_BACKOFFS_S)
    result: FetchResult | None = None
    for attempt in range(attempts):
        response = _session().get(url, params=params)
        result = FetchResult(
            url=url, final_url=str(response.url), status_code=response.status_code,
            content=response.content, via="httpx-printview",
        )
        if not result.looks_blocked:
            return result
        if attempt < len(BLOCK_BACKOFFS_S):
            wait = BLOCK_BACKOFFS_S[attempt]
            print(f"  [sg_sso] blocked ({result.status_code}) on {act_ref}; "
                  f"backing off {wait:.0f}s (attempt {attempt + 1}/{attempts})")
            time.sleep(wait)

    # httpx exhausted -> real-browser fallback (defeats CloudFront fingerprinting;
    # the anti-bot workaround is an explicitly scored differentiator, 1-Jun Q&A).
    print(f"  [sg_sso] httpx blocked persistently on {act_ref}; trying Playwright fallback")
    try:
        print_url = f"{url}?ViewType=Print&PrintType=html&ProvIds=all-.%2Ctoc-."
        pw = fetch_playwright(print_url, timeout_ms=120_000)
        if not pw.looks_blocked and len(pw.content) > 20_000:
            return FetchResult(url=url, final_url=pw.final_url, status_code=200,
                               content=pw.content, via="playwright-printview")
    except RuntimeError as error:
        print(f"  [sg_sso] Playwright unavailable: {error}")
    return result  # still blocked; caller raises


def acquire_act(act_ref: str, out_dir: str | Path = "data/raw/sg", kind: str = "Act") -> dict:
    """Fetch + archive an act with provenance; cache-aware (one fetch per day per act).

    Returns the manifest dict: {act_ref, url, final_url, sha256, access_date,
    bytes, via, html_path}. The archived copy + access date satisfy the
    link-preservation rule (DoDont §8) by construction.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / f"{act_ref}.manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("access_date") == date.today().isoformat() and Path(manifest["html_path"]).is_file():
            return manifest  # already archived today — don't hammer the portal

    time.sleep(POLITE_DELAY_S)
    result = fetch_act_full(act_ref, kind=kind)
    if result.looks_blocked:
        raise RuntimeError(
            f"sso.agc.gov.sg blocked the fetch for {act_ref} "
            f"(status {result.status_code}) — retry later or use the Playwright fallback."
        )
    result.raise_or_ok()
    html_path = out / f"{act_ref}.full.{result.sha256[:12]}.html"
    html_path.write_bytes(result.content)
    manifest = {
        "act_ref": act_ref,
        "url": result.url,
        "final_url": result.final_url,
        "sha256": result.sha256,
        "access_date": date.today().isoformat(),
        "bytes": len(result.content),
        "via": result.via,
        "html_path": str(html_path),
    }
    manifest_path.write_text(json.dumps(manifest, indent=1))
    return manifest
