"""DEPRECATED: finalization moved to immutable named approval replay.

The user records decisions in data/review/decisions.csv with columns:
  economy,indicator,law_contains,article,decision[,note]
(decision = approved | rejected; law_contains matches a substring of Law Name.)

This script stamps reviewer_decision on matching rows across the given run dirs
and rebuilds submission/consolidated_final.csv containing ONLY approved rows
(auto-clearable rows count as approved when --auto-approve-clear is passed and
the user has signed off on that policy).

Usage:
  .venv/bin/python scripts/approve_rows.py --auto-approve-clear outputs/final_* 
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def load_decisions() -> list[dict]:
    path = Path("data/review/decisions.csv")
    if not path.is_file():
        return []
    return list(csv.DictReader(path.open(encoding="utf-8")))


def decide(row: dict, decisions: list[dict], auto_clear: bool) -> str:
    for d in decisions:
        if (d.get("economy", "") in ("", row["Economy"])
                and d.get("indicator", "") in ("", row["Indicator ID"])
                and d.get("law_contains", "").lower() in row["Law Name"].lower()
                and d.get("article", "") in ("", row["Article / Section"])):
            return d.get("decision", "pending").strip().lower()
    is_clear = (row.get("Discovery Tag") == "KNOWN"
                and row.get("Status", "") == "in_force"
                and "PENDING_REVIEW" not in row.get("Verbatim Snippet", ""))
    return "approved" if (auto_clear and is_clear) else "pending"


def main() -> int:
    print("approve_rows.py is disabled: use scripts/submission_replay.py with "
          "data/review/decisions.json containing named, timestamped approvals.")
    return 2
    # Historical implementation retained below only for migration reference.
    auto_clear = "--auto-approve-clear" in sys.argv
    run_dirs = [Path(a) for a in sys.argv[1:] if not a.startswith("--")]
    decisions = load_decisions()
    out = Path("submission")
    out.mkdir(exist_ok=True)

    approved, pending, rejected, header, seen = [], 0, 0, None, set()
    for run in run_dirs:
        for row in csv.DictReader((run / "output.csv").open(encoding="utf-8")):
            key = (row["Economy"], row["Indicator ID"], row["Law Name"], row["Article / Section"])
            if key in seen:
                continue
            seen.add(key)
            header = header or list(row.keys())
            verdict = decide(row, decisions, auto_clear)
            if verdict == "approved":
                approved.append(row)
            elif verdict == "rejected":
                rejected += 1
            else:
                pending += 1
    order = {"Singapore": 0, "Malaysia": 1, "Australia": 2}
    approved.sort(key=lambda r: (order.get(r["Economy"], 9), r["Indicator ID"]))
    with (out / "consolidated_final.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=header)
        w.writeheader()
        w.writerows(approved)
    print(f"consolidated_final.csv: {len(approved)} approved | {pending} pending | {rejected} rejected")
    if pending:
        print("Pending rows are EXCLUDED from the submitted file (L4).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
