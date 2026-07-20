"""Merge per-run outputs into the ONE consolidated submission artifact (15-Jun rule).

Usage:
  .venv/bin/python scripts/consolidate_submission.py outputs/p1_sg_p6_v4 outputs/p1_sg_p7_v2 \
      outputs/p2_my_p6_v3 outputs/p2_au_p6 [more run dirs...]

Writes candidate-only submission/consolidated.csv + JSON. Final artifacts are
created exclusively by scripts/submission_replay.py from named approvals.
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import date
from pathlib import Path


def read(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return list(csv.DictReader(path.open(encoding="utf-8")))


def main() -> int:
    run_dirs = [Path(a) for a in sys.argv[1:]]
    if not run_dirs:
        print(__doc__)
        return 1
    out = Path("submission")
    out.mkdir(exist_ok=True)

    for stale in (out / "consolidated_final.csv", out / "consolidated_final.json"):
        if stale.exists():
            stale.unlink()
    all_rows, seen = [], set()
    header = None
    for run in run_dirs:
        rows = read(run / "output.csv")
        for r in rows:
            key = (r["Economy"], r["Indicator ID"], r["Law Name"], r["Article / Section"])
            if key in seen:
                continue
            seen.add(key)
            header = header or list(r.keys())
            all_rows.append(r)

    order = {"Singapore": 0, "Malaysia": 1, "Australia": 2}
    for rows_out, name in ((all_rows, "consolidated.csv"),):
        rows_out.sort(key=lambda r: (order.get(r["Economy"], 9), r["Indicator ID"]))
        with (out / name).open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=header)
            w.writeheader()
            w.writerows(rows_out)
    # E4 (P3.5): the JSON artifact carries the COMPLETE per-row audit record from
    # each run's output.json (provenance, gates, status evidence, reviewer fields) —
    # never the CSV projection, which would silently drop JSON-only fields.
    json_rows, json_seen = [], set()
    for run in run_dirs:
        env_path = run / "output.json"
        if not env_path.is_file():
            continue
        env = json.loads(env_path.read_text())
        for f in env.get("findings", []):
            key = (f.get("Economy", f.get("economy")), f.get("Indicator ID", f.get("indicator_id")),
                   f.get("Law Name", f.get("law_name")), f.get("Article / Section", f.get("article_section")))
            if key in json_seen:
                continue
            json_seen.add(key)
            json_rows.append(f)
    (out / "consolidated.json").write_text(json.dumps(
        {"generated": date.today().isoformat(), "runs": [str(r) for r in run_dirs],
         "rows": json_rows}, indent=1))
    print(f"submission/consolidated.csv: {len(all_rows)} candidate rows from {len(run_dirs)} runs; "
          "no final file is produced without named approval replay")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
