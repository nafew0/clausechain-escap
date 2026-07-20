"""⭐ Malaysia master-data error audit (the double-weight Round-1 task).

The 1-Jun deck: MY weight 20 = "error-checking AND new data collection" — the
sample data contains PLANTED ERRORS to detect and correct. This script audits
EVERY Malaysia master row for the named failure classes:

  A. dead/broken References URL              (fetch -> HTTP status)
  B. non-official source domain              (vs the official whitelist)
  C. cited article absent from the act text  (vs our parsed corpus)
  D. a Bill/draft cited as a measure         (never recordable)
  E. malformed Timeframe                     (format-requirements PDF)

Output: data/audit/my_master_audit.csv (one row per finding) + a summary.
Findings are AI-detected; Legal (the user) confirms before anything ships.

Usage: .venv/bin/python scripts/my_error_audit.py [--no-fetch]
"""
from __future__ import annotations

import csv
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.core.envfile import load_env_file  # noqa: E402

load_env_file()

import httpx  # noqa: E402

from packages.discovery.diff import laws_match, section_base  # noqa: E402
from packages.graph.sqlite_graph import SqliteGraphStore  # noqa: E402

HEADERS = {"User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/125.0 Safari/537.36 ClauseChain-research/0.1")}
TIMEFRAME_OK = re.compile(r"(since\s+\w+\s*\d{4}|last\s+(amended|reviewed))", re.I)


def official_domains() -> set[str]:
    domains = {"lom.agc.gov.my", "pdp.gov.my", "www.pdp.gov.my", "federalgazette.agc.gov.my"}
    mined = Path("data/official_domains.json")
    if mined.is_file():
        data = json.loads(mined.read_text())
        domains |= set(data.get("economies", {}).get("Malaysia", {}).get("official_whitelist", {}))
    return {d.lower().removeprefix("www.") for d in domains}


def corpus_sections_by_law(store) -> list[tuple[str, set[str]]]:
    """[(law_name, {base sections in our parsed text})] for loaded MY acts."""
    rows = store._connect().execute(
        "SELECT props FROM nodes WHERE label='Provision'").fetchall()
    by_law: dict[str, set[str]] = {}
    for (props,) in rows:
        p = json.loads(props)
        if p.get("economy") != "Malaysia":
            continue
        base = section_base(p.get("article_section", ""))
        if base:
            by_law.setdefault(p.get("law_name", ""), set()).add(base)
    return list(by_law.items())


def main() -> int:
    do_fetch = "--no-fetch" not in sys.argv
    master = json.loads(Path("data/known_index.json").read_text())["economies"]["Malaysia"]
    whitelist = official_domains()
    corpus = corpus_sections_by_law(SqliteGraphStore())
    findings: list[dict] = []

    def add(row, check, verdict, evidence, correction):
        findings.append({
            "pillar": row.get("pillar"), "indicator": row.get("indicator_raw"),
            "act": (row.get("act") or "").replace("\n", " ")[:90],
            "check": check, "verdict": verdict, "evidence": evidence[:180],
            "suggested_correction": correction[:180],
        })

    checked_urls: dict[str, str] = {}
    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=30) as client:
        for row in master:
            # D. Bill cited as a measure
            if re.search(r"\bbill\b", row.get("act", ""), re.I):
                add(row, "D-bill-as-measure", "ERROR",
                    "Acts column cites a Bill — drafts/bills are never recordable measures",
                    "Cite the enacted Act (e.g. PDP (Amendment) Act A1727 2024) or remove")
            # E. timeframe format
            tf = (row.get("timeframe") or "").strip()
            if tf and not TIMEFRAME_OK.search(tf):
                add(row, "E-timeframe-format", "WARN", f"timeframe={tf!r}",
                    "Use 'Since [Month Year]; last amended [Month Year]' per format rules")
            # A/B. references
            for ref in row.get("references", []):
                for url in re.findall(r"https?://\S+", ref):
                    url = url.rstrip(";,)")
                    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
                    if host and not any(host == d or host.endswith("." + d) for d in whitelist):
                        add(row, "B-non-official-source", "ERROR",
                            f"References cite {host} (not an official portal)",
                            f"Cite lom.agc.gov.my / the issuing regulator; keep {host} only as archive")
                    if do_fetch and url not in checked_urls:
                        time.sleep(1.0)
                        try:
                            status = str(client.get(url).status_code)
                        except httpx.HTTPError as error:
                            status = f"unreachable ({type(error).__name__})"
                        checked_urls[url] = status
                    if do_fetch:
                        status = checked_urls.get(url, "")
                        if status and status not in ("200",):
                            add(row, "A-dead-link", "ERROR", f"{url[:90]} -> {status}",
                                "Replace with a live official link (format rules: broken links must be replaced)")
            # C. cited article exists in our parsed act text (when loaded)
            for law_name, sections in corpus:
                if any(laws_match(a, law_name) for a in row.get("acts_norm", [])):
                    for ref in row.get("articles", []):
                        base = section_base(ref)
                        if base and base.upper() not in {s.upper() for s in sections}:
                            add(row, "C-article-not-found", "WARN",
                                f"{ref} not found in parsed text of {law_name[:50]} "
                                f"(have {len(sections)} sections)",
                                "Verify the article number against the current official text")
                    break

    out = Path("data/audit"); out.mkdir(parents=True, exist_ok=True)
    path = out / "my_master_audit.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(findings[0].keys()) if findings else
                                ["pillar", "indicator", "act", "check", "verdict", "evidence", "suggested_correction"])
        writer.writeheader()
        writer.writerows(findings)

    import collections
    summary = collections.Counter(f["check"] for f in findings)
    print(f"MY master audit: {len(findings)} findings -> {path}")
    for check, count in summary.most_common():
        print(f"  {check:24s} {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
