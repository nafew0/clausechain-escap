"""Quarantine one derived instrument while retaining its source and reason record."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.graph.sqlite_graph import SqliteGraphStore  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--economy", required=True)
    parser.add_argument("--law", required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    removed = SqliteGraphStore().purge_instrument_provisions(
        args.economy, args.law, args.reason)
    print(f"quarantined {removed} provisions: {args.economy} / {args.law} / {args.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
