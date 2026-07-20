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
from datetime import date
from pathlib import Path

import httpx
import os

_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/125.0 Safari/537.36 ClauseChain-research/0.1"),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
}
POLITE_DELAY_S = 3.0
ECON_CC = {"Singapore": "sg", "Malaysia": "my", "Australia": "au"}


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
            browser = p.chromium.launch(headless=True)
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
    offline = os.getenv("CLAUSECHAIN_OFFLINE") == "1"
    with httpx.Client(headers=_HEADERS, follow_redirects=True, timeout=90) as client:
        for row in rows:
            url = (row.get("url") or "").strip()
            if not url.startswith("http"):
                continue
            meta_fields = {"act": row.get("act"), "indicator_code": row.get("indicator_code"),
                           "policy": row.get("policy"), "coverage": row.get("coverage"),
                           "source_type": row.get("source_type"), "cluster": row.get("cluster"),
                           "expected_citations": row.get("expected_citations"),
                           "expected_phrases": row.get("expected_phrases")}
            prior = manifest.get(url)
            if prior and prior.get("status") == "ok":
                recon["already_ok"] += 1
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
            try:
                response = client.get(url)
                status_code, content = response.status_code, response.content
                content_type = response.headers.get("content-type", "")
                final_url = str(response.url)
            except httpx.HTTPError as error:
                entry.update(error=str(error)[:200])
            if not (status_code == 200 and len(content) > 500):
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
            else:
                entry.update(status="dead", http_status=status_code, bytes=len(content))
            manifest[url] = entry
            recon["fetched_now" if entry.get("status") == "ok" else "dead"] += 1
            manifest_path.write_text(json.dumps(manifest, indent=1))
    recon["generated_at"] = date.today().isoformat()
    (out_dir / "seeds_reconciliation.json").write_text(json.dumps(recon, indent=1))
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
    args = parser.parse_args()
    result = fetch_seeds(args.economy, None if args.all_pillars else ("P6", "P7"))
    ok = sum(1 for e in result.values() if e.get("status") == "ok")
    dead = sum(1 for e in result.values() if e.get("status") == "dead")
    print(f"{args.economy}: {ok} archived, {dead} DEAD links (audit leads) "
          f"-> data/raw/{ECON_CC[args.economy]}/seeds_manifest.json")
