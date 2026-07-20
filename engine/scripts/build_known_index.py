"""Build data/known_index.json (KNOWN baseline) + data/seeds.json (crawler seeds).

Primary baseline = master dataset xlsx (articles parsed from the Impact column).
Secondary       = portals CSV (P6/P7 indicator names) + Legal Inventory CSV (seeds).

Usage (from engine/):
    uv run python scripts/build_known_index.py
    uv run python scripts/build_known_index.py --knowledge-root "/path/to/Hackthon_Knowledge"
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.ingest.known_index import (  # noqa: E402
    build_index,
    parse_known_csv,
    parse_master,
    parse_round2,
)

DEFAULT_KNOWLEDGE = Path(__file__).resolve().parents[2] / "Hackthon_Knowledge"

MASTER = "Sample Kit/ESCAP-RDTII-2.1_ Round 1 Database.xlsx"
PORTALS = "Resource Library/Sample governemnt portals_Pillar 6_7.csv"
INVENTORY = "Mail Content 10 June/Singapore, Malaysia, Australia, Legal Inventory.csv"
ROUND2 = "ESCAP-RDTII-2.1_ Round 2 Database.xlsx"   # finals gold (CN/IN/ID/LA/MN/RU/TH)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--knowledge-root", default=str(DEFAULT_KNOWLEDGE))
    parser.add_argument("--out-dir", default="data")
    args = parser.parse_args()

    root = Path(args.knowledge_root)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    master_path = root / MASTER
    portals_path = root / PORTALS
    inventory_path = root / INVENTORY
    for path in (master_path, portals_path, inventory_path):
        if not path.exists():
            print(f"ERROR: missing input file: {path}", file=sys.stderr)
            return 1

    master = parse_master(master_path)
    portals = parse_known_csv(portals_path, source="portals_csv")
    inventory = parse_known_csv(inventory_path, source="legal_inventory")

    index = build_index(master, portals)
    index_path = out_dir / "known_index.json"
    index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")

    seeds: dict[str, list[dict]] = {}
    for entry in inventory:
        seeds.setdefault(entry["economy"], []).append({
            "act": entry["act"],
            "url": entry["references"][0] if entry["references"] else "",
            "coverage": entry["coverage"],
            "policy": entry["indicator_raw"],
            "indicator_code": entry["indicator_code"],
            "cluster": entry.get("cluster", ""),
        })
    seeds_path = out_dir / "seeds.json"
    seeds_path.write_text(
        json.dumps({"source": "Legal Inventory CSV (10 Jun) — secondary; seeds only",
                    "economies": seeds}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # ---- report ----
    print(f"KNOWN index -> {index_path}")
    print(f"  master rows: {len(master)} "
          f"(with parsed articles: {index['counts']['master_rows_with_articles']})")
    print(f"  portal rows: {len(portals)}")
    by_economy = Counter(e["economy"] for e in master)
    print(f"  master rows by economy: {dict(by_economy)}")
    p67 = [e for e in master if (e["indicator_code"] or "").startswith(("P6-", "P7-"))]
    print(f"  master P6/P7 rows: {len(p67)}")
    article_total = sum(len(e["articles"]) for e in master)
    print(f"  total article refs parsed from Impact prose: {article_total}")
    print(f"Seeds -> {seeds_path}")
    for economy, rows in seeds.items():
        print(f"  {economy}: {len(rows)} seed acts")

    # ---- Round-2 finals gold (CN/IN/ID/LA/MN/RU/TH) — finals KNOWN/eval baseline ----
    round2_path = root / ROUND2
    if round2_path.exists():
        r2 = parse_round2(round2_path)
        r2_index = build_index(r2, [])
        r2_path = out_dir / "known_index_round2.json"
        r2_path.write_text(json.dumps(r2_index, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nROUND-2 KNOWN index -> {r2_path}")
        print(f"  rows: {len(r2)} | by economy: {dict(Counter(e['economy'] for e in r2))}")
        r2_p67 = [e for e in r2 if (e["indicator_code"] or "").startswith(("P6-", "P7-"))]
        print(f"  P6/P7 rows: {len(r2_p67)} | article refs parsed: {sum(len(e['articles']) for e in r2)}")
    else:
        print(f"\n(Round-2 DB not found at {round2_path} — skipped)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
