"""Write the final-round export (ESCAP's OUTPUT_TEMPLATE_FINAL_ROUND) from the
workspace's current results.

The backend's Export button pipes the active snapshot's rows, their current review
state and the indicator matrix on stdin:

    {"mode": "hybrid", "source": {...}, "excluded": {"rejected": n, "absence": n},
     "rows": [{"finding": <consolidated row>, "review": {...}}], "scores": [<matrix cell>]}

It writes OUTPUT_FINAL_ROUND.<type> into --out and prints the manifest as JSON. It
reads nothing else and writes no decisions or graph data.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.core.schemas import MappedFinding  # noqa: E402
from packages.export.final_round import FORMATS, export_final_round  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--type", choices=(*FORMATS, "all"), default="all")
    args = parser.parse_args()
    payload = json.load(sys.stdin)
    entries = [(MappedFinding.model_validate(item["finding"]), item.get("review") or {})
               for item in payload.get("rows") or []]
    manifest = export_final_round(
        entries, Path(args.out), mode=payload.get("mode") or "hybrid",
        score_cells=payload.get("scores") or [], source=payload.get("source"),
        excluded=payload.get("excluded"), formats=FORMATS if args.type == "all" else (args.type,))
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
