"""Derive the official-domain whitelist from ESCAP's OWN citations.

Reads every References URL in the Round-1 KNOWN index + inventory seeds (and the
Round-2 index if present) and emits data/official_domains.json: per-economy domain
frequencies, split into government (whitelist candidates) vs non-government
(upgrade targets — rows where ESCAP itself lacked an official link).

This makes our L1 whitelist provably at least as broad as ESCAP's own practice.

Usage (from engine/):  uv run python scripts/mine_official_domains.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

GOV_HINTS = (".gov.", ".gob.", ".go.", ".gouv.", ".mil.")
GOV_SUFFIXES = (".gov", ".gov.au", ".gov.sg", ".gov.my", ".int")
KNOWN_OFFICIAL = {  # official bodies without a .gov domain
    "ssm.com.my",            # Companies Commission of Malaysia (statutory body)
    "standards.org.au",      # Standards Australia
    "legislation.gov.au", "sso.agc.gov.sg", "lom.agc.gov.my",
}


def domain_of(url: str) -> str | None:
    url = url.strip()
    if not url.startswith("http"):
        return None
    netloc = urlparse(url).netloc.lower().removeprefix("www.")
    return netloc or None


def is_government(domain: str) -> bool:
    return (
        domain in KNOWN_OFFICIAL
        or domain.endswith(GOV_SUFFIXES)
        or any(hint in domain for hint in GOV_HINTS)
    )


def main() -> int:
    data_dir = Path("data")
    per_economy: dict[str, Counter] = defaultdict(Counter)

    def eat(economy: str, text: str) -> None:
        for url in re.findall(r"https?://\S+", text or ""):
            if d := domain_of(url):
                per_economy[economy][d] += 1

    for index_file in ("known_index.json", "known_index_round2.json"):
        path = data_dir / index_file
        if not path.exists():
            continue
        index = json.loads(path.read_text(encoding="utf-8"))
        for economy, entries in index["economies"].items():
            for entry in entries:
                for ref in entry.get("references", []):
                    eat(economy, ref)

    seeds_path = data_dir / "seeds.json"
    if seeds_path.exists():
        seeds = json.loads(seeds_path.read_text(encoding="utf-8"))
        for economy, rows in seeds["economies"].items():
            for row in rows:
                eat(economy, row.get("url", ""))

    result: dict[str, dict] = {}
    for economy, counts in sorted(per_economy.items()):
        gov = {d: n for d, n in counts.most_common() if is_government(d)}
        other = {d: n for d, n in counts.most_common() if not is_government(d)}
        result[economy] = {"official_whitelist": gov, "upgrade_targets_nonofficial": other}

    out = data_dir / "official_domains.json"
    out.write_text(
        json.dumps({"source": "mined from ESCAP References (R1 master + inventory + R2 DB)",
                    "economies": result}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"-> {out}")
    for economy, buckets in result.items():
        print(f"  {economy}: {len(buckets['official_whitelist'])} official domains, "
              f"{len(buckets['upgrade_targets_nonofficial'])} non-official (upgrade targets)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
