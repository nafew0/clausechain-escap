"""Build the deterministic expected-anchor ledger from verified research tables."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.ingest.expected_anchors import parse_research_reports  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docs", default="docs")
    parser.add_argument("--out", default="configs/expected_anchors.json")
    args = parser.parse_args()
    docs = Path(args.docs)
    paths = sorted(docs.glob("*deep-research-report*.md"))
    anchors = parse_research_reports(paths)
    sources = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths
    }
    payload = {
        "contract": "clausechain-expected-anchors-v1",
        "source_fingerprint": hashlib.sha256(
            json.dumps(sources, sort_keys=True).encode()
        ).hexdigest(),
        "source_reports": sources,
        "anchors": anchors,
    }
    Path(args.out).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"expected-anchor ledger: {len(anchors)} anchors -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
