"""Repair pass for Round-2 seed links the direct fetcher could not reach.

Two honest escalations, recorded in the manifest's ``via`` field:
  1. server-proxy — fetch through the ClauseChain deploy server (different
     network + DNS; fixes local DNS failures and some geo-gated hosts).
  2. wayback — latest Internet Archive snapshot of the OFFICIAL url. The
     manifest keeps the official source_url; ``wayback_url`` records where the
     bytes actually came from, so provenance is never silently rewritten.

Usage: .venv/bin/python scripts/repair_r2_seeds.py [--cc th,in,id]
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

# A server whose network the source site accepts (user@host); unset = no proxy.
PROXY_SSH = os.environ.get("CLAUSECHAIN_PROXY_SSH", "")
SSH = ["ssh", "-i", str(Path.home() / ".ssh/clausechain_deploy"),
       "-p", os.environ.get("CLAUSECHAIN_PROXY_SSH_PORT", "22"),
       "-o", "ConnectTimeout=15", PROXY_SSH]
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")


def server_proxy_fetch(url: str) -> bytes | None:
    """curl on the deploy server, bytes streamed back over ssh stdout."""
    if not PROXY_SSH:
        return None
    cmd = SSH + ["curl", "-sL", "--max-time", "120", "-A", f'"{UA}"',
                 "-H", '"Referer: ' + url.split("/", 3)[0] + "//" + url.split("/", 3)[2] + '/"',
                 f'"{url}"']
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=150)
        return out.stdout if out.returncode == 0 and len(out.stdout) > 500 else None
    except subprocess.TimeoutExpired:
        return None


def wayback_fetch(client: httpx.Client, url: str) -> tuple[bytes, str] | None:
    """Latest archived snapshot of the official URL, if any."""
    try:
        r = client.get("https://archive.org/wayback/available", params={"url": url}, timeout=45)
        snap = (r.json().get("archived_snapshots") or {}).get("closest") or {}
        snap_url = snap.get("url")
        if not (snap.get("available") and snap_url):
            return None
        # id_ variant serves the original bytes without the Wayback toolbar chrome.
        raw_url = snap_url.replace("/http", "id_/http", 1) if "id_/" not in snap_url else snap_url
        r2 = client.get(raw_url, timeout=120)
        if r2.status_code == 200 and len(r2.content) > 500:
            return r2.content, snap_url
    except (httpx.HTTPError, ValueError):
        pass
    return None


def main() -> int:
    ccs = ["th", "in", "id"]
    for arg in sys.argv[1:]:
        if arg.startswith("--cc"):
            ccs = arg.split("=", 1)[1].split(",")
    total_fixed = 0
    with httpx.Client(headers={"User-Agent": UA}, follow_redirects=True) as client:
        for cc in ccs:
            mpath = Path(f"data/raw/{cc}/seeds_manifest.json")
            manifest = json.loads(mpath.read_text())
            dead = [u for u, e in manifest.items() if e.get("status") == "dead"]
            fixed = 0
            for url in dead:
                entry = manifest[url]
                content, via, wb_url = None, None, None
                proxied = server_proxy_fetch(url)
                # Strict acceptance: a .pdf URL must return PDF bytes; an HTML
                # response for a PDF link is a block/error page, not a recovery
                # (the bug that briefly archived ratchakitcha 403 pages as "ok").
                if proxied is not None:
                    looks_pdf = proxied[:5] == b"%PDF-"
                    wants_pdf = ".pdf" in url.lower()
                    if looks_pdf or (not wants_pdf and len(proxied) > 5000
                                     and b"<html" in proxied[:400].lower()):
                        content, via = proxied, "server-proxy"
                if content is None:
                    wb = wayback_fetch(client, url)
                    if wb:
                        content, wb_url = wb
                        via = "wayback"
                if content is None:
                    continue
                sha = hashlib.sha256(content).hexdigest()
                suffix = ".pdf" if content[:5] == b"%PDF-" else ".html"
                path = Path(f"data/raw/{cc}/seed_{sha[:12]}{suffix}")
                path.write_bytes(content)
                entry.pop("error", None)
                entry.update(status="ok", http_status=200, sha256=sha, bytes=len(content),
                             file=str(path), final_url=url, via=via,
                             access_date=date.today().isoformat())
                if wb_url:
                    entry["wayback_url"] = wb_url
                fixed += 1
                mpath.write_text(json.dumps(manifest, indent=1))
                time.sleep(2)
            still = sum(1 for e in manifest.values() if e.get("status") == "dead")
            print(f"[repair] {cc}: {fixed} recovered ({len(dead)} attempted), {still} still dead")
            total_fixed += fixed
    print(f"[repair] total recovered: {total_fixed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
