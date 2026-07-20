"""AI-1 P0 spike: fetch one SG PDPA page from sso.agc.gov.sg, save raw bytes + SHA-256.

Usage (from engine/):
    uv run python scripts/spike_sg_fetch.py
    uv run python scripts/spike_sg_fetch.py --playwright   # if httpx is blocked (anti-bot)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.connectors.sg_sso import PDPA_URL, fetch_httpx, fetch_playwright, save_raw  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=PDPA_URL)
    parser.add_argument("--playwright", action="store_true", help="Use Playwright instead of httpx.")
    args = parser.parse_args()

    try:
        result = fetch_playwright(args.url) if args.playwright else fetch_httpx(args.url)
    except Exception as error:  # noqa: BLE001
        print(f"FAIL fetch ({'playwright' if args.playwright else 'httpx'}): {error!r}", file=sys.stderr)
        if not args.playwright:
            print("Next: uv sync --group crawl && uv run playwright install chromium && "
                  "uv run python scripts/spike_sg_fetch.py --playwright", file=sys.stderr)
        return 1

    print(f"via={result.via} status={result.status_code} bytes={len(result.content)} "
          f"final_url={result.final_url}")
    if result.looks_blocked:
        print("BLOCKED: anti-bot suspected (expected per the 1-Jun workshop — SG portal has protection).")
        if not args.playwright:
            print("Next: uv sync --group crawl && uv run playwright install chromium && "
                  "uv run python scripts/spike_sg_fetch.py --playwright")
        return 2

    path = save_raw(result)
    print(f"PASS: saved {path} sha256={result.sha256}")
    title_probe = result.content[:2000].decode("utf-8", errors="ignore")
    if "Personal Data Protection" in title_probe:
        print("PASS: page content mentions 'Personal Data Protection' — right document.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
